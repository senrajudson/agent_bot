from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from domain.analysis.services.xlsx_projection import XlsxSheet
from mcp_server.services.delivery.exceptions import ArtifactLimitExceededError
from mcp_server.services.delivery.xlsx_report_builder import XlsxReportBuilder


@pytest.fixture
def builder(tmp_path: Path) -> XlsxReportBuilder:
    return XlsxReportBuilder(
        temp_dir=str(tmp_path),
        max_rows=100,
        max_bytes=1_000_000,
        max_columns=10,
        max_cell_bytes=1024,
    )


def _make_sheet(name: str = "TestSheet", rows: int = 5) -> XlsxSheet:
    return XlsxSheet(
        name=name,
        columns=["col_a", "col_b", "col_c"],
        rows=[[f"val_{i}_{j}" for j in range(3)] for i in range(rows)],
    )


class TestWorkbookOpens:
    def test_workbook_valid(self, builder: XlsxReportBuilder) -> None:
        path = builder.build_xlsx([_make_sheet()])
        assert path.exists()
        wb = load_workbook(str(path))
        assert len(wb.sheetnames) == 1
        wb.close()
        path.unlink(missing_ok=True)


class TestSheetsCorrect:
    def test_multiple_sheets(self, builder: XlsxReportBuilder) -> None:
        sheets = [_make_sheet("S1"), _make_sheet("S2"), _make_sheet("S3")]
        path = builder.build_xlsx(sheets)
        wb = load_workbook(str(path))
        assert wb.sheetnames == ["S1", "S2", "S3"]
        wb.close()
        path.unlink(missing_ok=True)


class TestFormulaProtection:
    def test_formula_prefix_protected(self, builder: XlsxReportBuilder) -> None:
        sheet = XlsxSheet(
            name="Formula",
            columns=["data"],
            rows=[["=SUM(A1:A10)"], ["+addition"], ["-subtraction"]],
        )
        path = builder.build_xlsx([sheet])
        wb = load_workbook(str(path))
        ws = wb.active
        assert ws.cell(row=2, column=1).value == "'=SUM(A1:A10)"
        assert ws.cell(row=3, column=1).value == "'+addition"
        assert ws.cell(row=4, column=1).value == "'-subtraction"
        wb.close()
        path.unlink(missing_ok=True)


class TestSheetNameSanitized:
    def test_invalid_chars_removed(self, builder: XlsxReportBuilder) -> None:
        sheet = XlsxSheet(name="Bad:Name/*?", columns=["a"], rows=[["1"]])
        path = builder.build_xlsx([sheet])
        wb = load_workbook(str(path))
        assert "Bad_Name___" in wb.sheetnames[0]
        wb.close()
        path.unlink(missing_ok=True)

    def test_max_31_chars(self, builder: XlsxReportBuilder) -> None:
        long_name = "A" * 50
        sheet = XlsxSheet(name=long_name, columns=["a"], rows=[["1"]])
        path = builder.build_xlsx([sheet])
        wb = load_workbook(str(path))
        assert len(wb.sheetnames[0]) <= 31
        wb.close()
        path.unlink(missing_ok=True)


class TestDuplicateNames:
    def test_duplicates_resolved(self, builder: XlsxReportBuilder) -> None:
        sheets = [_make_sheet("Dup"), _make_sheet("Dup"), _make_sheet("Dup")]
        path = builder.build_xlsx(sheets)
        wb = load_workbook(str(path))
        assert len(wb.sheetnames) == 3
        assert len(set(wb.sheetnames)) == 3
        wb.close()
        path.unlink(missing_ok=True)


class TestLimits:
    def test_max_rows_exceeded(self, builder: XlsxReportBuilder) -> None:
        sheet = _make_sheet(rows=200)
        with pytest.raises(ArtifactLimitExceededError, match="row_count"):
            builder.build_xlsx([sheet])

    def test_max_bytes_exceeded(self, tmp_path: Path) -> None:
        builder = XlsxReportBuilder(
            temp_dir=str(tmp_path),
            max_rows=1_000_000,
            max_bytes=100,
            max_columns=50,
            max_cell_bytes=1024,
        )
        sheet = XlsxSheet(name="Big", columns=["a"], rows=[["x" * 200] for _ in range(10)])
        with pytest.raises(ArtifactLimitExceededError, match="file_bytes"):
            builder.build_xlsx([sheet])


class TestCleanup:
    def test_temp_file_removed_on_error(self, builder: XlsxReportBuilder) -> None:
        sheet = _make_sheet(rows=200)
        with pytest.raises(ArtifactLimitExceededError):
            builder.build_xlsx([sheet])
        remaining = list(builder._temp_dir.glob("*.xlsx"))
        assert len(remaining) == 0
