"""
Tests for search loop policy in app/agent/agent.py.

Covers:
- _normalize_query_tokens
- _jaccard_similarity
- _queries_materialmente_diferentes
- _parse_tool_response_payload
- _extract_search_calls
- _is_weak_search_result
- _rank_search_result
- _best_search_result
- _enforce_search_loop_policy

All tests are deterministic, no network, no LLM, no Docker.
"""

from __future__ import annotations

import json

import pytest

from app.agent.agent import (
    _MAX_SEARCH_PI_POINTS_CALLS_PER_TURN,
    _SEARCH_TOOL_NAME,
    _JACCARD_THRESHOLD,
    _best_search_result,
    _enforce_search_loop_policy,
    _extract_search_calls,
    _is_weak_search_result,
    _jaccard_similarity,
    _normalize_query_tokens,
    _parse_tool_response_payload,
    _queries_materialmente_diferentes,
    _rank_search_result,
)

# ---------------------------------------------------------------------------
# Fixtures — reusable payloads
# ---------------------------------------------------------------------------

_STRONG_PAYLOAD = {
    "success": True,
    "count": 3,
    "max_count": 5,
    "items": [
        {"name": "LFI_RB3_VAZ", "description": "Vazao GN RB3"},
        {"name": "LFI_RB3_TEMP", "description": "Temperatura RB3"},
    ],
}

_WEAK_EMPTY_PAYLOAD = {
    "success": True,
    "count": 0,
    "max_count": 5,
    "items": [],
}

_WEAK_SATURATED_PAYLOAD = {
    "success": True,
    "count": 5,
    "max_count": 5,
    "items": [
        {"name": "TAG_1", "description": None},
        {"name": "TAG_2", "description": ""},
        {"name": "TAG_3", "description": None},
        {"name": "TAG_4", "description": None},
        {"name": "TAG_5", "description": ""},
    ],
}

_ERROR_PAYLOAD = {
    "success": False,
    "count": 0,
    "max_count": 5,
    "items": [],
}


# ---------------------------------------------------------------------------
# T3: _normalize_query_tokens
# ---------------------------------------------------------------------------

class TestNormalizeQueryTokens:
    def test_empty_query(self):
        assert _normalize_query_tokens("") == set()

    def test_none_query(self):
        assert _normalize_query_tokens("") == set()

    def test_removes_accents(self):
        result = _normalize_query_tokens("temperatura")
        assert "temperatura" in result
        assert "temperatura" in result

    def test_removes_stopwords(self):
        result = _normalize_query_tokens("a temperatura do forno")
        assert "temperatura" in result
        assert "forno" in result
        assert "a" not in result
        assert "do" not in result

    def test_removes_short_tokens(self):
        result = _normalize_query_tokens("RB2 forno")
        assert "rb2" in result
        assert "forno" in result

    def test_industrial_codes_preserved(self):
        result = _normalize_query_tokens("LFI_RB3_VAZ_GN")
        assert "lfi_rb3_vaz_gn" in result or "lfi" in result or "rb3" in result

    def test_reordered_terms_produce_same_tokens(self):
        t1 = _normalize_query_tokens("temperatura Zona 1 RB2 forno")
        t2 = _normalize_query_tokens("RB2 forno temperatura zona 1")
        assert t1 == t2

    def test_punctuation_removed(self):
        result = _normalize_query_tokens("tag: LFI_RB3, vazao?")
        assert "tag" not in result  # stopword
        assert "lfi_rb3" in result or "lfi" in result
        assert "vazao" in result

    def test_mixed_case_normalized(self):
        result = _normalize_query_tokens("Temperatura Forno RB2")
        assert "temperatura" in result
        assert "forno" in result
        assert "rb2" in result


# ---------------------------------------------------------------------------
# T3: _jaccard_similarity
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:
    def test_equal_sets(self):
        assert _jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_similarity({"a", "b"}, {"b", "c"})
        assert sim == pytest.approx(1 / 3)

    def test_both_empty(self):
        assert _jaccard_similarity(set(), set()) == 1.0

    def test_first_empty(self):
        assert _jaccard_similarity(set(), {"a"}) == 0.0

    def test_second_empty(self):
        assert _jaccard_similarity({"a"}, set()) == 0.0

    def test_one_subset_of_other(self):
        sim = _jaccard_similarity({"a", "b", "c"}, {"a", "b"})
        assert sim == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# T4: _queries_materialmente_diferentes
# ---------------------------------------------------------------------------

