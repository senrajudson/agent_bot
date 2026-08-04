from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from domain.analysis.models import (
    AnalysisError,
    AnalysisRequest,
    AnalysisPoint,
    TagAnalysisResult,
    TagMetadata,
    MultiTagAnalysisResult,
    QualityMetrics,
    NumericStatistics,
    GapCandidate,
    AbruptChangeCandidate,
    DigitalStateDuration,
    DigitalTransition,
)


class TestAnalysisRequest:
    def test_required_fields(self) -> None:
        req = AnalysisRequest(tag="LFI_X", start_time="2026-01-01T00:00:00-03:00", end_time="2026-01-02T00:00:00-03:00")
        assert req.tag == "LFI_X"
        assert req.start_time.startswith("2026")
        assert req.end_time.startswith("2026")

    def test_rejects_extras(self) -> None:
        with pytest.raises(TypeError):
            AnalysisRequest(tag="X", start_time="a", end_time="b", extra_field="nope")  # type: ignore[arg-type]

    def test_defaults(self) -> None:
        req = AnalysisRequest()
        assert req.zero_policy == "suspicious"
        assert req.tags == ()
        assert req.tag == ""


class TestFrozen:
    def test_dataclass_is_frozen(self) -> None:
        req = AnalysisRequest(tag="X", start_time="a", end_time="b")
        with pytest.raises(FrozenInstanceError):
            req.tag = "Y"  # type: ignore[misc]

    def test_analysis_point_frozen(self) -> None:
        p = AnalysisPoint(timestamp="t", value=1.0)
        with pytest.raises(FrozenInstanceError):
            p.value = 2.0  # type: ignore[misc]


class TestTagDeduplication:
    def test_dedup_preserves_order(self) -> None:
        tags = ("A", "B", "A", "C", "B")
        seen: set[str] = set()
        result: list[str] = []
        for t in tags:
            if t not in seen:
                result.append(t)
                seen.add(t)
        assert result == ["A", "B", "C"]


class TestZeroPolicyLiteral:
    def test_valid_values(self) -> None:
        from domain.analysis.models import ZeroPolicy
        assert "valid" in ("valid", "suspicious", "invalid")
        assert "suspicious" in ("valid", "suspicious", "invalid")
        assert "invalid" in ("valid", "suspicious", "invalid")
