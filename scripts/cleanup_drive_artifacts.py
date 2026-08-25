#!/usr/bin/env python3
"""
Script de manutenção para retenção e limpeza automática de artefatos expirados no Google Drive.

Exclui permanentemente arquivos da pasta configurada no Google Drive que possuam a propriedade
`appProperties.source == "pi-chat"` e data de criação superior ao limite de retenção (default 7 dias).

Uso:
    poetry run python scripts/cleanup_drive_artifacts.py --dry-run
    poetry run python scripts/cleanup_drive_artifacts.py --retention-days 7
"""

import argparse
from datetime import datetime, timezone
import logging
import os
import sys
from pathlib import Path

# Adiciona a raiz do monorepo ao PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp_server.clients.google_drive_client import GoogleDriveClient, DriveCsvError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cleanup_drive_artifacts")


def parse_iso_datetime(dt_str: str) -> datetime:
    """Converte string ISO 8601 da API do Google Drive em datetime timezone-aware em UTC."""
    if not dt_str:
        return datetime.now(timezone.utc)
    clean_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def run_cleanup(
    *,
    credentials_path: str,
    folder_id: str,
    retention_days: int,
    dry_run: bool,
    timeout_seconds: float = 30.0,
) -> dict:
    if not credentials_path or not Path(credentials_path).is_file():
        logger.error(
            "Credenciais do Google Drive não encontradas: '%s'. Abortando.",
            credentials_path,
        )
        sys.exit(1)

    if not folder_id:
        logger.error(
            "ID da pasta do Google Drive (GOOGLE_DRIVE_EXPORT_FOLDER_ID) não configurado. Abortando."
        )
        sys.exit(1)

    logger.info(
        "Iniciando rotina de limpeza do Google Drive | retention_days=%d dry_run=%s folder_id=%s",
        retention_days,
        dry_run,
        folder_id[:8] + "..." if len(folder_id) > 8 else folder_id,
    )

    client = GoogleDriveClient(
        credentials_path=credentials_path,
        folder_id=folder_id,
        timeout_seconds=timeout_seconds,
    )

    service = client._build_service()
    now_utc = datetime.now(timezone.utc)

    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None

    total_scanned = 0
    skipped_not_pi_chat = 0
    skipped_recent = 0
    expired_count = 0
    deleted_count = 0
    error_count = 0

    while True:
        try:
            response = (
                service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, createdTime, appProperties)",
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
        except Exception as e:
            logger.exception("Erro ao listar arquivos do Google Drive: %s", e)
            sys.exit(1)

        files = response.get("files", [])
        total_scanned += len(files)

        for f in files:
            file_id = f.get("id", "")
            file_name = f.get("name", "sem_nome")
            created_str = f.get("createdTime", "")
            app_props = f.get("appProperties") or {}

            # Filtro 1: Apenas arquivos originados pelo PI Chat
            if app_props.get("source") != "pi-chat":
                logger.debug(
                    "Ignorando arquivo fora do escopo pi-chat: id=%s name=%s appProperties=%s",
                    file_id,
                    file_name,
                    app_props,
                )
                skipped_not_pi_chat += 1
                continue

            # Filtro 2: Calcular idade do arquivo
            created_dt = parse_iso_datetime(created_str)
            age_days = (now_utc - created_dt).total_seconds() / 86400.0

            if age_days < retention_days:
                logger.debug(
                    "Arquivo dentro do prazo de retenção (%.1f dias < %ddias): id=%s name=%s",
                    age_days,
                    retention_days,
                    file_id,
                    file_name,
                )
                skipped_recent += 1
                continue

            expired_count += 1

            if dry_run:
                logger.info(
                    "[DRY-RUN] Arquivo expirado elegível para exclusão: id=%s name=%s created=%s (idade: %.1f dias)",
                    file_id,
                    file_name,
                    created_str,
                    age_days,
                )
            else:
                logger.info(
                    "Excluindo arquivo expirado: id=%s name=%s created=%s (idade: %.1f dias)",
                    file_id,
                    file_name,
                    created_str,
                    age_days,
                )
                try:
                    service.files().delete(
                        fileId=file_id, supportsAllDrives=True
                    ).execute()
                    deleted_count += 1
                except Exception as e:
                    logger.error(
                        "Falha ao excluir arquivo id=%s name=%s: %s",
                        file_id,
                        file_name,
                        e,
                    )
                    error_count += 1

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    summary = {
        "total_scanned": total_scanned,
        "skipped_not_pi_chat": skipped_not_pi_chat,
        "skipped_recent": skipped_recent,
        "expired_count": expired_count,
        "deleted_count": deleted_count,
        "error_count": error_count,
        "dry_run": dry_run,
        "retention_days": retention_days,
    }

    logger.info(
        "Limpeza concluída | analisados=%d pi_chat_expirados=%d excluídos=%d "
        "recientes_mantidos=%d não_pi_chat_ignorados=%d erros=%d dry_run=%s",
        total_scanned,
        expired_count,
        deleted_count,
        skipped_recent,
        skipped_not_pi_chat,
        error_count,
        dry_run,
    )

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Limpeza e retenção automática de artefatos do PI Chat no Google Drive."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula a execução e lista os arquivos elegíveis sem efetuar exclusão.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.getenv("GOOGLE_DRIVE_ARTIFACT_RETENTION_DAYS", "7")),
        help="Prazo máximo de retenção em dias (default: 7).",
    )
    parser.add_argument(
        "--credentials-path",
        type=str,
        default=os.getenv(
            "GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE",
            "secrets/google_drive_credentials.json",
        ),
        help="Caminho para o arquivo JSON de credenciais da Service Account.",
    )
    parser.add_argument(
        "--folder-id",
        type=str,
        default=os.getenv("GOOGLE_DRIVE_EXPORT_FOLDER_ID", ""),
        help="ID da pasta exportada no Google Drive.",
    )

    args = parser.parse_args()

    run_cleanup(
        credentials_path=args.credentials_path,
        folder_id=args.folder_id,
        retention_days=args.retention_days,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