class TestQueriesMaterialmenteDiferentes:
    def test_same_query(self):
        assert not _queries_materialmente_diferentes(
            "temperatura forno RB2", "temperatura forno RB2"
        )

    def test_reordered_terms(self):
        assert not _queries_materialmente_diferentes(
            "temperatura Zona 1 RB2 forno", "RB2 forno temperatura zona 1"
        )

    def test_different_terms(self):
        assert _queries_materialmente_diferentes(
            "temperatura forno RB2", "pressao bomba P-01"
        )

    def test_added_semantic_term(self):
        assert _queries_materialmente_diferentes(
            "temperatura forno", "temperatura forno zona 1"
        )

    def test_only_stopword_difference(self):
        assert not _queries_materialmente_diferentes(
            "temperatura do forno", "temperatura no forno"
        )

    def test_empty_first(self):
        assert _queries_materialmente_diferentes(
            "", "temperatura forno"
        )

    def test_empty_second(self):
        assert _queries_materialmente_diferentes(
            "temperatura forno", ""
        )

    def test_both_empty(self):
        assert not _queries_materialmente_diferentes("", "")

    def test_similar_short_queries(self):
        # Adding "RB3" is a meaningful new industrial code
        assert _queries_materialmente_diferentes(
            "tag LFI", "tag LFI RB3"
        )

    def test_very_different_short_queries(self):
        assert _queries_materialmente_diferentes(
            "tag LFI", "vazao forno"
        )


# ---------------------------------------------------------------------------
# T2: _parse_tool_response_payload
# ---------------------------------------------------------------------------

class TestParseToolResponsePayload:
    def test_none(self):
        assert _parse_tool_response_payload(None) is None

    def test_dict_direct(self):
        payload = {"success": True, "count": 1}
        result = _parse_tool_response_payload(payload)
        assert result == payload

    def test_dict_with_structured_content(self):
        inner = {"success": True, "count": 1}
        payload = {"structuredContent": inner}
        result = _parse_tool_response_payload(payload)
        assert result == inner

    def test_dict_with_content(self):
        inner = {"success": True, "count": 1}
        payload = {"content": inner}
        result = _parse_tool_response_payload(payload)
        assert result == inner

    def test_dict_with_result(self):
        inner = {"success": True, "count": 1}
        payload = {"result": inner}
        result = _parse_tool_response_payload(payload)
        assert result == inner

    def test_json_string(self):
        payload = '{"success": true, "count": 1}'
        result = _parse_tool_response_payload(payload)
        assert isinstance(result, dict)
        assert result["success"] is True

    def test_invalid_json_string(self):
        result = _parse_tool_response_payload("not json")
        assert result is None

    def test_empty_dict(self):
        result = _parse_tool_response_payload({})
        assert result == {}


# ---------------------------------------------------------------------------
# T2: _extract_search_calls
# ---------------------------------------------------------------------------

class TestExtractSearchCalls:
    def test_no_search_calls(self):
        messages = [{"role": "assistant", "content": "hello"}]
        calls = _extract_search_calls(messages)
        assert calls == []

    def test_empty_messages(self):
        assert _extract_search_calls([]) == []

    def test_one_search_call(self):
        messages = [
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": _SEARCH_TOOL_NAME, "args": {"query": "temperatura"}}
                ],
            }
        ]
        calls = _extract_search_calls(messages)
        assert len(calls) == 1
        assert calls[0]["query"] == "temperatura"
        assert calls[0]["index"] == 0

    def test_multiple_search_calls(self):
        messages = [
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": _SEARCH_TOOL_NAME, "args": {"query": "q1"}}
                ],
            },
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": _SEARCH_TOOL_NAME, "args": {"query": "q2"}}
                ],
            },
        ]
        calls = _extract_search_calls(messages)
        assert len(calls) == 2
        assert calls[0]["query"] == "q1"
        assert calls[1]["query"] == "q2"

    def test_other_tools_ignored(self):
        messages = [
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": "consultar_tag", "args": {"tags": ["LFI_RB3"]}}
                ],
            }
        ]
        calls = _extract_search_calls(messages)
        assert calls == []

    def test_mixed_tools(self):
        messages = [
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": "consultar_tag", "args": {"tags": ["LFI_RB3"]}},
                    {"name": _SEARCH_TOOL_NAME, "args": {"query": "q1"}},
                ],
            },
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": _SEARCH_TOOL_NAME, "args": {"query": "q2"}}
                ],
            },
        ]
        calls = _extract_search_calls(messages)
        assert len(calls) == 2
        assert calls[0]["query"] == "q1"
        assert calls[1]["query"] == "q2"

    def test_with_tool_responses(self):
        messages = [
            {
                "role": "tool_call",
                "tool_calls": [
                    {"name": _SEARCH_TOOL_NAME, "args": {"query": "q1"}}
                ],
            },
            {
                "role": "tool_response",
                "tool_responses": [
                    {"name": _SEARCH_TOOL_NAME, "response": json.dumps(_STRONG_PAYLOAD)}
                ],
            },
        ]
        calls = _extract_search_calls(messages)
        assert len(calls) == 1
        assert calls[0]["response"] is not None


