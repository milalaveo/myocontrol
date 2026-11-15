CREATE SCHEMA data_protocol;
CREATE TABLE data_protocol.participants (
    id uuid PRIMARY KEY,
    pseudonym varchar(100) NOT NULL UNIQUE,
    CONSTRAINT participants_pseudonym_format CHECK (pseudonym ~ '^[A-Za-z0-9_-]{1,100}$')
);
