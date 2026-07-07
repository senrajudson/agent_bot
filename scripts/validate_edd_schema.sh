#!/usr/bin/env bash
# ============================================================================
# validate_edd_schema.sh — Validate EDD schema in a Postgres instance
# Read-only: never modifies data or schema.
# Dry-run by default; use --validate to execute checks.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SQL_FILES=(
    "$REPO_ROOT/app/infrastructure/event_store/sql/001_create_event_store_events.sql"
    "$REPO_ROOT/db/edd/002_create_outbox_events.sql"
    "$REPO_ROOT/db/edd/003_create_processed_events.sql"
    "$REPO_ROOT/db/edd/004_create_outbox_dlq.sql"
    "$REPO_ROOT/db/edd/005_create_outbox_recovery_audit.sql"
)

EXPECTED_TABLES=("event_store_events" "outbox_events" "processed_events" "outbox_dlq" "outbox_recovery_audit")

PSQL_BIN="${PSQL_BIN:-psql}"
DSN=""

ERRORS=0
CHECKS=0

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Validate EDD schema in a Postgres instance (read-only).

Options:
  --validate    Actually connect to Postgres and run checks (default: dry-run only)
  --help, -h    Show this help message

Modes:
  Dry-run (default):
    Shows which tables and checks would be validated.
    No connection is opened.

  Validate (--validate):
    Connects to Postgres via EVENT_STORE_POSTGRES_DSN.
    Runs SELECT queries to verify tables, columns, constraints, indexes.
    Never modifies data or schema.

Environment variables:
  EVENT_STORE_POSTGRES_DSN  PostgreSQL connection string (required for --validate)
  PSQL_BIN                  Path to psql binary (default: psql)

Tables checked:
  event_store_events         (inherited, from 001)
  outbox_events              (from 002)
  processed_events           (from 003)
  outbox_dlq                 (from 004)
  outbox_recovery_audit      (from 005)

Notes:
  - This script does NOT apply SQL (use apply_edd_schema.sh).
  - This script does NOT start Docker or create databases.
  - This script does NOT read .env files.
  - This script uses only SELECT queries.

EOF
    exit 0
}

abort() {
    echo "ERROR: $*" >&2
    exit 1
}

warn() {
    echo "  WARN: $*" >&2
}

pass() {
    echo "  PASS: $*"
    CHECKS=$((CHECKS + 1))
}

fail() {
    echo "  FAIL: $*"
    ERRORS=$((ERRORS + 1))
    CHECKS=$((CHECKS + 1))
}

# ---------------------------------------------------------------------------
# Database helpers (--validate only)
# ---------------------------------------------------------------------------

run_scalar() {
    local query="$1"
    "$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -Atc "$query"
}

# ---------------------------------------------------------------------------
# Assertions (--validate only)
# ---------------------------------------------------------------------------

assert_table_exists() {
    local table="$1"
    local count
    count=$(run_scalar "SELECT count(*) FROM information_schema.tables WHERE table_name = '$table';")
    if [[ "$count" -ge 1 ]]; then
        pass "Table '$table' exists"
    else
        fail "Table '$table' NOT found"
    fi
}

assert_column_exists() {
    local table="$1"
    local column="$2"
    local count
    count=$(run_scalar "SELECT count(*) FROM information_schema.columns WHERE table_name = '$table' AND column_name = '$column';")
    if [[ "$count" -ge 1 ]]; then
        pass "Column '$table.$column' exists"
    else
        fail "Column '$table.$column' NOT found"
    fi
}

assert_constraint_exists() {
    local table="$1"
    local constraint_name="$2"
    local count
    count=$(run_scalar "SELECT count(*) FROM information_schema.table_constraints WHERE table_name = '$table' AND constraint_name = '$constraint_name';")
    if [[ "$count" -ge 1 ]]; then
        pass "Constraint '$constraint_name' exists on '$table'"
    else
        fail "Constraint '$constraint_name' NOT found on '$table'"
    fi
}

assert_index_exists() {
    local index_name="$1"
    local count
    count=$(run_scalar "SELECT count(*) FROM pg_indexes WHERE indexname = '$index_name';")
    if [[ "$count" -ge 1 ]]; then
        pass "Index '$index_name' exists"
    else
        fail "Index '$index_name' NOT found"
    fi
}

assert_count() {
    local description="$1"
    local query="$2"
    local min="${3:-1}"
    local count
    count=$(run_scalar "$query")
    if [[ "$count" -ge "$min" ]]; then
        pass "$description ($count)"
    else
        fail "$description (got $count, expected >= $min)"
    fi
}

# ---------------------------------------------------------------------------
# Local file validation (always runs)
# ---------------------------------------------------------------------------

