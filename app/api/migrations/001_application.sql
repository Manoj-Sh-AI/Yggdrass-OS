CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.schema_migrations (
    version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.sessions (
    token_hash text PRIMARY KEY, csrf text NOT NULL, password_fingerprint text NOT NULL,
    expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.login_guard (
    id integer PRIMARY KEY CHECK (id = 1), failures integer NOT NULL DEFAULT 0,
    window_start timestamptz NOT NULL DEFAULT now(), locked_until timestamptz
);
INSERT INTO app.login_guard (id) VALUES (1);
CREATE TABLE app.routines (
    id text PRIMARY KEY, title text NOT NULL, description text NOT NULL, goal text NOT NULL,
    scheduled_date date NOT NULL, window_start time NOT NULL, window_end time NOT NULL,
    timezone text NOT NULL, expected_minutes integer NOT NULL CHECK (expected_minutes > 0),
    status text NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','completed')),
    progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    started_at timestamptz, completed_at timestamptz, updated_at timestamptz,
    CHECK (window_end > window_start),
    CHECK ((status = 'not_started' AND progress = 0 AND started_at IS NULL AND completed_at IS NULL)
      OR (status = 'in_progress' AND started_at IS NOT NULL AND completed_at IS NULL)
      OR (status = 'completed' AND progress = 100 AND started_at IS NOT NULL AND completed_at IS NOT NULL))
);
CREATE TABLE app.routine_progress (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    routine_id text NOT NULL REFERENCES app.routines(id),
    percent integer NOT NULL CHECK (percent BETWEEN 0 AND 100), at timestamptz NOT NULL
);
CREATE TABLE app.tasks (
    id uuid PRIMARY KEY, title text NOT NULL CHECK (length(trim(title)) > 0),
    description text NOT NULL DEFAULT '', area text NOT NULL, due_date date NOT NULL,
    done boolean NOT NULL DEFAULT false, note_ref text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
