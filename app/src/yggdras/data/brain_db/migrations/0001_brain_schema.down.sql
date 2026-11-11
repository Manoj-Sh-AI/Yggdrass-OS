-- Roll back 0001: drop every table and function it created. The `brain` schema itself and
-- the migration log stay (the migration runner owns them).

DROP TABLE IF EXISTS brain.map_cache;
DROP TABLE IF EXISTS brain.changes;
DROP TABLE IF EXISTS brain.dated_items;
DROP TABLE IF EXISTS brain.aliases;
DROP TABLE IF EXISTS brain.note_bodies;
DROP TABLE IF EXISTS brain.relationships;
DROP TABLE IF EXISTS brain.verbs;
ALTER TABLE IF EXISTS brain.areas DROP CONSTRAINT IF EXISTS areas_hub_slug_fkey;
DROP TABLE IF EXISTS brain.notes;
DROP TABLE IF EXISTS brain.areas;
DROP FUNCTION IF EXISTS brain.bump_note_version_from_body();
DROP FUNCTION IF EXISTS brain.bump_note_version();