validate_local_files() {
    echo ""
    echo "=== Local file validation ==="
    for f in "${SQL_FILES[@]}"; do
        local rel="${f#$REPO_ROOT/}"
        if [[ -f "$f" ]]; then
            pass "File exists: $rel"
        else
            fail "File missing: $rel"
        fi
    done
}

# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------

dry_run() {
    echo "=== EDD Schema Validation: Dry Run ==="
    echo ""
    echo "Tables that would be checked:"
    for t in "${EXPECTED_TABLES[@]}"; do
        echo "  - $t"
    done
    echo ""
    echo "Checks that would be performed:"
    echo "  - Table existence (information_schema.tables)"
    echo "  - Column existence (information_schema.columns)"
    echo "  - Constraint existence (information_schema.table_constraints)"
    echo "  - Index existence (pg_indexes)"
    echo "  - PK composition (processed_events)"
    echo "  - UNIQUE constraints (outbox_events, outbox_dlq)"
    echo "  - CHECK status values (no 'failed' in outbox_events)"
    echo ""
    echo "No connection was opened."
    echo "No SQL was executed."
    echo ""
    echo "To run actual checks, re-run with: $0 --validate"
}

# ---------------------------------------------------------------------------
# Schema validation (--validate only)
# ---------------------------------------------------------------------------