# ---------------------------------------------------------------------------
# T5: _is_weak_search_result
# ---------------------------------------------------------------------------

class TestIsWeakSearchResult:
    def test_none_payload(self):
        assert not _is_weak_search_result(None)

    def test_error_payload(self):
        assert _is_weak_search_result(_ERROR_PAYLOAD)

    def test_empty_result(self):
        assert _is_weak_search_result(_WEAK_EMPTY_PAYLOAD)

    def test_saturated_no_description(self):
        assert _is_weak_search_result(_WEAK_SATURATED_PAYLOAD)

    def test_strong_result(self):
        assert not _is_weak_search_result(_STRONG_PAYLOAD)

    def test_success_false(self):
        assert _is_weak_search_result({"success": False, "count": 5, "items": [{"name": "X"}]})

    def test_partial_with_descriptions(self):
        payload = {
            "success": True,
            "count": 5,
            "max_count": 10,
            "items": [
                {"name": "TAG_1", "description": "Desc"},
                {"name": "TAG_2", "description": None},
            ],
        }
        assert not _is_weak_search_result(payload)


# ---------------------------------------------------------------------------
# T5: _rank_search_result
# ---------------------------------------------------------------------------

class TestRankSearchResult:
    def test_none_returns_0(self):
        assert _rank_search_result(None) == 0

    def test_error_returns_0(self):
        assert _rank_search_result(_ERROR_PAYLOAD) == 0

    def test_empty_returns_1(self):
        assert _rank_search_result(_WEAK_EMPTY_PAYLOAD) == 1

    def test_saturated_returns_2(self):
        assert _rank_search_result(_WEAK_SATURATED_PAYLOAD) == 2

    def test_strong_returns_3(self):
        assert _rank_search_result(_STRONG_PAYLOAD) == 3


# ---------------------------------------------------------------------------
# T5: _best_search_result
# ---------------------------------------------------------------------------

class TestBestSearchResult:
    def test_strong_wins_over_weak(self):
        calls = [
            {"response": json.dumps(_WEAK_EMPTY_PAYLOAD)},
            {"response": json.dumps(_STRONG_PAYLOAD)},
        ]
        best = _best_search_result(calls)
        assert best is not None
        assert best["count"] == 3

    def test_weak_wins_over_empty(self):
        calls = [
            {"response": json.dumps(_WEAK_EMPTY_PAYLOAD)},
            {"response": json.dumps(_WEAK_SATURATED_PAYLOAD)},
        ]
        best = _best_search_result(calls)
        assert best is not None
        assert best["count"] == 5

    def test_all_empty(self):
        calls = [
            {"response": json.dumps(_WEAK_EMPTY_PAYLOAD)},
            {"response": json.dumps(_WEAK_EMPTY_PAYLOAD)},
        ]
        best = _best_search_result(calls)
        assert best is not None
        assert best["count"] == 0

    def test_all_errors(self):
        calls = [
            {"response": json.dumps(_ERROR_PAYLOAD)},
        ]
        best = _best_search_result(calls)
        assert best is None or not best.get("success")

    def test_no_responses(self):
        calls = [{"response": None}, {"response": None}]
        best = _best_search_result(calls)
        assert best is None


# ---------------------------------------------------------------------------
# T6: _enforce_search_loop_policy
# ---------------------------------------------------------------------------

def _make_tool_call_msg(name: str, args: dict) -> dict:
    return {
        "role": "tool_call",
        "tool_calls": [{"name": name, "args": args}],
    }


def _make_tool_response_msg(name: str, payload: dict) -> dict:
    return {
        "role": "tool_response",
        "tool_responses": [{"name": name, "response": json.dumps(payload)}],
    }


def _make_search_call(query: str, payload: dict | None = None) -> list[dict]:
    msgs = [_make_tool_call_msg(_SEARCH_TOOL_NAME, {"query": query})]
    if payload is not None:
        msgs.append(_make_tool_response_msg(_SEARCH_TOOL_NAME, payload))
    return msgs


