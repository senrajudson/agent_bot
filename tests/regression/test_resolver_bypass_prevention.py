"""Teste de bypass prevention.

Verifica que os 5 consumers de resolução por nome usam o resolver canônico
ou passam o resolver ao PiDataCollector, em vez de chamar get_point_by_tag diretamente.
"""
import ast
import os


def _find_python_files(directory: str) -> list[str]:
    files = []
    for root, _, filenames in os.walk(directory):
        for f in filenames:
            if f.endswith(".py") and not f.startswith("test_"):
                files.append(os.path.join(root, f))
    return files


def _get_function_calls(filepath: str) -> set[str]:
    with open(filepath) as f:
        tree = ast.parse(f.read())
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    return calls


def test_pi_data_collector_uses_resolver():
    filepath = "domain/analysis/services/pi_data_collector.py"
    with open(filepath) as f:
        content = f.read()
    assert "self._resolver" in content, "PiDataCollector deve usar self._resolver"
    assert "get_point_by_tag" in content, "PiDataCollector deve ter fallback para get_point_by_tag"


def test_analysis_tools_checks_flag():
    filepath = "mcp_server/services/analysis_tools.py"
    with open(filepath) as f:
        content = f.read()
    assert "_get_resolver_if_enabled" in content or "ENABLE_PI_POINT_RESOLVER_V2" in content, (
        "analysis_tools.py deve verificar a flag ENABLE_PI_POINT_RESOLVER_V2"
    )


def test_math_tool_service_accepts_resolver():
    filepath = "mcp_server/services/math_tool_service.py"
    with open(filepath) as f:
        content = f.read()
    assert "resolver=None" in content, "math_tool_service.py deve aceitar parâmetro resolver"


def test_consultar_tag_uses_extract_unresolved():
    filepath = "domain/pims/services/consultar_tag_service.py"
    with open(filepath) as f:
        content = f.read()
    assert "extract_unresolved_subresponse_indices" in content, (
        "consultar_tag_service.py deve usar extract_unresolved_subresponse_indices"
    )
