"use client";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  addDays,
  conflicts,
  calendarLanes,
  onLocalDay,
  dateInZone,
  minuteOfDay,
  minutesBetween,
  monthDays,
  wallTime,
  weekDays,
  type CalendarEvent,
  type PlanningBlock,
  type PlanningTask,
  type CalendarDateItem,
  type AvailabilityWindow,
} from "@/lib/planning";
import { usePlanning } from "./planning-provider";
import { Capacity } from "./planning-daily";
import {
  CommandButton,
  PlanningFeedback,
  TaskRow,
  TimeForm,
} from "./planning-ui";
import { Empty, Icon, Modal, Panel } from "./ui";
import { planningTabsKeyDown } from "@/lib/planning-accessibility";
import { LinkedNoteContext } from "./linked-note-context";
import { AvailabilityForm, CalendarDateForm } from "./calendar-date-form";
import { temporalWrite } from "@/lib/temporal-api";
import {
  blockHeight,
  blockMode,
  hourHeight,
  minuteTop,
  placement,
  scrollToNow,
} from "@/features/calendar/grid";
import { NowLine, useNow } from "@/features/calendar/now-line";
import { MiniMonth } from "@/features/calendar/mini-month";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/primitives";
import { useRegisterPageContext } from "@/features/side-chat/page-context";

