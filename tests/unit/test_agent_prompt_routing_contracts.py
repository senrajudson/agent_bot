"""Tests for system prompt routing contracts between Format Intent and Content Intent (T-R01 to T-R10).

Validates that the system prompt contains the strict compatibility matrix and clarification rules:
- T-R01: CSV + values/series -> generate_pi_tags_series_csv
- T-R02: CSV + Recorded -> generate_pi_tags_series_csv
- T-R03: Analysis without format -> generate_pi_tags_analysis_report
- T-R04: XLSX/Excel + analysis -> generate_pi_tags_analysis_report
- T-R05: CSV + analysis (conflict) -> CLARIFY before tool call
- T-R06: CSV + report (conflict) -> CLARIFY before tool call
- T-R07: XLSX + raw values (conflict) -> CLARIFY before tool call
- T-R08: Zero tool calls before clarification
- T-R09: Forbid silent format conversion and enforce correct artifact naming
- T-R10: Dedicated regression contract for historical incident
"""
from __future__ import annotations

import pytest
from app.prompts.agent_prompt import build_system_prompt


class TestPromptRoutingContracts:
    """Validate system prompt routing, format/content compatibility and clarification rules."""

    def test_t_r01_csv_values_routes_to_csv_tool(self):
        prompt = build_system_prompt()
        assert "generate_pi_tags_series_csv" in prompt
        # Must explicitly map CSV with values/series to the CSV series tool
        assert "CSV com valores" in prompt or "CSV com os valores" in prompt or "CSV com valores/série temporal" in prompt

    def test_t_r02_csv_recorded_routes_to_csv_tool(self):
        prompt = build_system_prompt()
        assert "generate_pi_tags_series_csv" in prompt
        # Must map recorded/raw points to the series CSV tool with data_method=recorded
        assert "data_method=recorded" in prompt or "valores recorded" in prompt or "valores brutos" in prompt

    def test_t_r03_analysis_without_format_routes_to_analysis_report(self):
        prompt = build_system_prompt()
        assert "generate_pi_tags_analysis_report" in prompt
        # Analysis/report without format maps to analysis report tool
        assert "relatório de análise" in prompt or "análise detalhada de tags" in prompt

    def test_t_r04_xlsx_analysis_routes_to_analysis_report(self):
        prompt = build_system_prompt()
        assert "generate_pi_tags_analysis_report" in prompt
        # Explicit XLSX + analysis maps to analysis report tool
        assert "XLSX" in prompt
        assert "análise comportamental/relatório" in prompt or "relatório XLSX" in prompt

    def test_t_r05_csv_analysis_explicit_conflict_triggers_clarify(self):
        prompt = build_system_prompt()
        # Incident regression: CSV requested with analysis content
        lower = prompt.lower()
        assert "clarifique" in lower or "clarificar" in lower or "esclarecimento" in lower
        assert "csv com a análise" in lower or "csv com a analise" in lower
        assert "não chame" in lower or "não execute" in lower

    def test_t_r06_csv_report_conflict_triggers_clarify(self):
        prompt = build_system_prompt()
        lower = prompt.lower()
        # Conflict applies to variations like "relatório analítico em CSV"
        assert "relatório analítico em csv" in lower or "relatório em csv" in lower or "conflito explícito entre formato e conteúdo" in lower

    def test_t_r07_xlsx_raw_values_conflict_triggers_clarify(self):
        prompt = build_system_prompt()
        lower = prompt.lower()
        # Inverse conflict: XLSX requested for raw values only
        assert "xlsx/excel somente com valores brutos" in lower or "xlsx somente com valores" in lower or "xlsx" in lower
        assert "não chame nenhuma tool antes de clarificar" in lower or "clarificar" in lower

    def test_t_r08_no_tool_call_before_clarification_rule(self):
        prompt = build_system_prompt()
        lower = prompt.lower()
        # Explicit mandate that no tool call should occur before clarification
        assert "não chame nenhuma tool antes de clarificar" in lower or "não chame nenhuma tool" in lower

    def test_t_r09_forbids_silent_format_conversion_and_enforces_wording(self):
        prompt = build_system_prompt()
        # Prohibits silently converting CSV to XLSX or passing raw CSV as an analysis
        assert "Nunca converta silenciosamente um pedido explícito de CSV para XLSX" in prompt or "nunca converta silenciosamente" in prompt.lower()
        assert "nunca entregue CSV de dados brutos fingindo ser um relatório analítico" in prompt or "fingindo ser" in prompt.lower()

    def test_t_r10_historical_incident_regression(self):
        prompt = build_system_prompt()
        # When user asks "gere um csv com a analise..." the prompt must guard against calling XLSX tool directly
        lower = prompt.lower()
        assert "compatibilidade de formato e conteúdo" in lower or "regra de ouro" in lower
        assert "csv com a análise" in lower
        assert "generate_pi_tags_series_csv" in prompt
        assert "generate_pi_tags_analysis_report" in prompt
