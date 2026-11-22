-- User-selected important blocks belong to the timetable. Store timing as timestamptz
-- from that timetable, and keep a durable local-date/zone intent for recurring anchors.
CREATE TABLE app.routine_important_blocks (
 block_id uuid PRIMARY KEY REFERENCES app.execution_blocks(id) ON DELETE CASCADE
);
CREATE TABLE app.scheduled_jobs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 kind text NOT NULL,
 payload jsonb NOT NULL,
 run_at timestamptz NOT NULL,
 available_at timestamptz NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed','cancelled')),
 attempts integer NOT NULL DEFAULT 0,
 max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 10),
 dedupe_key text NOT NULL UNIQUE,
 source_ref text NOT NULL,
 locked_until timestamptz,
 outcome text NOT NULL DEFAULT ''
);
CREATE INDEX scheduled_jobs_due ON app.scheduled_jobs(available_at,id) WHERE status='pending';
CREATE INDEX scheduled_jobs_source ON app.scheduled_jobs(source_ref) WHERE status IN ('pending','running');
CREATE TABLE app.scheduled_job_attempts (
 job_id bigint NOT NULL REFERENCES app.scheduled_jobs(id) ON DELETE CASCADE,
 attempt integer NOT NULL, started_at timestamptz NOT NULL, finished_at timestamptz,
 outcome text NOT NULL DEFAULT 'running', PRIMARY KEY(job_id,attempt)
);
CREATE TABLE app.routine_escalations (
 id uuid PRIMARY KEY, block_id uuid NOT NULL REFERENCES app.execution_blocks(id) ON DELETE CASCADE,
 task_id uuid NOT NULL REFERENCES app.tasks(id) ON DELETE CASCADE,
 starts_at timestamptz NOT NULL, local_day date NOT NULL, zone text NOT NULL,
 state text NOT NULL CHECK(state IN ('sent','started','snoozed','expired','called','call_failed')),
 not_yet_at timestamptz, call_id uuid REFERENCES app.calls(id), attempts integer NOT NULL DEFAULT 0,
 summary text NOT NULL DEFAULT '', context text NOT NULL DEFAULT '',
 UNIQUE(block_id, starts_at)
);
CREATE INDEX routine_escalation_day ON app.routine_escalations(local_day,task_id);

-- Any writer, including an agent, can change a task or its block. Reconcile its
-- pending jobs inside that writer's transaction; a rolled-back edit changes neither.
CREATE FUNCTION app.replan_important_block(bid uuid) RETURNS void
LANGUAGE plpgsql AS $fn$
DECLARE rec record; source text := 'block:' || bid; revision text; body jsonb;
BEGIN
 SELECT b.starts_at,b.id,b.task_id,b.version AS block_version,t.version AS task_version
 INTO rec FROM app.execution_blocks b JOIN app.tasks t ON t.id=b.task_id
 JOIN app.routine_important_blocks m ON m.block_id=b.id WHERE b.id=bid
 AND NOT b.cancelled AND NOT t.done AND t.state IN ('todo','paused');

 IF FOUND THEN
   revision := source || ':' || rec.task_version || ':' || rec.block_version;
   body := jsonb_build_object('block_id',bid,'task_id',rec.task_id,'starts_at',rec.starts_at,
          'task_version',rec.task_version,'block_version',rec.block_version);
 END IF;

 UPDATE app.scheduled_jobs SET status='cancelled',outcome='timetable changed',locked_until=NULL
 WHERE source_ref=source AND status IN ('pending','running')
 AND (revision IS NULL OR (kind IN ('prep','notify') AND dedupe_key NOT IN (revision||':prep',revision||':notify'))
      OR (kind NOT IN ('prep','notify') AND (payload->>'starts_at')::timestamptz<>rec.starts_at));
 UPDATE app.routine_escalations SET state='expired'
 WHERE block_id=bid AND state IN ('sent','snoozed','called')
 AND (revision IS NULL OR starts_at<>rec.starts_at);
 IF revision IS NULL THEN RETURN; END IF;
 INSERT INTO app.scheduled_jobs(kind,payload,run_at,available_at,dedupe_key,source_ref)
 SELECT k,body,at,at,revision||':'||k,source FROM
 (VALUES ('prep',rec.starts_at-interval '10 minutes'),('notify',rec.starts_at)) AS v(k,at)
 ON CONFLICT(dedupe_key) DO UPDATE SET status='pending',outcome='',available_at=EXCLUDED.available_at
 WHERE app.scheduled_jobs.status='cancelled' AND app.scheduled_jobs.outcome='timetable changed';
END $fn$;

CREATE FUNCTION app.reschedule_routine_jobs() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE bid uuid;
BEGIN
 IF TG_TABLE_NAME='tasks' THEN
   FOR bid IN SELECT b.id FROM app.execution_blocks b JOIN app.routine_important_blocks m
      ON m.block_id=b.id WHERE b.task_id=NEW.id ORDER BY b.id LOOP
     PERFORM app.replan_important_block(bid);
   END LOOP;
 ELSIF TG_TABLE_NAME='execution_blocks' THEN
   IF EXISTS (SELECT FROM app.routine_important_blocks WHERE block_id=NEW.id) THEN
     PERFORM app.replan_important_block(NEW.id);
   END IF;
 ELSE
   PERFORM app.replan_important_block(CASE WHEN TG_OP='DELETE' THEN OLD.block_id ELSE NEW.block_id END);
 END IF;
 RETURN NULL;
END $fn$;
CREATE TRIGGER routine_job_mark AFTER INSERT OR DELETE ON app.routine_important_blocks
FOR EACH ROW EXECUTE FUNCTION app.reschedule_routine_jobs();
CREATE TRIGGER routine_job_block AFTER UPDATE ON app.execution_blocks
FOR EACH ROW EXECUTE FUNCTION app.reschedule_routine_jobs();
CREATE TRIGGER routine_job_task AFTER UPDATE ON app.tasks
FOR EACH ROW EXECUTE FUNCTION app.reschedule_routine_jobs();
