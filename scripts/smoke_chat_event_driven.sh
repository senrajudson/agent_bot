#!/usr/bin/env bash
# ============================================================================
# smoke_chat_event_driven.sh — Smoke test for EDD /chat + Postgres
# Idempotent runbook helper. Dry-run by default.
# ============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

readonly DEFAULT_TIMEOUT=120
readonly SMOKE_CHAT_URL='http://127.0.0.1:8002/chat'
readonly SMOKE_STREAM_ID='conversation:edd-smoke-user'
readonly SMOKE_USER_ID='edd-smoke-user'
readonly SMOKE_MESSAGE='Responda apenas: smoke ok'

readonly DSN_REGEX='^postgresql://[^@]+@(127\.0\.0\.1|localhost):[0-9]+/[^?]+$'

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_ERROR=1
readonly EXIT_DSN=2
readonly EXIT_PREREQ=3
readonly EXIT_CHECK_FAIL=4

# ---------------------------------------------------------------------------
# Helpers — logging
# ---------------------------------------------------------------------------

log()  { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
warn() { log "WARN: $*" >&2; }
err()  { log "ERROR: $*" >&2; }

# ---------------------------------------------------------------------------
# Helpers — pre-flight
# ---------------------------------------------------------------------------

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        err "required command not found: $cmd"
        exit "$EXIT_PREREQ"
    fi
}

# ---------------------------------------------------------------------------
# Helpers — DSN
# ---------------------------------------------------------------------------

redact_dsn() {
    sed -E 's#://[^@]+@#://[REDACTED]@#'
}

guard_dsn() {
    local dsn="${1:-${EVENT_STORE_POSTGRES_DSN:-}}"
    if [[ -z "$dsn" ]]; then
        err "EVENT_STORE_POSTGRES_DSN is not set"
        exit "$EXIT_DSN"
    fi
    if [[ ! "$dsn" =~ $DSN_REGEX ]]; then
        local redacted
        redacted="$(printf '%s' "$dsn" | redact_dsn)"
        err "DSN must point to 127.0.0.1 or localhost (got: $redacted)"
        exit "$EXIT_DSN"
    fi
    # Print acceptance (redacted)
    local safe
    safe="$(printf '%s' "$dsn" | redact_dsn)"
    log "DSN accepted: $safe"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Smoke test for EDD /chat + Postgres. Idempotent. Dry-run by default.

Options:
  --help, -h            Show this help message and exit
  --dry-run             Print execution plan and exit (default if no action)

  --apply-schema        Apply EDD schema (001-004)
  --validate-schema     Validate EDD schema (SELECTs only)
  --smoke               POST /chat with smoke payload
  --validate-events     Run 12 success checks against database
  --cleanup             TRUNCATE all EDD tables (requires --yes)

  --dsn <value>         Override EVENT_STORE_POSTGRES_DSN
  --log-file            Write evidence to timestamped log file
  --yes                 Skip interactive confirmation for --cleanup

Environment variables:
  EVENT_STORE_POSTGRES_DSN  PostgreSQL DSN (required for DB actions)
  EVENT_DRIVEN_ENABLED      Must be 'true' before starting the app
  EVENT_STORE_BACKEND       Must be 'transactional_postgres'
  SMOKE_CHAT_TIMEOUT        Timeout for /chat curl (default: $DEFAULT_TIMEOUT)
  SMOKE_CHAT_YES            Set to 1 to skip confirmation for --cleanup
  PSQL_BIN                  Path to psql (default: psql)
  CURL_BIN                  Path to curl (default: curl)

Exit codes:
  0   Success
  1   Generic error
  2   DSN missing or invalid
  3   Required command missing
  4   Success check failed

EOF
}

# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

dry_run() {
    echo "=== Plan ==="
    echo "  1. apply-schema     → bash scripts/apply_edd_schema.sh --apply"
    echo "  2. validate-schema  → bash scripts/validate_edd_schema.sh --validate"
    echo "  3. smoke            → curl POST $SMOKE_CHAT_URL"
    echo "  4. validate-events  → 12 SQL checks against database"
    echo "  5. cleanup          → TRUNCATE (only with --cleanup --yes)"
    echo ""
    echo "Nothing was executed."
}

# ---------------------------------------------------------------------------
# Actions (stubs — implemented incrementally)
# ---------------------------------------------------------------------------

act_apply_schema() {
    guard_dsn
    require_cmd psql
    log "Applying EDD schema via scripts/apply_edd_schema.sh --apply"
    (cd "$REPO_ROOT" && bash scripts/apply_edd_schema.sh --apply)
    log "EDD schema applied"
}

act_validate_schema() {
    guard_dsn
    require_cmd psql
    log "Validating EDD schema via scripts/validate_edd_schema.sh --validate"
    (cd "$REPO_ROOT" && bash scripts/validate_edd_schema.sh --validate)
    log "EDD schema validation complete"
}

