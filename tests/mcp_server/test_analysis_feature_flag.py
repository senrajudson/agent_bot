from __future__ import annotations

import pytest


class TestFeatureFlag:
    def test_default_false(self) -> None:
        from mcp_server.core.config import Settings
        s = Settings()
        assert s.ENABLE_MCP_ANALYSIS_TOOLS is False

    def test_true_registers_both_tools(self) -> None:
        from mcp_server.core.config import Settings
        s = Settings(ENABLE_MCP_ANALYSIS_TOOLS=True)
        assert s.ENABLE_MCP_ANALYSIS_TOOLS is True

    def test_false_tools_absent(self) -> None:
        from mcp_server.core.config import Settings
        s = Settings(ENABLE_MCP_ANALYSIS_TOOLS=False)
        assert s.ENABLE_MCP_ANALYSIS_TOOLS is False

    def test_startup_log(self) -> None:
        from mcp_server.core.config import Settings
        s = Settings(ENABLE_MCP_ANALYSIS_TOOLS=True)
        assert s.ENABLE_MCP_ANALYSIS_TOOLS is True
