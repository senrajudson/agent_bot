from __future__ import annotations

import pytest
from domain.analysis.models import (
    AnalysisCompleteness,
    AnalysisCompletenessMetadata,
    AnalysisError,
    AnalysisRequest,
    LimitStatus,
    TagMetadata,
)
from domain.analysis.services.pi_data_collector import CollectedData
from domain.analysis.services.tag_analysis_service import TagAnalysisService
from domain.core.config import configure_domain_settings
from domain.core.integration_settings import DomainIntegrationSettings


@pytest.fixture(autouse=True)
def setup_domain_settings():
    try:
        configure_domain_settings(DomainIntegrationSettings())
    except RuntimeError:
        pass


def test_multitag_completeness_aggregation() -> None:
    """T032: Testa agregação de completude multitag mista (1 completa, 1 truncada, 1 erro)."""
    service = TagAnalysisService()

    meta_complete = AnalysisCompletenessMetadata(
        requested_start_time="2026-08-12T00:00:00Z",
        requested_end_time="2026-08-19T00:00:00Z",
        effective_start_time="2026-08-12T00:00:00Z",
        effective_end_time="2026-08-19T00:00:00Z",
        returned_point_count=50,
        configured_point_limit=150000,
        pi_request_safe_limit=150000,
        artifact_safe_row_limit=1000000,
        effective_point_limit=150000,
        limit_status=LimitStatus.NOT_REACHED,
        analysis_completeness=AnalysisCompleteness.COMPLETE,
        truncated=False,
    )

    meta_partial = AnalysisCompletenessMetadata(
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
    )

    data1 = CollectedData(metadata=TagMetadata(tag="TAG1", point_type="numeric"), completeness=meta_complete)
    data2 = CollectedData(metadata=TagMetadata(tag="TAG2", point_type="numeric"), completeness=meta_partial)
    err3 = AnalysisError(tag="TAG3", code="TAG_NOT_FOUND", message="Não encontrada")

    collected = {
        "TAG1": data1,
        "TAG2": data2,
        "TAG3": err3,
    }

    request = AnalysisRequest(start_time="2026-08-12T00:00:00Z", end_time="2026-08-19T00:00:00Z")
    res = service.analyze_many(collected, request)

    assert res.total_requested == 3
    assert res.total_processed == 2
    assert len(res.errors) == 1
    assert res.overall_completeness == AnalysisCompleteness.PARTIAL
    assert res.results[0].completeness.analysis_completeness == AnalysisCompleteness.COMPLETE
    assert res.results[1].completeness.analysis_completeness == AnalysisCompleteness.PARTIAL
