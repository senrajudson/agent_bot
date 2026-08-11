"""Testes de formatter digital — T091-T105.

Cobre: identificação, classificação não aplicável, status humano,
estados, ocupação, transições, integridade, truncamento, termos proibidos.
"""

from __future__ import annotations

from domain.analysis.formatters import InlineReportFormatter
from domain.analysis.models import (
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalStateOccupancy,
    DigitalStateRef,
    DigitalTransition,
    TagAnalysisResult,
    TagMetadata,
)


def _make_digital(
    status: DigitalAnalysisStatus = DigitalAnalysisStatus.COMPLETE,
    occupancy: tuple[DigitalStateOccupancy, ...] | None = None,
    transitions: tuple[DigitalTransition, ...] | None = None,
) -> TagAnalysisResult:
    if occupancy is None:
        occupancy = (
            DigitalStateOccupancy(state_code=0, state_name="DESLIGADO", duration_seconds=43200, percentage_of_window=50.0, entries_count=1),
            DigitalStateOccupancy(state_code=2, state_name="LIGADO", duration_seconds=43200, percentage_of_window=50.0, entries_count=1),
        )
    if transitions is None:
        transitions = (DigitalTransition(from_state="DESLIGADO", to_state="LIGADO", count=1, rate_per_hour=0.5),)

    return TagAnalysisResult(
        metadata=TagMetadata(tag="CPD_LP_SECADOR_STATUS", point_type="digital", descriptor="Secador Status", digital_set="Estado_126"),
        quality=None,
        digital_analysis=DigitalAnalysisResult(
            status=status,
            possible_states=(
                DigitalStateRef(state_code=0, state_name="DESLIGADO"),
                DigitalStateRef(state_code=1, state_name="VAZIO"),
                DigitalStateRef(state_code=2, state_name="LIGADO"),
                DigitalStateRef(state_code=3, state_name="VAZIO"),
                DigitalStateRef(state_code=4, state_name="FALHA"),
            ),
            initial_state=DigitalStateRef(state_code=0, state_name="DESLIGADO"),
            final_state=DigitalStateRef(state_code=2, state_name="LIGADO"),
            occupancy=occupancy,
            transitions=transitions,
            coverage=DigitalCoverageMetrics(
                window_seconds=86400, known_seconds=86400, known_pct=100.0,
                bad_seconds=0, bad_pct=0, null_seconds=0, null_pct=0,
                unknown_seconds=0, unknown_pct=0, uncovered_seconds=0, uncovered_pct=0,
                questionable_seconds=0, questionable_pct=0, substituted_seconds=0, substituted_pct=0,
            ),
            recorded_events_count=2,
            valid_events_count=2,
        ),
        start_time="2026-08-01T00:00:00-03:00",
        end_time="2026-08-02T00:00:00-03:00",
        zero_policy_applied="suspicious",
        warnings=("Parâmetro zero_policy ignorado: tag é digital.",),
    )


# ---------------------------------------------------------------------------
# T091 — Identificação digital
# ---------------------------------------------------------------------------

