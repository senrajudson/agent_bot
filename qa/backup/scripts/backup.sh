#!/bin/sh
set -eu

HOST="${PGHOST:-db_qa}"
USER="${PGUSER:-postgres}"
PRIMARY_DB="${PGDATABASE:-agent_bot_qa}"
N8N_DB="${N8N_DB_NAME:-n8n_qa}"
OUTDIR="${OUTDIR:-/backup}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP="${KEEP_LAST:-7}"

mkdir -p "$OUTDIR"

log() { echo "[$(date '+%F %T')] $*"; }

wait_pg() {
  log "aguardando Postgres responder (host=$HOST user=$USER)..."
  until pg_isready -h "$HOST" -U "$USER" >/dev/null 2>&1; do
    sleep 2
  done
  log "Postgres OK"
}

do_dump_for_db() {
  target_db="$1"
  ts="$(date +%F_%H-%M-%S)"
  out="$OUTDIR/${target_db}_${ts}.sql"
  tmp="${out}.tmp"
  err="$OUTDIR/pg_dump_${target_db}_${ts}.err"

  log "pg_dump -> $out (db=$target_db)"

  # pg_dump plain (SQL)
  if pg_dump -h "$HOST" -U "$USER" -d "$target_db" > "$tmp" 2> "$err"; then
    mv -f "$tmp" "$out"
    if [ ! -s "$err" ]; then rm -f "$err"; fi
    log "backup OK: $out"
  else
    log "ERRO no pg_dump ($target_db): veja $err"
    rm -f "$tmp"
  fi

  # retencao por banco
  ls -1t "$OUTDIR"/${target_db}_*.sql 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
}

do_dump() {
  for db_item in "$PRIMARY_DB" "$N8N_DB"; do
    if [ -n "$db_item" ]; then
      do_dump_for_db "$db_item"
    fi
  done
}

trap 'log "recebi sinal, saindo..."; exit 0' INT TERM

wait_pg

# 1) backup imediato ao iniciar o container
do_dump

# 2) backups recorrentes
while true; do
  sleep "$INTERVAL"
  wait_pg
  do_dump
done