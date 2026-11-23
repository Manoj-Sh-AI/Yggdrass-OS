-- Connected data, step 1 (planning/connected-data-proposal.md): one typed, sourced link
-- table. EXPAND only. The four *_note_links tables stay, keep their foreign keys and stay
-- the writers' target; triggers mirror every insert/update/delete into app.links in the
-- same transaction (writers write to both) until step 5 retires them. Safe to run twice.

-- The fixed verb list (proposal, decision 1). Inverses read the link the other way.
CREATE TABLE IF NOT EXISTS app.link_verbs (
 verb text PRIMARY KEY CHECK (verb ~ '^[a-z_]{2,40}$'),
 inverse text NOT NULL UNIQUE CHECK (inverse ~ '^[a-z_]{2,40}$'),
 meaning text NOT NULL CHECK (length(meaning) BETWEEN 1 AND 200)
);
INSERT INTO app.link_verbs (verb, inverse, meaning) VALUES
 ('about', 'subject_of', 'A thing concerns a note: the note is its context.'),
 ('source_of', 'sourced_from', 'A note is where a thing came from.'),
 ('result_of', 'resulted_in', 'A note was produced by a thing.'),
 ('blocks', 'blocked_by', 'One thing must finish before another can start.'),
 ('part_of', 'has_part', 'One thing is a piece of a larger one.'),
 ('evidence_for', 'supported_by', 'One thing backs up another.'),
 ('scheduled_for', 'scheduled_as', 'A thing is planned into a time slot.'),
 ('follows_up', 'followed_up_by', 'One thing continues another.')
ON CONFLICT (verb) DO NOTHING;