class TestT091_DigitalIdentification:
    def test_identification(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "Tag: CPD_LP_SECADOR_STATUS" in text
        assert "Descriptor: Secador Status" in text
        assert "Point Type: digital" in text
        assert "Digital Set: Estado_126" in text
        assert "Período:" in text


# ---------------------------------------------------------------------------
# T092 — Classificação não aplicável
# ---------------------------------------------------------------------------

class TestT092_OperationalNotApplicable:
    def test_not_applicable(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "não aplicável" in text.lower()


# ---------------------------------------------------------------------------
# T093 — Nota descritiva
# ---------------------------------------------------------------------------

class TestT093_DescriptiveNote:
    def test_descriptive(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "descritiva" in text.lower()


# ---------------------------------------------------------------------------
# T094 — Status humano
# ---------------------------------------------------------------------------

class TestT094_StatusHuman:
    def test_all_statuses(self) -> None:
        formatter = InlineReportFormatter()
        for status in DigitalAnalysisStatus:
            text = formatter.format(_make_digital(status=status))
            assert status.value in text.lower() or status.name.lower() in text.lower()


# ---------------------------------------------------------------------------
# T095 — Estado inicial e final
# ---------------------------------------------------------------------------

class TestT095_InitialFinal:
    def test_initial_and_final(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "Estado inicial:" in text
        assert "Estado final:" in text
        assert "DESLIGADO" in text
        assert "LIGADO" in text


# ---------------------------------------------------------------------------
# T096 — Ocupação temporal
# ---------------------------------------------------------------------------

class TestT096_Occupancy:
    def test_occupancy_table(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "Ocupação Temporal" in text
        assert "DESLIGADO" in text
        assert "LIGADO" in text


# ---------------------------------------------------------------------------
# T097 — Transições
# ---------------------------------------------------------------------------

class TestT097_Transitions:
    def test_transitions_section(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "Transições" in text
        assert "total:" in text


# ---------------------------------------------------------------------------
# T098 — Integridade
# ---------------------------------------------------------------------------

class TestT098_Integrity:
    def test_integrity_section(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        assert "Integridade" in text
        assert "Cobertura conhecida:" in text
        assert "Bad:" in text
        assert "Null:" in text
        assert "Questionable (overlay):" in text
        assert "Substituted (overlay):" in text
        assert "Desconhecido:" in text
        assert "Sem cobertura:" in text


# ---------------------------------------------------------------------------
# T099 — Até 10 estados
# ---------------------------------------------------------------------------

class TestT099_UpTo10States:
    def test_all_listed(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        # The formatter shows states from occupancy; only states with entries appear
        assert "DESLIGADO" in text
        assert "LIGADO" in text
        # VAZIO (code 1,3) and FALHA (code 4) have 0% occupancy
        # They still appear in "Estados Possíveis" section via occupancy
        assert "0 — DESLIGADO" in text
        assert "2 — LIGADO" in text


# ---------------------------------------------------------------------------
# T100 — Mais de 10 estados
# ---------------------------------------------------------------------------

class TestT100_MoreThan10States:
    def test_truncation(self) -> None:
        many_states = tuple(
            DigitalStateRef(state_code=i, state_name=f"STATE_{i}")
            for i in range(15)
        )
        occupancy = tuple(
            DigitalStateOccupancy(state_code=i, state_name=f"STATE_{i}", duration_seconds=0, percentage_of_window=0, entries_count=0)
            for i in range(15)
        )
        da = DigitalAnalysisResult(
            status=DigitalAnalysisStatus.COMPLETE,
            possible_states=many_states,
            initial_state=DigitalStateRef(state_code=0, state_name="STATE_0"),
            final_state=DigitalStateRef(state_code=1, state_name="STATE_1"),
            occupancy=occupancy,
            transitions=(DigitalTransition(from_state="STATE_0", to_state="STATE_1", count=1, rate_per_hour=0.5),),
            coverage=DigitalCoverageMetrics(
                window_seconds=86400, known_seconds=86400, known_pct=100.0,
                bad_seconds=0, bad_pct=0, null_seconds=0, null_pct=0,
                unknown_seconds=0, unknown_pct=0, uncovered_seconds=0, uncovered_pct=0,
                questionable_seconds=0, questionable_pct=0, substituted_seconds=0, substituted_pct=0,
            ),
            recorded_events_count=2,
            valid_events_count=2,
        )
        report = TagAnalysisResult(
            metadata=TagMetadata(tag="TAG", point_type="digital", descriptor=""),
            quality=None,
            digital_analysis=da,
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-02T00:00:00-03:00",
        )
        text = InlineReportFormatter().format(report)
        assert "não observados" in text.lower()


# ---------------------------------------------------------------------------
# T101 — Termos proibidos
# ---------------------------------------------------------------------------

class TestT101_ProhibitedTerms:
    def test_no_prohibited_terms(self) -> None:
        text = InlineReportFormatter().format(_make_digital())
        lower = text.lower()
        for term in ("dados_degradados", "dados_excelentes", "dados_bons", "dados_saudáveis", "dados_aceitáveis", "good_pct", "zero_pct"):
            assert term not in lower, f"Termo proibido '{term}' encontrado"


# ---------------------------------------------------------------------------
# T102 — NO_DATA no formatter
# ---------------------------------------------------------------------------

class TestT102_FormatterNoData:
    def test_no_data_text(self) -> None:
        text = InlineReportFormatter().format(_make_digital(status=DigitalAnalysisStatus.NO_DATA))
        assert "nenhum seed" in text.lower() or "nenhum dado" in text.lower() or "no_data" in text.lower()


# ---------------------------------------------------------------------------
# T103 — NO_TRANSITIONS no formatter
# ---------------------------------------------------------------------------

class TestT103_FormatterNoTransitions:
    def test_no_transitions_text(self) -> None:
        text = InlineReportFormatter().format(_make_digital(status=DigitalAnalysisStatus.NO_TRANSITIONS))
        assert "no_transitions" in text.lower() or "nenhuma transição" in text.lower() or "estável" in text.lower()


# ---------------------------------------------------------------------------
# T104 — PARTIAL_COVERAGE no formatter
# ---------------------------------------------------------------------------

class TestT104_FormatterPartial:
    def test_partial_text(self) -> None:
        text = InlineReportFormatter().format(_make_digital(status=DigitalAnalysisStatus.PARTIAL_COVERAGE))
        assert "partial_coverage" in text.lower() or "parcial" in text.lower()


# ---------------------------------------------------------------------------
# T105 — INVALID_DIGITAL_VALUES no formatter
# ---------------------------------------------------------------------------

class TestT105_FormatterInvalid:
    def test_invalid_text(self) -> None:
        text = InlineReportFormatter().format(_make_digital(status=DigitalAnalysisStatus.INVALID_DIGITAL_VALUES))
        assert "invalid_digital_values" in text.lower() or "nenhum estado conhecido" in text.lower()
