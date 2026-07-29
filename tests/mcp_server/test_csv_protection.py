import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery._csv_protection import apply_formula_protection


class TestApplyFormulaProtection:
    def test_equal_prefix(self):
        assert apply_formula_protection("=CMD") == "'=CMD"

    def test_plus_prefix(self):
        assert apply_formula_protection("+1+2") == "'+1+2"

    def test_minus_prefix(self):
        assert apply_formula_protection("-1-2") == "'-1-2"

    def test_at_prefix(self):
        assert apply_formula_protection("@SUM") == "'@SUM"

    def test_tab_prefix(self):
        assert apply_formula_protection("\ta") == "'\ta"

    def test_cr_prefix(self):
        assert apply_formula_protection("\ra") == "'\ra"

    def test_normal_string(self):
        assert apply_formula_protection("hello") == "hello"

    def test_empty_string(self):
        assert apply_formula_protection("") == ""

    def test_numeric_string(self):
        assert apply_formula_protection("123") == "123"
