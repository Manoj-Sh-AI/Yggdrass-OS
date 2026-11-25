import { useState } from "react";
import { Alert, Text, View } from "react-native";
import { api } from "./api";
import { addDays, dayKey, wallClock, zonedInstant } from "./dates";
import { Button, ErrorText, Field, Sheet, styles } from "./ui";
import { useWorkspace } from "./workspace";
import type { DateItem, TimedItem } from "./types";

export type Selection =
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
    selection?.type || "event",
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

export { Calendar } from "./calendar-screen";
