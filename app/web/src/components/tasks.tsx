"use client";
import { useEffect, useMemo, useState } from "react";
import { usePlanning } from "./planning-provider";
import { DailyPlanning } from "./planning-daily";
import { RoutineManager } from "./planning-routines";
import {
  GroupManager,
  PlanningFeedback,
  TaskForm,
  TaskRow,
} from "./planning-ui";
import { Empty, Icon, Modal, Panel } from "./ui";
import { dateInZone, onLocalDay } from "@/lib/planning";
import { planningTabsKeyDown } from "@/lib/planning-accessibility";
import { TaskBoard } from "./task-board";
export function TasksPage() {
  const { data, day, setDay, timezone, busy } = usePlanning();
  const [tab, setTab] = useState("tasks"),
    [scope, setScope] = useState("All"),
    [layout, setLayout] = useState<"board" | "list">("board"),
    [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [priority, setPriority] = useState(""),
    [group, setGroup] = useState(""),
    [sort, setSort] = useState("priority"),
    [create, setCreate] = useState(false),
    [limit, setLimit] = useState(80);
  useEffect(() => {
    if (new URLSearchParams(location.search).get("tab") === "plan")
      setTab("plan");
    try {
      const saved = localStorage.getItem("yggdress.tasks.layout.v1");
      if (saved === "board" || saved === "list") setLayout(saved);
    } catch {
      /* View choice is optional; task data stays server-backed. */
    }
  }, []);
  function chooseLayout(next: "board" | "list") {
    setLayout(next);
    try {
      localStorage.setItem("yggdress.tasks.layout.v1", next);
    } catch {
      /* Keep this session usable. */
    }
  }
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query);
      setLimit(80);
    }, 150);
    return () => clearTimeout(timer);
  }, [query]);
  const today = dateInZone(new Date(), timezone);
  const tasks = useMemo(() => {
    if (!data) return [];
    const scheduled = new Set(
      data.blocks
        .filter((b) => onLocalDay(b, day, timezone))
        .map((b) => b.task_id),
    );
    const futureScheduled = new Set(
      data.blocks
        .filter((b) => dateInZone(b.starts_at, timezone) > day)
        .map((b) => b.task_id),
    );
    return data.tasks
      .filter(
        (t) =>
          t.state !== "skipped" &&
          (scope === "Completed" ? t.done : layout === "board" || !t.done) &&
          (scope === "All" ||
            scope === "Completed" ||
            (scope === "Today" &&
              (t.due_date === day ||
                scheduled.has(t.id) ||
                t.occurrence_date === day)) ||
            (scope === "Upcoming" &&
              ((t.due_date && t.due_date > day) ||
                futureScheduled.has(t.id) ||
                (t.next_scheduled_at &&
                  dateInZone(t.next_scheduled_at, timezone) > day))) ||
            (scope === "Inbox" && !t.due_date && !t.template_id) ||
            (scope === "Backlog" &&
              ((t.due_date && t.due_date < day) ||
                (!t.due_date && !t.next_scheduled_at)))) &&
          (!priority || String(t.priority) === priority) &&
          (!group || t.project_id === group || t.goal_id === group) &&
          (!search ||
            `${t.title} ${t.objective} ${t.description} ${t.tags.join(" ")}`
              .toLowerCase()
              .includes(search.toLowerCase())),
      )
      .sort((a, b) =>
        sort === "title"
          ? a.title.localeCompare(b.title)
          : sort === "duration"
            ? a.estimated_minutes - b.estimated_minutes
            : sort === "due"
              ? (a.due_date || "9999").localeCompare(b.due_date || "9999")
              : a.priority - b.priority ||
                (a.due_date || "9999").localeCompare(b.due_date || "9999"),
      );
  }, [data, day, timezone, scope, priority, group, search, sort, layout]);
  return (
    <div className="standard-page planning-page task-workspace-page">
      <div className="page-intro">
        <div>
          <h1>Tasks</h1>
        </div>
        <button className="button primary" onClick={() => setCreate(true)}>
          <Icon name="Plus" size={16} />
          New task
        </button>
      </div>
      <div className="planning-toolbar">
        <div
          className="planning-tabs"
          role="tablist"
          onKeyDown={planningTabsKeyDown}
          aria-label="Planning workspace"
        >
          {[
            ["tasks", "Tasks"],
            ["routines", "Routines"],
            ["goals", "Goals & projects"],
            ["plan", "Plan & review"],
          ].map(([id, label]) => (
            <button
              key={id}
              role="tab"
              tabIndex={tab === id ? 0 : -1}
              aria-selected={tab === id}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="planning-date-label">
          Planning date
          <input
            aria-label="Planning date"
            type="date"
            value={day}
            onChange={(e) => {
              if (e.target.value) setDay(e.target.value);
            }}
          />
        </label>
        <button className="button small-button" onClick={() => setDay(today)}>
          Today
        </button>
      </div>
      <PlanningFeedback />
      {!data ? (
        <Panel className="planning-tasks-panel">
          <div
            className="kanban-loading"
            role="status"
            aria-label="Opening your tasks"
          >
            <span className="sr-only">Opening your tasks…</span>
            {[0, 1, 2, 3].map((i) => (
              <i key={i} aria-hidden="true" />
            ))}
          </div>
        </Panel>
      ) : tab === "routines" ? (
        <RoutineManager />
      ) : tab === "goals" ? (
        <GroupManager />
      ) : tab === "plan" ? (
        <DailyPlanning />
      ) : (
        <Panel className="planning-tasks-panel">
          <div className="planning-scopes">
            {["Today", "Upcoming", "Inbox", "Backlog", "All", "Completed"].map(
              (s) => (
                <button
                  aria-pressed={scope === s}
                  key={s}
                  onClick={() => {
                    setScope(s);
                    setLimit(80);
                  }}
                >
                  {s}
                </button>
              ),
            )}
          </div>
          <div className="planning-filters">
            <label className="planning-search">
              <Icon name="Search" size={17} />
              <input
                aria-label="Search tasks"
                placeholder="Search tasks, outcomes, tags…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <details className="quiet-task-filters">
              <summary>
                Filters & sort
                {priority || group || sort !== "priority" ? " · applied" : ""}
              </summary>
              <div>
                <select
                  aria-label="Filter priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                >
                  <option value="">All priorities</option>
                  <option value={1}>High</option>
                  <option value={2}>Medium</option>
                  <option value={3}>Low</option>
                </select>
                <select
                  aria-label="Filter project or goal"
                  value={group}
                  onChange={(e) => setGroup(e.target.value)}
                >
                  <option value="">All projects & goals</option>
                  {[...data.projects, ...data.goals].map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.title}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Sort tasks"
                  value={sort}
                  onChange={(e) => setSort(e.target.value)}
                >
                  <option value="priority">Priority</option>
                  <option value="due">Due date</option>
                  <option value="duration">Estimate</option>
                  <option value="title">Title</option>
                </select>
              </div>
            </details>
          </div>
          <div className="planning-list-heading">
            <span>
              {scope} · {tasks.length} task{tasks.length !== 1 ? "s" : ""}
            </span>
            <div
              className="task-view-switch"
              role="group"
              aria-label="Task view"
            >
              <button
                aria-pressed={layout === "board"}
                onClick={() => chooseLayout("board")}
                disabled={busy}
              >
                <Icon name="Layers" size={14} />
                Board
              </button>
              <button
                aria-pressed={layout === "list"}
                onClick={() => chooseLayout("list")}
                disabled={busy}
              >
                <Icon name="List" size={14} />
                List
              </button>
            </div>
          </div>
          {layout === "board" && tasks.length > 0 ? (
            <TaskBoard tasks={tasks} />
          ) : (
            layout === "list" &&
            tasks.slice(0, limit).map((t) => <TaskRow key={t.id} task={t} />)
          )}
          {!tasks.length && (
            <Empty
              icon="SquareCheck"
              title="No tasks in this view"
              detail="Capture a task, choose a different view, or adjust your filters."
            />
          )}
          {layout === "list" && tasks.length > limit && (
            <button className="button" onClick={() => setLimit((n) => n + 80)}>
              Load 80 more tasks
            </button>
          )}
        </Panel>
      )}
      <Modal
        open={create}
        onOpenChange={setCreate}
        title="New task"
        description="Capture the commitment first. Choose execution time when you are ready."
      >
        <TaskForm onSaved={() => setCreate(false)} />
      </Modal>
    </div>
  );
}