type Item = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  kind: "event" | "block" | "routine";
  task?: PlanningTask;
  block?: PlanningBlock;
  event?: CalendarEvent;
};
export function CalendarPage() {
  const { data, day, setDay, timezone, setTimezone, run, select } =
    usePlanning();
  const [view, setView] = useState<"day" | "week" | "month" | "agenda">("week"),
    [editing, setEditing] = useState<Item | null>(null),
    [newEvent, setNewEvent] = useState(false),
    [railQuery, setRailQuery] = useState(""),
    [scheduling, setScheduling] = useState(false);
  const [newKind, setNewKind] = useState<
    "event" | "date_item" | "availability"
  >("event");
  const [editingDate, setEditingDate] = useState<CalendarDateItem | null>(null);
  const [editingAvailability, setEditingAvailability] =
    useState<AvailabilityWindow | null>(null);
  const [showAvailability, setShowAvailability] = useState(false),
    [temporalBusy, setTemporalBusy] = useState(false),
    [temporalError, setTemporalError] = useState("");
  const today = dateInZone(new Date(), timezone);
  const items = useMemo<Item[]>(
    () =>
      !data
        ? []
        : [
            ...data.events.map((event) => ({
              ...event,
              kind: "event" as const,
              event,
            })),
            ...data.blocks.map((block) => {
              const task = data.tasks.find((t) => t.id === block.task_id);
              return {
                ...block,
                title: task?.title || "Task",
                kind: task?.template_id
                  ? ("routine" as const)
                  : ("block" as const),
                block,
                task,
              };
            }),
          ].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)),
    [data],
  );
  // Mini month: one dot per day with any commitment (presence, never a count).
  const busyDays = useMemo(
    () => new Set(items.map((i) => dateInZone(i.starts_at, timezone))),
    [items, timezone],
  );
  const conflictIds = conflicts(
    items.filter((i) => !i.task?.done && i.task?.state !== "skipped"),
  );
  const visibleDays =
    view === "month" ? monthDays(day) : view === "week" ? weekDays(day) : [day];
  const dateItems = (data?.date_items || []).filter(
    (item) => showAvailability || item.kind !== "availability",
  );
  const datesOn = (date: string) =>
    dateItems.filter(
      (item) => item.starts_on <= date && item.ends_before > date,
    );
  const visibleDateItems = dateItems.filter(
    (item) =>
      item.starts_on <=
        (view === "agenda"
          ? data?.summaries.at(-1)?.day || day
          : visibleDays.at(-1)!) && item.ends_before > visibleDays[0],
  );
  // Phase E: the side chat sees the period in view and its items (ids, titles, times).
  useRegisterPageContext("calendar", () => ({
    surface: `calendar-${view}`,
    focus: {
      kind: "view",
      id: `${view}:${visibleDays[0]}`,
      label:
        view === "week"
          ? `Week of ${visibleDays[0]}`
          : view === "month"
            ? `Month of ${day.slice(0, 7)}`
            : `Day ${day}`,
      origin: "ambient",
    },
    visible: items
      .filter((i) => visibleDays.includes(dateInZone(i.starts_at, timezone)))
      .map((i) => ({
        kind: i.kind === "event" ? ("event" as const) : ("task" as const),
        id: i.id,
        label: i.title,
        origin: "ambient" as const,
        fields: { starts: i.starts_at, ends: i.ends_at },
      })),
    capabilities: ["event.read", "block.move"],
  }));
  const closeEditor = () => {
    setNewEvent(false);
    setEditing(null);
    setEditingDate(null);
    setEditingAvailability(null);
    setTemporalError("");
  };
  const backlog =
    data?.tasks.filter(
      (t) =>
        !t.done &&
        t.state !== "skipped" &&
        !t.next_scheduled_at &&
        `${t.title} ${t.tags.join(" ")}`
          .toLowerCase()
          .includes(railQuery.toLowerCase()),
    ) || [];
  function navigate(direction: number) {
    if (view === "month") {
      const date = new Date(day + "T12:00:00Z");
      date.setUTCDate(1);
      date.setUTCMonth(date.getUTCMonth() + direction);
      setDay(date.toISOString().slice(0, 10));
    } else setDay(addDays(day, direction * (view === "week" ? 7 : 1)));
  }
  const open = (item: Item) => {
    if (item.task) select(item.task.id);
    else setEditing(item);
  };
  return (
    <div className="standard-page planning-page planning-calendar-page">
      <div className="page-intro">
        <div>
          <h1>Calendar</h1>
        </div>
        <button
          className="button primary"
          onClick={() => {
            setNewKind("event");
            setNewEvent(true);
          }}
        >
          <Icon name="Plus" size={16} />
          New event
        </button>
      </div>
      <div className="calendar-surface" data-view={view}>
        <header className="planning-toolbar calendar-toolbar">
          <div className="calendar-heading">
            <h2>
              <span>
                {new Date(day + "T12:00:00Z").toLocaleDateString("en", {
                  month: "long",
                  timeZone: "UTC",
                })}
              </span>
              <span className="calendar-year">{day.slice(0, 4)}</span>
            </h2>
            <p>
              {view === "week"
                ? `${new Date(visibleDays[0] + "T12:00:00Z").toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" })} – ${new Date(visibleDays[6] + "T12:00:00Z").toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" })}`
                : view === "day"
                  ? new Date(day + "T12:00:00Z").toLocaleDateString("en", {
                      weekday: "long",
                      day: "numeric",
                      timeZone: "UTC",
                    })
                  : view === "agenda"
                    ? "Upcoming commitments"
                    : "Month view"}
            </p>
          </div>
          <div className="planning-nav calendar-period-nav">
            <button
              className="button calendar-today"
              onClick={() => setDay(today)}
            >
              Today
            </button>
            <div className="calendar-arrows">
              <button
                className="icon-button"
                aria-label={`Previous ${view}`}
                onClick={() => navigate(-1)}
              >
                <Icon name="ChevronLeft" size={18} />
              </button>
              <button
                className="icon-button"
                aria-label={`Next ${view}`}
                onClick={() => navigate(1)}
              >
                <Icon name="ChevronRight" size={18} />
              </button>
            </div>
          </div>
          <div
            className="planning-tabs"
            role="tablist"
            onKeyDown={planningTabsKeyDown}
            aria-label="Calendar view"
          >
            {(["day", "week", "month", "agenda"] as const).map((v) => (
              <button
                key={v}
                role="tab"
                tabIndex={view === v ? 0 : -1}
                aria-selected={view === v}
                onClick={() => setView(v)}
              >
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
        </header>
        <div className="calendar-utilities">
          <label className="calendar-jump">
            <Icon name="CalendarDays" size={15} />
            <span className="sr-only">Go to date</span>
            <input
              aria-label="Calendar date"
              type="date"
              value={day}
              onChange={(event) => {
                if (event.target.value) setDay(event.target.value);
              }}
            />
          </label>
          <Popover>
            <PopoverTrigger asChild>
              <button className="button" aria-label="Month picker">
                <Icon name="CalendarRange" size={15} />
                Month
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-2">
              <MiniMonth
                day={day}
                today={today}
                busy={busyDays}
                onPick={setDay}
              />
            </PopoverContent>
          </Popover>
          <button
            className="button"
            aria-pressed={showAvailability}
            onClick={() => setShowAvailability((value) => !value)}
          >
            Availability
          </button>
          <button
            className="button"
            aria-expanded={scheduling}
            aria-controls="calendar-scheduling"
            onClick={() => setScheduling((value) => !value)}
          >
            Schedule tasks
          </button>
          <details className="quiet-calendar-options">
            <summary>Timezone</summary>
            <select
              aria-label="Calendar timezone"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
            >
              {[
                ...new Set([
                  timezone,
                  "Europe/Berlin",
                  "Europe/London",
                  "America/New_York",
                  "Asia/Kolkata",
                  "UTC",
                ]),
              ].map((z) => (
                <option key={z}>{z}</option>
              ))}
            </select>
          </details>
        </div>
        <PlanningFeedback />
        {conflictIds.size > 0 && (
          <p className="planning-warning" role="status">
            {conflictIds.size} overlapping items. Open them to review.
          </p>
        )}
        <div
          className={`unified-calendar-layout ${scheduling ? "" : "schedule-closed"}`}
        >
          {scheduling && (
            <div id="calendar-scheduling">
              <Panel
                className="planning-calendar-rail"
                title="Unscheduled tasks"
              >
                <p className="muted">
                  Drag a task onto a time slot, or open it to enter an exact
                  time.
                </p>
                <input
                  className="planning-rail-search"
                  aria-label="Find unscheduled tasks"
                  placeholder="Find a task…"
                  value={railQuery}
                  onChange={(e) => setRailQuery(e.target.value)}
                />
                {backlog.slice(0, 30).map((t) => (
                  <TaskRow key={t.id} task={t} scheduling />
                ))}
                {!backlog.length && (
                  <Empty
                    title="No unscheduled tasks"
                    detail="Capture tasks in the Task Manager, then choose their execution windows."
                  />
                )}
                <a className="button" href="/tasks">
                  Open Task Manager
                </a>
                <Capacity day={day} />
              </Panel>
            </div>
          )}
          <Panel className="unified-calendar-panel">
            {view !== "month" && visibleDateItems.length > 0 && (
              <div
                className="calendar-date-strip"
                aria-label="All-day calendar items"
              >
                <span>All day</span>
                {visibleDateItems.slice(0, 12).map((item) => (
                  <button
                    key={item.id}
                    className={`calendar-date-item ${item.kind}`}
                    onClick={() => setEditingDate(item)}
                  >
                    {item.title}
                    <small>
                      {item.starts_on}
                      {item.ends_before > addDays(item.starts_on, 1)
                        ? ` – ${addDays(item.ends_before, -1)}`
                        : ""}
                    </small>
                  </button>
                ))}
                {visibleDateItems.length > 12 && (
                  <span>
                    {visibleDateItems.length - 12} more date items in this range
                  </span>
                )}
              </div>
            )}
            {!data ? (
              <p role="status">Loading your shared calendar…</p>
            ) : view === "month" ? (
              <>
                <div className="calendar-weekdays">
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                    (d) => (
                      <span key={d}>{d}</span>
                    ),
                  )}
                </div>
                <div className="calendar-grid">
                  {visibleDays.map((d) => {
                    const entries = items.filter((i) =>
                        onLocalDay(i, d, timezone),
                      ),
                      deadlines = data.tasks.filter(
                        (t) =>
                          t.due_date === d && !t.done && t.state !== "skipped",
                      );
                    const dates = datesOn(d);
                    return (
                      <div
                        key={d}
                        className={`calendar-cell unified-month-cell ${d.slice(0, 7) !== day.slice(0, 7) ? "outside" : ""} ${d === today ? "is-today" : ""} ${d === day ? "selected" : ""}`}
                      >
                        <button
                          className="day-number"
                          aria-label={`${d}, ${entries.length} scheduled items, ${deadlines.length} deadlines${dates.length ? `, ${dates.length} date items` : ""}`}
                          onClick={() => {
                            setDay(d);
                            setView("day");
                          }}
                        >
                          {Number(d.slice(-2))}
                        </button>
                        {entries.length + deadlines.length + dates.length >
                          0 && (
                          <span
                            className="calendar-day-count"
                            aria-hidden="true"
                          >
                            {entries.length + deadlines.length + dates.length}{" "}
                            {entries.length +
                              deadlines.length +
                              dates.length ===
                            1
                              ? "item"
                              : "items"}
                          </span>
                        )}
                        <div className="calendar-cell-events">
                          {dates.slice(0, 2).map((item) => (
                            <button
                              key={item.id}
                              className={`planning-month-item date-item ${item.kind}`}
                              title={`${item.title} · ${item.starts_on} to ${addDays(item.ends_before, -1)}`}
                              onClick={() => setEditingDate(item)}
                            >
                              {item.kind === "review"
                                ? "Review · "
                                : item.kind === "availability"
                                  ? "Available · "
                                  : "All day · "}
                              {item.title}
                            </button>
                          ))}
                          {entries.slice(0, 3).map((i) => (
                            <button
                              key={i.id}
                              className={`planning-month-item ${i.kind} ${i.task?.done ? "done" : ""}`}
                              title={`${wallTime(i.starts_at, timezone)} · ${i.title}`}
                              onClick={() => open(i)}
                            >
                              {dateInZone(i.starts_at, timezone) === d
                                ? wallTime(i.starts_at, timezone)
                                : "↳"}{" "}
                              {i.title}
                            </button>
                          ))}
                          {deadlines.slice(0, 2).map((t) => (
                            <button
                              key={t.id}
                              className="planning-month-item deadline"
                              onClick={() => select(t.id)}
                            >
                              ◇ {t.title}
                            </button>
                          ))}
                          {(entries.length > 3 ||
                            deadlines.length > 2 ||
                            dates.length > 2) && (
                            <button
                              onClick={() => {
                                setDay(d);
                                setView("agenda");
                              }}
                            >
                              View all{" "}
                              {entries.length + deadlines.length + dates.length}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : view === "agenda" ? (
              <div className="planning-agenda">
                {data.summaries
                  .map((s) => s.day)
                  .filter(
                    (d) =>
                      d >= day &&
                      (items.some((i) => onLocalDay(i, d, timezone)) ||
                        data.tasks.some((t) => t.due_date === d && !t.done) ||
                        datesOn(d).length > 0),
                  )
                  .slice(0, 31)
                  .map((d) => (
                    <section key={d}>
                      <h3>
                        {new Date(d + "T12:00:00Z").toLocaleDateString("en", {
                          weekday: "long",
                          month: "short",
                          day: "numeric",
                          timeZone: "UTC",
                        })}
                      </h3>
                      {datesOn(d).map((item) => (
                        <button
                          key={item.id}
                          className="planning-agenda-item date-item"
                          onClick={() => setEditingDate(item)}
                        >
                          <span>All day</span>
                          <strong>{item.title}</strong>
                          <small>
                            {item.kind === "availability"
                              ? "Available days"
                              : item.kind === "review"
                                ? "Review date"
                                : "Date item"}
                          </small>
                        </button>
                      ))}
                      {items
                        .filter((i) => onLocalDay(i, d, timezone))
                        .map((i) => (
                          <button
                            className={`planning-agenda-item ${i.kind}`}
                            key={i.id}
                            onClick={() => open(i)}
                          >
                            <span>
                              {wallTime(i.starts_at, timezone)}–
                              {wallTime(i.ends_at, timezone)}
                            </span>
                            <strong>{i.title}</strong>
                            <small>
                              {i.kind === "event"
                                ? "Fixed event"
                                : i.kind === "routine"
                                  ? "Routine"
                                  : "Flexible task block"}{" "}
                              ·{" "}
                              {Math.round(
                                minutesBetween(i.starts_at, i.ends_at),
                              )}{" "}
                              min
                              {conflictIds.has(i.id)
                                ? " · overlaps another commitment"
                                : ""}
                            </small>
                          </button>
                        ))}
                      {data.tasks
                        .filter((t) => t.due_date === d && !t.done)
                        .map((t) => (
                          <button
                            className="planning-agenda-item deadline"
                            key={t.id}
                            onClick={() => select(t.id)}
                          >
                            ◇ Deadline · {t.title}
                          </button>
                        ))}
                    </section>
                  ))}
                {!items.length &&
                  !visibleDateItems.length &&
                  !data.tasks.some((t) => t.due_date && t.due_date >= day) && (
                    <Empty
                      title="No upcoming calendar entries"
                      detail="Create an event or schedule a task to begin."
                    />
                  )}
              </div>
            ) : (
              <TimeGrid
                days={visibleDays}
                items={items}
                availability={showAvailability ? data.availability || [] : []}
                openAvailability={setEditingAvailability}
                conflictIds={conflictIds}
                open={open}
                edit={setEditing}
              />
            )}
          </Panel>
        </div>
      </div>
      <Modal
        open={newEvent || !!editing || !!editingDate || !!editingAvailability}
        preventDismiss={temporalBusy}
        onOpenChange={(value) => {
          if (!value) {
            closeEditor();
          }
        }}
        title={
          editingDate
            ? "Edit date item"
            : editingAvailability
              ? "Edit availability"
              : newEvent && newKind === "date_item"
                ? "New date item"
                : newEvent && newKind === "availability"
                  ? "New availability"
                  : editing?.block
                    ? "Move or resize execution block"
                    : editing
                      ? "Edit fixed event"
                      : "New fixed event"
        }
        description="Calendar changes preserve task objectives and deadlines."
      >
        {(newEvent || editing || editingDate || editingAvailability) && (
          <>
            {newEvent && (
              <label className="calendar-item-kind">
                Calendar item type
                <select
                  value={newKind}
                  onChange={(event) =>
                    setNewKind(event.target.value as typeof newKind)
                  }
                >
                  <option value="event">Timed appointment</option>
                  <option value="date_item">All-day event or date range</option>
                  <option value="availability">Available time</option>
                </select>
              </label>
            )}
            {temporalError && (
              <p className="error" role="alert">
                {temporalError}
              </p>
            )}
            {editingDate && (
              <LinkedNoteContext
                kind="date_item"
                id={editingDate.id}
                version={editingDate.version}
              />
            )}
            {editingAvailability && (
              <LinkedNoteContext
                kind="availability"
                id={editingAvailability.id}
                version={editingAvailability.version}
              />
            )}
            {editingDate || (newEvent && newKind === "date_item") ? (
              <CalendarDateForm
                item={editingDate || undefined}
                onSaved={closeEditor}
                onPendingChange={setTemporalBusy}
              />
            ) : editingAvailability ||
              (newEvent && newKind === "availability") ? (
              <AvailabilityForm
                item={editingAvailability || undefined}
                onSaved={closeEditor}
                onPendingChange={setTemporalBusy}
              />
            ) : (
              <>
                {editing?.event && (
                  <LinkedNoteContext
                    kind="event"
                    id={editing.id}
                    version={editing.event.version}
                  />
                )}
                <TimeForm
                  key={editing?.id || "new"}
                  event={editing?.event}
                  block={editing?.block}
                  task={editing?.task}
                  onSaved={() => {
                    setNewEvent(false);
                    setEditing(null);
                  }}
                />
              </>
            )}
            {(editingDate || editingAvailability) && (
              <button
                className="button planning-remove"
                disabled={temporalBusy}
                onClick={async () => {
                  const item = editingDate || editingAvailability!;
                  setTemporalBusy(true);
                  setTemporalError("");
                  try {
                    await temporalWrite(
                      editingDate ? "date_item.remove" : "availability.remove",
                      {},
                      item.id,
                      item.version,
                    );
                    closeEditor();
                  } catch (error) {
                    setTemporalError(
                      error instanceof Error
                        ? error.message
                        : "Could not remove this calendar item.",
                    );
                  } finally {
                    setTemporalBusy(false);
                  }
                }}
              >
                Remove this calendar item
              </button>
            )}
            {editing && (
              <CommandButton
                className="button planning-remove"
                action={async () => {
                  await run(
                    editing.block ? "block.remove" : "event.remove",
                    {},
                    editing.id,
                    (editing.block || editing.event)!.version,
                  );
                  setEditing(null);
                }}
              >
                Remove {editing.block ? "this block (keep task)" : "event"}
              </CommandButton>
            )}
          </>
        )}
      </Modal>
    </div>
  );
}

function TimeGrid({
  days,
  items,
  availability,
  openAvailability,
  conflictIds,
  open,
  edit,
}: {
  days: string[];
  items: Item[];
  availability: AvailabilityWindow[];
  openAvailability: (item: AvailabilityWindow) => void;
  conflictIds: Set<string>;
  open: (item: Item) => void;
  edit: (item: Item) => void;
}) {
  const { data, timezone, run, busy, select } = usePlanning();
  const lanes = calendarLanes(items);
  const scrollRef = useRef<HTMLDivElement>(null);
  const dayKey = days.join("|");
  // Phase C: 13 visible hours fill the grid (--hour-h, 44-72px), measured from its height.
  const [hourPx, setHourPx] = useState(56);
  useEffect(() => {
    const box = scrollRef.current;
    if (!box) return;
    const measure = () => setHourPx(hourHeight(box.clientHeight));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);
  const now = useNow();
  const todayKey = dateInZone(now, timezone);
  const nowMinute = minuteOfDay(now.toISOString(), timezone);
  const showsToday = days.includes(todayKey);
  const hadToday = useRef<boolean | null>(null);
  // Scroll to now (a third from the top) on mount and when returning to this week;
  // other week changes keep the reader's scroll position.
  useEffect(() => {
    const box = scrollRef.current;
    if (!box) return;
    if (hadToday.current === null || (showsToday && !hadToday.current))
      box.scrollTop = showsToday
        ? scrollToNow(nowMinute, hourPx, box.clientHeight)
        : minuteTop(7 * 60, hourPx);
    hadToday.current = showsToday;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dayKey, hourPx]);
  const [hover, setHover] = useState(""),
    [resize, setResize] = useState<{
      item: Item;
      y: number;
      end: number;
    } | null>(null),
    [preview, setPreview] = useState<number | null>(null);
  const [moving, setMoving] = useState<{
    item?: Item;
    taskId?: string;
    x: number;
    y: number;
  } | null>(null);
  useEffect(() => {
    const external = (event: Event) =>
      setMoving(
        (event as CustomEvent<{ taskId: string; x: number; y: number }>).detail,
      );
    window.addEventListener("yggdress:planning-drag-task", external);
    return () =>
      window.removeEventListener("yggdress:planning-drag-task", external);
  }, []);
  useEffect(() => {
    if (!moving) return;
    let target: { day: string; minute: number } | null = null;
    let moved = false;
    const point = (event: PointerEvent) => {
      if (
        Math.hypot(event.clientX - moving.x, event.clientY - moving.y) < 6 &&
        !moved
      )
        return;
      moved = true;
      const column = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest<HTMLElement>("[data-calendar-day]");
      if (!column) {
        target = null;
        setHover("");
        return;
      }
      const minute = Math.max(
        0,
        Math.min(
          1410,
          Math.floor(
            (event.clientY - column.getBoundingClientRect().top) / 28,
          ) * 30,
        ),
      );
      target = { day: column.dataset.calendarDay!, minute };
      setHover(target.day + Math.floor(minute / 30));
    };
    const finish = () => {
      setMoving(null);
      setHover("");
      if (!moved || !target) return;
      const chosen = target as { day: string; minute: number };
      const time = `${String(Math.floor(chosen.minute / 60)).padStart(2, "0")}:${String(chosen.minute % 60).padStart(2, "0")}`;
      const task = data?.tasks.find((t) => t.id === moving.taskId);
      const item = moving.item;
      if (item?.block)
        void run(
          "block.update",
          {
            start: `${chosen.day}T${time}`,
            duration_minutes: minutesBetween(item.starts_at, item.ends_at),
            timezone,
            reason: "Manually dragged in Calendar",
          },
          item.id,
          item.block.version,
        ).catch(() => {});
      else if (task)
        void run("block.create", {
          task_id: task.id,
          start: `${chosen.day}T${time}`,
          duration_minutes: task.estimated_minutes,
          timezone,
          reason: "Dragged from ready-to-schedule tasks",
        }).catch(() => {});
    };
    const cancel = () => {
      setMoving(null);
      setHover("");
    };
    window.addEventListener("pointermove", point);
    window.addEventListener("pointerup", finish, { once: true });
    window.addEventListener("pointercancel", cancel, { once: true });
    return () => {
      window.removeEventListener("pointermove", point);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
    };
  }, [moving, data, run, timezone]);
  async function drop(e: DragEvent, day: string, minute: number) {
    e.preventDefault();
    setHover("");
    if (busy) return;
    const taskId = e.dataTransfer.getData("application/yggdress-task"),
      blockId = e.dataTransfer.getData("application/yggdress-block");
    const time = `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
    const task = data?.tasks.find((t) => t.id === taskId),
      item = items.find((i) => i.id === blockId);
    const duration =
      task?.estimated_minutes ||
      (item ? minutesBetween(item.starts_at, item.ends_at) : 30);
    try {
      if (item?.block)
        await run(
          "block.update",
          {
            start: `${day}T${time}`,
            duration_minutes: duration,
            timezone,
            reason: "Manually moved in Calendar",
          },
          item.id,
          item.block.version,
        );
      else if (task)
        await run("block.create", {
          task_id: task.id,
          start: `${day}T${time}`,
          duration_minutes: duration,
          timezone,
          reason: "Dragged from ready-to-schedule tasks",
        });
    } catch {}
  }
  useEffect(() => {
    if (!resize) return;
    let current = resize.end;
    const moved = (event: PointerEvent) => {
      current = Math.max(
        Date.parse(resize.item.starts_at) + 15 * 60000,
        Math.min(
          Date.parse(resize.item.starts_at) + 7 * 86400000,
          resize.end +
            Math.round((((event.clientY - resize.y) / hourPx) * 60) / 15) *
              15 *
              60000,
        ),
      );
      setPreview(current);
    };
    const end = () => {
      setResize(null);
      setPreview(null);
      if (current !== resize.end && resize.item.block)
        void run(
          "block.update",
          {
            start: resize.item.starts_at,
            end: new Date(current).toISOString(),
            timezone: resize.item.block.timezone,
            reason: "Manually resized in Calendar",
          },
          resize.item.id,
          resize.item.block.version,
        ).catch(() => {});
    };
    const cancel = () => {
      setResize(null);
      setPreview(null);
    };
    window.addEventListener("pointermove", moved);
    window.addEventListener("pointerup", end, { once: true });
    window.addEventListener("pointercancel", cancel, { once: true });
    return () => {
      window.removeEventListener("pointermove", moved);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", cancel);
    };
  }, [resize, run]);
  return (
    <>
      <p className="planning-grid-hint">
        Drag task blocks to move them. Drag their bottom edge to resize. Use the
        item menu or the time form for keyboard and touch scheduling. Repeated
        clock-change hours show their UTC offset.
      </p>
      <div
        className={`planning-time-scroll ${days.length === 1 ? "single-day" : ""}`}
        ref={scrollRef}
        style={{ "--hour-h": `${hourPx}px` } as React.CSSProperties}
      >
        <div
          className="planning-time-head"
          style={{
            gridTemplateColumns: `48px repeat(${days.length},minmax(110px,1fr))`,
          }}
        >
          <span />
          {days.map((day) => (
            <div
              key={day}
              className={
                day === dateInZone(new Date(), timezone) ? "time-day-today" : ""
              }
            >
              <strong className="time-day-heading">
                {new Date(day + "T12:00:00Z").toLocaleDateString("en", {
                  weekday: "short",
                  timeZone: "UTC",
                })}
                <span>{Number(day.slice(-2))}</span>
              </strong>
              <div className="planning-day-deadlines">
                {data?.tasks
                  .filter(
                    (t) =>
                      t.due_date === day && !t.done && t.state !== "skipped",
                  )
                  .slice(0, 3)
                  .map((t) => (
                    <button
                      key={t.id}
                      onClick={() => select(t.id)}
                      title={t.title}
                    >
                      ◇ {t.title}
                    </button>
                  ))}
              </div>
            </div>
          ))}
        </div>
        <div
          className="planning-time-body"
          style={{
            gridTemplateColumns: `48px repeat(${days.length},minmax(110px,1fr))`,
          }}
        >
          <div className="planning-hour-labels">
            {Array.from({ length: 24 }, (_, hour) => (
              <span key={hour}>{String(hour).padStart(2, "0")}:00</span>
            ))}
          </div>
          {days.map((day) => (
            <div
              className="planning-day-column"
              key={day}
              data-calendar-day={day}
            >
              {day === todayKey ? (
                <NowLine minute={nowMinute} hourPx={hourPx} />
              ) : null}
              {availability
                .filter((item) => onLocalDay(item, day, timezone))
                .map((item) => {
                  const start =
                    dateInZone(item.starts_at, timezone) === day
                      ? minuteOfDay(item.starts_at, timezone)
                      : 0;
                  const end =
                    dateInZone(item.ends_at, timezone) === day
                      ? minuteOfDay(item.ends_at, timezone)
                      : 1440;
                  if (end <= start) return null;
                  return (
                    <button
                      key={item.id}
                      className="calendar-availability-window"
                      style={{
                        top: minuteTop(start, hourPx),
                        height: blockHeight(end - start, hourPx),
                      }}
                      onClick={() => openAvailability(item)}
                      aria-label={`Available: ${item.title}, ${wallTime(item.starts_at, timezone)} to ${wallTime(item.ends_at, timezone)}`}
                    >
                      {item.title}
                    </button>
                  );
                })}
              {Array.from({ length: 48 }, (_, slot) => (
                <div
                  key={slot}
                  className={`planning-time-slot ${hover === day + slot ? "drag-over" : ""}`}
                  aria-label={`${day} ${String(Math.floor(slot / 2)).padStart(2, "0")}:${slot % 2 ? "30" : "00"}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setHover(day + slot);
                  }}
                  onDragLeave={() => setHover("")}
                  onDrop={(e) => void drop(e, day, slot * 30)}
                />
              ))}
              {items
                .filter((i) => onLocalDay(i, day, timezone))
                .map((item) => {
                  const starts =
                    dateInZone(item.starts_at, timezone) === day
                      ? minuteOfDay(item.starts_at, timezone)
                      : 0;
                  const endISO =
                    resize?.item.id === item.id && preview
                      ? new Date(preview).toISOString()
                      : item.ends_at;
                  const ends =
                    dateInZone(endISO, timezone) === day
                      ? minuteOfDay(endISO, timezone)
                      : 1440;
                  if (ends === 0 && dateInZone(endISO, timezone) === day)
                    return null;
                  const offset = new Intl.DateTimeFormat("en", {
                    timeZone: timezone,
                    timeZoneName: "shortOffset",
                    hour: "numeric",
                  })
                    .formatToParts(new Date(item.starts_at))
                    .find((p) => p.type === "timeZoneName")?.value;
                  const height = blockHeight(ends - starts, hourPx);
                  const place = placement(
                    lanes.get(item.id) || { lane: 0, lanes: 1 },
                  );
                  const isTask = item.kind !== "event";
                  return (
                    <div
                      key={item.id}
                      data-mode={blockMode(height)}
                      data-type={isTask ? "task" : "event"}
                      className={`planning-time-item ${item.kind} ${conflictIds.has(item.id) ? "conflict" : ""} ${item.task?.done ? "done" : ""} ${place.cascade ? "cascade" : ""}`}
                      style={{
                        top: minuteTop(starts, hourPx),
                        height,
                        left: place.left,
                        width: place.width,
                        right: "auto",
                      }}
                      draggable={!!item.block && !item.task?.done}
                      onDragStart={(e) => {
                        e.dataTransfer.setData(
                          "application/yggdress-block",
                          item.id,
                        );
                        e.dataTransfer.effectAllowed = "move";
                      }}
                    >
                      <button
                        className="planning-time-content"
                        onClick={() => open(item)}
                      >
                        <strong>
                          {isTask ? (
                            <Icon
                              name={item.task?.done ? "SquareCheck" : "Square"}
                              size={12}
                            />
                          ) : null}
                          {item.title}
                        </strong>
                        <span>
                          {wallTime(item.starts_at, timezone)}–
                          {wallTime(endISO, timezone)} {offset}
                        </span>
                        {conflictIds.has(item.id) && (
                          <small>Overlapping commitment</small>
                        )}
                      </button>
                      {item.block && !item.task?.done && (
                        <>
                          <button
                            type="button"
                            className="planning-drag-handle"
                            draggable={false}
                            disabled={busy}
                            aria-label={`Move time block ${item.title}`}
                            onClick={(e) => e.preventDefault()}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                edit(item);
                              }
                            }}
                            onPointerDown={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setMoving({ item, x: e.clientX, y: e.clientY });
                            }}
                          >
                            ⠿
                          </button>
                          <button
                            className="planning-block-menu"
                            aria-label={`Edit time for ${item.title}`}
                            onClick={() => edit(item)}
                          >
                            •••
                          </button>
                          <button
                            className="planning-resize"
                            aria-label={`Resize ${item.title}; arrow keys change duration by 15 minutes`}
                            title="Drag to resize; arrow keys adjust 15 minutes"
                            disabled={busy}
                            onPointerDown={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setResize({
                                item,
                                y: e.clientY,
                                end: Date.parse(item.ends_at),
                              });
                            }}
                            onKeyDown={(e) => {
                              if (
                                e.key === "ArrowDown" ||
                                e.key === "ArrowUp"
                              ) {
                                e.preventDefault();
                                void run(
                                  "block.update",
                                  {
                                    start: item.starts_at,
                                    end: new Date(
                                      Math.max(
                                        Date.parse(item.starts_at) + 15 * 60000,
                                        Date.parse(item.ends_at) +
                                          (e.key === "ArrowDown" ? 15 : -15) *
                                            60000,
                                      ),
                                    ).toISOString(),
                                    timezone: item.block!.timezone,
                                    reason: "Resized with keyboard",
                                  },
                                  item.id,
                                  item.block!.version,
                                ).catch(() => {});
                              }
                            }}
                          />
                        </>
                      )}
                    </div>
                  );
                })}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
