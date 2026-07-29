from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from domain.shared.errors import DomainValidationError, ValidationErrorCode
from domain.shared.time import resolve_pi_time_range, ResolvedTimeRange


TZ = ZoneInfo("America/Sao_Paulo")
ANCHOR = datetime(2026, 7, 29, 11, 0, 0, tzinfo=TZ)


class TestStar:
    def test_star_equal_raises(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("*", "*", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_WINDOW

    def test_star_1h(self):
        r = resolve_pi_time_range("*-1h", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(hours=1)
        assert r.end == ANCHOR
        assert r.input_kind == "relative"

    def test_star_24h(self):
        r = resolve_pi_time_range("*-24h", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(hours=24)
        assert r.end == ANCHOR

    def test_star_1d(self):
        r = resolve_pi_time_range("*-1d", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(days=1)
        assert r.end == ANCHOR

    def test_star_7d(self):
        r = resolve_pi_time_range("*-7d", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(days=7)
        assert r.end == ANCHOR

    def test_star_1_h_with_space(self):
        r = resolve_pi_time_range("*-1 h", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(hours=1)

    def test_star_3_d_with_space(self):
        r = resolve_pi_time_range("*-3 d", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(days=3)


class TestTandY:
    def test_T(self):
        r = resolve_pi_time_range("T", "*", now=ANCHOR)
        assert r.start == ANCHOR.replace(hour=0, minute=0, second=0, microsecond=0)
        assert r.end == ANCHOR

    def test_T_lowercase(self):
        r = resolve_pi_time_range("t", "*", now=ANCHOR)
        expected = ANCHOR.replace(hour=0, minute=0, second=0, microsecond=0)
        assert r.start == expected

    def test_Y(self):
        r = resolve_pi_time_range("Y", "*", now=ANCHOR)
        expected = (ANCHOR - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        assert r.start == expected

    def test_Y_lowercase(self):
        r = resolve_pi_time_range("y", "*", now=ANCHOR)
        expected = (ANCHOR - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        assert r.start == expected


class TestISO:
    def test_iso_neg_offset(self):
        start = "2026-07-29T10:00:00-03:00"
        end = "2026-07-29T11:00:00-03:00"
        r = resolve_pi_time_range(start, end, now=ANCHOR)
        assert r.start == datetime(2026, 7, 29, 10, 0, 0, tzinfo=TZ)
        assert r.end == datetime(2026, 7, 29, 11, 0, 0, tzinfo=TZ)
        assert r.input_kind == "absolute"

    def test_iso_utc_z(self):
        start = "2026-07-29T13:00:00Z"
        end = "2026-07-29T14:00:00Z"
        r = resolve_pi_time_range(start, end, now=ANCHOR)
        assert r.start == datetime(2026, 7, 29, 10, 0, 0, tzinfo=TZ)
        assert r.end == datetime(2026, 7, 29, 11, 0, 0, tzinfo=TZ)

    def test_iso_preserved_unchanged(self):
        start = "2026-07-29T10:00:00-03:00"
        end = "2026-07-29T11:00:00-03:00"
        r = resolve_pi_time_range(start, end, now=ANCHOR)
        assert r.start_iso == "2026-07-29T10:00:00-03:00"
        assert r.end_iso == "2026-07-29T11:00:00-03:00"


class TestMixed:
    def test_start_relative_end_absolute(self):
        r = resolve_pi_time_range("*-1h", "2026-07-29T11:00:00-03:00", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(hours=1)
        assert r.end == ANCHOR
        assert r.input_kind == "mixed"

    def test_start_absolute_end_relative(self):
        r = resolve_pi_time_range("2026-07-29T10:00:00-03:00", "*", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(hours=1)
        assert r.end == ANCHOR
        assert r.input_kind == "mixed"


class TestInputKind:
    def test_relative_relative(self):
        r = resolve_pi_time_range("*-2h", "*-1h", now=ANCHOR)
        assert r.input_kind == "relative"

    def test_absolute_absolute(self):
        r = resolve_pi_time_range(
            "2026-07-29T09:00:00-03:00", "2026-07-29T11:00:00-03:00", now=ANCHOR
        )
        assert r.input_kind == "absolute"

    def test_mixed(self):
        r = resolve_pi_time_range("*-1h", "2026-07-29T11:00:00-03:00", now=ANCHOR)
        assert r.input_kind == "mixed"


class TestErrors:
    def test_empty_start(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("", "*", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_EXPRESSION

    def test_invalid_expression(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("*-xh", "*", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION

    def test_start_equal_end(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("*", "*", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_WINDOW

    def test_start_after_end(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("*-1h", "*-2h", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_WINDOW

    def test_unsupported_token(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("*+1h", "*", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION

    def test_now_naive(self):
        naive = datetime(2026, 7, 29, 11, 0, 0)
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("*-1h", "*", now=naive)
        assert exc.value.code == ValidationErrorCode.TIME_RESOLUTION_ERROR

    def test_iso_without_offset_naive(self):
        with pytest.raises(DomainValidationError) as exc:
            resolve_pi_time_range("2026-07-29T10:00:00", "2026-07-29T11:00:00-03:00", now=ANCHOR)
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION


class TestDeterminism:
    def test_same_anchor_for_both(self):
        fixed = datetime(2026, 7, 29, 11, 0, 0, tzinfo=TZ)
        r = resolve_pi_time_range("*-1h", "*", now=fixed)
        assert r.start == fixed - timedelta(hours=1)
        assert r.end == fixed

    def test_no_z_on_local(self):
        r = resolve_pi_time_range("*-1h", "*", now=ANCHOR)
        assert not r.start_iso.endswith("Z")
        assert not r.end_iso.endswith("Z")
        assert "-03:00" in r.start_iso or "+" in r.start_iso


class TestProperties:
    def test_window_seconds(self):
        r = resolve_pi_time_range("*-1h", "*", now=ANCHOR)
        assert r.window_seconds == 3600

    def test_window_seconds_large(self):
        r = resolve_pi_time_range("*-24h", "*", now=ANCHOR)
        assert r.window_seconds == 86400

    def test_timezone_default(self):
        r = resolve_pi_time_range("*-1h", "*", now=ANCHOR)
        assert r.timezone == "America/Sao_Paulo"

    def test_timezone_explicit(self):
        r = resolve_pi_time_range(
            "*-1h", "*", now=ANCHOR, timezone="America/Sao_Paulo"
        )
        assert r.timezone == "America/Sao_Paulo"


class TestMixedWindow:
    def test_relative_relative_window(self):
        r = resolve_pi_time_range("*-2h", "*-1h", now=ANCHOR)
        assert r.start == ANCHOR - timedelta(hours=2)
        assert r.end == ANCHOR - timedelta(hours=1)
        assert r.window_seconds == 3600
