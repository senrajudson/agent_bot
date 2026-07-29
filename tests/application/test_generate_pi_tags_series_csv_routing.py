"""Testes de roteamento semântico — valida prompt e QA matrix."""

from __future__ import annotations

from pathlib import Path


_PROMPT_PATH = Path(__file__).parent.parent.parent / "app" / "prompts" / "agent_prompt.py"
_QA_MATRIX_PATH = Path(__file__).parent.parent.parent / "tests" / "qa_routing_matrix.md"


def test_prompt_contains_new_tool() -> None:
    content = _PROMPT_PATH.read_text()
    assert "generate_pi_tags_series_csv" in content
    assert "valores minuto a minuto" in content
    assert "SOMENTE operações estatísticas" in content or "exclusivamente" in content


def test_prompt_has_routing_table() -> None:
    content = _PROMPT_PATH.read_text()
    assert '"valores minuto a minuto"' in content
    assert '"valores brutos"' in content
    assert '"média por minuto"' in content
    assert '"máximo a cada 5 minutos"' in content


def test_prompt_csv_rule_updated() -> None:
    content = _PROMPT_PATH.read_text()
    assert "confirmar a geração de CSV" in content


def test_qa_matrix_has_new_cases() -> None:
    content = _QA_MATRIX_PATH.read_text()
    assert "generate_pi_tags_series_csv" in content
    assert "valores minuto a minuto" in content
    assert "valores brutos" in content


def test_qa_matrix_has_negative_case() -> None:
    content = _QA_MATRIX_PATH.read_text()
    assert "NÃO usar" in content
