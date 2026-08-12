from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Protocol

from mcp_server.services.delivery._csv_protection import apply_formula_protection
from mcp_server.services.delivery.exceptions import ArtifactLimitExceededError


class ReportBuilder(Protocol):
    def build_csv(
        self,
        *,
        columns: list[str],
        rows: Iterable[list[Any]],
        max_rows: int,
        max_bytes: int,
        max_cell_bytes: int,
    ) -> Path: ...


class CsvReportBuilder:
    def __init__(
        self,
        temp_dir: str = "/tmp/agent_bot_mcp_artifacts",
        encoding: str = "utf-8-sig",
        delimiter: str = ";",
        lineterminator: str = "\r\n",
    ) -> None:
        self._temp_dir = temp_dir
        self._encoding = encoding
        self._delimiter = delimiter
        self._lineterminator = lineterminator

    def build_csv(
        self,
        *,
        columns: list[str],
        rows: Iterable[list[Any]],
        max_rows: int,
        max_bytes: int,
        max_cell_bytes: int,
    ) -> Path:
        os.makedirs(self._temp_dir, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding=self._encoding,
            newline="",
            suffix=".csv",
            dir=self._temp_dir,
            delete=False,
        )
        tmp_path = Path(tmp.name)
        try:
            writer = csv.writer(
                tmp,
                delimiter=self._delimiter,
                lineterminator=self._lineterminator,
                quoting=csv.QUOTE_MINIMAL,
            )
            safe_header = [apply_formula_protection(c) for c in columns]
            writer.writerow(safe_header)

            row_count = 0
            for row in rows:
                if len(row) != len(columns):
                    raise ArtifactLimitExceededError(
                        field="header_row_mismatch",
                        limit=len(columns),
                        actual=len(row),
                    )
                safe_row: list[str] = []
                for cell in row:
                    s = self._normalize(cell)
                    s = apply_formula_protection(s)
                    if len(s.encode(self._encoding)) > max_cell_bytes:
                        raise ArtifactLimitExceededError(
                            field="cell_bytes",
                            limit=max_cell_bytes,
                            actual=len(s.encode(self._encoding)),
                        )
                    safe_row.append(s)
                writer.writerow(safe_row)
                row_count += 1

                if row_count % 1000 == 0:
                    tmp.flush()
                    current_size = tmp_path.stat().st_size
                    if current_size > max_bytes:
                        raise ArtifactLimitExceededError(
                            field="file_bytes",
                            limit=max_bytes,
                            actual=current_size,
                        )

                if row_count > max_rows:
                    raise ArtifactLimitExceededError(
                        field="row_count",
                        limit=max_rows,
                        actual=row_count,
                    )

            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            return tmp_path
        except BaseException:
            tmp.close()
            os.unlink(tmp_path)
            raise

    def _normalize(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not __import__("math").isfinite(value):
                raise ArtifactLimitExceededError(
                    field="non_finite_float",
                    limit=1,
                    actual=1,
                )
            return repr(value) if isinstance(value, float) else str(value)
        if isinstance(value, (bytes, bytearray)):
            return value.decode(self._encoding, errors="replace")
        return str(value)
