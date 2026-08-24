import pytest

from domain.analysis.models import AnalysisRequest, MetricExecutionKind, MetricSource
from domain.analysis.services.analysis_execution_planner import AnalysisExecutionPlanner
from domain.shared.errors import DomainValidationError


def test_planner_all_metrics():
    planner = AnalysisExecutionPlanner()
    req = AnalysisRequest(
        tag="TEST_TAG",
        start_time="2026-01-01T00:00:00-03:00",
        end_time="2026-01-01T01:00:00-03:00",
        analysis_types=("all",),
    )
    plan = planner.create_plan(req)
    assert plan.needs_recorded is True
    assert plan.needs_interpolated is True
    assert plan.needs_local_metrics is True
    assert "Average" in plan.pi_summary_types
    assert "Maximum" in plan.pi_summary_types


def test_planner_specific_summary_metrics():
    planner = AnalysisExecutionPlanner()
    req = AnalysisRequest(
        tag="TEST_TAG",
        start_time="2026-01-01T00:00:00-03:00",
        end_time="2026-01-01T01:00:00-03:00",
        analysis_types=("mean", "max"),
    )
    plan = planner.create_plan(req)
    assert plan.needs_recorded is False
    assert plan.needs_interpolated is False
    assert plan.pi_summary_types == ("Average", "Maximum")
    assert plan.metric_kinds["mean"] == MetricExecutionKind.PI_SUMMARY


def test_planner_local_metrics_only():
    planner = AnalysisExecutionPlanner()
    req = AnalysisRequest(
        tag="TEST_TAG",
        start_time="2026-01-01T00:00:00-03:00",
        end_time="2026-01-01T01:00:00-03:00",
        analysis_types=("median", "p99"),
    )
    plan = planner.create_plan(req)
    assert plan.needs_local_metrics is True
    assert plan.needs_interpolated is True
    assert len(plan.pi_summary_types) == 0


def test_planner_all_combined_with_other_raises():
    planner = AnalysisExecutionPlanner()
    req = AnalysisRequest(
        tag="TEST_TAG",
        start_time="2026-01-01T00:00:00-03:00",
        end_time="2026-01-01T01:00:00-03:00",
        analysis_types=("all", "mean"),
    )
    with pytest.raises(DomainValidationError):
        planner.create_plan(req)
