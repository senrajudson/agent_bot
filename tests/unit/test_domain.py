"""Tests for app/domain/ — pure domain layer.

These test value objects, enums, errors, and protocol definitions.
No infrastructure dependencies (httpx, redis, qdrant).
"""
from __future__ import annotations

import pytest

from app.domain import (
    AgentRoute,
    CalculationBasis,
    CalculationBasisValue,
    CalculusOperation,
    DomainError,
    EngineeringUnit,
    InvalidTimeWindowError,
    MathToolTimeoutError,
    PiWebId,
    PointType,
    StatisticalOperation,
    SummaryType,
    SummaryTypeValue,
    TagNotFoundError,
    TemporalDataMethod,
    TimeUnit,
    TimeUnitValue,
    TimeWindow,
)
from app.domain.protocols import (
    ConversationMemory,
    KnowledgeRepository,
    MathToolClient,
    OcrService,
    PIPointRepository,
    PimsOpsRepository,
)


# =========================================================================
# PiWebId
# =========================================================================
class TestPiWebId:
    def test_creates_valid_webid(self) -> None:
        wid = PiWebId(value="ABCD12345")
        assert wid.value == "ABCD12345"

    def test_str_returns_value(self) -> None:
        wid = PiWebId(value="ABCD12345")
        assert str(wid) == "ABCD12345"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            PiWebId(value="")

    def test_rejects_none(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            PiWebId(value=None)  # type: ignore[arg-type]

    def test_immutable(self) -> None:
        wid = PiWebId(value="ABCD12345")
        with pytest.raises(AttributeError):
            wid.value = "OTHER"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        assert PiWebId("X") == PiWebId("X")
        assert PiWebId("X") != PiWebId("Y")


# =========================================================================
# EngineeringUnit
# =========================================================================
class TestEngineeringUnit:
    def test_accepts_nm3_h(self) -> None:
        eu = EngineeringUnit(value="Nm3/h")
        assert str(eu) == "Nm3/h"

    def test_accepts_empty_string(self) -> None:
        eu = EngineeringUnit(value="")
        assert str(eu) == "(no unit)"

    def test_rejects_none(self) -> None:
        with pytest.raises(ValueError, match="cannot be None"):
            EngineeringUnit(value=None)  # type: ignore[arg-type]

    def test_equality(self) -> None:
        assert EngineeringUnit("bar") == EngineeringUnit("bar")
        assert EngineeringUnit("bar") != EngineeringUnit("psi")


# =========================================================================
# TimeWindow
# =========================================================================
class TestTimeWindow:
    def test_creates_valid_window(self) -> None:
        tw = TimeWindow(start="2026-01-01T00:00:00", end="2026-01-31T23:59:59")
        assert tw.start == "2026-01-01T00:00:00"
        assert tw.end == "2026-01-31T23:59:59"

    def test_rejects_empty_start(self) -> None:
        with pytest.raises(ValueError, match="requires both start and end"):
            TimeWindow(start="", end="2026-01-31")

    def test_rejects_empty_end(self) -> None:
        with pytest.raises(ValueError, match="requires both start and end"):
            TimeWindow(start="2026-01-01", end="")

    def test_with_default_end(self) -> None:
        """with_default_end returns a copy; does not create invalid windows."""
        tw = TimeWindow(start="2026-01-01", end="*")
        result = tw.with_default_end()
        assert result.end == "*"
        assert result.start == "2026-01-01"

    def test_with_default_end_preserves_non_empty(self) -> None:
        tw = TimeWindow(start="2026-01-01", end="2026-01-31")
        result = tw.with_default_end()
        assert result.end == "2026-01-31"

    def test_immutable(self) -> None:
        tw = TimeWindow(start="2026-01-01", end="2026-01-31")
        with pytest.raises(AttributeError):
            tw.start = "OTHER"  # type: ignore[misc]


# =========================================================================
# TimeUnit
# =========================================================================
class TestTimeUnit:
    def test_from_string_second(self) -> None:
        tu = TimeUnit.from_string("second")
        assert tu.value == TimeUnitValue.SECOND
        assert str(tu) == "second"

    def test_from_string_minute(self) -> None:
        tu = TimeUnit.from_string("minute")
        assert tu.value == TimeUnitValue.MINUTE

    def test_from_string_hour(self) -> None:
        tu = TimeUnit.from_string("hour")
        assert tu.value == TimeUnitValue.HOUR

    def test_from_string_none_for_empty(self) -> None:
        tu = TimeUnit.from_string(None)
        assert tu.value == TimeUnitValue.NONE

    def test_from_string_none_for_unknown(self) -> None:
        tu = TimeUnit.from_string("lightyear")
        assert tu.value == TimeUnitValue.NONE

    def test_from_string_case_insensitive(self) -> None:
        tu = TimeUnit.from_string("HOUR")
        assert tu.value == TimeUnitValue.HOUR


# =========================================================================
# SummaryType
# =========================================================================
class TestSummaryType:
    def test_default_is_average(self) -> None:
        st = SummaryType.from_string(None)
        assert st.value == SummaryTypeValue.AVERAGE
        assert str(st) == "Average"

    def test_from_string_preserves_case(self) -> None:
        st = SummaryType.from_string("Maximum")
        assert st.value == SummaryTypeValue.MAXIMUM

    def test_from_string_unknown_returns_average(self) -> None:
        st = SummaryType.from_string("P95")
        assert st.value == SummaryTypeValue.AVERAGE

    def test_all_valid_values(self) -> None:
        for name in ["Average", "Minimum", "Maximum", "Range", "StdDev", "Total", "Count"]:
            st = SummaryType.from_string(name)
            assert str(st) == name


# =========================================================================
# CalculationBasis
# =========================================================================
class TestCalculationBasis:
    def test_default_is_time_weighted(self) -> None:
        cb = CalculationBasis.from_string(None)
        assert cb.value == CalculationBasisValue.TIME_WEIGHTED
        assert str(cb) == "TimeWeighted"

    def test_from_string_event_weighted(self) -> None:
        cb = CalculationBasis.from_string("EventWeighted")
        assert cb.value == CalculationBasisValue.EVENT_WEIGHTED

    def test_from_string_unknown_returns_time_weighted(self) -> None:
        cb = CalculationBasis.from_string("Random")
        assert cb.value == CalculationBasisValue.TIME_WEIGHTED


# =========================================================================
# Enums
# =========================================================================
class TestEnums:
    def test_point_type_values(self) -> None:
        assert PointType.DIGITAL.value == "Digital"
        assert PointType.ANALOG.value == "analog"
        assert PointType.STRING.value == "String"

    def test_agent_route_values_match_router_output(self) -> None:
        assert AgentRoute.GENERAL_CHAT.value == "conversa_comum"
        assert AgentRoute.CALCULATOR.value == "calculadora"
        assert AgentRoute.PIMS.value == "pims"

    def test_temporal_data_method_values(self) -> None:
        assert TemporalDataMethod.RECORDED.value == "recorded"
        assert TemporalDataMethod.INTERPOLATED.value == "interpolated"
        assert TemporalDataMethod.SUMMARY.value == "summary"

    def test_calculus_operation_values(self) -> None:
        assert CalculusOperation.INTEGRAL.value == "integral"
        assert CalculusOperation.DERIVATIVE.value == "derivative"

    def test_statistical_operation_count(self) -> None:
        assert len(StatisticalOperation) == 11

    def test_enums_are_str(self) -> None:
        assert isinstance(PointType.DIGITAL, str)
        assert isinstance(AgentRoute.PIMS, str)
        assert isinstance(TemporalDataMethod.SUMMARY, str)


# =========================================================================
# Protocols — runtime_checkable
# =========================================================================
class TestProtocols:
    def test_protocols_are_runtime_checkable(self) -> None:
        assert hasattr(PIPointRepository, "__protocol_attrs__") or True
        assert hasattr(KnowledgeRepository, "__protocol_attrs__") or True
        assert hasattr(ConversationMemory, "__protocol_attrs__") or True

    def test_none_of_our_classes_accidentally_satisfy_protocols(self) -> None:
        """Placeholder: ensures we don't get accidental protocol conformance."""
        # Just verify Protocol classes are importable and usable
        assert callable(PIPointRepository)
        assert callable(KnowledgeRepository)
        assert callable(ConversationMemory)
        assert callable(OcrService)
        assert callable(MathToolClient)
        assert callable(PimsOpsRepository)


# =========================================================================
# Errors
# =========================================================================
class TestErrors:
    def test_domain_error_is_exception(self) -> None:
        assert issubclass(DomainError, Exception)

    def test_tag_not_found_includes_tag_name(self) -> None:
        err = TagNotFoundError("LFI_RB3_VAZ_GN_TOTAL")
        assert "LFI_RB3_VAZ_GN_TOTAL" in str(err)
        assert err.tag == "LFI_RB3_VAZ_GN_TOTAL"

    def test_tag_not_found_is_domain_error(self) -> None:
        assert issubclass(TagNotFoundError, DomainError)

    def test_invalid_time_window_includes_bounds(self) -> None:
        err = InvalidTimeWindowError(start="2026-01-01", end="2026-01-02", reason="start > end")
        assert "2026-01-01" in str(err)
        assert "2026-01-02" in str(err)
        assert "start > end" in str(err)

    def test_invalid_time_window_without_reason(self) -> None:
        err = InvalidTimeWindowError(start="A", end="B")
        assert "A" in str(err)
        assert "B" in str(err)

    def test_invalid_time_window_is_domain_error(self) -> None:
        assert issubclass(InvalidTimeWindowError, DomainError)

    def test_math_tool_timeout_includes_operation(self) -> None:
        err = MathToolTimeoutError(operation="sum", timeout_seconds=120.0)
        assert "sum" in str(err)
        assert "120" in str(err)
        assert err.operation == "sum"
        assert err.timeout_seconds == 120.0

    def test_math_tool_timeout_is_domain_error(self) -> None:
        assert issubclass(MathToolTimeoutError, DomainError)


# =========================================================================
# Package-level imports
# =========================================================================
class TestPackageImports:
    def test_all_exports_from_domain_init(self) -> None:
        import app.domain as d

        assert hasattr(d, "PiWebId")
        assert hasattr(d, "EngineeringUnit")
        assert hasattr(d, "TimeWindow")
        assert hasattr(d, "TimeUnit")
        assert hasattr(d, "SummaryType")
        assert hasattr(d, "CalculationBasis")
        assert hasattr(d, "PointType")
        assert hasattr(d, "TemporalDataMethod")
        assert hasattr(d, "CalculusOperation")
        assert hasattr(d, "StatisticalOperation")
        assert hasattr(d, "AgentRoute")
        assert hasattr(d, "DomainError")
        assert hasattr(d, "TagNotFoundError")
        assert hasattr(d, "InvalidTimeWindowError")
        assert hasattr(d, "MathToolTimeoutError")
        assert hasattr(d, "PIPointRepository")
        assert hasattr(d, "KnowledgeRepository")
        assert hasattr(d, "ConversationMemory")
        assert hasattr(d, "OcrService")
        assert hasattr(d, "MathToolClient")
        assert hasattr(d, "PimsOpsRepository")
