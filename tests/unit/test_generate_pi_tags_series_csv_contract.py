"""Testes de contrato da nova tool generate_pi_tags_series_csv."""

from __future__ import annotations

import pytest

from domain.pims.services.generate_pi_tags_series_csv_service import (
    validate_series_csv_contract,
)
from domain.shared.errors import DomainValidationError, ValidationErrorCode


class TestContractValidation:
    def test_one_tag_accepted(self) -> None:
        tags, _, _, method, interval, _ = validate_series_csv_contract(
            ["LFS_RB2_TAG"], "*-1h", "*", "interpolated", None,
        )
        assert len(tags) == 1
        assert tags == ["LFS_RB2_TAG"]
        assert method == "interpolated"
        assert interval == "1m"

    def test_ten_tags_accepted(self) -> None:
        tags_list = [f"TAG_{i}" for i in range(10)]
        tags, _, _, _, _, _ = validate_series_csv_contract(
            tags_list, "*-1h", "*", "interpolated", "5m",
        )
        assert len(tags) == 10

    def test_zero_tags_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract([], "*-1h", "*", "interpolated", None)
        assert exc.value.code == ValidationErrorCode.INVALID_ARGUMENT_COMBINATION

    def test_eleven_tags_rejected(self) -> None:
        tags_list = [f"TAG_{i}" for i in range(11)]
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract(tags_list, "*-1h", "*", "interpolated", None)
        assert exc.value.code == ValidationErrorCode.INVALID_ARGUMENT_COMBINATION

    def test_empty_tag_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract(
                ["TAG_A", "", "TAG_B"], "*-1h", "*", "interpolated", None,
            )
        assert exc.value.code == ValidationErrorCode.INVALID_ARGUMENT_COMBINATION

    def test_duplicates_removed_preserving_order(self) -> None:
        tags, _, _, _, _, _ = validate_series_csv_contract(
            ["TAG_B", "TAG_A", "TAG_B", "TAG_C", "TAG_A"],
            "*-1h", "*", "interpolated", None,
        )
        assert tags == ["TAG_B", "TAG_A", "TAG_C"]

    def test_interpolated_without_interval_defaults_to_1m(self) -> None:
        _, _, _, _, interval, _ = validate_series_csv_contract(
            ["TAG_A"], "*-1h", "*", "interpolated", None,
        )
        assert interval == "1m"

    def test_interpolated_with_interval_accepted(self) -> None:
        _, _, _, _, interval, _ = validate_series_csv_contract(
            ["TAG_A"], "*-1h", "*", "interpolated", "5m",
        )
        assert interval == "5m"

    def test_recorded_without_interval_accepted(self) -> None:
        _, _, _, method, interval, _ = validate_series_csv_contract(
            ["TAG_A"], "*-1h", "*", "recorded", None,
        )
        assert method == "recorded"
        assert interval is None

    def test_recorded_with_interval_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "recorded", "1m",
            )
        assert exc.value.code == ValidationErrorCode.INTERVAL_NOT_ALLOWED

    def test_data_method_summary_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "summary", None,
            )
        assert exc.value.code == ValidationErrorCode.INVALID_DATA_METHOD

    def test_data_method_calculated_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "calculated", None,
            )

    def test_data_method_aggregate_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "aggregate", None,
            )

    def test_invalid_interval_0m_rejected(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "interpolated", "0m",
            )
        assert exc.value.code == ValidationErrorCode.INVALID_INTERVAL

    def test_invalid_interval_1_5m_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "interpolated", "1.5m",
            )

    def test_invalid_interval_pt1m_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "interpolated", "PT1M",
            )

    def test_invalid_interval_1mo_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            validate_series_csv_contract(
                ["TAG_A"], "*-1h", "*", "interpolated", "1mo",
            )

    def test_interval_1s_accepted(self) -> None:
        _, _, _, _, interval, _ = validate_series_csv_contract(
            ["TAG_A"], "*-1h", "*", "interpolated", "1s",
        )
        assert interval == "1s"

    def test_interval_2d_accepted(self) -> None:
        _, _, _, _, interval, _ = validate_series_csv_contract(
            ["TAG_A"], "*-1h", "*", "interpolated", "2d",
        )
        assert interval == "2d"

    def test_estimated_rows_1M_accepted(self) -> None:
        # 1 tag, 1h window (3600s), interval=1s → 3600 linhas, bem abaixo do limite
        _, _, _, _, _, estimated = validate_series_csv_contract(
            ["TAG_A"], "*-1h", "*", "interpolated", "1m",
        )
        assert estimated == 60

    def test_estimated_rows_exceeds_limit(self) -> None:
        # 30 dias (2.592.000s) com interval=1s: 2.592.000 linhas > 1.000.000
        # Usamos 30 dias porque ainda está dentro do limite de 31 dias
        with pytest.raises(DomainValidationError) as exc:
            validate_series_csv_contract(
                ["TAG_A"], "*-30d", "*", "interpolated", "1s",
            )
        assert exc.value.code == ValidationErrorCode.ESTIMATED_ROW_LIMIT_EXCEEDED
