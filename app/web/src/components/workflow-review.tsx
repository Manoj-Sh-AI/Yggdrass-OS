"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { applicationApi } from "@/lib/api";
import { workspaceRetry } from "@/lib/workspace-retry";
import { Modal } from "./ui";

type Review = {
  id: string;
  version: number;
  slug: string;
  lifecycle: string;
  reason: string;
  proposal: {
    disposition?: string;
    precision?: string;
    meaning?: string;
    action?: string;
    original_phrase?: string;
    explanation?: string;
    lifecycle?: string;
    data?: Record<string, unknown>;
  };
  current: Record<string, unknown> | null;
  agent?: string;
  blocked?: string;
  operation?: string;
};
type AgentReview = {
  id: string;
  version: number;
  agent_id: string;
  payload: {
    operation: string;
    data: Record<string, unknown>;
    explanation: string;
  };
  current: Record<string, unknown> | null;
  blocked: string;
};
export function WorkflowReview() {
  const [rows, setRows] = useState<Review[]>([]),
    [more, setMore] = useState(false),
    [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const live = useRef(true),
    lock = useRef(false),
    generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const [result, agents] = await Promise.all([
        applicationApi<{
          reviews: Review[];
          truncated: boolean;
        }>("application/workflow/reviews"),
        applicationApi<{ reviews: AgentReview[]; truncated: boolean }>(
          "application/agents/reviews",
        ),
      ]);
      if (live.current && current === generation.current) {
        setRows([
          ...result.reviews,
          ...agents.reviews.map((row): Review => ({
            id: row.id,
            version: row.version,
            slug: "",
            lifecycle: "chat",
            agent: row.agent_id,
            reason: row.payload.explanation,
            blocked: row.blocked,
            operation: row.payload.operation,
            proposal: {
              data: row.payload.data,
              disposition: "clear",
              precision: "date",
              action:
                row.payload.operation.endsWith(".remove") ||
                row.payload.operation.endsWith(".cancel")
                  ? "retract"
                  : "upsert",
            },
            current: row.current,
          })),
        ]);
        setMore(result.truncated || agents.truncated);
        setError("");
      }
    } catch (error) {
      if (live.current && current === generation.current)
        setError(
          error instanceof Error ? error.message : "Could not check updates.",
        );
    }
  }, []);
  useEffect(() => {
    live.current = true;
    const refresh = () => {
      if (document.visibilityState === "visible") void load();
    };
    refresh();
    const timer = setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    window.addEventListener("yggdress:tasks-changed", refresh);
    window.addEventListener("yggdress:agent-changes", refresh);
    return () => {
      live.current = false;
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("yggdress:tasks-changed", refresh);
      window.removeEventListener("yggdress:agent-changes", refresh);
    };
  }, [load]);
  async function decide(row: Review, decision: "accept" | "dismiss") {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const data = {
        id: row.id,
        version: row.version,
        decision,
        ...(!row.agent ? { target_version: row.current?.version ?? null } : {}),
      };
      const retry = await workspaceRetry(
        "workflow-review:" + JSON.stringify(data),
      );
      await applicationApi(
        row.agent
          ? "application/agents/reviews/resolve"
          : "application/workflow/reviews/resolve",
        {
          method: "POST",
          body: JSON.stringify({ key: retry.key, ...data }),
        },
      );
      retry.complete();
      await load();
      window.dispatchEvent(new Event("yggdress:tasks-changed"));
      window.dispatchEvent(new Event("yggdress:connections-changed"));
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save your decision.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (!rows.length && !error && !open) return null;
  return (
    <>
      <button
        className="button small-button workflow-review-trigger"
        onClick={() => {
          setOpen(true);
          void load();
        }}
      >
        {rows.length
          ? `Review changes (${rows.length}${more ? "+" : ""})`
          : "Check updates"}
      </button>
      <Modal
        open={open}
        onOpenChange={setOpen}
        preventDismiss={busy}
        title="Changes that need your decision"
        description="Review the exact changes before applying them. Saved notes stay saved."
      >
        {error && (
          <div role="alert" className="error">
            <p>{error}</p>
            <button
              className="button"
              disabled={busy}
              onClick={() => void load()}
            >
              Refresh decisions
            </button>
          </div>
        )}
        {!rows.length && !error && <p>Nothing needs your decision.</p>}
        <div className="workflow-reviews">
          {rows.map((row) => {
            const proposed = row.proposal.data || {};
            const canAccept = row.agent
              ? !row.blocked
              : row.proposal.disposition === "clear" &&
                !row.proposal.lifecycle &&
                !["relative", "month", "year", "unspecified"].includes(
                  row.proposal.precision || "",
                ) &&
                !["recurrence", "preference"].includes(
                  row.proposal.meaning || "",
                ) &&
                !(
                  row.current?.objective &&
                  proposed.objective &&
                  proposed.objective !== row.current.objective
                ) &&
                !["completed", "in_progress", "paused", "skipped"].includes(
                  String(row.current?.state),
                );
            return (
              <section key={row.id} className="workflow-review-item">
                <h3>
                  {String(
                    proposed.title ||
                      row.current?.title ||
                      "Source context changed",
                  )}
                </h3>
                {row.agent ? (
                  <p className="muted">
                    {row.agent === "tasks" ? "Task Manager" : "Calendar"} ·{" "}
                    {row.operation?.replaceAll(".", " ")}
                  </p>
                ) : row.lifecycle === "active" ? (
                  <Link
                    href={`/notes?note=${encodeURIComponent(row.slug)}`}
                    onClick={() => setOpen(false)}
                  >
                    Open source note
                  </Link>
                ) : (
                  <p className="muted">
                    Source {row.lifecycle}; its reference and work history are
                    preserved.
                  </p>
                )}
                <p>{row.reason}</p>
                {row.blocked && (
                  <p role="alert" className="error">
                    {row.blocked}
                  </p>
                )}
                {row.proposal.original_phrase && (
                  <blockquote>{row.proposal.original_phrase}</blockquote>
                )}
                {row.proposal.explanation && <p>{row.proposal.explanation}</p>}
                <dl>
                  {Object.keys(proposed)
                    .filter((key) => proposed[key] !== undefined)
                    .map((key) => {
                      const currentKey =
                        key === "start"
                          ? "starts_at"
                          : key === "end"
                            ? "ends_at"
                            : key;
                      const currentValue = row.current?.[currentKey];
                      return (
                        <div key={key}>
                          <dt>{key.replaceAll("_", " ")}</dt>
                          <dd>
                            {currentValue !== undefined && (
                              <span>
                                Current: {String(currentValue ?? "none")} ·{" "}
                              </span>
                            )}
                            Proposed: {String(proposed[key] ?? "none")}
                          </dd>
                        </div>
                      );
                    })}
                </dl>
                <div className="linked-work-actions">
                  {canAccept && (
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() => void decide(row, "accept")}
                    >
                      {row.proposal.action === "retract"
                        ? "Confirm cancellation"
                        : "Apply reviewed change"}
                    </button>
                  )}
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() => void decide(row, "dismiss")}
                  >
                    {row.current ? "Keep current work" : "Dismiss proposal"}
                  </button>
                </div>
              </section>
            );
          })}
        </div>
        {more && (
          <p className="muted">
            More decisions remain. This list refreshes as you resolve them.
          </p>
        )}
      </Modal>
    </>
  );
}
