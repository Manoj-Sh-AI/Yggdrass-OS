-- Date precision stays date precision: never fabricate midnight appointments.
CREATE TABLE app.calendar_date_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 180),
 description text NOT NULL DEFAULT '' CHECK(length(description)<=2000),
 kind text NOT NULL CHECK(kind IN ('event','availability','review')),
 starts_on date NOT NULL, ends_before date NOT NULL CHECK(ends_before>starts_on),
 cancelled boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1 CHECK(version>0)
);
CREATE INDEX calendar_date_item_range ON app.calendar_date_items(starts_on,ends_before) WHERE NOT cancelled;
CREATE TABLE app.availability_windows (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 180),
 description text NOT NULL DEFAULT '' CHECK(length(description)<=2000),
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL CHECK(ends_at>starts_at), timezone text NOT NULL,
 cancelled boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1 CHECK(version>0)
);
CREATE INDEX availability_range ON app.availability_windows(starts_at,ends_at) WHERE NOT cancelled;
CREATE TABLE app.date_item_note_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), date_item_id uuid NOT NULL REFERENCES app.calendar_date_items(id),
 note_ref_id uuid NOT NULL REFERENCES app.note_refs(id), kind text NOT NULL CHECK(kind IN ('source','context','result')),
 source_revision text CHECK(source_revision IS NULL OR length(source_revision) BETWEEN 1 AND 200),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(date_item_id,note_ref_id,kind)
);
CREATE INDEX date_item_note_reverse ON app.date_item_note_links(note_ref_id,date_item_id);
CREATE TABLE app.availability_note_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), availability_id uuid NOT NULL REFERENCES app.availability_windows(id),
 note_ref_id uuid NOT NULL REFERENCES app.note_refs(id), kind text NOT NULL CHECK(kind IN ('source','context','result')),
 source_revision text CHECK(source_revision IS NULL OR length(source_revision) BETWEEN 1 AND 200),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(availability_id,note_ref_id,kind)
);
CREATE INDEX availability_note_reverse ON app.availability_note_links(note_ref_id,availability_id);
CREATE TRIGGER workspace_change AFTER INSERT OR UPDATE OR DELETE ON app.calendar_date_items FOR EACH ROW EXECUTE FUNCTION app.record_workspace_change();
CREATE TRIGGER workspace_change AFTER INSERT OR UPDATE OR DELETE ON app.availability_windows FOR EACH ROW EXECUTE FUNCTION app.record_workspace_change();
CREATE TRIGGER workspace_change AFTER INSERT OR UPDATE OR DELETE ON app.date_item_note_links FOR EACH ROW EXECUTE FUNCTION app.record_workspace_change();
CREATE TRIGGER workspace_change AFTER INSERT OR UPDATE OR DELETE ON app.availability_note_links FOR EACH ROW EXECUTE FUNCTION app.record_workspace_change();

-- Preserve new typed reference IDs when a link is removed.
CREATE OR REPLACE FUNCTION app.record_workspace_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE
 before_row jsonb := '{}'; after_row jsonb := '{}'; identity_row jsonb;
 field_names jsonb; reference_names text[] := ARRAY['task_id','event_id','note_ref_id','goal_id','project_id','parent_id','template_id','block_id','date_item_id','availability_id'];
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
