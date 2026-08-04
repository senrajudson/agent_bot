from __future__ import annotations

import pytest

from domain.analysis.policies import (
    GAP_THRESHOLD_INTERPOLATED_SECONDS,
    GAP_THRESHOLD_RECORDED_FALLBACK_SECONDS,
    MAX_PERIOD_DAYS,
    MAX_TAGS,
    PROHIBITED_VERDICT_TERMS,
    SPIKE_RELATIVE_DELTA,
    SPIKE_ROLLING_WINDOW,
    SPIKE_TOP_N,
    ZERO_POLICIES,
    assess_quality,
    validate_analysis_report_contract,
)
from domain.shared.errors import DomainValidationError


class TestQualityMatrix:
    def test_dados_excelentes(self) -> None:
        assert assess_quality(99.5, 0.0, 0.0, 3.0, "valid") == "DADOS_EXCELENTES"

    def test_dados_excelentes_with_valid_zero_policy(self) -> None:
        assert assess_quality(99.5, 0.0, 0.0, 8.0, "valid") == "DADOS_EXCELENTES"

    def test_dados_saudaveis(self) -> None:
        assert assess_quality(96.0, 0.5, 0.5, 10.0, "suspicious") == "DADOS_SAUDÁVEIS"

    def test_dados_aceitaveis(self) -> None:
        assert assess_quality(85.0, 5.0, 3.0, 20.0, "suspicious") == "DADOS_ACEITÁVEIS"

    def test_dados_degradados(self) -> None:
        assert assess_quality(70.0, 10.0, 10.0, 30.0, "suspicious") == "DADOS_DEGRADADOS"

    def test_boundary_good_99(self) -> None:
        assert assess_quality(99.0, 0.0, 0.0, 3.0, "valid") == "DADOS_EXCELENTES"

    def test_boundary_good_95(self) -> None:
        assert assess_quality(95.0, 1.0, 1.0, 10.0, "suspicious") == "DADOS_SAUDÁVEIS"

    def test_boundary_good_80(self) -> None:
        assert assess_quality(80.0, 5.0, 5.0, 20.0, "suspicious") == "DADOS_ACEITÁVEIS"


class TestGapThresholds:
    def test_interpolated_seconds(self) -> None:
        assert GAP_THRESHOLD_INTERPOLATED_SECONDS == 900

    def test_recorded_fallback_seconds(self) -> None:
        assert GAP_THRESHOLD_RECORDED_FALLBACK_SECONDS == 1800


class TestSpikeThresholds:
    def test_rolling_window(self) -> None:
        assert SPIKE_ROLLING_WINDOW == 5

    def test_relative_delta(self) -> None:
        assert SPIKE_RELATIVE_DELTA == 0.5

    def test_top_n(self) -> None:
        assert SPIKE_TOP_N == 5


class TestZeroPolicies:
    def test_policies_tuple(self) -> None:
        assert ZERO_POLICIES == ("valid", "suspicious", "invalid")


class TestProhibitedTerms:
    def test_terms_present(self) -> None:
        assert "processo" in PROHIBITED_VERDICT_TERMS
        assert "equipamento" in PROHIBITED_VERDICT_TERMS
        assert "operador" in PROHIBITED_VERDICT_TERMS
        assert "normal" in PROHIBITED_VERDICT_TERMS
        assert "anormal" in PROHIBITED_VERDICT_TERMS
        assert "defeituoso" in PROHIBITED_VERDICT_TERMS


class TestValidateContract:
    def test_empty_tags_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="Pelo menos uma tag"):
            validate_analysis_report_contract([], "2026-01-01T00:00:00-03:00", "2026-01-02T00:00:00-03:00")

    def test_empty_tag_name_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="Tag vazia"):
            validate_analysis_report_contract([""], "2026-01-01T00:00:00-03:00", "2026-01-02T00:00:00-03:00")

    def test_too_many_tags_raises(self) -> None:
        tags = [f"TAG_{i}" for i in range(11)]
        with pytest.raises(DomainValidationError, match="Máximo de 10"):
            validate_analysis_report_contract(tags, "2026-01-01T00:00:00-03:00", "2026-01-02T00:00:00-03:00")

    def test_invalid_start_time_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="não é ISO 8601 válido"):
            validate_analysis_report_contract(["X"], "not-a-date", "2026-01-02T00:00:00-03:00")

    def test_start_after_end_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="start_time deve ser anterior"):
            validate_analysis_report_contract(["X"], "2026-01-02T00:00:00-03:00", "2026-01-01T00:00:00-03:00")

    def test_window_exceeds_max(self) -> None:
        with pytest.raises(DomainValidationError, match="Período máximo é 31"):
            validate_analysis_report_contract(["X"], "2026-01-01T00:00:00-03:00", "2026-02-15T00:00:00-03:00")

    def test_duplicate_tags_deduped(self) -> None:
        validate_analysis_report_contract(["A", "A", "B"], "2026-01-01T00:00:00-03:00", "2026-01-02T00:00:00-03:00")

    def test_invalid_zero_policy(self) -> None:
        with pytest.raises(DomainValidationError, match="zero_policy deve ser um de"):
            validate_analysis_report_contract(["X"], "2026-01-01T00:00:00-03:00", "2026-01-02T00:00:00-03:00", zero_policy="unknown")  # type: ignore[arg-type]

    def test_max_tags(self) -> None:
        tags = [f"TAG_{i}" for i in range(10)]
        validate_analysis_report_contract(tags, "2026-01-01T00:00:00-03:00", "2026-01-02T00:00:00-03:00")

    def test_max_period(self) -> None:
        validate_analysis_report_contract(["X"], "2026-01-01T00:00:00-03:00", "2026-02-01T00:00:00-03:00")
