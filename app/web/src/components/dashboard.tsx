"use client";
import Link from "next/link";
import type { CSSProperties } from "react";
import { areas, areaOf } from "@/lib/data";
import { useApp } from "./provider";
import { Icon, Panel, Progress } from "./ui";
import { ActivityFeed, CaptureShortcuts, Goals, QuoteBanner } from "./today";
import { NoteList } from "./notes";
export function DashboardPage() {
  const { state } = useApp();
  const completed = state.tasks.filter((t) => t.done).length;
  return (
    <div className="standard-page">
      <div className="page-intro">
        <div>
          <span className="eyebrow">THE BIGGER PICTURE</span>
          <h1>Your connected life</h1>
          <p>Everything you’re growing, in one place.</p>
        </div>
        <Link className="button" href="/today">
          Back to today
          <Icon name="ArrowRight" size={16} />
        </Link>
      </div>
      <div className="stats-grid">
        {[
          {
            label: "Thoughts captured",
            value: state.notes.length,
            icon: "NotebookPen",
            color: "#8fb5ff",
          },
          {
            label: "Connections made",
            value: state.notes.reduce((v, n) => v + n.links.length, 0),
            icon: "Network",
            color: "#bc9cfa",
          },
          {
            label: "Tasks completed",
            value: completed,
            icon: "CircleCheck",
            color: "#70dbb0",
          },
          {
            label: "Life areas",
            value: areas.length,
            icon: "Sprout",
            color: "#efc07a",
          },
        ].map((s) => (
          <Panel key={s.label} className="stat-card">
            <span style={{ color: s.color }}>
              <Icon name={s.icon} size={23} />
            </span>
            <strong>{s.value}</strong>
            <small>{s.label}</small>
          </Panel>
        ))}
      </div>
      <div className="dashboard-columns">
        <div>
          <div className="section-heading">
            <h2>Your life areas</h2>
            <span className="muted">Make room for each part of you.</span>
          </div>
          <div className="area-grid">
            {areas.map((a) => {
              const notes = state.notes.filter(
                  (n) => n.area === a.id || n.also.includes(a.id),
                ),
                goal = state.goals.find((g) => g.area === a.id);
              return (
                <Link
                  className="panel area-card"
                  href={`/areas/${a.id}`}
                  key={a.id}
                  style={{ "--legacy-accent": a.color } as CSSProperties}
                >
                  <div className="area-card-heading">
                    <span className="area-card-icon">
                      <Icon name={a.icon} size={23} />
                    </span>
                    <Icon name="ArrowUpRight" size={17} />
                  </div>
                  <h3>{a.name}</h3>
                  <p>{a.description}</p>
                  <div className="area-card-footer">
                    <span>{notes.length} notes</span>
                    <span>
                      {goal ? `${goal.progress}% of goal` : "Room to grow"}
                    </span>
                  </div>
                  <Progress
                    value={goal?.progress || 0}
                    color={a.color}
                    label={`${a.name} progress`}
                  />
                </Link>
              );
            })}
          </div>
          <Panel title="Recently opened thoughts" className="recent-notes">
            <NoteList
              notes={[...state.notes]
                .sort((a, b) => b.updated.localeCompare(a.updated))
                .slice(0, 8)}
            />
          </Panel>
        </div>
        <div className="dashboard-side">
          <Panel title="Quick Capture">
            <CaptureShortcuts />
          </Panel>
          <Panel title="Steady progress">
            <Goals />
          </Panel>
          <Panel title="Your activity">
            <ActivityFeed limit={8} />
          </Panel>
        </div>
      </div>
      <QuoteBanner />
    </div>
  );
}
