-- App-owned journal, reviews and receipts. Knowledge itself remains in Lia's store.
CREATE TABLE app.journal_entries (
 id uuid PRIMARY KEY, local_date date NOT NULL, source text NOT NULL CHECK(source IN ('voice','text','system')),
 kind text NOT NULL, text text NOT NULL, meta jsonb NOT NULL DEFAULT '{}',
 supersedes_id uuid UNIQUE REFERENCES app.journal_entries(id), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX daily_journal_day ON app.journal_entries(local_date,created_at,id);
CREATE FUNCTION app.immutable_journal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Journal entries are append-only; insert a correction'; END $$;
CREATE TRIGGER journal_append_only BEFORE UPDATE OR DELETE ON app.journal_entries
 FOR EACH ROW EXECUTE FUNCTION app.immutable_journal();

CREATE TABLE app.daily_reviews (
 local_date date PRIMARY KEY, entry_id uuid NOT NULL REFERENCES app.journal_entries(id),
 outcome text NOT NULL, tomorrow text NOT NULL, next_steps jsonb NOT NULL
);
CREATE TABLE app.daily_lessons (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), local_date date NOT NULL, slot smallint NOT NULL CHECK(slot BETWEEN 1 AND 2),
 evidence_id uuid NOT NULL REFERENCES app.journal_entries(id), text text NOT NULL,
 status text NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate','active','retired')),
 confirmed_at timestamptz, review_due date, UNIQUE(local_date,slot)
);
CREATE TABLE app.daily_briefs (
 kind text NOT NULL, for_date date NOT NULL, source_ref text NOT NULL DEFAULT '',
 input_hash text NOT NULL, text text NOT NULL, context text NOT NULL, details jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(kind,for_date,source_ref)
);
CREATE TABLE app.daily_inputs (
 for_date date NOT NULL, timezone text NOT NULL, settings_hash text NOT NULL, weather jsonb, news jsonb NOT NULL,
 status jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(for_date,timezone)
);
CREATE TABLE app.daily_filing_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), for_date date NOT NULL,
 input_hash text NOT NULL UNIQUE, entry_ids uuid[] NOT NULL,
 state text NOT NULL CHECK(state IN ('running','proposed','failed')), lease uuid NOT NULL,
 locked_until timestamptz NOT NULL, proposal jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.daily_filing_actions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES app.daily_filing_runs(id),
 ordinal int NOT NULL, target text NOT NULL, fact text NOT NULL, evidence jsonb NOT NULL,
 state text NOT NULL CHECK(state IN ('proposed','applying','applied','rejected','undoing','reverted','uncertain')),
 created_at timestamptz NOT NULL DEFAULT now(), applied_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(),
 undo_ref jsonb, UNIQUE(run_id,ordinal)
);
