"use client";
import Link from "next/link";
import { useState, type CSSProperties } from "react";
import { areaOf } from "@/lib/data";
import type { Activity } from "@/lib/types";
import { useApp } from "./provider";
import { useScenery } from "./scenery";
import { launchCapture } from "./shell";
import {
  AreaBadge,
  Empty,
  Icon,
  Modal,
  Panel,
  Progress,
  relativeTime,
} from "./ui";
import { TodayRoutine } from "./today-routine";
import { TodayPlanning } from "./planning-daily";
import { usePlanning } from "./planning-provider";
import { TimeForm } from "./planning-ui";
import {
  dateInZone,
  onLocalDay,
  wallTime,
  minutesBetween,
  type CalendarEvent,
} from "@/lib/planning";
export function Goals({ area }: { area?: string }) {
  const { data } = usePlanning();
  const goals = (data?.goals || [])
    .map((g) => {
      const tasks = data!.tasks.filter((t) => t.goal_id === g.id);
      return {
        ...g,
        area: tasks[0]?.area || "work",
        progress: tasks.length
          ? Math.round(
              (tasks.filter((t) => t.done).length / tasks.length) * 100,
            )
          : 0,
      };
    })
    .filter((g) => !area || g.area === area);
  return goals.length ? (
    <div className="goals-list">
      {goals.map((g) => (
        <div className="goal" key={g.id}>
          <div>
            <span>{g.title}</span>
            <span>{g.progress}%</span>
          </div>
          <Progress
            value={g.progress}
            color={areaOf(g.area).color}
            label={g.title}
          />
        </div>
      ))}
    </div>
  ) : (
    <Empty
      title="Progress starts with a small step"
      detail="Your area goals will appear here."
    />
  );
}
export function ActivityFeed({ limit = 4 }: { limit?: number }) {
  const { state, openNote } = useApp();
  return (
    <div className="activity-list">
      {state.activities.slice(0, limit).map((a) => (
        <button
          key={a.id}
          className="activity-item"
          disabled={!a.noteId}
          onClick={() => a.noteId && openNote(a.noteId)}
        >
          <Icon
            name={
              a.kind === "task"
                ? "CircleCheck"
                : a.kind === "idea"
                  ? "Lightbulb"
                  : "FileClock"
            }
            size={15}
          />
          <span>
            {a.title}
            <small>{relativeTime(a.date)}</small>
          </span>
          {a.noteId && (
            <Icon className="activity-arrow" name="ChevronRight" size={13} />
          )}
        </button>
      ))}
    </div>
  );
}
export function CaptureShortcuts() {
  return (
    <div className="capture-shortcuts">
      {(
        [
          {
            kind: "note",
            label: "Note",
            icon: "NotebookPen",
            color: "#64e1a4",
          },
          {
            kind: "task",
            label: "Task",
            icon: "SquareCheck",
            color: "#b795f6",
          },
          { kind: "idea", label: "Idea", icon: "Lightbulb", color: "#f5c369" },
          { kind: "file", label: "File", icon: "File", color: "#79afff" },
        ] as const
      ).map((c) => (
        <button
          key={c.kind}
          onClick={() => launchCapture(c.kind)}
          style={{ "--accent": c.color } as CSSProperties}
        >
          <span>
            <Icon name={c.icon} size={24} />
          </span>
          {c.label}
        </button>
      ))}
    </div>
  );
}
export function QuoteBanner() {
  const { scene } = useScenery(),
    [quote, setQuote] = useState(0);
  const quotes = [
    "Small steps consistently create big changes.",
    "Make space for what moves your life forward.",
    "You don’t have to see the whole path to take the next step.",
  ];
  return (
    <div
      className="quote-banner"
      style={{
        backgroundImage: `linear-gradient(90deg,rgba(5,14,23,.78),rgba(5,14,23,.2)),url('/scenes/${scene.key}-960.webp')`,
      }}
    >
      <Icon name="Lightbulb" size={20} />
      <div>
        <small>Keep going</small>
        <p>“{quotes[quote]}”</p>
      </div>
      <button
        className="quote-next icon-button"
        aria-label="Next reflection"
        onClick={() => setQuote((quote + 1) % quotes.length)}
      >
        <Icon name="ArrowRight" size={22} />
      </button>
    </div>
  );
}
export { TodayPage } from "./today-workspace";
