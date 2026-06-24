-- Event Store: append-only table for domain events
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS event_store_events (
    event_id UUID PRIMARY KEY,
    stream_id TEXT NOT NULL,
    stream_version BIGINT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    correlation_id TEXT,
    causation_id TEXT,
    conversation_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ux_event_store_stream_version UNIQUE (stream_id, stream_version)
);

CREATE INDEX IF NOT EXISTS ix_event_store_events_stream_id
    ON event_store_events (stream_id, stream_version);

CREATE INDEX IF NOT EXISTS ix_event_store_events_correlation_id
    ON event_store_events (correlation_id)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_event_store_events_event_type
    ON event_store_events (event_type);

CREATE INDEX IF NOT EXISTS ix_event_store_events_occurred_at
    ON event_store_events (occurred_at);