CREATE TABLE IF NOT EXISTS app.links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 from_kind text NOT NULL CHECK (from_kind IN ('task','event','availability','date_item','note')),
 from_id uuid NOT NULL,
 verb text NOT NULL REFERENCES app.link_verbs(verb),
 to_kind text NOT NULL CHECK (to_kind IN ('task','event','availability','date_item','note')),
 to_id uuid NOT NULL,
 -- who or what made it: manual = Manoj, agent, import = copied from an old link table
 origin text NOT NULL CHECK (origin IN ('manual','agent','import','rule','connector')),
 origin_ref text CHECK (origin_ref IS NULL OR length(origin_ref) BETWEEN 1 AND 200),
 approved boolean NOT NULL DEFAULT false,
 approved_by text CHECK (approved_by IS NULL OR length(approved_by) BETWEEN 1 AND 100),
 approved_at timestamptz,
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
 retired_at timestamptz,
 source_revision text CHECK (source_revision IS NULL OR length(source_revision) BETWEEN 1 AND 200),
 -- the old row this mirrors, until step 5 (contract)
 legacy_table text CHECK (legacy_table IN
   ('task_note_links','event_note_links','availability_note_links','date_item_note_links')),
 legacy_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((legacy_table IS NULL) = (legacy_id IS NULL)),
 CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
 CHECK (approved = (approved_at IS NOT NULL)),
 CHECK (from_kind <> to_kind OR from_id <> to_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS links_legacy ON app.links (legacy_table, legacy_id)
 WHERE legacy_table IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS links_active_edge ON app.links (from_kind, from_id, verb, to_kind, to_id)
 WHERE status = 'active';
CREATE INDEX IF NOT EXISTS links_from ON app.links (from_kind, from_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS links_to ON app.links (to_kind, to_id) WHERE status = 'active';

-- Polymorphic ends cannot have foreign keys: a trigger checks the row exists instead.
CREATE OR REPLACE FUNCTION app.link_end_exists(end_kind text, end_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $$
 SELECT CASE end_kind
  WHEN 'task' THEN EXISTS (SELECT 1 FROM app.tasks WHERE id = end_id)
  WHEN 'event' THEN EXISTS (SELECT 1 FROM app.calendar_events WHERE id = end_id)
  WHEN 'availability' THEN EXISTS (SELECT 1 FROM app.availability_windows WHERE id = end_id)
  WHEN 'date_item' THEN EXISTS (SELECT 1 FROM app.calendar_date_items WHERE id = end_id)
  WHEN 'note' THEN EXISTS (SELECT 1 FROM app.note_refs WHERE id = end_id)
  ELSE false END
$$;

CREATE OR REPLACE FUNCTION app.links_check_ends() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $$
BEGIN
 IF NOT app.link_end_exists(NEW.from_kind, NEW.from_id)
    OR NOT app.link_end_exists(NEW.to_kind, NEW.to_id) THEN
  RAISE EXCEPTION 'A link end does not exist (% %, % %).',
   NEW.from_kind, NEW.from_id, NEW.to_kind, NEW.to_id USING ERRCODE = 'foreign_key_violation';
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER links_check_ends BEFORE INSERT OR UPDATE OF from_kind, from_id, to_kind, to_id
 ON app.links FOR EACH ROW EXECUTE FUNCTION app.links_check_ends();

-- One old row as a typed link. The old `kind` becomes a verb with a direction:
--   context -> (thing) about (note)        source -> (note) source_of (thing)
--   result  -> (note) result_of (thing)
CREATE OR REPLACE FUNCTION app.legacy_link(legacy_table text, old_row jsonb,
 OUT from_kind text, OUT from_id uuid, OUT verb text, OUT to_kind text, OUT to_id uuid)
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE thing_kind text; thing_column text; thing uuid; note uuid;
BEGIN
 SELECT k, c INTO thing_kind, thing_column FROM (VALUES
  ('task_note_links', 'task', 'task_id'), ('event_note_links', 'event', 'event_id'),
  ('availability_note_links', 'availability', 'availability_id'),
  ('date_item_note_links', 'date_item', 'date_item_id')) AS m(t, k, c) WHERE m.t = legacy_table;
 IF thing_kind IS NULL THEN RAISE EXCEPTION 'Unknown link table %.', legacy_table; END IF;
 thing := (old_row ->> thing_column)::uuid;
 note := (old_row ->> 'note_ref_id')::uuid;
 CASE old_row ->> 'kind'
  WHEN 'context' THEN from_kind := thing_kind; from_id := thing; verb := 'about'; to_kind := 'note'; to_id := note;
  WHEN 'source' THEN from_kind := 'note'; from_id := note; verb := 'source_of'; to_kind := thing_kind; to_id := thing;
  WHEN 'result' THEN from_kind := 'note'; from_id := note; verb := 'result_of'; to_kind := thing_kind; to_id := thing;
  ELSE RAISE EXCEPTION 'Unknown link kind %.', old_row ->> 'kind';
 END CASE;
END $$;

-- Writers write to both: every change to an old link table is mirrored, same transaction.
CREATE OR REPLACE FUNCTION app.links_mirror_legacy() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $$
DECLARE l record; r jsonb;
BEGIN
 IF TG_OP = 'DELETE' THEN
  UPDATE app.links SET status = 'retired', retired_at = now()
   WHERE legacy_table = TG_TABLE_NAME AND legacy_id = OLD.id AND status = 'active';
  RETURN OLD;
 END IF;
 r := to_jsonb(NEW);
 SELECT * INTO l FROM app.legacy_link(TG_TABLE_NAME, r);
 IF TG_OP = 'INSERT' THEN
  INSERT INTO app.links (from_kind, from_id, verb, to_kind, to_id, origin, origin_ref,
    approved, approved_by, approved_at, source_revision, legacy_table, legacy_id, created_at)
  VALUES (l.from_kind, l.from_id, l.verb, l.to_kind, l.to_id, 'import', 'app.' || TG_TABLE_NAME,
    true, 'import', NEW.created_at, r ->> 'source_revision', TG_TABLE_NAME, NEW.id, NEW.created_at);
 ELSE
  UPDATE app.links SET from_kind = l.from_kind, from_id = l.from_id, verb = l.verb,
    to_kind = l.to_kind, to_id = l.to_id, source_revision = r ->> 'source_revision'
   WHERE legacy_table = TG_TABLE_NAME AND legacy_id = NEW.id;
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE TRIGGER links_mirror AFTER INSERT OR UPDATE OR DELETE ON app.task_note_links
 FOR EACH ROW EXECUTE FUNCTION app.links_mirror_legacy();
CREATE OR REPLACE TRIGGER links_mirror AFTER INSERT OR UPDATE OR DELETE ON app.event_note_links
 FOR EACH ROW EXECUTE FUNCTION app.links_mirror_legacy();
CREATE OR REPLACE TRIGGER links_mirror AFTER INSERT OR UPDATE OR DELETE ON app.availability_note_links
 FOR EACH ROW EXECUTE FUNCTION app.links_mirror_legacy();
CREATE OR REPLACE TRIGGER links_mirror AFTER INSERT OR UPDATE OR DELETE ON app.date_item_note_links
 FOR EACH ROW EXECUTE FUNCTION app.links_mirror_legacy();

-- Backfill by copy (the old rows stay). ON CONFLICT makes a second run a no-op.
INSERT INTO app.links (from_kind, from_id, verb, to_kind, to_id, origin, origin_ref,
  approved, approved_by, approved_at, source_revision, legacy_table, legacy_id, created_at)
SELECT l.from_kind, l.from_id, l.verb, l.to_kind, l.to_id, 'import', 'app.' || o.t,
  true, 'import', o.created_at, o.source_revision, o.t, o.id, o.created_at
FROM (
  SELECT 'task_note_links' AS t, id, created_at, source_revision, to_jsonb(x) AS r FROM app.task_note_links x
  UNION ALL SELECT 'event_note_links', id, created_at, source_revision, to_jsonb(x) FROM app.event_note_links x
  UNION ALL SELECT 'availability_note_links', id, created_at, source_revision, to_jsonb(x) FROM app.availability_note_links x
  UNION ALL SELECT 'date_item_note_links', id, created_at, source_revision, to_jsonb(x) FROM app.date_item_note_links x
) AS o, LATERAL app.legacy_link(o.t, o.r) AS l
ON CONFLICT (legacy_table, legacy_id) WHERE legacy_table IS NOT NULL DO NOTHING;
