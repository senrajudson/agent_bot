"""Testes de Digital Recorded em generate_pi_tags_series_csv_service.

Cobre: happy path, raw dict, scalar digital, code zero, duplicate names,
unknown code, upstream name, set failure, Good=False, NULL, no_data,
500, mixed, warnings vs status, metadata precedence.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from domain.pims.services.generate_pi_tags_series_csv_service import (
    _build_state_map,
    _extract_digital_value,
    _normalize_digital_state_key,
    _resolve_digital_state_name,
    generate_pi_tags_series_csv_service,
)


def _make_pi_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"Items": items}


def _make_digital_point_meta(tag: str = "TEST_DIGITAL") -> dict[str, Any]:
    return {
        "WebId": f"WID_{tag}",
        "Name": tag,
        "PointType": "Digital",
        "DigitalSetName": "TestSet",
        "EngineeringUnits": "",
    }


def _make_numeric_point_meta(tag: str = "TEST_NUMERIC") -> dict[str, Any]:
    return {
        "WebId": f"WID_{tag}",
        "Name": tag,
        "PointType": "Float32",
        "EngineeringUnits": "C",
    }


def _make_digital_item(ts: str, code: int | str, name: str, good: bool = True) -> dict[str, Any]:
    return {
        "Timestamp": ts,
        "Value": {"Value": code, "Name": name},
        "Good": good,
        "Questionable": False,
        "Substituted": False,
        "Annotated": False,
    }


def _make_numeric_item(ts: str, value: float, good: bool = True) -> dict[str, Any]:
    return {
        "Timestamp": ts,
        "Value": value,
        "Good": good,
        "Questionable": False,
        "Substituted": False,
        "Annotated": False,
    }


DIGITAL_SET_STATES = {
    "states": [
        {"indice": 0, "nome": "OFF", "descricao": "Desligado"},
        {"indice": 1, "nome": "ON", "descricao": "Ligado"},
        {"indice": 2, "nome": "FAULT", "descricao": "Falha"},
    ]
}


def _setup_digital_mocks(stack: ExitStack):
    stack.enter_context(patch(
        "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
        new_callable=AsyncMock,
        return_value=_make_digital_point_meta(),
    ))
    stack.enter_context(patch(
        "domain.pims.services.generate_pi_tags_series_csv_service.get_digital_set_states",
        new_callable=AsyncMock,
        return_value=DIGITAL_SET_STATES,
    ))
    stack.enter_context(patch(
        "domain.pims.services.generate_pi_tags_series_csv_service.resolve_digital_set_name",
        return_value=type("R", (), {"name": "TestSet", "is_invalid": False})(),
    ))


class TestNormalizeDigitalStateKey:
    def test_int(self):
        assert _normalize_digital_state_key(0) == 0
        assert _normalize_digital_state_key(7) == 7

    def test_float_int(self):
        assert _normalize_digital_state_key(1.0) == 1
        assert _normalize_digital_state_key(0.0) == 0

    def test_float_non_int(self):
        assert _normalize_digital_state_key(1.5) == 1.5

    def test_str_int(self):
        assert _normalize_digital_state_key("1") == 1
        assert _normalize_digital_state_key("0") == 0

    def test_str_float(self):
        assert _normalize_digital_state_key("1.0") == 1
        assert _normalize_digital_state_key("1.5") == 1.5

    def test_str_alpha(self):
        assert _normalize_digital_state_key("VAZIO") == "VAZIO"

    def test_none(self):
        assert _normalize_digital_state_key(None) is None


class TestBuildStateMap:
    def test_basic(self):
        states = [{"indice": 0, "nome": "OFF"}, {"indice": 1, "nome": "ON"}, {"indice": 2, "nome": "FAULT"}]
        sm = _build_state_map(states)
        assert sm[0]["name"] == "OFF"
        assert sm[1]["name"] == "ON"
        assert sm[2]["name"] == "FAULT"

    def test_duplicate_names(self):
        states = [{"indice": 1, "nome": "VAZIO"}, {"indice": 3, "nome": "VAZIO"}]
        sm = _build_state_map(states)
        assert sm[1]["name"] == "VAZIO"
        assert sm[3]["name"] == "VAZIO"
        assert len(sm) == 2

    def test_code_zero(self):
        states = [{"indice": 0, "nome": "OFF"}]
        sm = _build_state_map(states)
        assert 0 in sm
        assert sm[0]["name"] == "OFF"

    def test_empty(self):
        assert _build_state_map([]) == {}


class TestExtractDigitalValue:
    def test_dict_shape(self):
        code, name = _extract_digital_value({"Value": 1, "Name": "ON"}, "digital")
        assert code == 1
        assert name == "ON"

    def test_scalar_digital(self):
        code, name = _extract_digital_value(1, "digital")
        assert code == 1
        assert name is None

    def test_none_digital(self):
        code, name = _extract_digital_value(None, "digital")
        assert code is None
        assert name is None

    def test_dict_numeric(self):
        code, name = _extract_digital_value({"Value": 42.5, "Name": "Some"}, "numeric")
        assert code == 42.5
        assert name == "Some"

    def test_scalar_numeric(self):
        code, name = _extract_digital_value(42.5, "numeric")
        assert code == 42.5
        assert name is None


class TestResolveDigitalStateName:
    def test_known_code(self):
        sm = {0: {"name": "OFF"}, 1: {"name": "ON"}}
        name, warning = _resolve_digital_state_name(1, sm, None)
        assert name == "ON"
        assert warning is None

    def test_code_zero(self):
        sm = {0: {"name": "OFF"}}
        name, warning = _resolve_digital_state_name(0, sm, None)
        assert name == "OFF"
        assert warning is None

    def test_unknown_with_upstream(self):
        sm = {0: {"name": "OFF"}}
        name, warning = _resolve_digital_state_name(7, sm, "LEGACY")
        assert name == "LEGACY"
        assert warning == "UNKNOWN_DIGITAL_STATE"

    def test_unknown_without_upstream(self):
        sm = {0: {"name": "OFF"}}
        name, warning = _resolve_digital_state_name(7, sm, None)
        assert name == ""
        assert warning == "UNKNOWN_DIGITAL_STATE"

    def test_empty_state_map(self):
        name, warning = _resolve_digital_state_name(1, {}, None)
        assert name == ""
        assert warning == "UNKNOWN_DIGITAL_STATE"


class TestDigitalRecordedHappyPath:
    @pytest.mark.asyncio
    async def test_digital_recorded_success(self):
        pi_response = _make_pi_response([
            _make_digital_item("2026-08-04T08:00:00Z", 0, "OFF"),
            _make_digital_item("2026-08-04T09:00:00Z", 1, "ON"),
            _make_digital_item("2026-08-04T10:00:00Z", 2, "FAULT"),
            _make_digital_item("2026-08-04T11:00:00Z", 1, "ON"),
        ])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock,
                return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        rows = result["rows"]
        assert len(rows) == 4
        for row in rows:
            assert row["value_type"] == "digital"
            assert row["digital_state_code"] is not None
            assert row["digital_state_name"] != ""
        assert [r["digital_state_code"] for r in rows] == [0, 1, 2, 1]

    @pytest.mark.asyncio
    async def test_scalar_digital_metadata_digital(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 1, "ON")])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        rows = result["rows"]
        assert len(rows) == 1
        assert rows[0]["value_type"] == "digital"
        assert rows[0]["digital_state_code"] == 1
        assert rows[0]["digital_state_name"] == "ON"


class TestDigitalCodeZero:
    @pytest.mark.asyncio
    async def test_code_zero_preserved(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 0, "OFF")])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert result["rows"][0]["digital_state_code"] == 0
        assert result["rows"][0]["digital_state_name"] == "OFF"


class TestDigitalDuplicateNames:
    @pytest.mark.asyncio
    async def test_duplicate_names_preserved(self):
        states = {"states": [{"indice": 1, "nome": "VAZIO"}, {"indice": 3, "nome": "VAZIO"}]}
        pi_response = _make_pi_response([
            _make_digital_item("2026-08-04T08:00:00Z", 1, "VAZIO"),
            _make_digital_item("2026-08-04T09:00:00Z", 3, "VAZIO"),
        ])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock, return_value=_make_digital_point_meta(),
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_digital_set_states",
                new_callable=AsyncMock, return_value=states,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.resolve_digital_set_name",
                return_value=type("R", (), {"name": "DupSet", "is_invalid": False})(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        rows = result["rows"]
        assert len(rows) == 2
        assert rows[0]["digital_state_code"] == 1
        assert rows[1]["digital_state_code"] == 3


class TestDigitalUnknownCode:
    @pytest.mark.asyncio
    async def test_unknown_code_with_warning(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 7, "UNKNOWN")])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert result["rows"][0]["digital_state_code"] == 7
        warnings = result.get("warnings", [])
        assert len([w for w in warnings if w["code"] == "UNKNOWN_DIGITAL_STATE"]) == 1

    @pytest.mark.asyncio
    async def test_unknown_code_without_upstream_name(self):
        pi_response = _make_pi_response([{
            "Timestamp": "2026-08-04T08:00:00Z", "Value": 7, "Good": True,
            "Questionable": False, "Substituted": False, "Annotated": False,
        }])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert result["rows"][0]["digital_state_code"] == 7
        assert result["rows"][0]["digital_state_name"] == ""

    @pytest.mark.asyncio
    async def test_unknown_code_dedup(self):
        items = [_make_digital_item(f"2026-08-04T0{i}:00:00Z", 7, "UNKNOWN") for i in range(5)]
        pi_response = _make_pi_response(items)
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        warnings = result.get("warnings", [])
        assert len([w for w in warnings if w["code"] == "UNKNOWN_DIGITAL_STATE"]) == 1


class TestDigitalSetFailure:
    @pytest.mark.asyncio
    async def test_set_failure_preserves_rows(self):
        pi_response = _make_pi_response([
            _make_digital_item("2026-08-04T08:00:00Z", 1, "ON"),
            _make_digital_item("2026-08-04T09:00:00Z", 0, "OFF"),
        ])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock, return_value=_make_digital_point_meta(),
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_digital_set_states",
                new_callable=AsyncMock, side_effect=Exception("Connection refused"),
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.resolve_digital_set_name",
                return_value=type("R", (), {"name": "TestSet", "is_invalid": False})(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert len(result["rows"]) == 2
        warnings = result.get("warnings", [])
        assert len([w for w in warnings if w["code"] == "DIGITAL_STATE_RESOLUTION_FAILED"]) == 1
        assert len(result.get("errors_summary", [])) == 0


class TestDigitalGoodFalse:
    @pytest.mark.asyncio
    async def test_good_false_preserves_code_name(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 1, "ON", good=False)])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        row = result["rows"][0]
        assert row["value"] is None
        assert row["good"] is False
        assert row["digital_state_code"] == 1
        assert row["digital_state_name"] == "ON"


class TestDigitalNull:
    @pytest.mark.asyncio
    async def test_null_value_preserves_row(self):
        pi_response = _make_pi_response([{
            "Timestamp": "2026-08-04T08:00:00Z", "Value": None, "Good": True,
            "Questionable": False, "Substituted": False, "Annotated": False,
        }])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert result["rows"][0]["value"] is None


class TestDigitalNoData:
    @pytest.mark.asyncio
    async def test_no_data_returns_tag_no_data(self):
        pi_response = _make_pi_response([])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock, return_value=_make_digital_point_meta(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "no_data"
        assert len([w for w in result.get("warnings", []) if w["code"] == "TAG_NO_DATA"]) == 1


class TestDigital500:
    @pytest.mark.asyncio
    async def test_500_returns_error_not_no_data(self):
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, side_effect=Exception("PI Web API error: HTTP 500"),
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock, return_value=_make_digital_point_meta(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "all_failed"
        assert len(result.get("errors_summary", [])) == 1
        assert "PI Web API error" in result["errors_summary"][0]["error"]


class TestMixedNumericDigital:
    @pytest.mark.asyncio
    async def test_mixed_success(self):
        digital_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 1, "ON")])
        numeric_response = _make_pi_response([_make_numeric_item("2026-08-04T08:00:00Z", 42.5)])

        async def mock_get_recorded(tag, **kwargs):
            return digital_response if tag == "DIGITAL_TAG" else numeric_response

        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                side_effect=mock_get_recorded,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock,
                side_effect=lambda tag: _make_digital_point_meta() if tag == "DIGITAL_TAG" else _make_numeric_point_meta(),
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_digital_set_states",
                new_callable=AsyncMock, return_value=DIGITAL_SET_STATES,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.resolve_digital_set_name",
                return_value=type("R", (), {"name": "TestSet", "is_invalid": False})(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["NUMERIC_TAG", "DIGITAL_TAG"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert len(result["rows"]) == 2
        assert len([r for r in result["rows"] if r["value_type"] == "digital"]) == 1
        assert len([r for r in result["rows"] if r["value_type"] == "numeric"]) == 1

    @pytest.mark.asyncio
    async def test_mixed_partial(self):
        numeric_response = _make_pi_response([_make_numeric_item("2026-08-04T08:00:00Z", 42.5)])

        async def mock_get_recorded(tag, **kwargs):
            if tag == "DIGITAL_TAG":
                raise Exception("PI Web API error: HTTP 500")
            return numeric_response

        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                side_effect=mock_get_recorded,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock,
                side_effect=lambda tag: _make_digital_point_meta() if tag == "DIGITAL_TAG" else _make_numeric_point_meta(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["NUMERIC_TAG", "DIGITAL_TAG"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "partial_success"
        assert len(result["rows"]) == 1
        assert len(result.get("errors_summary", [])) == 1
        assert result["errors_summary"][0]["tag"] == "DIGITAL_TAG"


class TestWarningsStatus:
    @pytest.mark.asyncio
    async def test_warnings_do_not_change_success(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 7, "UNKNOWN")])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert len(result.get("warnings", [])) > 0


class TestMetadataPrecedence:
    @pytest.mark.asyncio
    async def test_metadata_digital_overrides_scalar_value(self):
        pi_response = _make_pi_response([{
            "Timestamp": "2026-08-04T08:00:00Z", "Value": 1, "Good": True,
            "Questionable": False, "Substituted": False, "Annotated": False,
        }])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        row = result["rows"][0]
        assert row["value_type"] == "digital"
        assert row["digital_state_code"] == 1

    @pytest.mark.asyncio
    async def test_suffix_status_does_not_make_digital(self):
        pi_response = _make_pi_response([{
            "Timestamp": "2026-08-04T08:00:00Z", "Value": 42.5, "Good": True,
            "Questionable": False, "Substituted": False, "Annotated": False,
        }])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock, return_value=_make_numeric_point_meta("ABC_STATUS"),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["ABC_STATUS"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert result["rows"][0]["value_type"] == "numeric"

    @pytest.mark.asyncio
    async def test_name_without_suffix_is_digital(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 1, "ON")])
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, return_value=pi_response,
            ))
            _setup_digital_mocks(stack)
            result = await generate_pi_tags_series_csv_service(
                tags=["TEMPERATURA"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "success"
        assert result["rows"][0]["value_type"] == "digital"


class TestNoSecondRecordedRequest:
    @pytest.mark.asyncio
    async def test_single_recorded_call_per_tag(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 1, "ON")])
        call_args = []

        async def mock_get_recorded(tag, **kwargs):
            call_args.append((tag, kwargs))
            return pi_response

        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                side_effect=mock_get_recorded,
            ))
            _setup_digital_mocks(stack)
            await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert len(call_args) == 1
        assert call_args[0][0] == "TEST_DIGITAL"


class TestMaxCountSentinel:
    @pytest.mark.asyncio
    async def test_max_count_propagated(self):
        pi_response = _make_pi_response([_make_digital_item("2026-08-04T08:00:00Z", 1, "ON")])
        call_kwargs = {}

        async def mock_get_recorded(tag, **kwargs):
            call_kwargs.update(kwargs)
            return pi_response

        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                side_effect=mock_get_recorded,
            ))
            _setup_digital_mocks(stack)
            await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*",
                data_method="recorded", recorded_max_count=12345,
            )
        assert call_kwargs.get("max_count") == 12345


class TestErrorTruncation:
    @pytest.mark.asyncio
    async def test_error_message_not_truncated_to_300(self):
        long_error = "x" * 400
        with ExitStack() as stack:
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
                new_callable=AsyncMock, side_effect=Exception(long_error),
            ))
            stack.enter_context(patch(
                "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
                new_callable=AsyncMock, return_value=_make_digital_point_meta(),
            ))
            result = await generate_pi_tags_series_csv_service(
                tags=["TEST_DIGITAL"], start_time="*-1h", end_time="*", data_method="recorded",
            )
        assert result["status"] == "all_failed"
        assert len(result["errors_summary"][0]["error"]) == 400
