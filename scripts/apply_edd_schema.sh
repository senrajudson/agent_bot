#!/usr/bin/env bash
# ============================================================================
# apply_edd_schema.sh — Apply EDD schema SQLs in order
# Idempotent: safe to run multiple times.
# Manual: never runs automatically.
# Dry-run by default; use --apply to execute.
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
)

PSQL_BIN="${PSQL_BIN:-psql}"

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Apply EDD schema SQL files in order (001 → 002 → 003 → 004).

Options:
  --apply     Actually apply SQL files (default: dry-run only)
  --help, -h  Show this help message

Modes:
  Dry-run (default):
    Shows which files would be applied, in which order.
    Nothing is executed.

  Apply (--apply):
    Executes psql against EVENT_STORE_POSTGRES_DSN.
    EVENT_STORE_POSTGRES_DSN must be set in the environment.

Environment variables:
  EVENT_STORE_POSTGRES_DSN  PostgreSQL connection string (required for --apply)
  PSQL_BIN                  Path to psql binary (default: psql)

Notes:
  - This script does NOT start Docker or create databases.
  - This script does NOT read .env files.
  - Each SQL file uses CREATE TABLE IF NOT EXISTS (idempotent).
  - Re-running is safe.

EOF
    exit 0
}

abort() {
    echo "ERROR: $*" >&2
    exit 1
}

validate_files() {
    local missing=0
    for f in "${SQL_FILES[@]}"; do
        if [[ ! -f "$f" ]]; then
            echo "ERROR: File not found: $f" >&2
            missing=1
        fi
    done
    if [[ "$missing" -eq 1 ]]; then
        abort "One or more required SQL files are missing."
    fi
}

dry_run() {
    echo "=== EDD Schema: Dry Run ==="
    echo ""
    echo "Files to apply (in order):"
    for i in "${!SQL_FILES[@]}"; do
        local idx=$((i + 1))
        local f="${SQL_FILES[$i]}"
        local rel="${f#$REPO_ROOT/}"
        echo "  $idx. $rel"
    done
    echo ""
    echo "Nothing was executed."
    echo "To apply, re-run with: $0 --apply"
    echo ""
    echo "Prerequisites:"
    echo "  - EVENT_STORE_POSTGRES_DSN must be set"
    echo "  - psql must be available (or set PSQL_BIN)"
}

apply_schema() {
    echo "=== EDD Schema: Apply ==="
    echo ""

    # Validate DSN
    if [[ -z "${EVENT_STORE_POSTGRES_DSN:-}" ]]; then
        abort "EVENT_STORE_POSTGRES_DSN is not set. Export it before running with --apply."
    fi

    # Validate psql exists
    if ! command -v "$PSQL_BIN" &>/dev/null; then
        abort "psql not found at: $PSQL_BIN"
    fi

    # Validate all files exist
    validate_files

    # Apply each file
    for i in "${!SQL_FILES[@]}"; do
        local idx=$((i + 1))
        local f="${SQL_FILES[$i]}"
        local rel="${f#$REPO_ROOT/}"

        echo "[$idx/${#SQL_FILES[@]}] Applying: $rel"
        "$PSQL_BIN" "$EVENT_STORE_POSTGRES_DSN" -v ON_ERROR_STOP=1 -f "$f"
        echo ""
    done

    echo "=== EDD Schema: Done ==="
    echo "${#SQL_FILES[@]} file(s) applied successfully."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MODE="dry-run"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            MODE="apply"
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
        validate_files
        dry_run
        ;;
    apply)
        apply_schema
        ;;
esac
