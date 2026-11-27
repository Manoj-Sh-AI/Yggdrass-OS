/** The Calendar tab, laid out the way Google Calendar's Android app is: a top bar with
 * the views menu, the month (tap for a mini month) and a today button; Schedule, Day,
 * 3-day and Month views; swipe to move; a floating + for Event or Task. Item kinds are
 * told apart by shape (filled, outlined, dashed), never by colours outside the tokens. */
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { api } from "./api";
import { EventEditor, type Selection } from "./calendar";
import {
  ALL_KINDS,
  entriesOn,
  lanes,
  merge,
  schedule,
  span,
  step,
  visibleDays,
  type CalendarView,
  type Entry,
  type Kinds,
} from "./calendar-model";
import { addDays, clock, dayKey, monthRange, shiftMonth, wallClock } from "./dates";
import { TaskDetails, TaskEditor } from "./tasks";
import type { Snapshot, Task, TimedItem } from "./types";
import { Button, ErrorText, Loading, Panel, Sheet, colors, styles } from "./ui";
import { usePlanning, useWorkspace } from "./workspace";

const HOUR = 56; // timeline height of one hour
const GUTTER = 48; // hour labels / date column
const VIEWS: { value: CalendarView; label: string }[] = [
  { value: "schedule", label: "Schedule" },
  { value: "day", label: "Day" },
  { value: "3day", label: "3 days" },
  { value: "month", label: "Month" },
];
const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];
const weekday = (day: string) =>
  new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: "short" });
const monthTitle = (day: string) =>
  new Date(`${day.slice(0, 7)}-01T12:00:00`).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
const filledKind = (e: Entry) => e.kind === "event" || e.kind === "allday";
const describe = (e: Entry) =>
  e.kind === "task" ? "Task" : e.kind === "availability" ? "Availability" : "Event";

/** One item: events filled, tasks outlined with a tick-circle, availability dashed. */
function Chip({
  entry,
  timezone,
  onOpen,
  onToggle,
}: {
  entry: Entry;
  timezone: string;
  onOpen: (entry: Entry) => void;
  onToggle: (task: Task) => void;
}) {
  const filled = filledKind(entry);
  const timed = entry.kind === "event" || entry.kind === "availability";
  const done = entry.kind === "task" && entry.done;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${describe(entry)}: ${entry.title}`}
      onPress={() => onOpen(entry)}
      style={({ pressed }) => ({
        flexDirection: "row",
        alignItems: "center",
        gap: 8,
        minHeight: 44,
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 12,
        borderWidth: 1,
        borderStyle: entry.kind === "availability" ? "dashed" : "solid",
        borderColor: filled ? colors.accent : colors.buttonBorder,
        backgroundColor: filled ? colors.accent : colors.buttonFill,
        opacity: pressed ? 0.7 : 1,
      })}
    >
      {entry.kind === "task" && (
        <Pressable
          accessibilityRole="checkbox"
          accessibilityLabel={done ? `Reopen ${entry.title}` : `Complete ${entry.title}`}
          accessibilityState={{ checked: done }}
          hitSlop={10}
          onPress={() => onToggle(entry.item)}
          style={{
            width: 20,
            height: 20,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: colors.accent,
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: done ? colors.accent : "transparent",
          }}
        >
          {done && <Text style={{ color: colors.ink, fontSize: 12 }}>✓</Text>}
        </Pressable>
      )}
      <View style={{ flex: 1 }}>
        <Text
          numberOfLines={1}
          style={{
            fontSize: 14,
            fontWeight: "500",
            color: filled ? colors.ink : done ? colors.faint : colors.text,
            textDecorationLine: done ? "line-through" : "none",
          }}
        >
          {entry.title}
        </Text>
        {timed && (
          <Text style={{ fontSize: 12, color: filled ? colors.ink : colors.muted }}>
            {clock((entry.item as TimedItem).starts_at, timezone)} –{" "}
            {clock((entry.item as TimedItem).ends_at, timezone)}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

function DayBadge({ day, today, onPress }: { day: string; today: string; onPress?: () => void }) {
  const isToday = day === today;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${weekday(day)} ${Number(day.slice(8))}${isToday ? ", today" : ""}`}
      onPress={onPress}
      style={{ alignItems: "center", width: GUTTER, gap: 2 }}
    >
      <Text style={{ fontSize: 12, color: isToday ? colors.accent : colors.muted }}>
        {weekday(day)}
      </Text>
      <View
        style={{
          width: 36,
          height: 36,
          borderRadius: 18,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: isToday ? colors.accent : "transparent",
        }}
      >
        <Text style={{ fontSize: 16, color: isToday ? colors.ink : colors.text }}>
          {Number(day.slice(8))}
        </Text>
      </View>
    </Pressable>
  );
}

