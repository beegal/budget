ALTER TABLE users ADD COLUMN created_at VARCHAR(32);

UPDATE users
SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP);

UPDATE schema_version SET version = 2;
