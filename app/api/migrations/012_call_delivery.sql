-- Call transport state belongs to the app, never Brain.
ALTER TABLE app.calls ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE app.calls ADD COLUMN request_key uuid UNIQUE;
ALTER TABLE app.calls ADD COLUMN answer_session text NOT NULL DEFAULT '';
ALTER TABLE app.calls ADD COLUMN expires_at timestamptz NOT NULL DEFAULT now()+interval '45 seconds';
ALTER TABLE app.calls ADD COLUMN media_state text NOT NULL DEFAULT 'idle'
 CHECK(media_state IN ('idle','connecting','connected','reconnecting','failed','ended'));
ALTER TABLE app.calls ADD COLUMN simulated boolean NOT NULL DEFAULT false;
ALTER TABLE app.calls ADD COLUMN failure text NOT NULL DEFAULT '';
ALTER TABLE app.devices ADD COLUMN session_hash text NOT NULL DEFAULT '';
ALTER TABLE app.devices ADD COLUMN revoked_at timestamptz;
ALTER TABLE app.devices ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE app.devices ADD COLUMN session_expires_at timestamptz;
ALTER TABLE app.devices ADD COLUMN password_fingerprint text NOT NULL DEFAULT '';
CREATE TABLE app.call_preferences (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 scheduled boolean NOT NULL DEFAULT true,
 calendar_starts boolean NOT NULL DEFAULT true,
 calendar_ends boolean NOT NULL DEFAULT true,
 routines boolean NOT NULL DEFAULT true,
 timezone text NOT NULL DEFAULT 'Europe/Berlin',
 quiet_start time NOT NULL DEFAULT '22:00', quiet_end time NOT NULL DEFAULT '08:00',
 version integer NOT NULL DEFAULT 1
);
CREATE TABLE app.call_events (
 seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 call_id uuid NOT NULL REFERENCES app.calls(id),
 state text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.call_delivery (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 call_id uuid NOT NULL REFERENCES app.calls(id), device_id uuid NOT NULL REFERENCES app.devices(id),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','sending','sent','failed','expired')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 event_state text NOT NULL DEFAULT 'ringing',
 UNIQUE(call_id,device_id,event_state)
);
CREATE TABLE app.voice_worker_lease (
 name text PRIMARY KEY, seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.call_commands (
 key uuid PRIMARY KEY, fingerprint text NOT NULL, response jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.call_reviews (
 id uuid PRIMARY KEY, call_id uuid NOT NULL REFERENCES app.calls(id),
 payload jsonb NOT NULL, state text NOT NULL DEFAULT 'waiting'
 CHECK(state IN ('waiting','accepted','dismissed')),
 version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app.call_schedules ADD COLUMN call_id uuid REFERENCES app.calls(id);
ALTER TABLE app.call_schedules ADD COLUMN source_type text;
ALTER TABLE app.call_schedules ADD COLUMN source_id uuid;
ALTER TABLE app.call_schedules ADD COLUMN source_revision integer;
CREATE INDEX call_delivery_pending ON app.call_delivery(state,available_at);
CREATE INDEX call_events_recent ON app.call_events(created_at);
