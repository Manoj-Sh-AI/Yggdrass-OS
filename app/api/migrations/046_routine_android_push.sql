-- Android routine reminders, enrolled independently from incoming calls (Codex, 2026-11-22;
-- numbered 046 by Claude, 2026-11-25). Numbered after 044 on purpose: 044 attaches the change
-- capture to every app table that exists when it runs, and the hosted database already ran
-- 044. Coming after it, this migration attaches the capture itself, so a fresh database and
-- the hosted one end up the same. On a database without the events stream (no 044), it skips.
-- Push tokens never reach app.events: the capture records only the row id and the kind.
CREATE TABLE app.routine_android_devices (
 id uuid PRIMARY KEY,
 push_token text UNIQUE NOT NULL CHECK (length(push_token) BETWEEN 10 AND 4096),
 session_hash text NOT NULL REFERENCES app.sessions(token_hash) ON DELETE CASCADE,
 password_fingerprint text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.android_routine_deliveries (
 id uuid PRIMARY KEY,
 device uuid NOT NULL REFERENCES app.routine_android_devices(id) ON DELETE CASCADE,
 dedupe_key text NOT NULL,
 kind text NOT NULL,
 escalation_id uuid,
 expires_at timestamptz NOT NULL,
 action_expires_at timestamptz NOT NULL,
 status text NOT NULL DEFAULT 'pending'
   CHECK (status IN ('pending','sending','accepted','failed','expired')),
 UNIQUE (device,dedupe_key)
);
CREATE INDEX android_routine_due ON app.android_routine_deliveries(expires_at)
 WHERE status IN ('pending','sending');

DO $$
BEGIN
 IF to_regprocedure('app.events_capture()') IS NOT NULL THEN
  CREATE OR REPLACE TRIGGER events_capture AFTER INSERT OR UPDATE OR DELETE
   ON app.routine_android_devices FOR EACH ROW EXECUTE FUNCTION app.events_capture();
  CREATE OR REPLACE TRIGGER events_capture AFTER INSERT OR UPDATE OR DELETE
   ON app.android_routine_deliveries FOR EACH ROW EXECUTE FUNCTION app.events_capture();
 END IF;
END $$;
