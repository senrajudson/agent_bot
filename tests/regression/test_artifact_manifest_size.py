"""
Teste de regressão: valida que um manifesto nunca ultrapassa o limite
configurado e que o retorno é drasticamente menor que a série inline.
"""
import json
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
from mcp_server.services.delivery.contracts import (
    ArtifactMetadata,
    RequestSummary,
    ErrorsSummaryItem,
    WarningsItem,
)


def _simulate_buckets(count: int) -> list[dict]:
    buckets = []
    for i in range(count):
        bucket = {
            "period_start": f"2026-07-01T{i // 60:02d}:{i % 60:02d}:00Z",
            "period_end": f"2026-07-01T{i // 60:02d}:{(i % 60) + 1:02d}:00Z",
            "value": 100.0 + (i % 50),
            "unit": "Nm3",
            "quality": "good",
        }
        buckets.append(bucket)
    return buckets


def _build_manifest_for(series_items: list[dict]) -> dict:
    summary = RequestSummary(
        tool_name="tag_statistics",
        tags_requested=1,
        tags_processed=1,
        operation="mean",
        group_by="1m",
        start_time="2026-07-01T00:00:00Z",
        end_time="2026-07-31T23:59:59Z",
    )
    artifact_meta = ArtifactMetadata(
        format="csv",
        filename="test.csv",
        mime_type="text/csv",
        row_count=len(series_items),
        column_count=5,
        size_bytes=len(series_items) * 50,
        view_url="https://drive.google.com/file/d/abc123/view",
    )
    manifest = build_artifact_manifest(
        status="success",
        tool_name="tag_statistics",
        request_summary=summary,
        artifact_metadata=artifact_meta,
        max_manifest_bytes=8192,
    )
    return manifest.to_dict()


class TestArtifactManifestSize:
    MANIFEST_MAX_BYTES = 8192

    def test_44640_buckets_fits_in_8k(self):
        """44.640 buckets (31 dias, group_by=1m) devem gerar manifesto < 8 KB."""
        buckets = _simulate_buckets(44640)
        manifest = _build_manifest_for(buckets)
        serialized = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
        size = len(serialized.encode("utf-8"))
        assert size < self.MANIFEST_MAX_BYTES, (
            f"Manifesto com {len(buckets)} buckets tem {size} bytes "
            f"(limite: {self.MANIFEST_MAX_BYTES})"
        )

    def test_manifest_does_not_contain_series(self):
        """Manifesto nunca deve conter o campo 'series'."""
        buckets = _simulate_buckets(100)
        manifest = _build_manifest_for(buckets)
        serialized = json.dumps(manifest)
        assert "series" not in serialized, "Manifesto não deve conter 'series'"

    def test_manifest_does_not_contain_bucket_values(self):
        """Manifesto nunca deve conter valores de buckets."""
        buckets = _simulate_buckets(44640)
        manifest = _build_manifest_for(buckets)
        serialized = json.dumps(manifest)
        assert "period_start" not in serialized, "Manifesto não deve conter period_start"
        assert "period_end" not in serialized, "Manifesto não deve conter period_end"
        assert '"value":' not in serialized, "Manifesto não deve conter values"

    def test_manifest_size_scales_logarithmically(self):
        """Tamanho do manifesto NÃO deve crescer linearmente com o número de buckets."""
        small = _simulate_buckets(1)
        medium = _simulate_buckets(100)
        large = _simulate_buckets(44640)

        json_small = json.dumps(_build_manifest_for(small), separators=(",", ":"))
        json_large = json.dumps(_build_manifest_for(large), separators=(",", ":"))

        ratio = len(json_large) / len(json_small)
        assert ratio < 10, (
            f"Manifesto de 44.640 buckets ({len(json_large)} bytes) é "
            f"{ratio:.1f}x maior que o de 1 bucket ({len(json_small)} bytes). "
            "Esperado < 10x para escala não linear."
        )

    def test_legacy_series_vs_manifest_comparison(self):
        """Demonstra a redução de tamanho: legado >> manifesto."""
        buckets = _simulate_buckets(44640)
        legacy_serialized = json.dumps(buckets, ensure_ascii=False, separators=(",", ":"))

        manifest = _build_manifest_for(buckets)
        manifest_serialized = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))

        reduction_pct = (1 - len(manifest_serialized) / len(legacy_serialized)) * 100
        assert reduction_pct > 95, (
            f"Redução de apenas {reduction_pct:.1f}%. "
            f"Legado: {len(legacy_serialized)} bytes, "
            f"Manifesto: {len(manifest_serialized)} bytes"
        )
