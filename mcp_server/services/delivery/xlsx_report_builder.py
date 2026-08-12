from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.utils.exceptions import InvalidFileException

from mcp_server.services.delivery._csv_protection import apply_formula_protection
from mcp_server.services.delivery.exceptions import ArtifactLimitExceededError


class XlsxReportBuilder:
    def __init__(
        self,
        *,
        temp_dir: str = "/tmp/agent_bot_mcp_artifacts",
        max_rows: int = 1_000_000,
        max_bytes: int = 104_857_600,
        max_columns: int = 50,
        max_cell_bytes: int = 32768,
    ) -> None:
        self._temp_dir = Path(temp_dir)
        self._max_rows = max_rows
        self._max_bytes = max_bytes
        self._max_columns = max_columns
        self._max_cell_bytes = max_cell_bytes

    def build_xlsx(
        self,
        sheets: list[Any],
    ) -> Path:
        self._validate_limits(sheets)
        sanitized = [self._sanitize_sheet(s) for s in sheets]
        deduped = self._dedup_sheet_names(sanitized)

        self._temp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", dir=str(self._temp_dir))
        os.close(fd)
        path = Path(tmp_path)

        try:
            wb = Workbook()
            wb.remove(wb.active)

            for s in deduped:
                ws = wb.create_sheet(title=s.name[:31])
                self._write_sheet(ws, s)

            wb.save(str(path))

            size = path.stat().st_size
            if size > self._max_bytes:
                path.unlink(missing_ok=True)
                raise ArtifactLimitExceededError(
                    field="file_bytes",
                    limit=self._max_bytes,
                    actual=size,
                )

            return path

        except InvalidFileException as exc:
            path.unlink(missing_ok=True)
            raise ArtifactLimitExceededError(
                field="file_bytes",
                limit=self._max_bytes,
                actual=0,
            ) from exc
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _validate_limits(self, sheets: list[Any]) -> None:
        total_rows = sum(len(s.rows) for s in sheets)
        total_cols = max((len(s.columns) for s in sheets), default=0)
        if total_rows > self._max_rows:
            raise ArtifactLimitExceededError(
                field="row_count",
                limit=self._max_rows,
                actual=total_rows,
            )
        if total_cols > self._max_columns:
            raise ArtifactLimitExceededError(
                field="column_count",
                limit=self._max_columns,
                actual=total_cols,
            )

    def _write_sheet(self, ws: Any, sheet: Any) -> None:
        for col_idx, col_name in enumerate(sheet.columns, 1):
            ws.cell(
                row=1,
                column=col_idx,
                value=apply_formula_protection(str(col_name)),
            )

        for row_idx, row in enumerate(sheet.rows, 2):
            for col_idx, value in enumerate(row, 1):
                cell_str = str(value) if value is not None else ""
                cell_bytes = len(cell_str.encode("utf-8"))
                if cell_bytes > self._max_cell_bytes:
                    raise ArtifactLimitExceededError(
                        field="cell_bytes",
                        limit=self._max_cell_bytes,
                        actual=cell_bytes,
                    )
                ws.cell(
                    row=row_idx,
                    column=col_idx,
                    value=apply_formula_protection(cell_str),
                )

    def _sanitize_sheet(self, sheet: Any) -> Any:
        safe_name = re.sub(r"[\\[\]:*?/]", "_", sheet.name)[:31]
        return sheet.__class__(name=safe_name, columns=sheet.columns, rows=sheet.rows)

    def _dedup_sheet_names(self, sheets: list[Any]) -> list[Any]:
        seen: set[str] = set()
        result: list[Any] = []
        for s in sheets:
            name = s.name
            if name in seen:
                counter = 2
                while f"{name}_{counter}" in seen:
                    counter += 1
                name = f"{name}_{counter}"
                s = s.__class__(name=name, columns=s.columns, rows=s.rows)
            seen.add(name)
            result.append(s)
        return result
