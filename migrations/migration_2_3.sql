ALTER TABLE budget_schedule ADD COLUMN date VARCHAR(10);

UPDATE schema_version SET version = 3;
