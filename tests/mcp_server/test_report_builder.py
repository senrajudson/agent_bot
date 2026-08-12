import os
import sys
import tempfile
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.report_builder import CsvReportBuilder
from mcp_server.services.delivery.exceptions import ArtifactLimitExceededError


@pytest.fixture
def builder():
    return CsvReportBuilder(
        temp_dir=tempfile.gettempdir(),
        encoding="utf-8-sig",
        delimiter=";",
        lineterminator="\r\n",
    )


class TestCsvReportBuilder:
    def test_basic_csv(self, builder):
        columns = ["Timestamp", "Tag", "Value"]
        rows = [["2026-01-01T00:00:00Z", "TAG_A", 100.0], ["2026-01-01T01:00:00Z", "TAG_A", 200.0]]
        path = builder.build_csv(
            columns=columns,
            rows=rows,
            max_rows=100000,
            max_bytes=104857600,
            max_cell_bytes=32768,
        )
        try:
            content = path.read_bytes()
            assert content.startswith(b"\xef\xbb\xbf")
            text = content.decode("utf-8-sig")
            assert "Timestamp" in text
            assert "TAG_A" in text
            assert "100.0" in text or "100" in text
        finally:
            path.unlink(missing_ok=True)

    def test_row_count_limit(self, builder):
        rows = iter([["x"]] for _ in range(10))
        with pytest.raises(ArtifactLimitExceededError):
            builder.build_csv(columns=["A"], rows=rows, max_rows=5, max_bytes=104857600, max_cell_bytes=32768)

    def test_temp_file_cleanup_on_error(self, builder):
        paths_before = set(os.listdir(tempfile.gettempdir()))
        try:
            builder.build_csv(columns=["A"], rows=iter([["x"]] * 10), max_rows=5, max_bytes=104857600, max_cell_bytes=32768)
        except ArtifactLimitExceededError:
            pass
        paths_after = set(os.listdir(tempfile.gettempdir()))
        new_files = paths_after - paths_before
        csv_new = [f for f in new_files if f.endswith(".csv")]
        assert len(csv_new) == 0, f"Temp files not cleaned: {csv_new}"

    def test_formula_protection(self, builder):
        columns = ["=CMD"]
        rows = [["=1+1"]]
        path = builder.build_csv(
            columns=columns,
            rows=rows,
            max_rows=100000,
            max_bytes=104857600,
            max_cell_bytes=32768,
        )
        try:
            content = path.read_text(encoding="utf-8-sig")
            assert "'=CMD" in content
            assert "'=1+1" in content
        finally:
            path.unlink(missing_ok=True)

    def test_utf8_bom(self, builder):
        columns = ["A"]
        rows = [["1"]]
        path = builder.build_csv(
            columns=columns,
            rows=rows,
            max_rows=100000,
            max_bytes=104857600,
            max_cell_bytes=32768,
        )
        try:
            content = path.read_bytes()
            assert content.startswith(b"\xef\xbb\xbf"), "BOM missing"
        finally:
            path.unlink(missing_ok=True)

    def test_semicolon_delimiter(self, builder):
        columns = ["A", "B"]
        rows = [["v1", "v2"]]
        path = builder.build_csv(
            columns=columns,
            rows=rows,
            max_rows=100000,
            max_bytes=104857600,
            max_cell_bytes=32768,
        )
        try:
            text = path.read_text(encoding="utf-8-sig")
            assert "v1;v2" in text or '"v1";"v2"' in text
        finally:
            path.unlink(missing_ok=True)

    def test_header_row_mismatch_fails(self, builder):
        with pytest.raises(ArtifactLimitExceededError) as exc_info:
            builder.build_csv(
                columns=["A", "B"],
                rows=[["only-one"]],
                max_rows=100,
                max_bytes=104857600,
                max_cell_bytes=32768,
            )
        assert exc_info.value.field == "header_row_mismatch"
