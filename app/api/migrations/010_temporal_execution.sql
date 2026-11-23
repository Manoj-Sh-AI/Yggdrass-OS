-- Operational execution metadata only; no Brain or canonical work-table changes.
CREATE TABLE app.agent_executions (
 run_id uuid PRIMARY KEY REFERENCES app.agent_runs(id) ON DELETE CASCADE,
 workflow_id text NOT NULL UNIQUE,
 state text NOT NULL DEFAULT 'pending'
 CHECK(state IN ('pending','running','waiting','completed','failed','cancelled')),
 version integer NOT NULL DEFAULT 1,
 cancellation_requested boolean NOT NULL DEFAULT false,
 context jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX agent_execution_pending ON app.agent_executions(state,created_at);
CREATE INDEX agent_decision_identity ON app.agent_proposals(decision_key) WHERE decision_key IS NOT NULL;
CREATE TABLE app.agent_effects (
 run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
 ordinal integer NOT NULL CHECK(ordinal>=0),
 agent_id text NOT NULL, kind text NOT NULL,
 fingerprint text NOT NULL,
 state text NOT NULL CHECK(state IN ('started','completed','failed','uncertain')),
 result jsonb, error text NOT NULL DEFAULT '',
 started_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 PRIMARY KEY(run_id,ordinal)
);
-- Private durable receipts. Owner traces deliberately omit result/context bodies.
