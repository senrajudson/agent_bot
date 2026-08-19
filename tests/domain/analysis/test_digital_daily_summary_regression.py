from __future__ import annotations

import pytest
from datetime import datetime, timezone
from domain.analysis.models import AnalysisPoint, TagMetadata
from domain.analysis.services._digital import reconstruct_timeline, enrich_digital_result
from domain.core.config import configure_domain_settings
from domain.core.integration_settings import DomainIntegrationSettings


@pytest.fixture(autouse=True)
def setup_domain_settings():
    try:
        configure_domain_settings(DomainIntegrationSettings())
    except RuntimeError:
        pass


def test_digital_daily_summary_regression_7d() -> None:
    """T021: Garante que a análise digital e a sumarização diária para 7 dias funcionam sem AttributeError."""
    states = [
        {"nome": "DESLIGADO", "indice": 0},
        {"nome": "LIGADO", "indice": 1},
    ]
    seed = AnalysisPoint(timestamp="2026-08-12T00:00:00Z", value=0.0, good=True)
    
    # Criar transições ao longo de 7 dias
    recorded = [
        AnalysisPoint(timestamp="2026-08-13T10:00:00Z", value=1.0, good=True),
        AnalysisPoint(timestamp="2026-08-14T14:00:00Z", value=0.0, good=True),
        AnalysisPoint(timestamp="2026-08-16T08:00:00Z", value=1.0, good=True),
        AnalysisPoint(timestamp="2026-08-18T18:00:00Z", value=0.0, good=True),
    ]
    start = "2026-08-12T00:00:00Z"
    end = "2026-08-19T00:00:00Z"
    w_start = datetime.fromisoformat(start).astimezone(timezone.utc)
    w_end = datetime.fromisoformat(end).astimezone(timezone.utc)

    base_res = reconstruct_timeline(w_start, w_end, seed, recorded, states)
    assert base_res.status.value in ("complete", "partial_coverage")

    enriched = enrich_digital_result(base_res, recorded, seed, states, w_start, w_end)
    assert enriched is not None
    assert len(enriched.daily_summary) > 0
    assert enriched.daily_summary[0].date in ("2026-08-11", "2026-08-12")