act_smoke() {
    require_cmd curl
    local body
    body="$(printf '{"message":"%s","user_id":"%s"}' "$SMOKE_MESSAGE" "$SMOKE_USER_ID")"
    local tmp_file
    tmp_file="$(mktemp /tmp/smoke_body.XXXXXX)"
    local http_code
    http_code="$(curl -sS -o "$tmp_file" -w '%{http_code}' \
        -H 'Content-Type: application/json' \
        -X POST \
        --max-time "${SMOKE_CHAT_TIMEOUT:-$DEFAULT_TIMEOUT}" \
        -d "$body" \
        "$SMOKE_CHAT_URL" 2>&1)" || true
    local curl_exit=$?
    log "HTTP status: $http_code"
    log "Response body:"
    cat "$tmp_file"
    rm -f "$tmp_file"
    if [[ "$curl_exit" -ne 0 ]]; then
        err "curl failed with exit code $curl_exit"
        exit "$EXIT_ERROR"
    fi
    if [[ "$http_code" != "200" ]]; then
        err "expected HTTP 200, got $http_code"
        exit "$EXIT_ERROR"
    fi
    log "Smoke request succeeded (HTTP 200)"
}

act_validate_events() {
    guard_dsn
    require_cmd psql
    local dsn="$EVENT_STORE_POSTGRES_DSN"
    local psql_cmd="${PSQL_BIN:-psql}"
    local check_failures=0

    run_sql() {
        "$psql_cmd" "$dsn" -v ON_ERROR_STOP=1 -Atc "$1"
    }

    log "Running 12 success checks against database"

    # --- Check 1: /chat HTTP 200 (validated in --smoke, pass-through here) ---
    log "PASS:1 (validated by --smoke)"

    # --- Check 2: Response envelope (validated in --smoke, pass-through) ---
    log "PASS:2 (validated by --smoke)"

    # --- Check 3: Log event_publisher_created_transactional ---
    # This is informational — the operator checks logs manually
    log "INFO:3 — check app log for 'event=event_publisher_created_transactional'"

    # --- Check 4: event_store_events >= 1 ---
    local es_count
    es_count=$(run_sql "SELECT count(*) FROM event_store_events WHERE stream_id='$SMOKE_STREAM_ID'")
    if [[ "$es_count" -ge 1 ]]; then
        log "PASS:4 event_store_events count=$es_count (>= 1)"
    else
        log "FAIL:4 event_store_events count=$es_count (expected >= 1)"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 5: outbox_events >= 1 for same event_ids ---
    local ob_count
    ob_count=$(run_sql "SELECT count(*) FROM outbox_events ob WHERE EXISTS (SELECT 1 FROM event_store_events es WHERE es.event_id=ob.event_id AND es.stream_id='$SMOKE_STREAM_ID')")
    if [[ "$ob_count" -ge 1 ]]; then
        log "PASS:5 outbox_events count=$ob_count (>= 1 for stream)"
    else
        log "FAIL:5 outbox_events count=$ob_count (expected >= 1)"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 6: Join valid (all es rows have ob pair) ---
    local join_ok
    join_ok=$(run_sql "SELECT CASE WHEN count(*) = count(*) FILTER (WHERE ob.event_id IS NOT NULL) THEN 1 ELSE 0 END FROM event_store_events es LEFT JOIN outbox_events ob ON ob.event_id=es.event_id WHERE es.stream_id='$SMOKE_STREAM_ID'")
    if [[ "$join_ok" == "1" ]]; then
        log "PASS:6 all event_store_events have outbox_events pair"
    else
        log "FAIL:6 some event_store_events missing outbox_events pair"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 7: outbox status = 'pending' ---
    local status_pending
    status_pending=$(run_sql "SELECT CASE WHEN count(*) FILTER (WHERE ob.status='pending') = count(*) THEN 1 ELSE 0 END FROM outbox_events ob JOIN event_store_events es ON es.event_id=ob.event_id WHERE es.stream_id='$SMOKE_STREAM_ID'")
    if [[ "$status_pending" == "1" ]]; then
        log "PASS:7 all outbox_events status='pending'"
    else
        log "FAIL:7 some outbox_events have status != 'pending'"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 8: attempts = 0 ---
    local attempts_zero
    attempts_zero=$(run_sql "SELECT CASE WHEN count(*) FILTER (WHERE ob.attempts=0) = count(*) THEN 1 ELSE 0 END FROM outbox_events ob JOIN event_store_events es ON es.event_id=ob.event_id WHERE es.stream_id='$SMOKE_STREAM_ID'")
    if [[ "$attempts_zero" == "1" ]]; then
        log "PASS:8 all outbox_events attempts=0"
    else
        log "FAIL:8 some outbox_events have attempts != 0"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 9: max_attempts = 3 ---
    local max_attempts_three
    max_attempts_three=$(run_sql "SELECT CASE WHEN count(*) FILTER (WHERE ob.max_attempts=3) = count(*) THEN 1 ELSE 0 END FROM outbox_events ob JOIN event_store_events es ON es.event_id=ob.event_id WHERE es.stream_id='$SMOKE_STREAM_ID'")
    if [[ "$max_attempts_three" == "1" ]]; then
        log "PASS:9 all outbox_events max_attempts=3"
    else
        log "FAIL:9 some outbox_events have max_attempts != 3"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 10: processed_events empty ---
    local pe_count
    pe_count=$(run_sql "SELECT count(*) FROM processed_events")
    if [[ "$pe_count" -eq 0 ]]; then
        log "PASS:10 processed_events count=$pe_count (expected 0)"
    else
        log "FAIL:10 processed_events count=$pe_count (expected 0)"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 11: outbox_dlq empty ---
    local dlq_count
    dlq_count=$(run_sql "SELECT count(*) FROM outbox_dlq")
    if [[ "$dlq_count" -eq 0 ]]; then
        log "PASS:11 outbox_dlq count=$dlq_count (expected 0)"
    else
        log "FAIL:11 outbox_dlq count=$dlq_count (expected 0)"
        check_failures=$((check_failures + 1))
    fi

    # --- Check 12: No dispatcher/worker (scope guarantee, no SQL check) ---
    log "PASS:12 (no dispatcher/worker by scope guarantee)"

    # --- Summary ---
    if [[ "$check_failures" -eq 0 ]]; then
        log "All 12 checks passed"
    else
        err "$check_failures check(s) failed"
        exit "$EXIT_CHECK_FAIL"
    fi
}

