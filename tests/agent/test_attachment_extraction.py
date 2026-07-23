"""Tests for _extract_attachments_from_agent_output."""
from __future__ import annotations

import json

import pytest

from app.agent.agent import (
    _ALLOWED_ATTACHMENT_MIMES,
    _dedupe_by_artifact_id,
    _enforce_attachment_limits,
    _extract_attachments_from_agent_output,
    _is_valid_attachment,
)


# ── _is_valid_attachment ──


class TestIsValidAttachment:
    def test_valid_with_all_required(self):
        item = {"artifact_id": "abc", "filename": "f.txt", "mime_type": "text/plain"}
        assert _is_valid_attachment(item) is True

    def test_missing_artifact_id_rejected(self):
        item = {"filename": "f.txt", "mime_type": "text/plain"}
        assert _is_valid_attachment(item) is False

    def test_blank_artifact_id_rejected(self):
        item = {"artifact_id": "", "filename": "f.txt", "mime_type": "text/plain"}
        assert _is_valid_attachment(item) is False

    def test_missing_filename_rejected(self):
        item = {"artifact_id": "a1", "mime_type": "text/plain"}
        assert _is_valid_attachment(item) is False

    def test_missing_mime_type_rejected(self):
        item = {"artifact_id": "a1", "filename": "f.txt"}
        assert _is_valid_attachment(item) is False

    def test_path_field_rejected(self):
        item = {"artifact_id": "a1", "filename": "f.txt", "mime_type": "text/plain",
                "path": "/tmp/x"}
        assert _is_valid_attachment(item) is False

    def test_download_url_rejected(self):
        item = {"artifact_id": "a1", "filename": "f.txt", "mime_type": "text/plain",
                "download_url": "http://x"}
        assert _is_valid_attachment(item) is False

    def test_mime_not_in_allowlist_rejected(self):
        item = {"artifact_id": "a1", "filename": "f.txt", "mime_type": "application/json"}
        assert _is_valid_attachment(item) is False

    def test_mime_in_allowlist_accepted(self):
        for mt in _ALLOWED_ATTACHMENT_MIMES:
            item = {"artifact_id": "a1", "filename": "f.txt", "mime_type": mt}
            assert _is_valid_attachment(item) is True

    def test_negative_size_bytes_rejected(self):
        item = {"artifact_id": "a1", "filename": "f.txt", "mime_type": "text/plain",
                "size_bytes": -1}
        assert _is_valid_attachment(item) is False

    def test_optional_fields_accepted(self):
        item = {"artifact_id": "a1", "filename": "f.txt", "mime_type": "text/plain",
                "size_bytes": 100, "cleanup_after_send": True, "caption": "my cap"}
        assert _is_valid_attachment(item) is True

    def test_non_dict_rejected(self):
        assert _is_valid_attachment("string") is False
        assert _is_valid_attachment(123) is False


# ── _dedupe_by_artifact_id ──


class TestDedupeByArtifactId:
    def test_removes_duplicates_keeps_first(self):
        items = [
            {"artifact_id": "a1", "filename": "a.txt"},
            {"artifact_id": "a1", "filename": "b.txt"},
            {"artifact_id": "a2", "filename": "c.txt"},
        ]
        result = _dedupe_by_artifact_id(items)
        assert len(result) == 2
        assert result[0]["filename"] == "a.txt"
        assert result[1]["filename"] == "c.txt"

    def test_empty_list(self):
        assert _dedupe_by_artifact_id([]) == []


# ── _enforce_attachment_limits ──


class TestEnforceAttachmentLimits:
    def test_max_3_truncated(self):
        items = [
            {"artifact_id": f"a{i}", "filename": f"f{i}.txt", "mime_type": "text/plain",
             "size_bytes": 100}
            for i in range(5)
        ]
        result = _enforce_attachment_limits(items, max_count=3)
        assert len(result) == 3

    def test_50mb_aggregated_rejected(self):
        items = [
            {"artifact_id": f"a{i}", "filename": f"f{i}.txt", "mime_type": "text/plain",
             "size_bytes": 30 * 1024 * 1024}
            for i in range(2)
        ]
        result = _enforce_attachment_limits(items, max_total_bytes=50 * 1024 * 1024)
        assert result == []

    def test_under_limit_passes(self):
        items = [
            {"artifact_id": "a1", "filename": "f.txt", "mime_type": "text/plain",
             "size_bytes": 1000}
        ]
        result = _enforce_attachment_limits(items, max_total_bytes=50_000_000)
        assert len(result) == 1

    def test_empty_list(self):
        assert _enforce_attachment_limits([]) == []


