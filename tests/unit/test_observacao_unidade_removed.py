"""Verify observacao_unidade has been removed from all math services."""

from pathlib import Path

_PROJECT = Path(__file__).parent.parent.parent

_TARGET_FILES = [
    _PROJECT / "domain/analytics/services/math_tool_service.py",
    _PROJECT / "mcp_server/services/math_tool_service.py",
]


def test_observacao_unidade_not_present():
    for filepath in _TARGET_FILES:
        assert filepath.exists(), f"File not found: {filepath}"
        content = filepath.read_text(encoding="utf-8")
        assert "observacao_unidade" not in content, (
            f"observacao_unidade still present in {filepath}"
        )


def test_unidade_final_inferida_present():
    for filepath in _TARGET_FILES:
        content = filepath.read_text(encoding="utf-8")
        assert "unidade_final_inferida" in content, (
            f"unidade_final_inferida missing in {filepath}"
        )


def test_glosa_interpretativa_present():
    for filepath in _TARGET_FILES:
        content = filepath.read_text(encoding="utf-8")
        assert "glosa_interpretativa" in content, (
            f"glosa_interpretativa missing in {filepath}"
        )
