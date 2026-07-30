"""Tests for artifact-related feature flag validation."""
from __future__ import annotations

import pytest

from app.core.config import Settings


class TestAppFlagValidation:
    def test_attachments_without_artifacts_fails(self):
        with pytest.raises(ValueError, match="ENABLE_CHAT_ATTACHMENTS=true"):
            Settings(ENABLE_CHAT_ATTACHMENTS=True, ENABLE_ARTIFACTS=False)

    def test_attachments_with_artifacts_ok(self):
        s = Settings(ENABLE_CHAT_ATTACHMENTS=True, ENABLE_ARTIFACTS=True)
        assert s.ENABLE_ARTIFACTS is True
        assert s.ENABLE_CHAT_ATTACHMENTS is True

    def test_all_flags_false_starts_without_token(self):
        s = Settings()
        assert s.ENABLE_ARTIFACTS is False
        assert s.ENABLE_CHAT_ATTACHMENTS is False
        assert s.ENABLE_TEST_ARTIFACT_TOOL is False
        assert s.AGENT_ARTIFACT_TOKEN is None

    def test_artifacts_alone_starts_without_token(self):
        s = Settings(ENABLE_ARTIFACTS=True)
        assert s.ENABLE_ARTIFACTS is True


class TestMcpFlagValidation:
    def test_test_artifact_tool_without_token_fails(self):
        from mcp_server.core.config import Settings as McpSettings
        with pytest.raises(ValueError, match="ENABLE_TEST_ARTIFACT_TOOL=true"):
            McpSettings(ENABLE_TEST_ARTIFACT_TOOL=True)

    def test_test_artifact_tool_without_api_url_fails(self):
        from mcp_server.core.config import Settings as McpSettings
        with pytest.raises(ValueError, match="ENABLE_TEST_ARTIFACT_TOOL=true"):
            McpSettings(ENABLE_TEST_ARTIFACT_TOOL=True, AGENT_ARTIFACT_TOKEN="x",
                        AGENT_API_BASE_URL="")

    def test_test_artifact_tool_with_all_deps_ok(self):
        from mcp_server.core.config import Settings as McpSettings
        s = McpSettings(
            ENABLE_TEST_ARTIFACT_TOOL=True,
            AGENT_ARTIFACT_TOKEN="test-token",
            AGENT_API_BASE_URL="http://localhost:8002",
        )
        assert s.ENABLE_TEST_ARTIFACT_TOOL is True

    def test_flags_false_start_without_deps(self):
        from mcp_server.core.config import Settings as McpSettings
        s = McpSettings(
            ENABLE_TEST_ARTIFACT_TOOL=False,
        )
        assert s.ENABLE_TEST_ARTIFACT_TOOL is False
