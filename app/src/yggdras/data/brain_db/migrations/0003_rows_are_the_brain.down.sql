-- Roll back 0003. Rows of kind 'unlink' are dropped first (the old check doesn't allow them).

DROP TABLE IF EXISTS brain.manual;
DELETE FROM brain.changes WHERE kind = 'unlink';
ALTER TABLE brain.changes DROP CONSTRAINT changes_kind_check;
ALTER TABLE brain.changes ADD CONSTRAINT changes_kind_check
    CHECK (kind IN ('add', 'replace', 'remove', 'archive', 'restore'));
DROP INDEX IF EXISTS brain.changes_request_id_idx;
ALTER TABLE brain.changes
    DROP COLUMN IF EXISTS request_id,
    DROP COLUMN IF EXISTS section,
    DROP COLUMN IF EXISTS pos,
    DROP COLUMN IF EXISTS tag;
