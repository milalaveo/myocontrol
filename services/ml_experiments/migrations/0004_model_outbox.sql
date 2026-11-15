CREATE TABLE ml_experiments.outbox_events (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL UNIQUE REFERENCES ml_experiments.source_lda_runs(id) ON DELETE RESTRICT,
    event_type varchar(100) NOT NULL CHECK (event_type = 'ModelPublished'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at timestamptz
);
CREATE INDEX outbox_unpublished ON ml_experiments.outbox_events(created_at) WHERE published_at IS NULL;
