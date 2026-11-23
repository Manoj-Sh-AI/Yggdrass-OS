-- The api schema itself is left in place: the app's migration 043 may own it.
DROP FUNCTION IF EXISTS api.brain_note_access(text);
DROP VIEW IF EXISTS api.brain_search;
DROP VIEW IF EXISTS api.brain_links;
DROP VIEW IF EXISTS api.brain_note_areas;
DROP VIEW IF EXISTS api.brain_note_bodies;
DROP VIEW IF EXISTS api.brain_notes;
DROP VIEW IF EXISTS api.brain_areas;
DROP FUNCTION IF EXISTS brain.masked_body(text);
DROP FUNCTION IF EXISTS brain.note_visible(text);
