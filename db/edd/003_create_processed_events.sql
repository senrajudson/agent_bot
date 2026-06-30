-- ============================================================================
-- Processed Events: per-consumer idempotency dedup
-- Idempotent: safe to run multiple times.
-- Schema: EDD Prompt 2 — Schema Postgres
-- ============================================================================

CREATE TABLE IF NOT EXISTS processed_events (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Context
    event_type TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    stream_version BIGINT,
    outbox_id BIGINT,
    handler_name TEXT,
    metadata JSONB,

    -- PK: each consumer tracks its own dedup by event_id
    PRIMARY KEY (consumer_name, event_id),

    -- Prevent empty strings
    CONSTRAINT chk_processed_consumer_nonempty CHECK (consumer_name <> ''),
    CONSTRAINT chk_processed_event_type_nonempty CHECK (event_type <> ''),
    CONSTRAINT chk_processed_stream_nonempty CHECK (stream_id <> ''),

    -- Version/outbox must be non-negative when present
    CONSTRAINT chk_processed_stream_version CHECK (
        stream_version IS NULL OR stream_version >= 0
    ),
    CONSTRAINT chk_processed_outbox_id CHECK (
        outbox_id IS NULL OR outbox_id > 0
    )
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_processed_event_id
    ON processed_events (event_id);

CREATE INDEX IF NOT EXISTS idx_processed_consumer_time
    ON processed_events (consumer_name, processed_at);

CREATE INDEX IF NOT EXISTS idx_processed_event_type
    ON processed_events (event_type);

CREATE INDEX IF NOT EXISTS idx_processed_stream
    ON processed_events (stream_id, stream_version);

CREATE INDEX IF NOT EXISTS idx_processed_outbox_id
    ON processed_events (outbox_id)
    WHERE outbox_id IS NOT NULL;
