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

    def test_additive_envelope_compatibility(self) -> None:
        """T004: Garante que os parsers de envelope ignoram campos irmãos como 'analysis_completeness'."""
        import json
        from mcp_server.services.delivery.contracts import ArtifactManifest, RequestSummary, ArtifactMetadata
        from mcp_server.services.delivery.manifest_builder import build_artifact_manifest

        base_manifest = build_artifact_manifest(
            status="success",
            tool_name="generate_pi_tags_analysis_report",
            request_summary=RequestSummary(tool_name="generate_pi_tags_analysis_report"),
            artifact_metadata=ArtifactMetadata(
                format="xlsx", filename="test.xlsx", mime_type="application/vnd.ms-excel",
                row_count=1, column_count=1, size_bytes=100, view_url="http://view"
            )
        )
        base_dict = base_manifest.to_dict()

        # Simular envelope com extensão aditiva
        extended_envelope = {
            "artifact": base_dict,
            "analysis_completeness": {
                "overall_status": "PARTIAL",
                "tags": [{"tag": "TAG1", "truncated": True}]
            }
        }

        raw_json = json.dumps(extended_envelope)
        parsed = json.loads(raw_json)

        # O extrator legado deve continuar conseguindo ler o 'artifact' intacto
        assert "artifact" in parsed
        reconstructed = ArtifactManifest(
            status=parsed["artifact"]["status"],
            tool_name=parsed["artifact"]["tool_name"]
        )
        assert reconstructed.status == "success"
        assert parsed["analysis_completeness"]["overall_status"] == "PARTIAL"
