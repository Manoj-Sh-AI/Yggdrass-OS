-- Connected data, step 4 (planning/connected-data-proposal.md): one table for every approve
-- and reject. EXPAND only; the source tables stay and stay the writers' target. Safe to run twice.
-- Sources (each row records its original table and row):
--   yggdras_feedback      every row: approved / rejected / undone, as recorded
--   workflow_reviews,
--   call_reviews,
--   agent_proposals       once decided: accepted -> approved, dismissed -> rejected
--                         (pending / waiting / superseded are not verdicts)
--   conductor_runs        approval cards answered by Manoj (written by the conductor's
--                         RunLog.append in the same transaction; backfilled from run state)
-- daily_reviews and item_outcomes are NOT sources: they record a day's reflection and
-- whether an item happened, not a decision on a proposal.

CREATE TABLE IF NOT EXISTS app.judgements (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 subject_kind text NOT NULL CHECK (subject_kind IN
   ('yggdras_card','workflow_review','call_review','agent_proposal','conductor_tool')),
 subject_key text NOT NULL CHECK (length(subject_key) BETWEEN 1 AND 300),
 verdict text NOT NULL CHECK (verdict IN ('approved','rejected','undone')),
 by text NOT NULL DEFAULT 'manoj' CHECK (length(by) BETWEEN 1 AND 100),
 reason text CHECK (reason IS NULL OR length(reason) <= 2000),
 at timestamptz NOT NULL DEFAULT now(),
 source_table text NOT NULL CHECK (source_table IN
   ('yggdras_feedback','workflow_reviews','call_reviews','agent_proposals','conductor_runs')),
 source_id text NOT NULL CHECK (length(source_id) BETWEEN 1 AND 300),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (source_table, source_id)
);
CREATE INDEX IF NOT EXISTS judgements_subject ON app.judgements (subject_kind, subject_key);

-- Writers write to both: a decision in a source table lands here in the same transaction.
CREATE OR REPLACE FUNCTION app.judgements_mirror() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $$
DECLARE r jsonb; v text; kind text; when_ timestamptz; why text;
BEGIN
 r := to_jsonb(NEW);
 IF TG_TABLE_NAME = 'yggdras_feedback' THEN
  kind := 'yggdras_card'; v := r ->> 'decision'; when_ := NEW.created_at;
  why := nullif(r ->> 'correction', '');
 ELSE
  kind := CASE TG_TABLE_NAME WHEN 'workflow_reviews' THEN 'workflow_review'
            WHEN 'call_reviews' THEN 'call_review' WHEN 'agent_proposals' THEN 'agent_proposal' END;
  v := CASE r ->> 'state' WHEN 'accepted' THEN 'approved' WHEN 'dismissed' THEN 'rejected' END;
  IF v IS NULL THEN RETURN NULL; END IF;     -- not decided: not a verdict
  when_ := coalesce((r ->> 'resolved_at')::timestamptz, now());
 END IF;
 INSERT INTO app.judgements (subject_kind, subject_key, verdict, reason, at, source_table, source_id)
 VALUES (kind, r ->> 'id', v, why, when_, TG_TABLE_NAME, r ->> 'id')
 ON CONFLICT (source_table, source_id) DO NOTHING;   -- a decision is recorded once
 RETURN NULL;
END $$;

CREATE OR REPLACE TRIGGER judgements_mirror AFTER INSERT ON app.yggdras_feedback
 FOR EACH ROW EXECUTE FUNCTION app.judgements_mirror();
CREATE OR REPLACE TRIGGER judgements_mirror AFTER INSERT OR UPDATE OF state ON app.workflow_reviews
 FOR EACH ROW EXECUTE FUNCTION app.judgements_mirror();
CREATE OR REPLACE TRIGGER judgements_mirror AFTER INSERT OR UPDATE OF state ON app.call_reviews
 FOR EACH ROW EXECUTE FUNCTION app.judgements_mirror();
CREATE OR REPLACE TRIGGER judgements_mirror AFTER INSERT OR UPDATE OF state ON app.agent_proposals
 FOR EACH ROW EXECUTE FUNCTION app.judgements_mirror();

-- The stream (044) captures this table too.
CREATE OR REPLACE TRIGGER events_capture AFTER INSERT OR UPDATE OR DELETE ON app.judgements
 FOR EACH ROW EXECUTE FUNCTION app.events_capture();

-- Backfill by copy. call_reviews has no decision time: its created_at is used (stated here).
INSERT INTO app.judgements (subject_kind, subject_key, verdict, reason, at, source_table, source_id)
SELECT 'yggdras_card', id::text, decision, nullif(correction, ''), created_at, 'yggdras_feedback', id::text
FROM app.yggdras_feedback
UNION ALL
SELECT 'workflow_review', id::text, CASE state WHEN 'accepted' THEN 'approved' ELSE 'rejected' END,
  NULL, coalesce(resolved_at, created_at), 'workflow_reviews', id::text
FROM app.workflow_reviews WHERE state IN ('accepted','dismissed')
UNION ALL
SELECT 'call_review', id::text, CASE state WHEN 'accepted' THEN 'approved' ELSE 'rejected' END,
  NULL, created_at, 'call_reviews', id::text
FROM app.call_reviews WHERE state IN ('accepted','dismissed')
UNION ALL
SELECT 'agent_proposal', id::text, CASE state WHEN 'accepted' THEN 'approved' ELSE 'rejected' END,
  NULL, coalesce(resolved_at, created_at), 'agent_proposals', id::text
FROM app.agent_proposals WHERE state IN ('accepted','dismissed')
UNION ALL
SELECT 'conductor_tool', r.id::text || ':' || (t ->> 'id'),
  CASE WHEN (t -> 'approval' ->> 'approved')::boolean THEN 'approved' ELSE 'rejected' END,
  nullif(t -> 'approval' ->> 'reason', ''), r.updated_at, 'conductor_runs', r.id::text || ':' || (t ->> 'id')
FROM app.conductor_runs r, jsonb_array_elements(coalesce(r.state -> 'tools', '[]'::jsonb)) t
WHERE t ->> 'state' = 'approval-responded' AND t ->> 'decided_by' = 'user' AND t -> 'approval' IS NOT NULL
ON CONFLICT (source_table, source_id) DO NOTHING;

-- What agents read: the verdicts, without free-text reasons (they can quote anything).
CREATE OR REPLACE VIEW api.judgements WITH (security_barrier) AS
SELECT id, subject_kind, subject_key, verdict, by, at, source_table FROM app.judgements;
