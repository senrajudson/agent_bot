-- ============================================================================
-- Outbox Recovery Audit: append-only log for future recovery operations
-- Idempotent: safe to run multiple times.
-- Schema: EDD Prompt 23 — Safe Recovery Execution Prerequisites
-- ============================================================================

CREATE TABLE IF NOT EXISTS outbox_recovery_audit (
    id BIGSERIAL PRIMARY KEY,

    -- Operation identity
    operation_id UUID NOT NULL,
    outbox_id BIGINT NOT NULL,
    event_id UUID NOT NULL,
    event_type TEXT NOT NULL,

    -- Operation context
    operation TEXT NOT NULL,
    command_source TEXT NOT NULL,

    -- State transition
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    previous_attempts INTEGER NOT NULL,
    new_attempts INTEGER NOT NULL,

    -- Authorization
    ticket TEXT,
    reason TEXT,
    requested_by TEXT,

    -- Timing
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Error (only for failed operations)
    sanitized_error TEXT,

    -- Operational metadata (worker_id, hostname, etc.)
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Unique constraint
    CONSTRAINT uq_recovery_audit_operation_id UNIQUE (operation_id),

    -- FK to outbox_events
    CONSTRAINT fk_recovery_audit_outbox_id FOREIGN KEY (outbox_id)
        REFERENCES outbox_events(outbox_id) ON DELETE RESTRICT,

    -- CHECK: operation type
    CONSTRAINT chk_recovery_audit_operation CHECK (
        operation IN ('recovery_execute', 'recovery_dry_run', 'recovery_blocked')
    ),

    -- CHECK: command source
    CONSTRAINT chk_recovery_audit_command_source CHECK (
        command_source IN ('cli', 'worker', 'api', 'unknown')
    ),

    -- CHECK: status aligned with outbox_events.status
    CONSTRAINT chk_recovery_audit_previous_status CHECK (
        previous_status IN ('pending', 'locked', 'dispatched', 'dead_letter')
    ),
    CONSTRAINT chk_recovery_audit_new_status CHECK (
        new_status IN ('pending', 'locked', 'dispatched', 'dead_letter')
    ),

    -- CHECK: at least one of ticket or reason
    CONSTRAINT chk_recovery_audit_ticket_or_reason CHECK (
        ticket IS NOT NULL OR reason IS NOT NULL
    ),

    -- CHECK: non-negative attempts
    CONSTRAINT chk_recovery_audit_previous_attempts CHECK (previous_attempts >= 0),
    CONSTRAINT chk_recovery_audit_new_attempts CHECK (new_attempts >= 0),

    -- CHECK: non-empty strings
    CONSTRAINT chk_recovery_audit_event_type_nonempty CHECK (event_type <> ''),
    CONSTRAINT chk_recovery_audit_operation_nonempty CHECK (operation <> ''),
    CONSTRAINT chk_recovery_audit_command_source_nonempty CHECK (command_source <> ''),
    CONSTRAINT chk_recovery_audit_previous_status_nonempty CHECK (previous_status <> ''),
    CONSTRAINT chk_recovery_audit_new_status_nonempty CHECK (new_status <> ''),

    -- CHECK: positive outbox_id
    CONSTRAINT chk_recovery_audit_outbox_id_pos CHECK (outbox_id > 0)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_recovery_audit_outbox_id
    ON outbox_recovery_audit (outbox_id);

CREATE INDEX IF NOT EXISTS idx_recovery_audit_event_id
    ON outbox_recovery_audit (event_id);

CREATE INDEX IF NOT EXISTS idx_recovery_audit_executed_at
    ON outbox_recovery_audit (executed_at);

CREATE INDEX IF NOT EXISTS idx_recovery_audit_operation
    ON outbox_recovery_audit (operation);

-- ============================================================================
-- Append-only trigger: blocks UPDATE and DELETE
-- TRUNCATE is NOT blocked by this trigger (see RUNBOOK)
-- ============================================================================

CREATE OR REPLACE FUNCTION outbox_recovery_audit_block_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'outbox_recovery_audit is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_outbox_recovery_audit_no_modify ON outbox_recovery_audit;
CREATE TRIGGER trg_outbox_recovery_audit_no_modify
    BEFORE UPDATE OR DELETE ON outbox_recovery_audit
    FOR EACH STATEMENT
    EXECUTE FUNCTION outbox_recovery_audit_block_update_delete();
