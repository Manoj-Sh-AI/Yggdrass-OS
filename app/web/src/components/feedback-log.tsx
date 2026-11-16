"use client";
import { useEffect, useState } from "react";
import { yggdrasApi } from "@/lib/yggdras-api";

type Step = { agent: string; model: string; skills?: string[]; tools?: string[] };
type Reaction = { tool: string; decision: string; correction: string };
type Run = {
  id: string;
  created_at: string;
  source: string;
  request: string;
  route: string;
  steps: Step[];
  cost_usd: string;
  latency_ms: number;
  checker_stopped: boolean;
  cards: number;
  error: string;
  reactions: Reaction[] | null;
};

/** Every request Yggdras handled: route, skills, tools and models per step, latency, cost,
 * whether the checker stopped it, and what Manoj did with each card. */
export function FeedbackLog() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    yggdrasApi
      .runs()
      .then((r) => setRuns(r as unknown as Run[]))
      .catch((e) => setError(e instanceof Error ? e.message : "Unavailable."));
  }, []);
  if (error) return <p className="ygg-error" role="alert">{error}</p>;
  if (!runs) return <p>Loading…</p>;
  const spent = runs.reduce((sum, r) => sum + Number(r.cost_usd || 0), 0);
  const stopped = runs.filter((r) => r.checker_stopped).length;
  return (
    <section className="ygg-feedback">
      <h1>How Yggdras works for you</h1>
      <p>
        {runs.length} recent requests · ${spent.toFixed(4)} · the checker stopped {stopped} for
        your approval
      </p>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>From</th>
            <th>Request</th>
            <th>Route</th>
            <th>Steps (agent · model · skills · tools)</th>
            <th>Time</th>
            <th>Cost</th>
            <th>Your call</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className={run.error ? "ygg-failed" : undefined}>
              <td>{new Date(run.created_at).toLocaleString()}</td>
              <td>{run.source}</td>
              <td>{run.request.slice(0, 140)}</td>
              <td>{run.route}</td>
              <td>
                {run.steps.map((s, i) => (
                  <div key={i}>
                    {s.agent} · {s.model.replace("claude-", "")}
                    {s.skills?.length ? ` · ${s.skills.join(", ")}` : ""}
                    {s.tools?.length ? ` · ${s.tools.join(", ")}` : ""}
                  </div>
                ))}
                {run.error && <div>Failed: {run.error}</div>}
              </td>
              <td>{(run.latency_ms / 1000).toFixed(1)} s</td>
              <td>${Number(run.cost_usd).toFixed(4)}</td>
              <td>
                {run.checker_stopped && <div>Checker stopped it</div>}
                {(run.reactions || []).map((r, i) => (
                  <div key={i}>
                    {r.decision} {r.tool.replace(/_/g, " ")}
                    {r.correction ? `: "${r.correction}"` : ""}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
