import { useState } from "react";
import { Switch, Text, View } from "react-native";
import { api } from "./api";
import { dayKey } from "./dates";
import { Button, ErrorText, Field, Panel, Sheet, styles } from "./ui";
import { useWorkspace } from "./workspace";
import type { Snapshot } from "./types";

export type Routine = Snapshot["routines"][number];
type Goal = Snapshot["goals"][number];
export function GoalEditor({
  goal,
  close,
  saved,
}: {
  goal: Goal | null;
  close: () => void;
  saved: () => void;
}) {
  const [title, setTitle] = useState(goal?.title || "");
  const [description, setDescription] = useState(goal?.description || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (!title.trim()) throw new Error("Add a goal title.");
      await api.plan(
        goal ? "goal.update" : "goal.create",
        { title, description },
        goal?.id,
        goal?.version,
      );
      saved();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this goal.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet visible title={goal ? "Edit goal" : "New goal"} onClose={close}>
      <Field
        label="Goal title"
        value={title}
        onChangeText={setTitle}
        maxLength={180}
      />
      <Field
        label="Goal description"
        value={description}
        onChangeText={setDescription}
        multiline
        maxLength={2000}
      />
      <Text style={styles.subtitle}>
        Editing this goal does not rewrite the original objective of an existing
        task.
      </Text>
      <ErrorText message={error} />
      <Button
        title={busy ? "Saving…" : "Save goal"}
        primary
        disabled={busy}
        onPress={() => void save()}
      />
    </Sheet>
  );
}

export function RoutineEditor({
  routine,
  close,
  saved,
}: {
  routine: Routine | null;
  close: () => void;
  saved: () => void;
}) {
  const { timezone } = useWorkspace();
  const [title, setTitle] = useState(routine?.title || "");
  const [objective, setObjective] = useState(routine?.objective || "");
  const [description, setDescription] = useState(routine?.description || "");
  const [start, setStart] = useState(
    routine?.window_start.slice(0, 5) || "09:00",
  );
  const [end, setEnd] = useState(routine?.window_end.slice(0, 5) || "10:00");
  const [minutes, setMinutes] = useState(
    String(routine?.expected_minutes || 30),
  );
  const [from, setFrom] = useState(
    routine?.starts_on || dayKey(new Date(), timezone),
  );
  const [until, setUntil] = useState(routine?.ends_on || "");
  const [weekdays, setWeekdays] = useState(
    routine?.weekdays || [0, 1, 2, 3, 4, 5, 6],
  );
  const [active, setActive] = useState(routine?.active ?? true);
  const [essential, setEssential] = useState(routine?.essential ?? false);
  const [interval, setInterval] = useState(
    String(routine?.interval_count || 1),
  );
  const [frequency, setFrequency] = useState<"daily" | "weekly">(
    routine?.frequency || "daily",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (!title.trim() || !objective.trim())
        throw new Error("Add a title and an objective.");
      if (
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(start) ||
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(end) ||
        end <= start
      )
        throw new Error(
          "Choose a same-day window with an end after its start (HH:mm).",
        );
      if (!weekdays.length) throw new Error("Choose at least one weekday.");
      await api.plan(
        routine ? "routine.update" : "routine.create",
        {
          title,
          description,
          objective,
          area: routine?.area || "health",
          frequency,
          interval_count: Number(interval),
          weekdays,
          starts_on: from,
          ends_on: until || null,
          window_start: start,
          window_end: end,
          expected_minutes: Number(minutes),
          timezone: routine?.timezone || timezone,
          priority: routine?.priority || 2,
          goal_id: routine?.goal_id || null,
          essential,
          active,
        },
        routine?.id,
        routine?.version,
      );
      saved();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this routine.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet
      visible
      title={routine ? "Edit routine" : "New routine"}
      onClose={close}
    >
      <Field
        label="Routine title"
        value={title}
        onChangeText={setTitle}
        maxLength={180}
      />
      <Field
        label="Routine objective"
        value={objective}
        onChangeText={setObjective}
        multiline
        maxLength={2000}
      />
      <Field
        label="Routine details"
        value={description}
        onChangeText={setDescription}
        multiline
      />
      <Text style={styles.subtitle}>
        {routine?.timezone || timezone} · future unstarted occurrences follow
        edits; execution history stays intact.
      </Text>
      <View style={styles.row}>
        <Button
          title="Daily"
          primary={frequency === "daily"}
          onPress={() => setFrequency("daily")}
        />
        <Button
          title="Weekly"
          primary={frequency === "weekly"}
          onPress={() => setFrequency("weekly")}
        />
      </View>
      <Field
        label="Repeat every"
        value={interval}
        onChangeText={setInterval}
        keyboardType="number-pad"
      />
      <View style={styles.row}>
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => (
          <Button
            key={d}
            title={d}
            accessibilityLabel={`${d}${weekdays.includes(i) ? ", selected" : ""}`}
            primary={weekdays.includes(i)}
            onPress={() =>
              setWeekdays((all) =>
                all.includes(i)
                  ? all.filter((v) => v !== i)
                  : [...all, i].sort(),
              )
            }
          />
        ))}
      </View>
      <Field
        label="Starts on (YYYY-MM-DD)"
        value={from}
        onChangeText={setFrom}
      />
      <Field
        label="Ends on · optional (YYYY-MM-DD)"
        value={until}
        onChangeText={setUntil}
      />
      <Field
        label="Window starts (HH:mm)"
        value={start}
        onChangeText={setStart}
      />
      <Field label="Window ends (HH:mm)" value={end} onChangeText={setEnd} />
      <Field
        label="Expected routine minutes"
        value={minutes}
        onChangeText={setMinutes}
        keyboardType="number-pad"
      />
      <View style={styles.row}>
        <Text style={styles.text}>Active</Text>
        <Switch
          accessibilityLabel="Routine active"
          value={active}
          onValueChange={setActive}
        />
      </View>
      <View style={styles.row}>
        <Text style={styles.text}>Essential</Text>
        <Switch
          accessibilityLabel="Routine essential"
          value={essential}
          onValueChange={setEssential}
        />
      </View>
      <ErrorText message={error} />
      <Button
        title={busy ? "Saving…" : "Save routine"}
        primary
        disabled={busy}
        onPress={() => void save()}
      />
    </Sheet>
  );
}

export function PlanningLibrary({
  snapshot,
  changed,
}: {
  snapshot: Snapshot | null;
  changed: () => void;
}) {
  const [goal, setGoal] = useState<Goal | null | undefined>();
  const [routine, setRoutine] = useState<Routine | null | undefined>();
  return (
    <Panel>
      <Text style={styles.text}>Goals and routines</Text>
      <View style={styles.row}>
        <Button title="New goal" onPress={() => setGoal(null)} />
        <Button title="New routine" onPress={() => setRoutine(null)} />
      </View>
      {snapshot?.goals.map((g) => (
        <Button
          key={g.id}
          title={g.title}
          accessibilityLabel={`Edit goal ${g.title}`}
          onPress={() => setGoal(g)}
        />
      ))}
      {snapshot?.routines.map((r) => (
        <Button
          key={r.id}
          title={`${r.title}${r.active ? "" : " · paused"}`}
          accessibilityLabel={`Edit routine ${r.title}`}
          onPress={() => setRoutine(r)}
        />
      ))}
      {goal !== undefined && (
        <GoalEditor
          goal={goal}
          close={() => setGoal(undefined)}
          saved={changed}
        />
      )}
      {routine !== undefined && (
        <RoutineEditor
          routine={routine}
          close={() => setRoutine(undefined)}
          saved={changed}
        />
      )}
    </Panel>
  );
}
