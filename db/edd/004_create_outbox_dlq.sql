-- ============================================================================
-- Outbox DLQ: terminal failures from outbox dispatcher
-- Idempotent: safe to run multiple times.
-- Schema: EDD Prompt 2 — Schema Postgres
-- ============================================================================

CREATE TABLE IF NOT EXISTS outbox_dlq (
    dlq_id BIGSERIAL PRIMARY KEY,

    -- Reference to originating outbox entry
    outbox_id BIGINT NOT NULL,
    event_id UUID NOT NULL,
    stream_id TEXT NOT NULL,
    stream_version BIGINT NOT NULL,
    aggregate_id TEXT,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Final error state
    final_error TEXT NOT NULL,
    final_error_class TEXT,

    -- Attempt history
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,

    -- Metadata
    moved_to_dlq_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    original_created_at TIMESTAMPTZ,
    correlation_id TEXT,
    causation_id TEXT,
    metadata JSONB,

    -- Constraints
    CONSTRAINT uq_dlq_outbox_id UNIQUE (outbox_id),

    CONSTRAINT chk_dlq_outbox_id_pos CHECK (outbox_id > 0),
    CONSTRAINT chk_dlq_event_type_nonempty CHECK (event_type <> ''),
    CONSTRAINT chk_dlq_stream_nonempty CHECK (stream_id <> ''),
    CONSTRAINT chk_dlq_stream_version CHECK (stream_version >= 0),
    CONSTRAINT chk_dlq_attempts CHECK (attempts >= 0),
    CONSTRAINT chk_dlq_max_attempts_pos CHECK (max_attempts > 0),
    CONSTRAINT chk_dlq_attempts_gte_max CHECK (attempts >= max_attempts),
    CONSTRAINT chk_dlq_final_error_nonempty CHECK (final_error <> '')
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dlq_event_id
    ON outbox_dlq (event_id);

CREATE INDEX IF NOT EXISTS idx_dlq_stream
    ON outbox_dlq (stream_id, stream_version);

CREATE INDEX IF NOT EXISTS idx_dlq_event_type
    ON outbox_dlq (event_type);

CREATE INDEX IF NOT EXISTS idx_dlq_moved_to_dlq_at
    ON outbox_dlq (moved_to_dlq_at);

CREATE INDEX IF NOT EXISTS idx_dlq_aggregate_id
    ON outbox_dlq (aggregate_id)
    WHERE aggregate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dlq_correlation_id
    ON outbox_dlq (correlation_id)
    WHERE correlation_id IS NOT NULL;
