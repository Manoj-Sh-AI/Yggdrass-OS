-- Connected data, step 2 (planning/connected-data-proposal.md). EXPAND only; safe to run twice.
-- 1. note_refs carries the note's sensitivity, never null. Existing rows start as
--    'unknown', which every rule below treats exactly like 'restricted'; migrate_hosted then
--    copies the real value from brain.notes (admin step: this migration's role cannot read
--    the brain schema), and the app keeps it current each time it observes a note.
-- 2. The api schema: read-only views that apply the sensitivity rule once. Agents, briefings
--    and MCP-facing code read these, not the tables. (The schema itself is created by
--    Database.migrate or, on a hosted database, by migrate_hosted as admin.)

ALTER TABLE app.note_refs ADD COLUMN IF NOT EXISTS sensitivity text NOT NULL DEFAULT 'unknown';
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint
                WHERE conname = 'note_refs_sensitivity_values' AND conrelid = 'app.note_refs'::regclass) THEN
  ALTER TABLE app.note_refs ADD CONSTRAINT note_refs_sensitivity_values
   CHECK (sensitivity IN ('normal', 'restricted', 'unknown'));
 END IF;
END $$;

-- The one rule: only a note known to be normal shows its slug, title or revision.
CREATE OR REPLACE FUNCTION app.note_visible(note_sensitivity text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$ SELECT note_sensitivity = 'normal' $$;

CREATE OR REPLACE VIEW api.note_refs WITH (security_barrier) AS
SELECT id,
       CASE WHEN app.note_visible(sensitivity) THEN external_id END AS slug,
       CASE WHEN app.note_visible(sensitivity) THEN observed_title ELSE 'Sensitive note' END AS title,
       CASE WHEN app.note_visible(sensitivity) THEN observed_revision END AS revision,
       sensitivity,
       last_verified_at
FROM app.note_refs;

-- A readable label for any link end, masked for notes by the same rule.
CREATE OR REPLACE FUNCTION app.link_end_label(end_kind text, end_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $$
 SELECT CASE end_kind
  WHEN 'note' THEN (SELECT CASE WHEN app.note_visible(sensitivity) THEN observed_title ELSE 'Sensitive note' END
                    FROM app.note_refs WHERE id = end_id)
  WHEN 'task' THEN (SELECT title FROM app.tasks WHERE id = end_id)
  WHEN 'event' THEN (SELECT title FROM app.calendar_events WHERE id = end_id)
  WHEN 'availability' THEN (SELECT title FROM app.availability_windows WHERE id = end_id)
  WHEN 'date_item' THEN (SELECT title FROM app.calendar_date_items WHERE id = end_id)
 END
$$;

CREATE OR REPLACE VIEW api.links WITH (security_barrier) AS
SELECT id, from_kind, from_id, app.link_end_label(from_kind, from_id) AS from_label,
       verb, to_kind, to_id, app.link_end_label(to_kind, to_id) AS to_label,
       origin, approved, created_at
FROM app.links
WHERE status = 'active';

-- The notes linked to a thing (task, event, ...), whichever direction the verb points.
CREATE OR REPLACE VIEW api.note_links WITH (security_barrier) AS
SELECT l.id AS link_id,
       CASE WHEN l.from_kind = 'note' THEN l.to_kind ELSE l.from_kind END AS thing_kind,
       CASE WHEN l.from_kind = 'note' THEN l.to_id ELSE l.from_id END AS thing_id,
       l.verb, n.id AS note_ref_id, n.slug, n.title, n.sensitivity
FROM app.links l
JOIN api.note_refs n ON n.id = CASE WHEN l.from_kind = 'note' THEN l.from_id ELSE l.to_id END
WHERE l.status = 'active' AND (l.from_kind = 'note' OR l.to_kind = 'note')
  AND NOT (l.from_kind = 'note' AND l.to_kind = 'note');

-- Search: only notes known to be normal exist here at all.
CREATE OR REPLACE VIEW api.note_search WITH (security_barrier) AS
SELECT id, slug, title FROM api.note_refs WHERE sensitivity = 'normal';
