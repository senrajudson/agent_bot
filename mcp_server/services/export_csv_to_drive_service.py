from __future__ import annotations

import csv
import io
import json
import math
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from mcp_server.clients.google_drive_client import GoogleDriveClient, DriveCsvError

logger = logging.getLogger("mcp_server.export_csv_to_drive")

DELIMITER = ";"
LINETERMINATOR = "\r\n"
ENCODING = "utf-8-sig"
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


class DriveCsvValidationError(ValueError):
    pass


class DriveCsvSerializationError(ValueError):
    pass


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DriveCsvValidationError(f"float não finito: {value}")
        return repr(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DriveCsvValidationError(f"Decimal não finito: {value}")
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise DriveCsvValidationError(
        f"Tipo não suportado: {type(value).__name__}"
    )


def _apply_formula_protection(s: str, enabled: bool) -> str:
    if not enabled:
        return s
    if s and s[0] in FORMULA_PREFIXES:
        return "'" + s
    return s


def _sanitize_filename(stem: str, max_length: int, now: datetime) -> str:
    s = stem.strip()
    if s.lower().endswith(".csv"):
        s = s[:-4]
    s = s.replace("/", "_").replace("\\", "_")
    s = "".join(
        c for c in s
        if c.isprintable() and c not in ('/', '\\', '\0', '\r', '\n', '\t')
    )
    s = "_".join(s.split())
    if not s or s in (".", ".."):
        raise DriveCsvValidationError("filename inválido")
    if s.upper() in WINDOWS_RESERVED:
        s = "_" + s
    ts = now.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{ts}.csv"
    if len(s) + len(suffix) > max_length:
        keep = max_length - len(suffix)
        if keep <= 0:
            raise DriveCsvValidationError(
                "MAX_FILENAME_LENGTH muito pequeno"
            )
        s = s[:keep]
    return s + suffix


def _validate_columns(
    columns: Any, max_columns: int, max_cell_bytes: int
) -> list[str]:
    if not isinstance(columns, list) or not columns:
        raise DriveCsvValidationError("columns vazio ou não é lista")
    if len(columns) > max_columns:
        raise DriveCsvValidationError(
            f"columns excede máximo de {max_columns}"
        )
    out: list[str] = []
    for i, c in enumerate(columns):
        if not isinstance(c, str) or not c:
            raise DriveCsvValidationError(f"column[{i}] inválida")
        if len(c.encode(ENCODING)) > max_cell_bytes:
            raise DriveCsvValidationError(
                f"column[{i}] excede {max_cell_bytes} bytes"
            )
        out.append(c)
    return out


def _validate_rows(
    rows: Any, columns_len: int, max_rows: int
) -> list[list[Any]]:
    if not isinstance(rows, list):
        raise DriveCsvValidationError("rows não é lista")
    if len(rows) > max_rows:
        raise DriveCsvValidationError(
            f"rows excede máximo de {max_rows}"
        )
    for i, row in enumerate(rows):
        if not isinstance(row, list):
            raise DriveCsvValidationError(f"row[{i}] não é lista")
        if len(row) != columns_len:
            raise DriveCsvValidationError(
                f"row[{i}] tem {len(row)} células, "
                f"esperado {columns_len}"
            )
    return rows


def _measure_input_bytes(
    filename: str, columns: list[str], rows: list[list[Any]]
) -> int:
    projection = {"f": filename, "c": columns, "r": rows}
    raw = json.dumps(
        projection,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return len(raw.encode("utf-8"))


def _measure_cell_bytes(cell_value: str) -> int:
    return len(cell_value.encode(ENCODING))


def _serialize_csv(
    columns: list[str],
    rows: list[list[Any]],
    *,
    formula_protection: bool,
    max_cell_bytes: int,
) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(
        buf,
        delimiter=DELIMITER,
        lineterminator=LINETERMINATOR,
        quoting=csv.QUOTE_MINIMAL,
    )
    header = [
        _apply_formula_protection(c, formula_protection)
        for c in columns
    ]
    writer.writerow(header)

    for row in rows:
        normalized_row: list[str] = []
        for cell in row:
            s = _normalize(cell)
            s = _apply_formula_protection(s, formula_protection)
            if _measure_cell_bytes(s) > max_cell_bytes:
                raise DriveCsvValidationError(
                    "célula excede MAX_CELL_BYTES"
                )
            normalized_row.append(s)
        writer.writerow(normalized_row)

    return buf.getvalue().encode(ENCODING)


def export_csv_to_drive(
    *,
    filename: str,
    columns: list[str],
    rows: list[list[Any]],
    drive_client: GoogleDriveClient,
    max_rows: int,
    max_columns: int,
    max_cell_bytes: int,
    max_input_bytes: int,
    max_file_bytes: int,
    max_filename_length: int,
    formula_protection: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)

    safe_filename = _sanitize_filename(filename, max_filename_length, now)
    safe_columns = _validate_columns(columns, max_columns, max_cell_bytes)
    safe_rows = _validate_rows(rows, len(safe_columns), max_rows)

    input_bytes = _measure_input_bytes(
        safe_filename, safe_columns, safe_rows
    )
    if input_bytes > max_input_bytes:
        raise DriveCsvValidationError(
            f"input_bytes {input_bytes} excede {max_input_bytes}"
        )

    csv_bytes = _serialize_csv(
        safe_columns,
        safe_rows,
        formula_protection=formula_protection,
        max_cell_bytes=max_cell_bytes,
    )

    if len(csv_bytes) > max_file_bytes:
        raise DriveCsvValidationError(
            f"file_bytes {len(csv_bytes)} excede {max_file_bytes}"
        )

    app_properties = {
        "source": "pi-chat",
        "created_by_tool": "export_csv_to_drive_tool",
        "created_at": now.isoformat(),
    }

    uploaded = drive_client.upload_csv(
        filename=safe_filename,
        csv_bytes=csv_bytes,
        app_properties=app_properties,
    )

    logger.info(
        "export_csv_to_drive: filename=%s rows=%d cols=%d "
        "input_bytes=%d file_bytes=%d file_id=%s",
        uploaded.name,
        len(rows),
        len(columns),
        input_bytes,
        len(csv_bytes),
        uploaded.file_id[:8] + "..." if len(uploaded.file_id) > 8 else uploaded.file_id,
    )

    return {
        "success": True,
        "answer": "O arquivo CSV foi criado no Google Drive.",
        "filename": uploaded.name,
        "mime_type": uploaded.mime_type,
        "view_url": uploaded.web_view_link,
        "download_url": uploaded.web_content_link,
        "expires_at": None,
    }
