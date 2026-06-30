-- ============================================================================
-- Outbox: durable queue for asynchronous event dispatch
-- Idempotent: safe to run multiple times.
-- Schema: EDD Prompt 2 — Schema Postgres
-- ============================================================================

CREATE TABLE IF NOT EXISTS outbox_events (
    outbox_id BIGSERIAL PRIMARY KEY,

    -- Event identity
    event_id UUID NOT NULL,
    stream_id TEXT NOT NULL,
    stream_version BIGINT NOT NULL,
    aggregate_id TEXT,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Provenance
    correlation_id TEXT,
    causation_id TEXT,
    metadata JSONB,

    -- Dispatch state
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Locking
    locked_by TEXT,
    locked_until TIMESTAMPTZ,

    -- Error tracking
    last_error TEXT,
    last_error_class TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dispatched_at TIMESTAMPTZ,
    dead_lettered_at TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT uq_outbox_event_id UNIQUE (event_id),

    CONSTRAINT chk_outbox_status CHECK (
        status IN ('pending', 'locked', 'dispatched', 'dead_letter')
    ),
    CONSTRAINT chk_outbox_attempts_nonneg CHECK (attempts >= 0),
    CONSTRAINT chk_outbox_max_attempts_pos CHECK (max_attempts > 0),
    CONSTRAINT chk_outbox_attempts_lte_max CHECK (attempts <= max_attempts),

    -- Lock invariant: locked status requires lock fields
    CONSTRAINT chk_outbox_lock_invariant CHECK (
        (status = 'locked') = (locked_by IS NOT NULL AND locked_until IS NOT NULL)
    ),

    -- Dispatch invariant: dispatched status requires dispatched_at
    CONSTRAINT chk_outbox_dispatch_invariant CHECK (
        (status = 'dispatched') = (dispatched_at IS NOT NULL)
    ),

    -- Dead-letter invariant: dead_letter status requires dead_lettered_at
    CONSTRAINT chk_outbox_dlq_invariant CHECK (
        (status = 'dead_letter') = (dead_lettered_at IS NOT NULL)
    )
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_outbox_status_available_at
    ON outbox_events (status, available_at);

CREATE INDEX IF NOT EXISTS idx_outbox_locked_until
    ON outbox_events (locked_until)
    WHERE status = 'locked';

CREATE INDEX IF NOT EXISTS idx_outbox_event_type
    ON outbox_events (event_type);

CREATE INDEX IF NOT EXISTS idx_outbox_stream
    ON outbox_events (stream_id, stream_version);

CREATE INDEX IF NOT EXISTS idx_outbox_aggregate_id
    ON outbox_events (aggregate_id)
    WHERE aggregate_id IS NOT NULL;
