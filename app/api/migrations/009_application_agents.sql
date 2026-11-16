-- Execution history belongs to the application, never to Brain memory.
CREATE TABLE app.agent_note_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 note_ref_id uuid NOT NULL REFERENCES app.note_refs(id),
 slug text NOT NULL, revision text NOT NULL,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','completed','failed','superseded')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX agent_note_revision ON app.agent_note_events(note_ref_id,revision);
CREATE TABLE app.agent_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 chat_request_id uuid UNIQUE REFERENCES app.chat_requests(id) ON DELETE CASCADE,
 note_event_id uuid UNIQUE REFERENCES app.agent_note_events(id),
 handoff_id uuid UNIQUE REFERENCES app.note_handoffs(id),
 agent_id text NOT NULL CHECK(agent_id IN ('yggdras','lia','tasks','calendar')),
 model_id text NOT NULL, state text NOT NULL DEFAULT 'queued'
 CHECK(state IN ('queued','running','completed','failed','cancelled')),
 lease uuid, lease_until timestamptz, error text NOT NULL DEFAULT '',
 result jsonb, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 CHECK(num_nonnulls(chat_request_id,note_event_id,handoff_id)=1)
);
CREATE INDEX agent_run_pending ON app.agent_runs(state,created_at,id);
CREATE TABLE app.agent_steps (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
 agent_id text NOT NULL, ordinal integer NOT NULL,
 state text NOT NULL CHECK(state IN ('started','completed')),
 input_tokens integer NOT NULL DEFAULT 0 CHECK(input_tokens>=0),
 output_tokens integer NOT NULL DEFAULT 0 CHECK(output_tokens>=0),
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
 UNIQUE(run_id,ordinal)
);
CREATE TABLE app.agent_proposals (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
 ordinal integer NOT NULL, agent_id text NOT NULL, payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','dismissed','superseded')),
 version integer NOT NULL DEFAULT 1, result jsonb,
 decision_key uuid, decision_fingerprint text,
 created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz,
 UNIQUE(run_id,ordinal)
);
CREATE INDEX agent_proposal_pending ON app.agent_proposals(state,created_at,id);
-- Prepare an observation before crossing the separate Brain HTTP transaction.
-- A restart can reconcile an interrupted save without storing a second note body.
CREATE TABLE app.agent_write_intents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_instance uuid,
 slug text NOT NULL, before_revision text,
 operation text NOT NULL CHECK(operation IN ('create','save','undo')),
 state text NOT NULL DEFAULT 'prepared' CHECK(state IN ('prepared','completed','rejected','failed')),
 observed_event_id uuid REFERENCES app.agent_note_events(id),
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX agent_write_intent_pending ON app.agent_write_intents(state,created_at,id);
