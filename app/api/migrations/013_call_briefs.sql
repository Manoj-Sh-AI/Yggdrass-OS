-- Voice reminders: a briefing prepared in the background before a scheduled call.
-- Keyed by the schedule's versioned source key, so a moved or edited item gets a new
-- briefing and a stale one is never read. Application data only; never Brain tables.
CREATE TABLE app.call_briefs (
 source_key text PRIMARY KEY CHECK(source_key <> ''),
 title text NOT NULL DEFAULT '',
 due_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('ready','failed')),
 summary text NOT NULL DEFAULT '',
 context text NOT NULL DEFAULT '',
 sources jsonb NOT NULL DEFAULT '[]',
 failure text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX call_briefs_due ON app.call_briefs(due_at);
