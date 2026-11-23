-- N1 (planning/cli-inventory.md): read-only api.* views over the brain, for the approved
-- read commands (brain tree, note, version, search). Same pattern as app migration 043:
-- the sensitivity rule lives once, here in SQL, and nothing reads the brain tables for an
-- agent. The rule matches migrate_hosted.backfill_sensitivity: a note whose sensitivity is
-- 'high' is restricted; every other note is normal. Archived notes are never shown.
-- Restricted notes: the tree shows a masked row (area kept, so the shelf count stays true);
-- every other view leaves them out completely, links to and from them included.
DO $$
BEGIN
 IF to_regnamespace('api') IS NULL THEN CREATE SCHEMA api; END IF;
END $$;

CREATE OR REPLACE FUNCTION brain.note_visible(note_sensitivity text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$ SELECT lower(coalesce(note_sensitivity, '')) <> 'high' $$;

-- A normal note's text can name a restricted one ("Taught by [[ada-lin]]"). Every wikilink
-- to a restricted note, [[slug]] or [[slug|label]] or [[slug#part]], becomes [[sensitive-note]].
-- Plain words (a person's first name written without a link) cannot be found this way.
CREATE OR REPLACE FUNCTION brain.masked_body(note_body text) RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, brain AS $$
DECLARE
 hidden text;
 result text := note_body;
BEGIN
 FOR hidden IN SELECT slug FROM brain.notes WHERE NOT brain.note_visible(sensitivity) LOOP
  result := regexp_replace(
   result,
   '\[\[' || regexp_replace(hidden, '([^a-zA-Z0-9_])', '\\\1', 'g') || '([|#][^\]]*)?\]\]',
   '[[sensitive-note]]', 'gi');
 END LOOP;
 RETURN result;
END $$;

CREATE OR REPLACE VIEW api.brain_areas WITH (security_barrier) AS
SELECT area_code, name, sort_order FROM brain.areas;

-- The tree, and the version token: a restricted note is a masked row.
CREATE OR REPLACE VIEW api.brain_notes WITH (security_barrier) AS
SELECT CASE WHEN brain.note_visible(n.sensitivity) THEN n.slug END AS slug,
       CASE WHEN brain.note_visible(n.sensitivity) THEN n.title ELSE 'Sensitive note' END AS title,
       CASE WHEN brain.note_visible(n.sensitivity) THEN n.type END AS type,
       n.area_code,
       CASE WHEN brain.note_visible(n.sensitivity) THEN n.shelf_no END AS shelf_no,
       -- a parent is named only when it is live and normal too
       CASE WHEN brain.note_visible(n.sensitivity) AND p.archived_at IS NULL
                 AND brain.note_visible(p.sensitivity) THEN n.parent_slug END AS parent_slug,
       CASE WHEN brain.note_visible(n.sensitivity) THEN n.version END AS version,
       CASE WHEN brain.note_visible(n.sensitivity) THEN 'normal' ELSE 'restricted' END AS sensitivity
FROM brain.notes n
LEFT JOIN brain.notes p ON p.slug = n.parent_slug
WHERE n.archived_at IS NULL;

-- One note with its text: normal live notes only.
CREATE OR REPLACE VIEW api.brain_note_bodies WITH (security_barrier) AS
SELECT n.slug, n.title, n.type, n.area_code, n.description, n.status, n.version,
       brain.masked_body(b.body) AS body
FROM brain.notes n JOIN brain.note_bodies b ON b.slug = n.slug
WHERE n.archived_at IS NULL AND brain.note_visible(n.sensitivity);

CREATE OR REPLACE VIEW api.brain_note_areas WITH (security_barrier) AS
SELECT a.slug, a.area_code, a.ord
FROM brain.note_areas a JOIN brain.notes n ON n.slug = a.slug
WHERE n.archived_at IS NULL AND brain.note_visible(n.sensitivity);

-- Links and mentions: only when both ends are live and normal.
CREATE OR REPLACE VIEW api.brain_links WITH (security_barrier) AS
SELECT r.from_slug, r.verb, v.inverse, r.to_slug, r.kind
FROM brain.relationships r
JOIN brain.verbs v ON v.verb = r.verb
JOIN brain.notes a ON a.slug = r.from_slug
JOIN brain.notes b ON b.slug = r.to_slug
WHERE a.archived_at IS NULL AND b.archived_at IS NULL
  AND brain.note_visible(a.sensitivity) AND brain.note_visible(b.sensitivity);

-- Full-text search: normal live notes only, over the masked text (so searching a restricted
-- slug finds nothing); otherwise the same document as brain_db.api.search.
CREATE OR REPLACE VIEW api.brain_search WITH (security_barrier) AS
SELECT n.slug, n.title, n.type, n.area_code, n.version,
       to_tsvector('simple', brain.masked_body(b.body)) AS document
FROM brain.notes n JOIN brain.note_bodies b ON b.slug = n.slug
WHERE n.archived_at IS NULL AND brain.note_visible(n.sensitivity);

-- Lets a reader tell "not allowed" from "not found" for one exact slug, without showing
-- anything else about a restricted note: 'normal', 'restricted', or NULL (no live note).
CREATE OR REPLACE FUNCTION api.brain_note_access(note_slug text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, brain AS $$
 SELECT CASE WHEN brain.note_visible(sensitivity) THEN 'normal' ELSE 'restricted' END
 FROM brain.notes WHERE slug = note_slug AND archived_at IS NULL
$$;
