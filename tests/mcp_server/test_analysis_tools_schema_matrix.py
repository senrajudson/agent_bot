from __future__ import annotations

import pytest


class TestInputSchema:
    def test_analyze_schema_has_required_fields(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        import inspect
        sig = inspect.signature(analyze_pi_tag_behavior)
        params = list(sig.parameters.keys())
        assert "tag" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "zero_policy" in params

    def test_report_schema_has_required_fields(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        import inspect
        sig = inspect.signature(generate_pi_tags_analysis_report)
        params = list(sig.parameters.keys())
        assert "tags" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "zero_policy" in params

    def test_no_context_text_in_analyze(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        import inspect
        sig = inspect.signature(analyze_pi_tag_behavior)
        assert "context_text" not in sig.parameters

    def test_no_pergunta_usuario_in_analyze(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        import inspect
        sig = inspect.signature(analyze_pi_tag_behavior)
        assert "pergunta_usuario" not in sig.parameters

    def test_no_data_server_in_analyze(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        import inspect
        sig = inspect.signature(analyze_pi_tag_behavior)
        assert "data_server" not in sig.parameters

    def test_zero_policy_literal_values(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        import inspect
        sig = inspect.signature(analyze_pi_tag_behavior)
        zp = sig.parameters["zero_policy"]
        assert zp.default == "suspicious"

    def test_report_zero_policy_default(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        import inspect
        sig = inspect.signature(generate_pi_tags_analysis_report)
        zp = sig.parameters["zero_policy"]
        assert zp.default == "invalid"
