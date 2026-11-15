CREATE TABLE recognition.model_events (
    event_id uuid PRIMARY KEY,
    model_run_id uuid NOT NULL,
    manifest_id uuid NOT NULL,
    correlation_id varchar(64) NOT NULL,
    received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX model_events_by_model ON recognition.model_events(model_run_id);
