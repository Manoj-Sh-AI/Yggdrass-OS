-- Yggdras's orchestration memory, notifications and calls. Application data only: nothing
-- here reads or writes the brain (the brain is reached only through its HTTP API).

-- Phase 4: one row per orchestrated request, and Manoj's reaction to each card.
CREATE TABLE app.yggdras_runs (
 id uuid PRIMARY KEY,
 source text NOT NULL CHECK(source IN ('chat','voice','mobile','notification','connector')),
 request text NOT NULL,
 route text NOT NULL CHECK(route IN ('quick','single','multi')),
 plan jsonb,
 steps jsonb NOT NULL DEFAULT '[]',   -- per step: agent, model, skills, tools, result
 usage jsonb NOT NULL DEFAULT '[]',   -- per model call: agent, model, tokens, cost
 cost_usd numeric(12,6) NOT NULL DEFAULT 0,
 latency_ms integer NOT NULL DEFAULT 0,
 checker_stopped boolean NOT NULL DEFAULT false,
 cards integer NOT NULL DEFAULT 0,
 error text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX yggdras_runs_recent ON app.yggdras_runs(created_at DESC);

CREATE TABLE app.yggdras_feedback (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id uuid REFERENCES app.yggdras_runs(id) ON DELETE SET NULL,
 card_id text NOT NULL,
 tool text NOT NULL,
 decision text NOT NULL CHECK(decision IN ('approved','rejected','undone')),
 correction text NOT NULL DEFAULT '' CHECK(length(correction) <= 2000),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX yggdras_feedback_recent ON app.yggdras_feedback(created_at DESC);

-- Phase 5: registered devices (push) and the notifications that were sent.
CREATE TABLE app.devices (
 id uuid PRIMARY KEY,
 platform text NOT NULL CHECK(platform IN ('android','ios','web')),
 push_token text NOT NULL CHECK(length(push_token) BETWEEN 1 AND 4096),
 label text NOT NULL DEFAULT '' CHECK(length(label) <= 100),
 created_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(platform, push_token)
);

CREATE TABLE app.notifications (
 id uuid PRIMARY KEY,
 kind text NOT NULL CHECK(kind IN ('approval','call','time_critical','deadline')),
 title text NOT NULL CHECK(length(title) <= 120),
 body text NOT NULL DEFAULT '' CHECK(length(body) <= 500),
 dedupe_key text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_recent ON app.notifications(created_at DESC);
CREATE UNIQUE INDEX notifications_dedupe ON app.notifications(dedupe_key);

-- Phase 6: one call record from ringing to answered, declined or missed.
CREATE TABLE app.calls (
 id uuid PRIMARY KEY,
 direction text NOT NULL CHECK(direction IN ('inbound','outbound')), -- outbound: Yggdras rings
 reason text NOT NULL DEFAULT '' CHECK(length(reason) <= 300),
 state text NOT NULL DEFAULT 'ringing'
  CHECK(state IN ('ringing','answered','declined','missed','ended')),
 room text NOT NULL,
 answered_by text NOT NULL DEFAULT '',   -- the device or window that took it
 summary text NOT NULL DEFAULT '' CHECK(length(summary) <= 4000),
 created_at timestamptz NOT NULL DEFAULT now(),
 answered_at timestamptz,
 ended_at timestamptz
);
CREATE INDEX calls_recent ON app.calls(created_at DESC);

CREATE TABLE app.call_schedules (
 id uuid PRIMARY KEY,
 kind text NOT NULL CHECK(kind IN ('one_off','snooze','event_start','event_end','routine')),
 due_at timestamptz NOT NULL,
 reason text NOT NULL DEFAULT '' CHECK(length(reason) <= 300),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','rung','cancelled')),
 source_key text NOT NULL DEFAULT '',   -- the event or routine it came from (no duplicates)
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX call_schedules_due ON app.call_schedules(state, due_at);
CREATE UNIQUE INDEX call_schedules_source ON app.call_schedules(source_key) WHERE source_key <> '';
