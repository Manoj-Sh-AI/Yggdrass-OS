-- Voice calls v3: one audit trail of what happened to each scheduled item occurrence
-- (completed, not done, not answered, removed, started, snoozed), who decided it and on
-- which call. Append-only: the newest row for an occurrence is its current outcome.
-- Retries after a missed reminder call get their own schedule kind.
-- Application data only; never Brain tables.
CREATE TABLE app.item_outcomes (
 id uuid PRIMARY KEY,
 item_kind text NOT NULL CHECK(item_kind IN ('event','routine','task')),
 item_id uuid NOT NULL,
 occurrence date NOT NULL,
 outcome text NOT NULL
  CHECK(outcome IN ('completed','not_done','not_answered','removed','started','snoozed')),
 decided_by text NOT NULL
  CHECK(decided_by IN ('voice','slot_end','after_retries','follow_up')),
 call_id uuid REFERENCES app.calls(id),
 note text NOT NULL DEFAULT '' CHECK(length(note) <= 500),
 at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX item_outcomes_occurrence ON app.item_outcomes(item_kind, item_id, occurrence, at DESC);
CREATE INDEX item_outcomes_recent ON app.item_outcomes(at DESC);

ALTER TABLE app.call_schedules DROP CONSTRAINT call_schedules_kind_check;
ALTER TABLE app.call_schedules ADD CONSTRAINT call_schedules_kind_check
 CHECK(kind IN ('one_off','snooze','event_start','event_end','routine','retry'));