/** Month grid: compact under the title (mini) or the full Month view with item labels. */
function MonthGrid({
  month,
  selected,
  today,
  snapshot,
  timezone,
  kinds,
  full,
  onPick,
}: {
  month: string;
  selected: string;
  today: string;
  snapshot: Snapshot | null;
  timezone: string;
  kinds: Kinds;
  full: boolean;
  onPick: (day: string) => void;
}) {
  return (
    <View>
      <View style={{ flexDirection: "row" }}>
        {WEEKDAYS.map((name, i) => (
          <Text key={i} style={[styles.label, { width: "14.285%", textAlign: "center" }]}>
            {name}
          </Text>
        ))}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {monthRange(month).days.map((day) => {
          const entries = entriesOn(snapshot, day, timezone, kinds);
          const isToday = day === today;
          return (
            <Pressable
              key={day}
              accessibilityRole="button"
              accessibilityLabel={`${day}${entries.length ? `, ${entries.length} items` : ""}`}
              accessibilityState={{ selected: day === selected }}
              onPress={() => onPick(day)}
              style={{
                width: "14.285%",
                minHeight: full ? 92 : 44,
                paddingVertical: 4,
                paddingHorizontal: 2,
                alignItems: "center",
                gap: 2,
                borderTopWidth: full ? 1 : 0,
                borderTopColor: colors.line,
                borderRadius: full ? 0 : 12,
                backgroundColor: !full && day === selected ? colors.glassStrong : "transparent",
              }}
            >
              <View
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 14,
                  alignItems: "center",
                  justifyContent: "center",
                  backgroundColor: isToday ? colors.accent : "transparent",
                }}
              >
                <Text
                  style={{
                    fontSize: 14,
                    color: isToday ? colors.ink : day.startsWith(month) ? colors.text : colors.faint,
                  }}
                >
                  {Number(day.slice(8))}
                </Text>
              </View>
              {full
                ? entries.slice(0, 3).map((e) => (
                    <Text
                      key={e.id}
                      numberOfLines={1}
                      style={{
                        alignSelf: "stretch",
                        fontSize: 12,
                        paddingHorizontal: 2,
                        borderRadius: 2,
                        overflow: "hidden",
                        color: filledKind(e) ? colors.ink : colors.text,
                        backgroundColor: filledKind(e) ? colors.accent : "transparent",
                        textDecorationLine: e.kind === "task" && e.done ? "line-through" : "none",
                      }}
                    >
                      {e.kind === "task" ? "○ " : ""}
                      {e.title}
                    </Text>
                  ))
                : !!entries.length && (
                    <View
                      style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: colors.accent }}
                    />
                  )}
              {full && entries.length > 3 && (
                <Text style={{ fontSize: 12, color: colors.muted }}>+{entries.length - 3}</Text>
              )}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** Day and 3-day: an all-day strip, then a 24-hour timeline with a now line. */
function Timeline({
  days,
  today,
  snapshot,
  timezone,
  kinds,
  onOpen,
  onToggle,
  onPickDay,
  onCreateAt,
}: {
  days: string[];
  today: string;
  snapshot: Snapshot | null;
  timezone: string;
  kinds: Kinds;
  onOpen: (e: Entry) => void;
  onToggle: (t: Task) => void;
  onPickDay: (day: string) => void;
  onCreateAt: (day: string) => void;
}) {
  const scroller = useRef<ScrollView>(null);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const [h] = wallClock(new Date().toISOString(), timezone).split(":").map(Number);
    const timer = setTimeout(
      () => scroller.current?.scrollTo({ y: Math.max(0, (h - 1) * HOUR), animated: false }),
      0,
    );
    return () => clearTimeout(timer);
  }, [timezone]);
  const [nh, nm] = wallClock(now.toISOString(), timezone).split(":").map(Number);
  const nowMinutes = nh * 60 + nm;
  const perDay = days.map((day) => {
    const entries = entriesOn(snapshot, day, timezone, kinds);
    return {
      day,
      strip: entries.filter((e) => e.kind === "allday" || e.kind === "task"),
      timed: lanes(
        entries
          .filter((e) => e.kind === "event" || e.kind === "availability")
          .map((e) => ({ entry: e, ...span(e.item as TimedItem, day, timezone) })),
      ),
    };
  });
  return (
    <View style={{ flex: 1 }}>
      <View style={{ flexDirection: "row", paddingBottom: 6 }}>
        <View style={{ width: GUTTER }} />
        {days.map((day) => (
          <View key={day} style={{ flex: 1, alignItems: "center" }}>
            <DayBadge day={day} today={today} onPress={() => onPickDay(day)} />
          </View>
        ))}
      </View>
      {perDay.some((d) => d.strip.length) && (
        <View
          style={{
            flexDirection: "row",
            paddingBottom: 6,
            borderBottomWidth: 1,
            borderBottomColor: colors.line,
          }}
        >
          <View style={{ width: GUTTER }} />
          {perDay.map(({ day, strip }) => (
            <View key={day} style={{ flex: 1, gap: 4, paddingHorizontal: 2 }}>
              {strip.map((e) => (
                <Chip key={e.id} entry={e} timezone={timezone} onOpen={onOpen} onToggle={onToggle} />
              ))}
            </View>
          ))}
        </View>
      )}
      <ScrollView ref={scroller} style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 96 }}>
        <View style={{ flexDirection: "row", height: 24 * HOUR }}>
          <View style={{ width: GUTTER }}>
            {Array.from({ length: 24 }, (_, h) => (
              <Text
                key={h}
                style={{
                  position: "absolute",
                  top: h * HOUR - 8,
                  right: 8,
                  fontSize: 12,
                  color: colors.muted,
                }}
              >
                {h ? `${String(h).padStart(2, "0")}:00` : ""}
              </Text>
            ))}
          </View>
          {perDay.map(({ day, timed }) => (
            <View key={day} style={{ flex: 1, borderLeftWidth: 1, borderLeftColor: colors.line }}>
              {Array.from({ length: 24 }, (_, h) => (
                <Pressable
                  key={h}
                  accessibilityRole="button"
                  accessibilityLabel={`New event ${day} ${String(h).padStart(2, "0")}:00`}
                  onPress={() => onCreateAt(day)}
                  style={{ height: HOUR, borderTopWidth: 1, borderTopColor: colors.line }}
                />
              ))}
              {timed.map((t) => {
                const filled = t.entry.kind === "event";
                const item = t.entry.item as TimedItem;
                return (
                  <Pressable
                    key={t.entry.id}
                    accessibilityRole="button"
                    accessibilityLabel={`${describe(t.entry)}: ${t.entry.title}, ${clock(item.starts_at, timezone)}`}
                    onPress={() => onOpen(t.entry)}
                    style={{
                      position: "absolute",
                      top: (t.start / 60) * HOUR + 1,
                      height: Math.max(((t.end - t.start) / 60) * HOUR - 2, 22),
                      left: `${(t.lane / t.lanes) * 100}%`,
                      width: `${100 / t.lanes}%`,
                      paddingHorizontal: 6,
                      paddingVertical: 2,
                      borderRadius: 12,
                      borderWidth: 1,
                      borderStyle: filled ? "solid" : "dashed",
                      borderColor: filled ? colors.accent : colors.buttonBorder,
                      backgroundColor: filled ? colors.accent : colors.glass,
                      overflow: "hidden",
                    }}
                  >
                    <Text
                      numberOfLines={2}
                      style={{ fontSize: 12, fontWeight: "600", color: filled ? colors.ink : colors.text }}
                    >
                      {t.entry.title}
                    </Text>
                    <Text numberOfLines={1} style={{ fontSize: 12, color: filled ? colors.ink : colors.muted }}>
                      {clock(item.starts_at, timezone)}
                    </Text>
                  </Pressable>
                );
              })}
              {day === today && (
                <View
                  accessibilityLabel="Current time"
                  pointerEvents="none"
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    top: (nowMinutes / 60) * HOUR,
                    height: 2,
                    backgroundColor: colors.error,
                  }}
                >
                  <View
                    style={{
                      position: "absolute",
                      left: -5,
                      top: -4,
                      width: 10,
                      height: 10,
                      borderRadius: 5,
                      backgroundColor: colors.error,
                    }}
                  />
                </View>
              )}
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

/** Schedule: the coming days that have something, the date on the left. */
function ScheduleList({
  snapshot,
  from,
  today,
  timezone,
  kinds,
  onOpen,
  onToggle,
  onPickDay,
}: {
  snapshot: Snapshot | null;
  from: string;
  today: string;
  timezone: string;
  kinds: Kinds;
  onOpen: (e: Entry) => void;
  onToggle: (t: Task) => void;
  onPickDay: (day: string) => void;
}) {
  const days = schedule(snapshot, from, timezone, kinds);
  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 12, paddingBottom: 96 }}>
      {!days.length && (
        <Text style={styles.subtitle}>Nothing scheduled in the next few weeks.</Text>
      )}
      {days.map(({ day, entries }, i) => (
        <View key={day} style={{ gap: 8 }}>
          {(i === 0 || days[i - 1].day.slice(0, 7) !== day.slice(0, 7)) && (
            <Text accessibilityRole="header" style={[styles.text, { fontWeight: "600" }]}>
              {monthTitle(day)}
            </Text>
          )}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <DayBadge day={day} today={today} onPress={() => onPickDay(day)} />
            <View style={{ flex: 1, gap: 6 }}>
              {entries.map((e) => (
                <Chip key={e.id} entry={e} timezone={timezone} onOpen={onOpen} onToggle={onToggle} />
              ))}
            </View>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

export function Calendar({ active }: { active: boolean }) {
  const { timezone } = useWorkspace();
  const today = dayKey(new Date(), timezone);
  const [view, setView] = useState<CalendarView>("schedule");
  const [selected, setSelected] = useState(today);
  const [kinds, setKinds] = useState<Kinds>(ALL_KINDS);
  const [drawer, setDrawer] = useState(false);
  const [mini, setMini] = useState(false);
  const [create, setCreate] = useState(false);
  const [editor, setEditor] = useState<Selection | null | undefined>(undefined);
  const [editorDay, setEditorDay] = useState(today);
  const [newTask, setNewTask] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const shown = visibleDays(view, selected);
  const month = selected.slice(0, 7);
  // A 3-day view or the schedule can run into the next month: load that month too.
  const last = view === "schedule" ? addDays(selected, 44) : shown[shown.length - 1];
  const first = usePlanning(month, active);
  const second = usePlanning(last.slice(0, 7), active);
  const snapshot = merge(first.snapshot, second.snapshot);
  const loadError = first.error || second.error;
  const changed = () => first.changed();
  const swipe = useRef<{ x: number; y: number } | null>(null);
  const move = (direction: number) => {
    if (view === "month") setSelected(`${shiftMonth(month, direction)}-01`);
    else setSelected(addDays(selected, direction * step(view)));
  };
  const onOpen = (entry: Entry) => {
    if (entry.kind === "task") setTask(entry.item);
    else if (entry.kind === "allday") setEditor({ type: "date", item: entry.item });
    else setEditor({ type: entry.kind, item: entry.item });
  };
  const onToggle = async (t: Task) => {
    setError("");
    try {
      await api.plan("task.execute", { action: t.done ? "reopen" : "complete" }, t.id, t.version);
      changed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the task.");
    }
  };
  const pickDay = (day: string) => {
    setSelected(day);
    setMini(false);
    if (view === "month" || view === "schedule") setView("day");
  };
  return (
    <View style={{ flex: 1 }}>
      <View style={{ paddingHorizontal: 16, paddingTop: 12, gap: 8 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Calendar views and filters"
            onPress={() => setDrawer(true)}
            style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}
          >
            <Text style={{ fontSize: 20, color: colors.text }}>☰</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`${monthTitle(selected)}, choose a date`}
            accessibilityState={{ expanded: mini }}
            onPress={() => setMini(!mini)}
            style={{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1, minHeight: 44 }}
          >
            <Text accessibilityRole="header" numberOfLines={1} style={styles.title}>
              {new Date(`${month}-01T12:00:00`).toLocaleDateString(undefined, { month: "long" })}
            </Text>
            <Text style={{ fontSize: 14, color: colors.muted }}>{mini ? "▴" : "▾"}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Go to today"
            onPress={() => {
              setSelected(today);
              setMini(false);
            }}
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: colors.buttonBorder,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={{ fontSize: 14, fontWeight: "600", color: colors.text }}>
              {Number(today.slice(8))}
            </Text>
          </Pressable>
        </View>
        {mini && view !== "month" && (
          <Panel>
            <MonthGrid
              month={month}
              selected={selected}
              today={today}
              snapshot={snapshot}
              timezone={timezone}
              kinds={kinds}
              full={false}
              onPick={(day) => {
                setSelected(day);
                setMini(false);
              }}
            />
            <View style={[styles.row, { justifyContent: "space-between" }]}>
              <Button
                title="‹"
                accessibilityLabel="Previous month"
                onPress={() => setSelected(`${shiftMonth(month, -1)}-01`)}
              />
              <Button
                title="›"
                accessibilityLabel="Next month"
                onPress={() => setSelected(`${shiftMonth(month, 1)}-01`)}
              />
            </View>
          </Panel>
        )}
        <ErrorText message={error || loadError} />
        {!!loadError && (
          <Button
            title="Retry"
            onPress={() => {
              first.refresh();
              second.refresh();
            }}
          />
        )}
        {(first.loading || second.loading) && !snapshot && <Loading />}
      </View>
      <View
        style={{ flex: 1, paddingHorizontal: view === "month" ? 8 : 16, paddingTop: 8 }}
        onTouchStart={(e) => {
          swipe.current = { x: e.nativeEvent.pageX, y: e.nativeEvent.pageY };
        }}
        onTouchEnd={(e) => {
          const start = swipe.current;
          swipe.current = null;
          if (!start || view === "schedule") return;
          const dx = e.nativeEvent.pageX - start.x;
          const dy = e.nativeEvent.pageY - start.y;
          if (Math.abs(dx) > 60 && Math.abs(dx) > 2 * Math.abs(dy)) move(dx < 0 ? 1 : -1);
        }}
      >
        {view === "schedule" && (
          <ScheduleList
            snapshot={snapshot}
            from={selected}
            today={today}
            timezone={timezone}
            kinds={kinds}
            onOpen={onOpen}
            onToggle={(t) => void onToggle(t)}
            onPickDay={pickDay}
          />
        )}
        {(view === "day" || view === "3day") && (
          <Timeline
            days={shown}
            today={today}
            snapshot={snapshot}
            timezone={timezone}
            kinds={kinds}
            onOpen={onOpen}
            onToggle={(t) => void onToggle(t)}
            onPickDay={(day) => {
              setSelected(day);
              setView("day");
            }}
            onCreateAt={(day) => {
              setEditorDay(day);
              setEditor(null);
            }}
          />
        )}
        {view === "month" && (
          <ScrollView contentContainerStyle={{ paddingBottom: 96 }}>
            <MonthGrid
              month={month}
              selected={selected}
              today={today}
              snapshot={snapshot}
              timezone={timezone}
              kinds={kinds}
              full
              onPick={pickDay}
            />
          </ScrollView>
        )}
      </View>
      {create && (
        <View
          style={{ position: "absolute", right: 16, bottom: 88, alignItems: "flex-end", gap: 8 }}
        >
          {(
            [
              ["Task", () => setNewTask(selected)],
              [
                "Event",
                () => {
                  setEditorDay(selected);
                  setEditor(null);
                },
              ],
            ] as const
          ).map(([label, act]) => (
            <Pressable
              key={label}
              accessibilityRole="button"
              accessibilityLabel={`New ${label.toLowerCase()}`}
              onPress={() => {
                setCreate(false);
                act();
              }}
              style={{
                minHeight: 44,
                justifyContent: "center",
                paddingHorizontal: 15,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: colors.glassBorder,
                backgroundColor: colors.glassStrong,
              }}
            >
              <Text style={styles.buttonText}>{label}</Text>
            </Pressable>
          ))}
        </View>
      )}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={create ? "Close create menu" : "Create"}
        onPress={() => setCreate(!create)}
        style={({ pressed }) => ({
          position: "absolute",
          right: 16,
          bottom: 16,
          width: 56,
          height: 56,
          borderRadius: 18,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: colors.accent,
          opacity: pressed ? 0.8 : 1,
        })}
      >
        <Text style={{ fontSize: 29, color: colors.ink }}>{create ? "×" : "+"}</Text>
      </Pressable>
      <Sheet visible={drawer} title="Calendar" onClose={() => setDrawer(false)}>
        <Text style={styles.label}>View</Text>
        <Panel>
          {VIEWS.map((v) => (
            <Pressable
              key={v.value}
              accessibilityRole="radio"
              accessibilityLabel={v.label}
              accessibilityState={{ checked: view === v.value }}
              onPress={() => {
                setView(v.value);
                setDrawer(false);
              }}
              style={{ minHeight: 48, flexDirection: "row", alignItems: "center", gap: 12 }}
            >
              <Text style={{ width: 20, color: colors.accent }}>{view === v.value ? "●" : "○"}</Text>
              <Text style={styles.text}>{v.label}</Text>
            </Pressable>
          ))}
        </Panel>
        <Text style={styles.label}>Show</Text>
        <Panel>
          {(
            [
              ["events", "Events"],
              ["tasks", "Tasks"],
              ["availability", "Availability"],
            ] as const
          ).map(([key, label]) => (
            <Pressable
              key={key}
              accessibilityRole="checkbox"
              accessibilityLabel={label}
              accessibilityState={{ checked: kinds[key] }}
              onPress={() => setKinds({ ...kinds, [key]: !kinds[key] })}
              style={{ minHeight: 48, flexDirection: "row", alignItems: "center", gap: 12 }}
            >
              <Text style={{ width: 20, color: colors.accent }}>{kinds[key] ? "☑" : "☐"}</Text>
              <Text style={styles.text}>{label}</Text>
            </Pressable>
          ))}
        </Panel>
        <Text style={styles.subtitle}>Times in {timezone}</Text>
      </Sheet>
      {editor !== undefined && (
        <EventEditor
          day={editorDay}
          selection={editor}
          onClose={() => setEditor(undefined)}
          onSaved={changed}
        />
      )}
      {newTask !== null && (
        <TaskEditor
          task={null}
          initialDue={newTask}
          onClose={() => setNewTask(null)}
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
    </View>
  );
}