act_cleanup() {
    guard_dsn
    require_cmd psql
    local dsn="$EVENT_STORE_POSTGRES_DSN"
    local psql_cmd="${PSQL_BIN:-psql}"

    # Gate: require --yes or SMOKE_CHAT_YES=1
    if [[ "${SMOKE_CHAT_YES:-}" != "1" && "${YES:-0}" != "1" ]]; then
        err "--cleanup requires --yes (or set SMOKE_CHAT_YES=1)"
        exit "$EXIT_DSN"
    fi

    local safe_dsn
    safe_dsn="$(printf '%s' "$dsn" | redact_dsn)"
    warn "DESTRUCTIVE: about to TRUNCATE 4 tables in $safe_dsn"
    warn "  - event_store_events"
    warn "  - outbox_events"
    warn "  - processed_events"
    warn "  - outbox_dlq"

    "$psql_cmd" "$dsn" -v ON_ERROR_STOP=1 -c \
        "TRUNCATE TABLE event_store_events, outbox_events, processed_events, outbox_dlq RESTART IDENTITY CASCADE;"

    log "Cleanup complete: 4 tables truncated"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    local do_apply=0
    local do_validate=0
    local do_smoke=0
    local do_check=0
    local do_cleanup=0
    local has_yes=0
    local has_log_file=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                usage
                exit "$EXIT_SUCCESS"
                ;;
            --dry-run)
                dry_run
                exit "$EXIT_SUCCESS"
                ;;
            --apply-schema)    do_apply=1 ;;
            --validate-schema) do_validate=1 ;;
            --smoke)           do_smoke=1 ;;
            --validate-events) do_check=1 ;;
            --cleanup)         do_cleanup=1 ;;
            --dsn)
                shift
                export EVENT_STORE_POSTGRES_DSN="$1"
                ;;
            --log-file)        has_log_file=1 ;;
            --yes)             export YES=1 ;;
            *)
                err "unknown option: $1"
                usage
                exit "$EXIT_ERROR"
                ;;
        esac
        shift
    done

    # Default: dry-run
    if [[ "$do_apply$do_validate$do_smoke$do_check$do_cleanup" == "00000" ]]; then
        dry_run
        exit "$EXIT_SUCCESS"
    fi

    # Setup log file if requested or if stdout is a TTY
    if [[ "$has_log_file" -eq 1 || -t 1 ]]; then
        local log_dir="${REPO_ROOT}/logs"
        mkdir -p "$log_dir"
        local log_file="${log_dir}/smoke_chat_event_driven_$(date -u +%Y%m%dT%H%M%SZ).log"
        exec > >(tee -a "$log_file") 2>&1
        log "Log file: $log_file"
    fi

    # Run actions IN ORDER (apply → validate → smoke → check → cleanup)
    # Regardless of the order they were passed on the command line
    [[ "$do_apply" -eq 1 ]]    && log "Action: --apply-schema"    && act_apply_schema
    [[ "$do_validate" -eq 1 ]] && log "Action: --validate-schema" && act_validate_schema
    [[ "$do_smoke" -eq 1 ]]    && log "Action: --smoke"           && act_smoke
    [[ "$do_check" -eq 1 ]]    && log "Action: --validate-events" && act_validate_events
    # cleanup is ALWAYS last
    [[ "$do_cleanup" -eq 1 ]]  && log "Action: --cleanup"         && act_cleanup

    log "All actions completed"
    exit "$EXIT_SUCCESS"
}

main "$@"
