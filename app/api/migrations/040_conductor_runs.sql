-- The conductor (chat orchestrator): one row per run and its append-only event log.
-- Application data only; the brain is reached through its HTTP API, never from here.
-- Additive: no existing table changes.

CREATE TABLE app.conductor_runs (
 id uuid PRIMARY KEY,
 conversation_id uuid REFERENCES app.chat_conversations(id) ON DELETE CASCADE,
 request text NOT NULL CHECK(length(request) BETWEEN 1 AND 100000),
 status text NOT NULL CHECK(status IN ('running','waiting','completed','failed','cancelled','interrupted')),
 mode text NOT NULL CHECK(mode IN ('answering','planning','executing')),
 state jsonb NOT NULL,                 -- snapshot after last_seq (validated RunState)
 last_seq bigint NOT NULL DEFAULT 0 CHECK(last_seq >= 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conductor_runs_conversation ON app.conductor_runs(conversation_id, created_at DESC);
CREATE INDEX conductor_runs_unfinished ON app.conductor_runs(status) WHERE status IN ('running','waiting');

-- seq is dense per run (1, 2, 3 ...): a client resumes with "everything after seq N".
CREATE TABLE app.conductor_events (
 run_id uuid NOT NULL REFERENCES app.conductor_runs(id) ON DELETE CASCADE,
 seq bigint NOT NULL CHECK(seq > 0),
 op text NOT NULL CHECK(op IN ('set','append-text')),
 path jsonb NOT NULL CHECK(jsonb_typeof(path) = 'array'),
 value jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (run_id, seq)
);