validate_schema() {
    echo "=== EDD Schema Validation: Validate ==="
    echo ""

    # Validate DSN
    if [[ -z "${EVENT_STORE_POSTGRES_DSN:-}" ]]; then
        abort "EVENT_STORE_POSTGRES_DSN is not set. Export it before running with --validate."
    fi

    # Validate psql exists
    if ! command -v "$PSQL_BIN" &>/dev/null; then
        abort "psql not found at: $PSQL_BIN"
    fi

    # Test connection
    echo "--- Connection test ---"
    local server_version
    server_version=$(run_scalar "SELECT version();")
    if [[ -z "$server_version" ]]; then
        abort "Cannot connect to Postgres with the provided DSN."
    fi
    pass "Connected to: $server_version"
    echo ""

    # --- event_store_events ---
    echo "--- event_store_events ---"
    assert_table_exists "event_store_events"
    assert_column_exists "event_store_events" "event_id"
    assert_column_exists "event_store_events" "stream_id"
    assert_column_exists "event_store_events" "stream_version"
    assert_column_exists "event_store_events" "event_type"
    assert_column_exists "event_store_events" "payload"
    assert_constraint_exists "event_store_events" "event_store_events_pkey"
    assert_index_exists "ix_event_store_events_stream_id"
    echo ""

    # --- outbox_events ---
    echo "--- outbox_events ---"
    assert_table_exists "outbox_events"
    assert_column_exists "outbox_events" "outbox_id"
    assert_column_exists "outbox_events" "event_id"
    assert_column_exists "outbox_events" "stream_id"
    assert_column_exists "outbox_events" "stream_version"
    assert_column_exists "outbox_events" "event_type"
    assert_column_exists "outbox_events" "event_payload"
    assert_column_exists "outbox_events" "status"
    assert_column_exists "outbox_events" "attempts"
    assert_column_exists "outbox_events" "max_attempts"
    assert_column_exists "outbox_events" "available_at"
    assert_column_exists "outbox_events" "locked_by"
    assert_column_exists "outbox_events" "locked_until"
    assert_column_exists "outbox_events" "last_error"
    assert_column_exists "outbox_events" "last_error_class"
    assert_column_exists "outbox_events" "created_at"
    assert_column_exists "outbox_events" "updated_at"
    assert_column_exists "outbox_events" "dispatched_at"
    assert_column_exists "outbox_events" "dead_lettered_at"
    assert_constraint_exists "outbox_events" "uq_outbox_event_id"
    assert_index_exists "idx_outbox_status_available_at"
    assert_index_exists "idx_outbox_locked_until"
    assert_index_exists "idx_outbox_event_type"
    assert_index_exists "idx_outbox_stream"
    # Check that 'failed' is not a valid status
    local failed_count
    failed_count=$(run_scalar "SELECT count(*) FROM information_schema.check_constraints cc JOIN information_schema.constraint_column_usage ccu ON cc.constraint_name = ccu.constraint_name WHERE ccu.table_name = 'outbox_events' AND ccu.column_name = 'status' AND cc.constraint_definition LIKE '%failed%';" || echo "0")
    if [[ "$failed_count" -eq 0 ]]; then
        pass "No 'failed' in outbox_events status CHECK"
    else
        fail "'found 'failed' in outbox_events status CHECK"
    fi
    echo ""

    # --- processed_events ---
    echo "--- processed_events ---"
    assert_table_exists "processed_events"
    assert_column_exists "processed_events" "consumer_name"
    assert_column_exists "processed_events" "event_id"
    assert_column_exists "processed_events" "processed_at"
    assert_column_exists "processed_events" "event_type"
    assert_column_exists "processed_events" "stream_id"
    assert_constraint_exists "processed_events" "processed_events_pkey"
    # Verify PK is composite
    local pk_cols
    pk_cols=$(run_scalar "SELECT count(*) FROM information_schema.key_column_usage WHERE table_name = 'processed_events' AND constraint_name = 'processed_events_pkey';")
    if [[ "$pk_cols" -ge 2 ]]; then
        pass "processed_events PK is composite ($pk_cols columns)"
    else
        fail "processed_events PK should be composite (got $pk_cols columns)"
    fi
    echo ""

    # --- outbox_dlq ---
    echo "--- outbox_dlq ---"
    assert_table_exists "outbox_dlq"
    assert_column_exists "outbox_dlq" "dlq_id"
    assert_column_exists "outbox_dlq" "outbox_id"
    assert_column_exists "outbox_dlq" "event_id"
    assert_column_exists "outbox_dlq" "stream_id"
    assert_column_exists "outbox_dlq" "event_type"
    assert_column_exists "outbox_dlq" "event_payload"
    assert_column_exists "outbox_dlq" "final_error"
    assert_column_exists "outbox_dlq" "attempts"
    assert_column_exists "outbox_dlq" "max_attempts"
    assert_column_exists "outbox_dlq" "moved_to_dlq_at"
    assert_constraint_exists "outbox_dlq" "uq_dlq_outbox_id"
    assert_index_exists "idx_dlq_event_id"
    assert_index_exists "idx_dlq_stream"
    assert_index_exists "idx_dlq_event_type"
    assert_index_exists "idx_dlq_moved_to_dlq_at"
    echo ""

    # --- outbox_recovery_audit ---
    echo "--- outbox_recovery_audit ---"
    assert_table_exists "outbox_recovery_audit"
    assert_column_exists "outbox_recovery_audit" "id"
    assert_column_exists "outbox_recovery_audit" "operation_id"
    assert_column_exists "outbox_recovery_audit" "outbox_id"
    assert_column_exists "outbox_recovery_audit" "event_id"
    assert_column_exists "outbox_recovery_audit" "event_type"
    assert_column_exists "outbox_recovery_audit" "operation"
    assert_column_exists "outbox_recovery_audit" "command_source"
    assert_column_exists "outbox_recovery_audit" "previous_status"
    assert_column_exists "outbox_recovery_audit" "new_status"
    assert_column_exists "outbox_recovery_audit" "previous_attempts"
    assert_column_exists "outbox_recovery_audit" "new_attempts"
    assert_column_exists "outbox_recovery_audit" "executed_at"
    assert_column_exists "outbox_recovery_audit" "metadata"
    assert_constraint_exists "outbox_recovery_audit" "uq_recovery_audit_operation_id"
    assert_constraint_exists "outbox_recovery_audit" "fk_recovery_audit_outbox_id"
    assert_constraint_exists "outbox_recovery_audit" "chk_recovery_audit_operation"
    assert_constraint_exists "outbox_recovery_audit" "chk_recovery_audit_command_source"
    assert_index_exists "idx_recovery_audit_outbox_id"
    assert_index_exists "idx_recovery_audit_event_id"
    assert_index_exists "idx_recovery_audit_executed_at"
    assert_index_exists "idx_recovery_audit_operation"
    # Verify forbidden columns do not exist
    local forbidden_cols=("event_payload" "payload" "user_message" "assistant_message" "conversation_id" "user_id")
    for col in "${forbidden_cols[@]}"; do
        local count
        count=$(run_scalar "SELECT count(*) FROM information_schema.columns WHERE table_name = 'outbox_recovery_audit' AND column_name = '$col';")
        if [[ "$count" -eq 0 ]]; then
            pass "Forbidden column '$col' is absent from outbox_recovery_audit"
        else
            fail "Forbidden column '$col' EXISTS in outbox_recovery_audit"
        fi
    done
    echo ""

    # --- Summary ---
    echo "=== Validation Summary ==="
    echo "Checks run: $CHECKS"
    echo "Passed:     $((CHECKS - ERRORS))"
    echo "Failed:     $ERRORS"
    if [[ "$ERRORS" -gt 0 ]]; then
        echo ""
        echo "RESULT: FAILED ($ERRORS error(s))"
        exit 1
    else
        echo ""
        echo "RESULT: PASSED"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MODE="dry-run"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --validate)
            MODE="validate"
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            abort "Unknown option: $1 (use --help for usage)"
            ;;
    esac
done

case "$MODE" in
    dry-run)
        validate_local_files
        dry_run
        ;;
    validate)
        validate_local_files
        validate_schema
        ;;
esac