# ── _extract_attachments_from_agent_output ──


class TestExtractAttachmentsFromAgentOutput:
    def make_envelope(self, answer: str, attachments: list) -> str:
        return json.dumps({
            "type": "agent_artifact_result",
            "answer": answer,
            "attachments": attachments,
        })

    def valid_att(self, artifact_id="a1", **kw) -> dict:
        base = {"artifact_id": artifact_id, "filename": "f.txt", "mime_type": "text/plain"}
        base.update(kw)
        return base

    def test_envelope_with_valid_attachments(self):
        output = self.make_envelope("ok", [self.valid_att()])
        answer, attachments = _extract_attachments_from_agent_output(output, [])
        assert answer == "ok"
        assert len(attachments) == 1

    def test_missing_artifact_id_filtered_out(self):
        output = self.make_envelope("ok", [
            {"filename": "f.txt", "mime_type": "text/plain"},
        ])
        _, attachments = _extract_attachments_from_agent_output(output, [])
        assert attachments == []

    def test_path_field_filtered_out(self):
        output = self.make_envelope("ok", [
            self.valid_att(path="/tmp/x"),
        ])
        _, attachments = _extract_attachments_from_agent_output(output, [])
        assert attachments == []

    def test_invalid_json_does_not_break(self):
        output = "invalid json"
        answer, attachments = _extract_attachments_from_agent_output(output, [])
        assert answer == output
        assert attachments == []

    def test_text_fallback_when_no_envelope(self):
        output = "resposta normal do agente"
        answer, attachments = _extract_attachments_from_agent_output(output, [])
        assert answer == "resposta normal do agente"
        assert attachments == []

    def test_drive_response_no_attachments(self):
        output = self.make_envelope("dados da tag LFI_RB3", [])
        answer, attachments = _extract_attachments_from_agent_output(output, [])
        assert "LFI_RB3" in answer
        assert attachments == []

    def test_duplicate_artifact_id_deduped(self):
        output = self.make_envelope("ok", [
            self.valid_att(artifact_id="a1"),
            self.valid_att(artifact_id="a1", filename="dup.txt"),
        ])
        _, attachments = _extract_attachments_from_agent_output(output, [])
        assert len(attachments) == 1

    def test_exceeds_3_truncated(self):
        atts = [self.valid_att(artifact_id=f"a{i}") for i in range(5)]
        output = self.make_envelope("ok", atts)
        _, attachments = _extract_attachments_from_agent_output(output, [])
        assert len(attachments) == 3

    def test_exceeds_50mb_rejected(self):
        atts = [
            self.valid_att(artifact_id="big1", size_bytes=30 * 1024 * 1024),
            self.valid_att(artifact_id="big2", size_bytes=30 * 1024 * 1024),
        ]
        output = self.make_envelope("ok", atts)
        _, attachments = _extract_attachments_from_agent_output(output, [])
        assert attachments == []

    def test_mime_invalid_rejected(self):
        output = self.make_envelope("ok", [
            self.valid_att(mime_type="application/json"),
        ])
        _, attachments = _extract_attachments_from_agent_output(output, [])
        assert attachments == []

    def test_adk_structured_content_wrapper(self):
        envelope = self.make_envelope("via structuredContent", [self.valid_att()])
        msg = {
            "role": "tool",
            "tool_responses": [{
                "name": "generate_test_artifact_tool",
                "response": {
                    "structuredContent": json.loads(envelope),
                },
            }],
        }
        answer, attachments = _extract_attachments_from_agent_output("", [msg])
        assert answer == "via structuredContent"
        assert len(attachments) == 1

    def test_adk_text_content_wrapper(self):
        envelope = self.make_envelope("via TextContent", [self.valid_att()])
        msg = {
            "role": "tool",
            "tool_responses": [{
                "name": "generate_test_artifact_tool",
                "response": {
                    "content": [{"type": "text", "text": envelope}],
                },
            }],
        }
        answer, attachments = _extract_attachments_from_agent_output("", [msg])
        assert answer == "via TextContent"
        assert len(attachments) == 1
