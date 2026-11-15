-- Application-owned references and operational relationships. No Brain DDL or data import.
CREATE TABLE app.note_refs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source text NOT NULL DEFAULT 'brain' CHECK(source='brain'),
 external_id text NOT NULL CHECK(external_id ~ '^[a-zA-Z0-9_-]{1,200}$'),
 observed_title text NOT NULL, observed_revision text NOT NULL CHECK(length(observed_revision)>0),
 last_verified_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(source,external_id)
);
CREATE TABLE app.task_note_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 task_id uuid NOT NULL REFERENCES app.tasks(id),
 note_ref_id uuid NOT NULL REFERENCES app.note_refs(id),
 kind text NOT NULL CHECK(kind IN ('source','context','result')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(task_id,note_ref_id,kind)
);
CREATE INDEX task_note_reverse ON app.task_note_links(note_ref_id,task_id);
CREATE TABLE app.event_note_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 event_id uuid NOT NULL REFERENCES app.calendar_events(id),
 note_ref_id uuid NOT NULL REFERENCES app.note_refs(id),
 kind text NOT NULL CHECK(kind IN ('source','context','result')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(event_id,note_ref_id,kind)
);
CREATE INDEX event_note_reverse ON app.event_note_links(note_ref_id,event_id);
CREATE TABLE app.event_task_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 event_id uuid NOT NULL REFERENCES app.calendar_events(id),
 task_id uuid NOT NULL REFERENCES app.tasks(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(event_id,task_id)
);
CREATE INDEX event_task_reverse ON app.event_task_links(task_id,event_id);

-- Unattended wall time is independent of human execution_sessions/focus totals.
-- This is storage only: no runner, dispatch, agent or task-completion trigger.
CREATE TABLE app.background_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 task_id uuid REFERENCES app.tasks(id),
 provider text NOT NULL CHECK(length(trim(provider)) BETWEEN 1 AND 100),
 external_run_id text NOT NULL CHECK(length(trim(external_run_id)) BETWEEN 1 AND 200),
 label text NOT NULL CHECK(length(trim(label)) BETWEEN 1 AND 180),
 state text NOT NULL CHECK(state IN ('queued','running','succeeded','failed','cancelled')),
 created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, ended_at timestamptz,
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 UNIQUE(provider,external_run_id),
 CHECK(started_at IS NULL OR started_at>=created_at),
 CHECK(ended_at IS NULL OR ended_at>=coalesce(started_at,created_at)),
 CHECK((state='queued' AND started_at IS NULL AND ended_at IS NULL)
    OR (state='running' AND started_at IS NOT NULL AND ended_at IS NULL)
    OR (state='succeeded' AND started_at IS NOT NULL AND ended_at IS NOT NULL)
    OR (state IN ('failed','cancelled') AND ended_at IS NOT NULL))
);
CREATE INDEX background_run_task ON app.background_runs(task_id,created_at DESC);

-- An append-only transaction journal, not a broker, agent, or global commit-order stream.
CREATE TABLE app.workspace_changes (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 event_id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
 entity_type text NOT NULL, entity_id text NOT NULL,
 entity_version integer, operation text NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),
 command_id uuid, actor text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
 detail jsonb NOT NULL
);
CREATE INDEX workspace_change_entity ON app.workspace_changes(entity_type,entity_id,sequence DESC);
CREATE INDEX workspace_change_command ON app.workspace_changes(command_id) WHERE command_id IS NOT NULL;

CREATE FUNCTION app.record_workspace_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE
 before_row jsonb := '{}'; after_row jsonb := '{}'; identity_row jsonb;
 field_names jsonb; reference_names text[] := ARRAY['task_id','event_id','note_ref_id','goal_id','project_id','parent_id','template_id','block_id'];
BEGIN
 IF TG_OP <> 'INSERT' THEN before_row := to_jsonb(OLD); END IF;
 IF TG_OP <> 'DELETE' THEN after_row := to_jsonb(NEW); END IF;
 IF TG_OP = 'UPDATE' AND before_row = after_row THEN RETURN NEW; END IF;
 identity_row := CASE WHEN TG_OP='DELETE' THEN before_row ELSE after_row END;
 SELECT coalesce(jsonb_agg(key ORDER BY key),'[]'::jsonb) INTO field_names
 FROM (SELECT key FROM jsonb_object_keys(before_row || after_row) AS fields(key)
       WHERE before_row->key IS DISTINCT FROM after_row->key) changed;
 INSERT INTO app.workspace_changes(entity_type,entity_id,entity_version,operation,command_id,actor,detail)
 VALUES(TG_TABLE_NAME,
   coalesce(identity_row->>'id',(identity_row->>'day')||'@'||(identity_row->>'timezone')),
   (identity_row->>'version')::integer,TG_OP,
   nullif(current_setting('yggdress.command_id',true),'')::uuid,session_user,
   jsonb_build_object('changed_fields',field_names,
     'previous_state',before_row->'state','state',after_row->'state',
     'before_refs',(SELECT coalesce(jsonb_object_agg(key,value),'{}'::jsonb) FROM jsonb_each(before_row) WHERE key=ANY(reference_names)),
     'after_refs',(SELECT coalesce(jsonb_object_agg(key,value),'{}'::jsonb) FROM jsonb_each(after_row) WHERE key=ANY(reference_names))));
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION app.record_workspace_change() FROM PUBLIC;
DO $$
DECLARE target text;
BEGIN
 FOREACH target IN ARRAY ARRAY['tasks','planning_goals','projects','routine_templates',
   'calendar_events','execution_blocks','execution_sessions','daily_plans','routines',
   'note_refs','task_note_links','event_note_links','event_task_links','background_runs'] LOOP
   EXECUTE format('CREATE TRIGGER workspace_change AFTER INSERT OR UPDATE OR DELETE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.record_workspace_change()',target);
 END LOOP;
END $$;

-- Read-only graph projection. Source tables enforce the actual references.
CREATE VIEW app.operational_edges AS
 SELECT 'task:'||task_id AS source, 'note:'||note_ref_id AS target, kind AS relation FROM app.task_note_links
 UNION ALL SELECT 'event:'||event_id,'note:'||note_ref_id,kind FROM app.event_note_links
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
