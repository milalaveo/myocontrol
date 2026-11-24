ALTER TABLE data_protocol.recordings
ADD COLUMN channel_count smallint NOT NULL DEFAULT 4 CHECK (channel_count BETWEEN 1 AND 6);

ALTER TABLE data_protocol.client_publications
ADD CONSTRAINT client_publication_operator_local_unique UNIQUE (operator_id, local_recording_id);

COMMENT ON COLUMN data_protocol.recordings.channel_count IS 'Actual stored sample width. Legacy ingestion and ML remain four-channel; desktop acquisition never pads missing channels.';
COMMENT ON CONSTRAINT client_publication_operator_local_unique ON data_protocol.client_publications IS 'Operator-owned local part identity survives desktop token/client rotation without duplicate publications.';
