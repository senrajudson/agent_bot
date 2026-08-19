from __future__ import annotations

from domain.analysis.models import (
    AnalysisCompleteness,
    AnalysisCompletenessMetadata,
    LimitStatus,
)


def test_completeness_models_mapping_matrix() -> None:
    """T010: Valida a matriz de mapeamento entre LimitStatus, AnalysisCompleteness e truncated."""
    # NOT_REACHED -> COMPLETE, truncated=False
    meta1 = AnalysisCompletenessMetadata(
        requested_start_time="2026-08-12T00:00:00Z",
        requested_end_time="2026-08-19T00:00:00Z",
        effective_start_time="2026-08-12T00:00:00Z",
        effective_end_time="2026-08-19T00:00:00Z",
        returned_point_count=500,
        configured_point_limit=150000,
        pi_request_safe_limit=150000,
        artifact_safe_row_limit=1000000,
        effective_point_limit=150000,
        limit_status=LimitStatus.NOT_REACHED,
        analysis_completeness=AnalysisCompleteness.COMPLETE,
        truncated=False,
    )
    assert meta1.limit_status == LimitStatus.NOT_REACHED
    assert meta1.analysis_completeness == AnalysisCompleteness.COMPLETE
    assert meta1.truncated is False

    # REACHED_EXACT -> COMPLETE, truncated=False
    meta2 = AnalysisCompletenessMetadata(
        requested_start_time="2026-08-12T00:00:00Z",
        requested_end_time="2026-08-19T00:00:00Z",
        effective_start_time="2026-08-12T00:00:00Z",
        effective_end_time="2026-08-19T00:00:00Z",
        returned_point_count=150000,
        configured_point_limit=150000,
        pi_request_safe_limit=150000,
        artifact_safe_row_limit=1000000,
        effective_point_limit=150000,
        limit_status=LimitStatus.REACHED_EXACT,
        analysis_completeness=AnalysisCompleteness.COMPLETE,
        truncated=False,
    )
    assert meta2.limit_status == LimitStatus.REACHED_EXACT
    assert meta2.analysis_completeness == AnalysisCompleteness.COMPLETE
    assert meta2.truncated is False

    # EXCEEDED -> PARTIAL, truncated=True
    meta3 = AnalysisCompletenessMetadata(
        requested_start_time="2026-08-12T00:00:00Z",
        requested_end_time="2026-08-19T00:00:00Z",
        effective_start_time="2026-08-12T00:00:00Z",
        effective_end_time="2026-08-15T12:00:00Z",
        returned_point_count=150000,
        configured_point_limit=150000,
        pi_request_safe_limit=150000,
        artifact_safe_row_limit=1000000,
        effective_point_limit=150000,
        limit_status=LimitStatus.EXCEEDED,
        analysis_completeness=AnalysisCompleteness.PARTIAL,
        truncated=True,
        unprocessed_start_time="2026-08-15T12:00:00Z",
        unprocessed_end_time="2026-08-19T00:00:00Z",
    )
    assert meta3.limit_status == LimitStatus.EXCEEDED
    assert meta3.analysis_completeness == AnalysisCompleteness.PARTIAL
    assert meta3.truncated is True

    # REACHED_UNCONFIRMED -> COMPLETENESS_UNCONFIRMED, truncated=None
    meta4 = AnalysisCompletenessMetadata(
        requested_start_time="2026-08-12T00:00:00Z",
        requested_end_time="2026-08-19T00:00:00Z",
        effective_start_time="2026-08-12T00:00:00Z",
        effective_end_time="2026-08-15T12:00:00Z",
        returned_point_count=150000,
        configured_point_limit=150000,
        pi_request_safe_limit=150000,
        artifact_safe_row_limit=1000000,
        effective_point_limit=150000,
        limit_status=LimitStatus.REACHED_UNCONFIRMED,
        analysis_completeness=AnalysisCompleteness.COMPLETENESS_UNCONFIRMED,
        truncated=None,
    )
    assert meta4.limit_status == LimitStatus.REACHED_UNCONFIRMED
    assert meta4.analysis_completeness == AnalysisCompleteness.COMPLETENESS_UNCONFIRMED
    assert meta4.truncated is None
