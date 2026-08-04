from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError


class TestClosureSafety:
    def test_context_text_rejected(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            import asyncio
            asyncio.run(analyze_pi_tag_behavior(
                tag="X", start_time="a", end_time="b", context_text="nope"
            ))

    def test_pergunta_usuario_rejected(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            import asyncio
            asyncio.run(analyze_pi_tag_behavior(
                tag="X", start_time="a", end_time="b", pergunta_usuario="nope"
            ))

    def test_data_server_rejected(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            import asyncio
            asyncio.run(analyze_pi_tag_behavior(
                tag="X", start_time="a", end_time="b", data_server="nope"
            ))

    def test_report_context_text_rejected(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            import asyncio
            asyncio.run(generate_pi_tags_analysis_report(
                tags=["X"], start_time="a", end_time="b", context_text="nope"
            ))
