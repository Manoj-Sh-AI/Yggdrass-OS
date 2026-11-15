-- Receiving-side application contracts. No Brain tables, agent or interpreter.
CREATE TABLE app.note_handoffs (
 id uuid PRIMARY KEY, producer text NOT NULL, namespace text NOT NULL, external_identity text NOT NULL,
 slug text NOT NULL, revision text NOT NULL, sequence bigint NOT NULL CHECK(sequence>=0),
 lifecycle text NOT NULL CHECK(lifecycle IN ('active','archived','missing')),
 fingerprint text NOT NULL, payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','acknowledged','superseded')),
 received_at timestamptz NOT NULL DEFAULT now(), acknowledged_at timestamptz,
 UNIQUE(producer,namespace,external_identity,sequence)
);
CREATE INDEX note_handoff_pending ON app.note_handoffs(state,received_at,id);
CREATE TABLE app.workflow_sources (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 producer text NOT NULL, namespace text NOT NULL, external_identity text NOT NULL,
 note_ref_id uuid UNIQUE REFERENCES app.note_refs(id),
 slug text NOT NULL, revision text NOT NULL, sequence bigint NOT NULL CHECK(sequence>=0),
 lifecycle text NOT NULL CHECK(lifecycle IN ('active','archived','missing')),
 observed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(producer,namespace,external_identity)
);
CREATE TABLE app.workflow_changes (
 id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES app.workflow_sources(id),
 handoff_id uuid NOT NULL REFERENCES app.note_handoffs(id),
 source_sequence bigint NOT NULL, source_revision text NOT NULL,
 fingerprint text NOT NULL, payload jsonb NOT NULL, result jsonb NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_id,source_sequence)
);
CREATE TABLE app.workflow_bindings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid NOT NULL REFERENCES app.workflow_sources(id),
 commitment_identity text NOT NULL, entity_type text NOT NULL CHECK(entity_type IN ('task','event','date_item','availability')),
 entity_id uuid NOT NULL,
 task_id uuid GENERATED ALWAYS AS (CASE WHEN entity_type='task' THEN entity_id END) STORED REFERENCES app.tasks(id),
 event_id uuid GENERATED ALWAYS AS (CASE WHEN entity_type='event' THEN entity_id END) STORED REFERENCES app.calendar_events(id),
 date_item_id uuid GENERATED ALWAYS AS (CASE WHEN entity_type='date_item' THEN entity_id END) STORED REFERENCES app.calendar_date_items(id),
 availability_id uuid GENERATED ALWAYS AS (CASE WHEN entity_type='availability' THEN entity_id END) STORED REFERENCES app.availability_windows(id),
 applied_version integer NOT NULL, source_revision text NOT NULL,
 last_payload jsonb NOT NULL, UNIQUE(source_id,commitment_identity)
);
CREATE TABLE app.workflow_reviews (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), change_id uuid NOT NULL REFERENCES app.workflow_changes(id) DEFERRABLE INITIALLY DEFERRED,
 source_id uuid NOT NULL REFERENCES app.workflow_sources(id), source_sequence bigint NOT NULL,
 commitment_identity text NOT NULL, reason text NOT NULL, proposal jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','dismissed','superseded')),
 version integer NOT NULL DEFAULT 1, resolved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(change_id,commitment_identity)
);
CREATE INDEX workflow_review_pending ON app.workflow_reviews(state,created_at,id);
CREATE INDEX workflow_target ON app.workflow_bindings(entity_type,entity_id);
ALTER TABLE app.background_runs ADD COLUMN next_sequence bigint NOT NULL DEFAULT 1;
ALTER TABLE app.background_runs ADD COLUMN cancellation_requested_at timestamptz;
CREATE OR REPLACE VIEW app.operational_edges AS
 SELECT 'task:'||task_id AS source, 'note:'||note_ref_id AS target, kind AS relation FROM app.task_note_links
 UNION ALL SELECT 'event:'||event_id,'note:'||note_ref_id,kind FROM app.event_note_links
 UNION ALL SELECT 'date_item:'||date_item_id,'note:'||note_ref_id,kind FROM app.date_item_note_links
 UNION ALL SELECT 'availability:'||availability_id,'note:'||note_ref_id,kind FROM app.availability_note_links
 UNION ALL SELECT 'event:'||event_id,'task:'||task_id,'associated_with' FROM app.event_task_links
 UNION ALL SELECT 'task:'||id,'goal:'||goal_id,'advances' FROM app.tasks WHERE goal_id IS NOT NULL
 UNION ALL SELECT 'task:'||id,'project:'||project_id,'belongs_to' FROM app.tasks WHERE project_id IS NOT NULL
 UNION ALL SELECT 'project:'||id,'goal:'||goal_id,'advances' FROM app.projects WHERE goal_id IS NOT NULL
 UNION ALL SELECT 'task:'||id,'task:'||parent_id,'part_of' FROM app.tasks WHERE parent_id IS NOT NULL
 UNION ALL SELECT 'task:'||task_id,'task:'||depends_on,'depends_on' FROM app.task_dependencies
 UNION ALL SELECT 'task:'||id,'routine:'||template_id,'instance_of' FROM app.tasks WHERE template_id IS NOT NULL
 UNION ALL SELECT 'task:'||task_id,'block:'||id,'scheduled_as' FROM app.execution_blocks WHERE NOT cancelled
 UNION ALL SELECT 'task:'||task_id,'session:'||id,'performed_as' FROM app.execution_sessions
 UNION ALL SELECT 'task:'||task_id,'background_run:'||id,'runs_in_background' FROM app.background_runs WHERE task_id IS NOT NULL;
