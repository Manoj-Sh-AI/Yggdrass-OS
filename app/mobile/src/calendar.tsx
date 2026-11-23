import { useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { api } from "./api";
import {
  addDays,
  clock,
  dayKey,
  monthRange,
  overlapsDay,
  taskDay,
  wallClock,
  shiftMonth,
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
import type { DateItem, TimedItem, Task } from "./types";
import { TaskDetails } from "./tasks";

type Selection =
  | { type: "date"; item: DateItem }
  | { type: "event" | "availability"; item: TimedItem };
export function EventEditor({
  day,
  selection,
  onClose,
  onSaved,
}: {
  day: string;
  selection: Selection | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { timezone } = useWorkspace();
  const [kind, setKind] = useState<"date" | "event" | "availability">(
    selection?.type || "date",
  );
  const item = selection?.item;
  const [title, setTitle] = useState(item?.title || "");
  const [description, setDescription] = useState(item?.description || "");
  const [date, setDate] = useState(
    selection?.type === "date"
      ? selection.item.starts_on
      : selection
        ? dayKey(new Date(selection.item.starts_at), timezone)
        : day,
  );
  const [lastDay, setLastDay] = useState(
    selection?.type === "date" ? addDays(selection.item.ends_before, -1) : day,
  );
  const [start, setStart] = useState(
    selection && selection.type !== "date"
      ? wallClock(selection.item.starts_at, timezone)
      : "09:00",
  );
  const [end, setEnd] = useState(
    selection && selection.type !== "date"
      ? wallClock(selection.item.ends_at, timezone)
      : "10:00",
  );
  const [busy, setBusy] = useState(false);
  const [endDate, setEndDate] = useState(
    selection && selection.type !== "date"
      ? dayKey(new Date(selection.item.ends_at), timezone)
      : day,
  );
  const [error, setError] = useState("");
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (!title.trim()) throw new Error("Add a title.");
      if (kind === "date")
        await api.time(
          selection ? "date_item.update" : "date_item.create",
          {
            title,
            description,
            kind: selection?.type === "date" ? selection.item.kind : "event",
            starts_on: date,
            ends_before: addDays(lastDay, 1),
          },
          item?.id,
          item?.version,
        );
      else {
        const instant = (
          which: "starts_at" | "ends_at",
          day: string,
          time: string,
        ) => {
          const previous =
            selection && selection.type !== "date"
              ? selection.item[which]
              : null;
          return previous &&
            dayKey(new Date(previous), timezone) === day &&
            wallClock(previous, timezone) === time
            ? previous
            : zonedInstant(day, time, timezone);
        };
        const data = {
          title,
          description,
          start: instant("starts_at", date, start),
          end: instant("ends_at", endDate, end),
          timezone,
        };
        if (kind === "event")
          await api.plan(
            selection ? "event.update" : "event.create",
            data,
            item?.id,
            item?.version,
          );
        else
          await api.time(
            selection ? "availability.update" : "availability.create",
            data,
            item?.id,
            item?.version,
          );
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this item.");
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    setBusy(true);
    setError("");
    try {
      if (!selection) return;
      if (kind === "event")
        await api.plan("event.remove", {}, item!.id, item!.version);
      else
        await api.time(
          kind === "date" ? "date_item.remove" : "availability.remove",
          {},
          item!.id,
          item!.version,
        );
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove this item.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet
      visible
      title={selection ? "Calendar item" : "Add to calendar"}
      onClose={onClose}
    >
      {!selection && (
        <View style={styles.row}>
          {(["date", "event", "availability"] as const).map((k) => (
            <Button
              key={k}
              title={
                {
                  date: "All day",
                  event: "Appointment",
                  availability: "Availability",
                }[k]
              }
              primary={kind === k}
              onPress={() => setKind(k)}
            />
          ))}
        </View>
      )}
      <Field label="Title" value={title} onChangeText={setTitle} />
      <Field
        label="Details"
        value={description}
        onChangeText={setDescription}
        multiline
      />
      <Field
        label="Date (YYYY-MM-DD)"
        value={date}
        onChangeText={(value) => {
          if (lastDay === date) setLastDay(value);
          if (endDate === date) setEndDate(value);
          setDate(value);
        }}
      />
      {kind === "date" ? (
        <Field
          label="Last day (inclusive)"
          value={lastDay}
          onChangeText={setLastDay}
        />
      ) : (
        <>
          <Text style={styles.subtitle}>Times in {timezone}</Text>
          <Field label="Start (HH:mm)" value={start} onChangeText={setStart} />
          <Field
            label="End date (YYYY-MM-DD)"
            value={endDate}
            onChangeText={setEndDate}
          />
          <Field label="End (HH:mm)" value={end} onChangeText={setEnd} />
        </>
      )}
      <ErrorText message={error} />
      <Button
        title={busy ? "Saving…" : "Save calendar item"}
        disabled={busy}
        primary
        onPress={() => void save()}
      />
      {selection && (
        <Button
          title="Remove calendar item"
          disabled={busy}
          onPress={() =>
            Alert.alert("Remove this item?", title, [
              { text: "Keep", style: "cancel" },
              {
                text: "Remove",
                style: "destructive",
                onPress: () => void remove(),
              },
            ])
          }
        />
      )}
    </Sheet>
  );
}
export function Calendar({ active }: { active: boolean }) {
  const { timezone } = useWorkspace();
  const today = dayKey(new Date(), timezone);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [selected, setSelected] = useState(today);
  const { snapshot, error, loading, refresh, changed } = usePlanning(
    month,
    active,
  );
  const [editor, setEditor] = useState<Selection | null | undefined>(undefined);
  const [task, setTask] = useState<Task | null>(null);
  const range = monthRange(month);
  const dated = (snapshot?.date_items || []).filter(
    (i) => i.starts_on <= selected && i.ends_before > selected,
  );
  const events = (snapshot?.events || []).filter((i) =>
    overlapsDay(i, selected, timezone),
  );
  const available = (snapshot?.availability || []).filter((i) =>
    overlapsDay(i, selected, timezone),
  );
  const due = (snapshot?.tasks || []).filter(
    (t) =>
      taskDay(t, timezone) === selected ||
      snapshot?.blocks.some(
        (b) => b.task_id === t.id && overlapsDay(b, selected, timezone),
      ),
  );
  const hasItems = (day: string) =>
    snapshot?.tasks.some((t) => taskDay(t, timezone) === day) ||
    snapshot?.events.some(
      (e) => dayKey(new Date(e.starts_at), timezone) === day,
    ) ||
    snapshot?.date_items?.some(
      (d) => d.starts_on <= day && d.ends_before > day,
    );
  const move = (direction: number) => {
    const value = shiftMonth(month, direction);
    setMonth(value);
    setSelected(`${value}-01`);
  };
  return (
    <Page title="Calendar" subtitle={timezone}>
      <View
        style={[styles.row, { justifyContent: "space-between", flexWrap: "nowrap" }]}
      >
        <Button
          title="‹"
          accessibilityLabel="Previous month"
          onPress={() => move(-1)}
        />
        <Text accessibilityRole="header" style={styles.text}>
          {new Date(`${month}-01T12:00:00`).toLocaleDateString(undefined, {
            month: "long",
            year: "numeric",
          })}
        </Text>
        <Button title="›" accessibilityLabel="Next month" onPress={() => move(1)} />
      </View>
      <Panel>
        <View style={{ flexDirection: "row" }}>
          {["M", "T", "W", "T", "F", "S", "S"].map((name, i) => (
            <Text
              key={i}
              style={[styles.label, { width: "14.285%", textAlign: "center" }]}
            >
              {name}
            </Text>
          ))}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          {range.days.map((day) => (
            <Pressable
              key={day}
              accessibilityRole="button"
              accessibilityLabel={`${day}${hasItems(day) ? ", has items" : ""}`}
              accessibilityState={{ selected: day === selected }}
              onPress={() => setSelected(day)}
              style={{
                width: "14.285%",
                minHeight: 48,
                alignItems: "center",
                justifyContent: "center",
                borderRadius: 12,
                backgroundColor:
                  day === selected ? colors.accent : "transparent",
              }}
            >
              <Text
                style={{
                  fontSize: 16,
                  color:
                    day === selected
                      ? colors.ink
                      : day.startsWith(month)
                        ? colors.text
                        : colors.muted,
                  fontWeight: day === today ? "800" : "400",
                }}
              >
                {Number(day.slice(8))}
              </Text>
              <View
                style={{
                  height: 4,
                  width: 4,
                  borderRadius: 2,
                  backgroundColor: hasItems(day)
                    ? day === selected
                      ? colors.ink
                      : colors.accent
                    : "transparent",
                }}
              />
            </Pressable>
          ))}
        </View>
      </Panel>
      <View style={styles.row}>
        <Text style={[styles.text, { flex: 1 }]}>
          {new Date(`${selected}T12:00:00`).toLocaleDateString(undefined, {
            weekday: "long",
            day: "numeric",
            month: "short",
          })}
        </Text>
        <Button title="Add item" primary onPress={() => setEditor(null)} />
      </View>
      <ErrorText message={error} />
      {error && <Button title="Retry" onPress={refresh} />}{" "}
      {loading && <Loading />}
      {!loading &&
        !dated.length &&
        !events.length &&
        !due.length &&
        !available.length && (
          <Text style={styles.subtitle}>Nothing scheduled for this day.</Text>
        )}
      {dated.map((item) => (
        <Panel key={item.id}>
          <Text style={styles.label}>All day</Text>
          <Text style={styles.text}>{item.title}</Text>
          <Button
            title="Open item"
            onPress={() => setEditor({ type: "date", item })}
          />
        </Panel>
      ))}
      {events.map((item) => (
        <Panel key={item.id}>
          <Text style={styles.label}>
            {clock(item.starts_at, timezone)} – {clock(item.ends_at, timezone)}
          </Text>
          <Text style={styles.text}>{item.title}</Text>
          <Button
            title="Open appointment"
            onPress={() => setEditor({ type: "event", item })}
          />
        </Panel>
      ))}
      {available.map((item) => (
        <Panel key={item.id}>
          <Text style={styles.label}>
            Available · {clock(item.starts_at, timezone)} –{" "}
            {clock(item.ends_at, timezone)}
          </Text>
          <Text style={styles.text}>{item.title}</Text>
          <Button
            title="Open availability"
            onPress={() => setEditor({ type: "availability", item })}
          />
        </Panel>
      ))}
      {due.map((item) => (
        <Panel key={item.id}>
          <Text style={styles.label}>{item.done ? "Completed" : "Task"}</Text>
          <Text style={styles.text}>{item.title}</Text>
          <Button title="Open task" onPress={() => setTask(item)} />
        </Panel>
      ))}
      {editor !== undefined && (
        <EventEditor
          day={selected}
          selection={editor}
          onClose={() => setEditor(undefined)}
          onSaved={changed}
        />
      )}
      {task && snapshot && (
        <TaskDetails
          task={task}
          snapshot={snapshot}
          onClose={() => setTask(null)}
          onChanged={changed}
        />
      )}
    </Page>
  );
}
