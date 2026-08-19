from __future__ import annotations

import json
from mcp_server.services.delivery.contracts import (
    ArtifactManifest,
    ArtifactMetadata,
    ErrorsSummaryItem,
    RequestSummary,
    WarningsItem,
)
from mcp_server.services.delivery.manifest_builder import build_artifact_manifest


def test_artifact_manifest_strict_schema_contract() -> None:
    """T003: Garante imutabilidade estrita das chaves públicas do ArtifactManifest."""
    manifest = build_artifact_manifest(
        status="success",
        tool_name="generate_pi_tags_analysis_report",
        request_summary=RequestSummary(
            tool_name="generate_pi_tags_analysis_report",
            tags_requested=1,
            tags_processed=1,
            start_time="2026-08-18T00:00:00Z",
            end_time="2026-08-19T00:00:00Z",
            operation="analyze",
        ),
        artifact_metadata=ArtifactMetadata(
            format="xlsx",
            filename="report.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            row_count=10,
            column_count=5,
            size_bytes=12345,
            view_url="https://drive.google.com/file/d/test/view",
        ),
        warnings=[WarningsItem(code="W01", message="Warning test")],
        errors_summary=[ErrorsSummaryItem(tag="TAG1", code="E01", message="Error test", retryable=False)],
    )

    data = manifest.to_dict()

    # Chaves de primeiro nível obrigatórias
    expected_top_level_keys = {
        "schema_version",
        "status",
        "delivery",
        "tool_name",
        "request_summary",
        "artifact",
        "warnings",
        "errors_summary",
    }
    assert set(data.keys()) == expected_top_level_keys, (
        f"Chaves públicas do ArtifactManifest alteradas! Esperado {expected_top_level_keys}, obtido {set(data.keys())}"
    )

    # Chaves da sub-estrutura 'artifact'
    expected_artifact_keys = {
        "format",
        "filename",
        "mime_type",
        "row_count",
        "column_count",
        "size_bytes",
        "view_url",
    }
    assert set(data["artifact"].keys()) == expected_artifact_keys, (
        f"Sub-chaves de 'artifact' alteradas! Esperado {expected_artifact_keys}, obtido {set(data['artifact'].keys())}"
    )

    # Propriedade 'delivery' é string (ex: 'drive_artifact')
    assert isinstance(data["delivery"], str)
    assert data["delivery"] == "drive_artifact"
