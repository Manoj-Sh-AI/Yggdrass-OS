-- 0003: the database is the brain (D44). Each change line knows its request, its section and
-- its place, so Undo can rebuild a note exactly; the manual lives here too.

-- request_id: one Lia request (one transaction): what Undo reverses.
-- section:    the heading the line sat under ('frontmatter', '## Facts', ...; 'note' for a
--             whole note created, archived or restored).
-- pos:        the line's index in the note after the change (where Undo puts the old text).
-- tag:        a superseded fact's History tag ("until: 2026-11-12", "wrong: <reason>").
ALTER TABLE brain.changes
    ADD COLUMN request_id text,
    ADD COLUMN section    text,
    ADD COLUMN pos        integer,
    ADD COLUMN tag        text;
CREATE INDEX changes_request_id_idx ON brain.changes (request_id);

-- unlink: a link line taken out (kept, so it can be undone). remove stays for erased facts.
ALTER TABLE brain.changes DROP CONSTRAINT changes_kind_check;
ALTER TABLE brain.changes ADD CONSTRAINT changes_kind_check
    CHECK (kind IN ('add', 'replace', 'remove', 'archive', 'restore', 'unlink'));

-- The manual Lia reads (taxonomy.md, node.md), so no file is needed after the switch.
CREATE TABLE brain.manual (
    name text PRIMARY KEY,
    text text NOT NULL
);
