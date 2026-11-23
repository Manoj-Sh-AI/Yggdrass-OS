-- Connected data, step 3 (planning/connected-data-proposal.md): one ordered, append-only
-- change stream. EXPAND only; safe to run twice.
-- Every write to every app table appends an event IN THE SAME TRANSACTION (a row trigger),
-- so a write cannot commit without its event and an event cannot outlive a rolled-back
-- write. Tables that would only add noise are listed, with a reason, in
-- app.event_exclusions; a test fails if any app table is neither captured nor listed.
-- Events carry ids, never content.

CREATE TABLE IF NOT EXISTS app.events (
 seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tx xid8 NOT NULL DEFAULT pg_current_xact_id(),   -- the writing transaction (cursor order)
 at timestamptz NOT NULL DEFAULT now(),
 kind text NOT NULL CHECK (kind ~ '^[a-z_]+\.(insert|update|delete)$'),
 subject_kind text NOT NULL,                        -- the table written
 subject_key text,                                  -- the row's id, when it has one
 actor text NOT NULL,                               -- the database role, or the app's yggdras.actor
 sensitivity text CHECK (sensitivity IS NULL OR sensitivity IN ('normal','restricted','unknown'))
);
CREATE INDEX IF NOT EXISTS events_tx_seq ON app.events (tx, seq);
CREATE INDEX IF NOT EXISTS events_subject ON app.events (subject_kind, subject_key);

-- A reader's position: the last (tx, seq) it has handled.
CREATE TABLE IF NOT EXISTS app.event_cursors (
 consumer text PRIMARY KEY CHECK (consumer ~ '^[a-z0-9_.:-]{1,80}$'),
 last_tx xid8 NOT NULL DEFAULT '0'::xid8,
 last_seq bigint NOT NULL DEFAULT 0,
 updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.event_exclusions (
 table_name text PRIMARY KEY,
 reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 300)
);
INSERT INTO app.event_exclusions (table_name, reason) VALUES
 ('events', 'The stream itself.'),
 ('event_cursors', 'Readers'' positions in the stream, not data.'),
 ('event_exclusions', 'This list.'),
 ('schema_migrations', 'Migration bookkeeping.'),
 ('sessions', 'Sign-in sessions: bookkeeping on every request, and security-sensitive.'),
 ('login_guard', 'Sign-in rate limiting: bookkeeping, and security-sensitive.'),
 ('conductor_runs', 'Heartbeat every 20 s; every change of a run is already in conductor_events.'),
 ('conductor_events', 'Already an append-only, ordered event log of each conductor run.'),
 ('voice_worker_lease', 'The voice worker''s heartbeat lease.'),
 ('scheduled_jobs', 'Scheduler claims and retries on every sweep; the work it does is captured where it writes.'),
 ('scheduled_job_attempts', 'Scheduler bookkeeping of each attempt.')
ON CONFLICT (table_name) DO NOTHING;

-- Append-only, for everyone (the owner included).
CREATE OR REPLACE FUNCTION app.events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'app.events is append-only.' USING ERRCODE = 'insufficient_privilege';
END $$;
CREATE OR REPLACE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON app.events
 FOR EACH ROW EXECUTE FUNCTION app.events_append_only();

-- The capture: runs as the owner, so the app role needs no write right on the stream.
CREATE OR REPLACE FUNCTION app.events_capture() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $$
DECLARE r jsonb;
BEGIN
 r := to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
 INSERT INTO app.events (kind, subject_kind, subject_key, actor, sensitivity)
 VALUES (TG_TABLE_NAME || '.' || lower(TG_OP), TG_TABLE_NAME,
         coalesce(r ->> 'id', r ->> 'sequence', r ->> 'seq'),
         coalesce(nullif(current_setting('yggdras.actor', true), ''), session_user::text),
         CASE WHEN TG_TABLE_NAME = 'note_refs' THEN r ->> 'sensitivity' END);
 RETURN NULL;  -- AFTER trigger: the result is ignored
END $$;

-- Attach to every app table not excluded. A later migration that adds a table attaches
-- its own (or lists it), and the coverage test enforces that.
DO $$
DECLARE t text;
BEGIN
 FOR t IN
  SELECT tablename FROM pg_tables
  WHERE schemaname = 'app'
    AND tablename NOT IN (SELECT table_name FROM app.event_exclusions)
 LOOP
  EXECUTE format('CREATE OR REPLACE TRIGGER events_capture AFTER INSERT OR UPDATE OR DELETE ON app.%I '
                 'FOR EACH ROW EXECUTE FUNCTION app.events_capture()', t);
 END LOOP;
END $$;

-- What agents read: ids and kinds, never content.
CREATE OR REPLACE VIEW api.events WITH (security_barrier) AS
SELECT seq, at, kind, subject_kind, subject_key, actor, sensitivity FROM app.events;
