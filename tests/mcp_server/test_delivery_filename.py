import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

from datetime import datetime, timezone

from mcp_server.services.delivery._filename import build_filename


class TestBuildFilename:
    def test_basic(self):
        now = datetime(2026, 7, 28, 14, 53, 0, tzinfo=timezone.utc)
        name = build_filename("dev", "tag_statistics", "csv", now=now)
        assert name.startswith("pi_chat_dev_tag_statistics_20260728T145300Z_")
        assert name.endswith(".csv")

    def test_environment_sanitized(self):
        name = build_filename("dev/prod@qa", "tool", "csv")
        assert "/" not in name
        assert "@" not in name

    def test_tool_sanitized(self):
        name = build_filename("dev", "tag statistics!", "csv")
        assert " " not in name
        assert "!" not in name

    def test_extension(self):
        name = build_filename("dev", "tool", "xlsx")
        assert name.endswith(".xlsx")

    def test_unique_ids(self):
        names = {build_filename("dev", "tool", "csv") for _ in range(100)}
        assert len(names) == 100

    def test_length_limit(self):
        name = build_filename("a" * 100, "b" * 100, "csv")
        assert len(name) <= 255
