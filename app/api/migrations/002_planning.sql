-- Additive application planning only. Existing tasks and sample routines are preserved.
CREATE TABLE app.planning_goals (
 id uuid PRIMARY KEY, title text NOT NULL CHECK(length(trim(title))>0),
 description text NOT NULL DEFAULT '', version integer NOT NULL DEFAULT 1
);
CREATE TABLE app.projects (
 id uuid PRIMARY KEY, title text NOT NULL CHECK(length(trim(title))>0),
 description text NOT NULL DEFAULT '', goal_id uuid REFERENCES app.planning_goals(id),
 version integer NOT NULL DEFAULT 1
);
CREATE TABLE app.routine_templates (
 id uuid PRIMARY KEY, title text NOT NULL, description text NOT NULL DEFAULT '',
 objective text NOT NULL, frequency text NOT NULL CHECK(frequency IN ('daily','weekly')),
 area text NOT NULL DEFAULT 'health',
 interval_count integer NOT NULL DEFAULT 1 CHECK(interval_count BETWEEN 1 AND 52),
 weekdays integer[] NOT NULL DEFAULT '{0,1,2,3,4,5,6}',
 starts_on date NOT NULL, ends_on date, timezone text NOT NULL,
 window_start time NOT NULL, window_end time NOT NULL,
 expected_minutes integer NOT NULL CHECK(expected_minutes BETWEEN 1 AND 1440),
 priority integer NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3),
 goal_id uuid REFERENCES app.planning_goals(id), essential boolean NOT NULL DEFAULT false,
 active boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 CHECK(ends_on IS NULL OR ends_on>=starts_on), CHECK(window_end>window_start)
);
ALTER TABLE app.tasks ALTER COLUMN due_date DROP NOT NULL;
ALTER TABLE app.tasks ADD COLUMN objective text NOT NULL DEFAULT '';
UPDATE app.tasks SET objective=title;
ALTER TABLE app.tasks ADD COLUMN deadline_at timestamptz;
ALTER TABLE app.tasks ADD COLUMN timezone text NOT NULL DEFAULT 'Europe/Berlin';
ALTER TABLE app.tasks ADD COLUMN priority integer NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3);
ALTER TABLE app.tasks ADD COLUMN estimated_minutes integer NOT NULL DEFAULT 30 CHECK(estimated_minutes BETWEEN 1 AND 1440);
ALTER TABLE app.tasks ADD COLUMN effort text NOT NULL DEFAULT 'unspecified' CHECK(effort IN ('unspecified','light','moderate','demanding'));
ALTER TABLE app.tasks ADD COLUMN tags text[] NOT NULL DEFAULT '{}';
ALTER TABLE app.tasks ADD COLUMN goal_id uuid REFERENCES app.planning_goals(id);
ALTER TABLE app.tasks ADD COLUMN project_id uuid REFERENCES app.projects(id);
ALTER TABLE app.tasks ADD COLUMN parent_id uuid REFERENCES app.tasks(id);
ALTER TABLE app.tasks ADD COLUMN template_id uuid REFERENCES app.routine_templates(id);
ALTER TABLE app.tasks ADD COLUMN occurrence_date date;
ALTER TABLE app.tasks ADD COLUMN occurrence_edited boolean NOT NULL DEFAULT false;
ALTER TABLE app.tasks ADD COLUMN routine_window_start time;
ALTER TABLE app.tasks ADD COLUMN routine_window_end time;
ALTER TABLE app.tasks ADD COLUMN state text NOT NULL DEFAULT 'todo' CHECK(state IN ('todo','in_progress','paused','completed','skipped'));
ALTER TABLE app.tasks ADD COLUMN progress integer NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100);
ALTER TABLE app.tasks ADD COLUMN completed_at timestamptz;
ALTER TABLE app.tasks ADD COLUMN version integer NOT NULL DEFAULT 1;
UPDATE app.tasks SET state='completed',progress=100,completed_at=updated_at WHERE done;
CREATE UNIQUE INDEX routine_occurrence_unique ON app.tasks(template_id,occurrence_date);
CREATE INDEX task_planning_due ON app.tasks(due_date,done);
CREATE TABLE app.task_dependencies (
 task_id uuid NOT NULL REFERENCES app.tasks(id), depends_on uuid NOT NULL REFERENCES app.tasks(id),
 PRIMARY KEY(task_id,depends_on), CHECK(task_id<>depends_on)
);
CREATE TABLE app.routine_exceptions (
 template_id uuid NOT NULL REFERENCES app.routine_templates(id), occurrence_date date NOT NULL,
 PRIMARY KEY(template_id,occurrence_date)
);
CREATE TABLE app.calendar_events (
 id uuid PRIMARY KEY, title text NOT NULL CHECK(length(trim(title))>0), description text NOT NULL DEFAULT '',
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, timezone text NOT NULL,
 cancelled boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1,
 CHECK(ends_at>starts_at)
);
CREATE TABLE app.execution_blocks (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES app.tasks(id),
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, timezone text NOT NULL,
 reason text NOT NULL, automatic boolean NOT NULL DEFAULT false,
 cancelled boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1,
 CHECK(ends_at>starts_at)
);
CREATE INDEX block_planning_range ON app.execution_blocks(starts_at,ends_at) WHERE NOT cancelled;
CREATE INDEX block_task ON app.execution_blocks(task_id);
CREATE INDEX event_planning_range ON app.calendar_events(starts_at,ends_at) WHERE NOT cancelled;
CREATE TABLE app.execution_sessions (
 id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES app.tasks(id),
 block_id uuid REFERENCES app.execution_blocks(id), started_at timestamptz NOT NULL,
 ended_at timestamptz, outcome text CHECK(outcome IN ('paused','completed')),
 expected_minutes integer NOT NULL, scheduled_start timestamptz,
 CHECK(ended_at IS NULL OR ended_at>=started_at)
);
CREATE UNIQUE INDEX one_running_execution ON app.execution_sessions((true)) WHERE ended_at IS NULL;
CREATE INDEX session_task ON app.execution_sessions(task_id,started_at);
CREATE TABLE app.task_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, task_id uuid NOT NULL REFERENCES app.tasks(id),
 kind text NOT NULL, detail jsonb NOT NULL DEFAULT '{}', at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX history_task ON app.task_history(task_id,id DESC);
CREATE TABLE app.daily_plans (
 day date NOT NULL, timezone text NOT NULL, available_minutes integer NOT NULL CHECK(available_minutes BETWEEN 0 AND 1440),
 energy text NOT NULL DEFAULT '', focus text NOT NULL DEFAULT '', sleep text NOT NULL DEFAULT '',
 intention text NOT NULL DEFAULT '', reflection text NOT NULL DEFAULT '',
 confirmed_at timestamptz, reviewed_at timestamptz, version integer NOT NULL DEFAULT 1,
 PRIMARY KEY(day,timezone)
);
CREATE TABLE app.reminder_requests (
 id text PRIMARY KEY, task_id uuid NOT NULL REFERENCES app.tasks(id),
 block_id uuid REFERENCES app.execution_blocks(id), kind text NOT NULL,
 eligible_at timestamptz NOT NULL, acknowledged_at timestamptz
);
CREATE INDEX reminder_eligibility ON app.reminder_requests(eligible_at) WHERE acknowledged_at IS NULL;
CREATE TABLE app.planning_commands (
 id uuid PRIMARY KEY, fingerprint text NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