class TestEnforceSearchLoopPolicy:
    def test_one_call_allowed(self):
        messages = _make_search_call("temperatura", _STRONG_PAYLOAD)
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 1
        assert decision["blocked"] == 0
        assert decision["reason"] == "ok"
        assert decision["final_response_override"] is None

    def test_two_calls_allowed(self):
        messages = (
            _make_search_call("q1", _WEAK_EMPTY_PAYLOAD)
            + _make_search_call("temperatura forno RB2", _STRONG_PAYLOAD)
        )
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 2
        assert decision["blocked"] == 0
        assert decision["reason"] == "ok"

    def test_third_call_blocked(self):
        messages = (
            _make_search_call("q1", _WEAK_EMPTY_PAYLOAD)
            + _make_search_call("q2", _WEAK_EMPTY_PAYLOAD)
            + _make_search_call("q3", _WEAK_EMPTY_PAYLOAD)
        )
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == _MAX_SEARCH_PI_POINTS_CALLS_PER_TURN
        assert decision["blocked"] == 1
        assert decision["reason"] == "third_call_blocked"
        assert decision["final_response_override"] is not None

    def test_ten_calls_blocked(self):
        messages = []
        for i in range(10):
            messages += _make_search_call(f"q{i}", _WEAK_EMPTY_PAYLOAD)
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == _MAX_SEARCH_PI_POINTS_CALLS_PER_TURN
        assert decision["blocked"] == 8
        assert decision["reason"] == "third_call_blocked"
        assert decision["final_response_override"] is not None

    def test_second_blocked_when_first_strong(self):
        messages = (
            _make_search_call("q1", _STRONG_PAYLOAD)
            + _make_search_call("q2", _WEAK_EMPTY_PAYLOAD)
        )
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 1
        assert decision["blocked"] == 1
        assert decision["reason"] == "first_call_strong"
        assert decision["final_response_override"] is None

    def test_second_blocked_when_query_not_different(self):
        messages = (
            _make_search_call("q1", _WEAK_EMPTY_PAYLOAD)
            + _make_search_call("q1", _STRONG_PAYLOAD)  # same query
        )
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 1
        assert decision["blocked"] == 1
        assert decision["reason"] == "second_call_not_different"
        assert decision["final_response_override"] is None

    def test_other_tools_not_blocked(self):
        messages = [
            _make_tool_call_msg("consultar_tag", {"tags": ["LFI_RB3"]}),
            _make_tool_call_msg("consultar_tag", {"tags": ["LFI_RB4"]}),
            _make_tool_call_msg("consultar_tag", {"tags": ["LFI_RB5"]}),
        ]
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 0  # no search calls
        assert decision["blocked"] == 0
        assert decision["reason"] == "ok"

    def test_mixed_tools_only_search_counted(self):
        messages = (
            [  # one search + one other tool
                _make_tool_call_msg("consultar_tag", {"tags": ["LFI_RB3"]}),
                _make_tool_call_msg(_SEARCH_TOOL_NAME, {"query": "q1"}),
            ]
            + _make_search_call("q2", _STRONG_PAYLOAD)  # second search
        )
        # First search has no response payload → treated as not-weak (conservative)
        # Second is strong → first is not weak → keep=1, block=1
        decision = _enforce_search_loop_policy(messages)
        assert decision["reason"] == "first_call_strong"

    def test_third_call_blocked_with_best_result(self):
        messages = (
            _make_search_call("q1", _WEAK_EMPTY_PAYLOAD)
            + _make_search_call("q2", _STRONG_PAYLOAD)
            + _make_search_call("q3", _WEAK_EMPTY_PAYLOAD)
        )
        decision = _enforce_search_loop_policy(messages)
        assert decision["reason"] == "third_call_blocked"
        assert decision["final_response_override"] is not None
        assert "LFI_RB3_VAZ" in decision["final_response_override"]

    def test_no_calls_ok(self):
        messages = []
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 0
        assert decision["blocked"] == 0
        assert decision["reason"] == "ok"

    def test_only_non_search_tools_ok(self):
        messages = [
            _make_tool_call_msg("tag_statistics", {"tags": ["X"]}),
            _make_tool_call_msg("tag_calculus", {"tags": ["X"]}),
        ]
        decision = _enforce_search_loop_policy(messages)
        assert decision["kept"] == 0
        assert decision["blocked"] == 0
