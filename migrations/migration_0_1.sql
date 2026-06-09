CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

INSERT INTO schema_version(version)
SELECT 0
WHERE NOT EXISTS (SELECT 1 FROM schema_version);

ALTER TABLE transactions ADD COLUMN transfer_pair_id INTEGER;

ALTER TABLE transactions ADD COLUMN transfer_auto INTEGER NOT NULL DEFAULT 0;

UPDATE schema_version SET version = 1;
