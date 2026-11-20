import { useEffect, useState } from "react";
import { Alert, FlatList, Text, View } from "react-native";
import { api } from "./api";
import {
  clock,
  dayKey,
  overlapsDay,
  taskDay,
  wallClock,
  zonedInstant,
} from "./dates";
import {
  Button,
  ErrorText,
  Field,
  Loading,
  Page,
  Panel,
  Sheet,
  styles,
  colors,
} from "./ui";
import { usePlanning, useWorkspace } from "./workspace";
import type { Snapshot, Task } from "./types";

export function focusData(snapshot: Snapshot, task: Task) {
  const session = snapshot.sessions.find((s) => s.ended_at === null);
  const prior = session
    ? snapshot.tasks.find((t) => t.id === session.task_id)
    : null;
  return prior && prior.id !== task.id
    ? { from_task_id: prior.id, from_version: prior.version }
    : {};
}
export function TaskEditor({
  task,
  onClose,
  onSaved,
}: {
  task: Task | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { timezone } = useWorkspace();
  const [title, setTitle] = useState(task?.title || "");
  const [goal, setGoal] = useState(task?.objective || "");
  const [description, setDescription] = useState(task?.description || "");
  const zone = task?.timezone || timezone;
  const [due, setDue] = useState(task?.due_date || "");
  const [deadlineDay, setDeadlineDay] = useState(
    task?.deadline_at ? dayKey(new Date(task.deadline_at), zone) : "",
  );
  const [deadlineTime, setDeadlineTime] = useState(
    task?.deadline_at ? wallClock(task.deadline_at, zone) : "",
  );
  const [minutes, setMinutes] = useState(String(task?.estimated_minutes || 30));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (!title.trim() || !goal.trim())
        throw new Error("Add a title and a goal.");
      const data = {
        title,
        objective: task?.objective || goal,
        description,
        area: task?.area || "work",
        due_date: due || null,
        estimated_minutes: Number(minutes),
        timezone: task?.timezone || timezone,
        priority: task?.priority || 2,
        effort: task?.effort || "unspecified",
        tags: task?.tags || [],
        goal_id: task?.goal_id || null,
        project_id: task?.project_id || null,
        parent_id: task?.parent_id || null,
        dependencies: task?.dependencies || [],
        deadline_at:
          deadlineDay || deadlineTime
            ? task?.deadline_at &&
              dayKey(new Date(task.deadline_at), zone) === deadlineDay &&
              wallClock(task.deadline_at, zone) === deadlineTime
              ? task.deadline_at
              : zonedInstant(deadlineDay, deadlineTime, zone)
            : null,
      };
      await api.plan(
        task ? "task.update" : "task.create",
        data,
        task?.id,
        task?.version,
      );
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet visible title={task ? "Edit task" : "New task"} onClose={onClose}>
      <Field
        label="Task title"
        value={title}
        onChangeText={setTitle}
        maxLength={180}
      />
      {task ? (
        <Panel>
          <Text style={styles.label}>Original goal · preserved</Text>
          <Text style={styles.text}>{task.objective}</Text>
        </Panel>
      ) : (
        <Field
          label="Goal"
          value={goal}
          onChangeText={setGoal}
          multiline
          maxLength={2000}
        />
      )}
      <Field
        label="Details"
        value={description}
        onChangeText={setDescription}
        multiline
      />
      <Field
        label="Due date · optional (YYYY-MM-DD)"
        value={due}
        onChangeText={setDue}
        autoCapitalize="none"
      />
      <Text style={styles.subtitle}>Exact deadline � optional � {zone}</Text>
      <Field
        label="Deadline date (YYYY-MM-DD)"
        value={deadlineDay}
        onChangeText={setDeadlineDay}
      />
      <Field
        label="Deadline time (HH:mm)"
        value={deadlineTime}
        onChangeText={setDeadlineTime}
      />
      <Field
        label="Expected minutes"
        value={minutes}
        onChangeText={setMinutes}
        keyboardType="number-pad"
      />
      <ErrorText message={error} />
      <Button
        title={busy ? "Saving…" : "Save task"}
        primary
        disabled={busy}
        onPress={() => void save()}
      />
    </Sheet>
  );
}
export function TaskDetails({
  task,
  snapshot,
  onClose,
  onChanged,
}: {
  task: Task;
  snapshot: Snapshot;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [edit, setEdit] = useState(false);
  const [percent, setPercent] = useState(String(task.progress));
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const running = snapshot.sessions.some(
    (s) => !s.ended_at && s.task_id === task.id,
  );
  const elapsed =
    task.actual_seconds +
    (running ? Math.max(0, (now - Date.parse(snapshot.server_now)) / 1000) : 0);
  async function execute(operation: string, data: object) {
    setBusy(true);
    setError("");
    try {
      await api.plan(operation, data, task.id, task.version);
      onChanged();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  const focus = () =>
    Alert.alert(
      "Start focusing?",
      "Your current focus timer will move to this task. Inspecting a task never changes your timer.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Start focus",
          onPress: () =>
            void execute("focus.switch", focusData(snapshot, task)),
        },
      ],
    );
  return (
    <Sheet visible title={task.title} onClose={onClose}>
      <Panel>
        <Text style={styles.label}>Original goal</Text>
        <Text style={styles.text}>{task.objective}</Text>
        <Text style={styles.subtitle}>
          {task.description || "No additional details."}
        </Text>
      </Panel>
      <Text style={styles.subtitle}>
        {task.state.replace(/_/g, " ")} · {task.estimated_minutes} min expected
        · {Math.floor(elapsed / 60)} min focus time{running ? " · running" : ""}
      </Text>
      <Text style={styles.subtitle}>
        {task.due_date ? `Due ${task.due_date}` : "No due date"}
      </Text>
      <View style={styles.row}>
        {!task.done && (
          <Button
            title={running ? "Pause focus" : "Focus on this"}
            primary
            disabled={busy}
            onPress={
              running
                ? () => void execute("task.execute", { action: "pause" })
                : focus
            }
          />
        )}
        <Button
          title={task.done ? "Reopen task" : "Complete task"}
          disabled={busy}
          onPress={() =>
            void execute("task.execute", {
              action: task.done ? "reopen" : "complete",
            })
          }
        />
        <Button
          title="Edit details"
          disabled={busy}
          onPress={() => setEdit(true)}
        />
      </View>
      {!task.done && (
        <>
          <Field
            label="Progress percent"
            value={percent}
            onChangeText={setPercent}
            keyboardType="number-pad"
          />
          <Button
            title="Save progress"
            disabled={busy}
            onPress={() =>
              void execute("task.execute", {
                action: "progress",
                percent: Number(percent),
              })
            }
          />
        </>
      )}
      <ErrorText message={error} />
      {edit && (
        <TaskEditor
          task={{
            ...task,
            dependencies:
              snapshot.dependencies
                ?.filter((d) => d.task_id === task.id)
                .map((d) => d.depends_on) ||
              task.dependencies ||
              [],
          }}
          onClose={() => setEdit(false)}
          onSaved={() => {
            onChanged();
            onClose();
          }}
        />
      )}
    </Sheet>
  );
}
export function Tasks({ active }: { active: boolean }) {
  const { timezone } = useWorkspace();
  const today = dayKey(new Date(), timezone);
  const { snapshot, error, loading, refresh, changed } = usePlanning(
    today.slice(0, 7),
    active,
  );
  const [lane, setLane] = useState("todo");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Task | null>(null);
  const [adding, setAdding] = useState(false);
  const tasks = (snapshot?.tasks || []).filter(
    (t) =>
      t.title.toLowerCase().includes(query.toLowerCase()) &&
      (lane === "completed"
        ? t.done
        : lane === "active"
          ? ["in_progress", "paused"].includes(t.state)
          : t.state === "todo"),
  );
  return (
    <View style={styles.screen}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Tasks
        </Text>
        <View style={styles.row}>
          <Button title="New task" primary onPress={() => setAdding(true)} />
          <Button title="Refresh" onPress={refresh} />
        </View>
        <Field label="Find a task" value={query} onChangeText={setQuery} />
        <View style={styles.row}>
          {["todo", "active", "completed"].map((value) => (
            <Button
              key={value}
              title={
                {
                  todo: "To do",
                  active: "In progress",
                  completed: "Completed",
                }[value]!
              }
              primary={lane === value}
              onPress={() => setLane(value)}
            />
          ))}
        </View>
        <ErrorText message={error} />
        {loading && <Loading />}
      </View>
      <FlatList
        data={tasks}
        keyExtractor={(t) => t.id}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{
          paddingHorizontal: 16,
          paddingBottom: 28,
          gap: 12,
        }}
        ListEmptyComponent={
          !loading ? (
            <Text style={styles.subtitle}>No tasks in this column.</Text>
          ) : null
        }
        renderItem={({ item }) => (
          <Panel>
            <Text style={styles.text}>{item.title}</Text>
            <Text style={styles.subtitle}>
              {item.progress}% · {item.estimated_minutes} min
              {item.due_date ? ` · due ${item.due_date}` : ""}
            </Text>
            <Button
              title="Open task"
              accessibilityLabel={`Open ${item.title}`}
              onPress={() => setSelected(item)}
            />
          </Panel>
        )}
      />
      {adding && (
        <TaskEditor
          task={null}
          onClose={() => setAdding(false)}
          onSaved={changed}
        />
      )}
      {selected && snapshot && (
        <TaskDetails
          task={selected}
          snapshot={snapshot}
          onClose={() => setSelected(null)}
          onChanged={changed}
        />
      )}
    </View>
  );
}
export function Today({
  active,
  openNotes,
}: {
  active: boolean;
  openNotes: () => void;
}) {
  const { timezone } = useWorkspace();
  const day = dayKey(new Date(), timezone);
  const { snapshot, error, loading, refresh, changed } = usePlanning(
    day.slice(0, 7),
    active,
  );
  const [selected, setSelected] = useState<Task | null>(null);
  const [adding, setAdding] = useState(false);
  const due = (snapshot?.tasks || []).filter(
    (t) =>
      !t.done &&
      t.state !== "skipped" &&
      ((taskDay(t, timezone) && taskDay(t, timezone)! <= day) ||
        t.state === "in_progress"),
  );
  const agenda = [
    ...(snapshot?.events || [])
      .filter((e) => overlapsDay(e, day, timezone))
      .map((e) => ({
        key: e.id,
        title: e.title,
        start: e.starts_at,
        task: null as Task | null,
      })),
    ...(snapshot?.blocks || [])
      .filter((b) => overlapsDay(b, day, timezone))
      .map((b) => ({
        key: b.id,
        title:
          snapshot?.tasks.find((t) => t.id === b.task_id)?.title ||
          "Work block",
        start: b.starts_at,
        task: snapshot?.tasks.find((t) => t.id === b.task_id) || null,
      })),
  ].sort((a, b) => a.start.localeCompare(b.start));
  return (
    <Page
      title="Today"
      subtitle={new Date().toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        timeZone: timezone,
      })}
    >
      <View style={styles.row}>
        <Button title="Add task" primary onPress={() => setAdding(true)} />
        <Button title="Capture a note" onPress={openNotes} />
        <Button title="Refresh" onPress={refresh} />
      </View>
      <ErrorText message={error} />
      {loading && <Loading />}
      {snapshot && (
        <>
          <Panel>
            <Text accessibilityRole="header" style={styles.text}>
              Your next steps
            </Text>
            {due.length ? (
              due.slice(0, 8).map((t) => (
                <View key={t.id} style={{ gap: 6 }}>
                  <Text style={styles.text}>{t.title}</Text>
                  <Button
                    title={
                      t.state === "in_progress" ? "Resume context" : "Open task"
                    }
                    accessibilityLabel={`Open ${t.title}`}
                    onPress={() => setSelected(t)}
                  />
                </View>
              ))
            ) : (
              <Text style={styles.subtitle}>
                Nothing due. You have room to choose what matters next.
              </Text>
            )}
          </Panel>
          <Panel>
            <Text accessibilityRole="header" style={styles.text}>
              Agenda
            </Text>
            {agenda.length ? (
              agenda.map((item) => (
                <View key={item.key} style={{ gap: 4 }}>
                  <Text style={{ color: colors.accent, fontSize: 15 }}>
                    {clock(item.start, timezone)}
                  </Text>
                  <Text style={styles.text}>{item.title}</Text>
                  {item.task && (
                    <Button
                      title="Open task"
                      onPress={() => setSelected(item.task)}
                    />
                  )}
                </View>
              ))
            ) : (
              <Text style={styles.subtitle}>No timed items today.</Text>
            )}
            {(snapshot.date_items || [])
              .filter((i) => i.starts_on <= day && i.ends_before > day)
              .map((i) => (
                <Text key={i.id} style={styles.text}>
                  All day · {i.title}
                </Text>
              ))}
          </Panel>
        </>
      )}
      {adding && (
        <TaskEditor
          task={null}
          onClose={() => setAdding(false)}
          onSaved={changed}
        />
      )}
      {selected && snapshot && (
        <TaskDetails
          task={selected}
          snapshot={snapshot}
          onClose={() => setSelected(null)}
          onChanged={changed}
        />
      )}
    </Page>
  );
}
