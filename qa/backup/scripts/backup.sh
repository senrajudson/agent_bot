#!/bin/sh
set -eu

HOST="${PGHOST:-db}"
USER="${PGUSER:-n8n}"
DB="${PGDATABASE:-n8n}"
OUTDIR="${OUTDIR:-/backup}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP="${KEEP_LAST:-7}"

mkdir -p "$OUTDIR"

log() { echo "[$(date '+%F %T')] $*"; }

wait_pg() {
  log "aguardando Postgres responder (host=$HOST db=$DB user=$USER)..."
  until pg_isready -h "$HOST" -U "$USER" -d "$DB" >/dev/null 2>&1; do
    sleep 2
  done
  log "Postgres OK"
}

do_dump() {
  ts="$(date +%F_%H-%M-%S)"
  out="$OUTDIR/${DB}_${ts}.sql"
  tmp="${out}.tmp"
  err="$OUTDIR/pg_dump_${ts}.err"

  log "pg_dump -> $out"

  # pg_dump plain (SQL)
  if pg_dump -h "$HOST" -U "$USER" -d "$DB" > "$tmp" 2> "$err"; then
    mv -f "$tmp" "$out"
    if [ ! -s "$err" ]; then rm -f "$err"; fi
    log "backup OK: $out"
  else
    log "ERRO no pg_dump: veja $err"
    rm -f "$tmp"
  fi

  # retenção
  ls -1t "$OUTDIR"/${DB}_*.sql 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
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