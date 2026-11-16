-- Revision at the moment a note was attached to work; never a copied note body.
-- Existing links have unknown provenance and remain NULL rather than invented.
ALTER TABLE app.task_note_links ADD COLUMN source_revision text
 CHECK(source_revision IS NULL OR length(source_revision) BETWEEN 1 AND 200);
ALTER TABLE app.event_note_links ADD COLUMN source_revision text
 CHECK(source_revision IS NULL OR length(source_revision) BETWEEN 1 AND 200);
