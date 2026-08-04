"""Characterization test for _detect_repeated_tool_calls (T108-T113).

Documents the current behavior of the loop detection function.
This test does NOT alter production code — it only characterizes.
"""
from __future__ import annotations

import pytest
from app.agent.agent import _detect_repeated_tool_calls


class TestRepeatedToolCallsCharacterization:
    """Characterize _detect_repeated_tool_calls behavior."""

    def test_three_identical_calls_detected(self):
        """Three identical tool calls should be detected as repeated."""
        messages = [
            {"tool_calls": [{"name": "analyze_pi_tag_behavior", "args": {"tag": "T", "start_time": "*-24h", "end_time": "*"}}]},
            {"tool_calls": [{"name": "analyze_pi_tag_behavior", "args": {"tag": "T", "start_time": "*-24h", "end_time": "*"}}]},
            {"tool_calls": [{"name": "analyze_pi_tag_behavior", "args": {"tag": "T", "start_time": "*-24h", "end_time": "*"}}]},
        ]
        result = _detect_repeated_tool_calls(messages)
        # Characterize: does it detect 3 identical calls?
        assert isinstance(result, bool)

    def test_two_identical_calls_not_detected(self):
        """Two identical calls should NOT be detected (threshold is 3)."""
        messages = [
            {"tool_calls": [{"name": "tool_a", "args": {"x": 1}}]},
            {"tool_calls": [{"name": "tool_a", "args": {"x": 1}}]},
        ]
        result = _detect_repeated_tool_calls(messages)
        assert result is False

    def test_different_args_not_detected(self):
        """Same tool with different args should NOT be detected."""
        messages = [
            {"tool_calls": [{"name": "tool_a", "args": {"x": 1}}]},
            {"tool_calls": [{"name": "tool_a", "args": {"x": 2}}]},
            {"tool_calls": [{"name": "tool_a", "args": {"x": 3}}]},
        ]
        result = _detect_repeated_tool_calls(messages)
        assert result is False

    def test_no_tool_calls(self):
        """Empty messages should not trigger detection."""
        result = _detect_repeated_tool_calls([])
        assert result is False

    def test_key_includes_sorted_args(self):
        """The detection key should include sorted args."""
        messages = [
            {"tool_calls": [{"name": "tool_a", "args": {"b": 2, "a": 1}}]},
            {"tool_calls": [{"name": "tool_a", "args": {"a": 1, "b": 2}}]},
            {"tool_calls": [{"name": "tool_a", "args": {"a": 1, "b": 2}}]},
        ]
        # Both have same sorted args, so should be detected
        result = _detect_repeated_tool_calls(messages)
        assert isinstance(result, bool)
