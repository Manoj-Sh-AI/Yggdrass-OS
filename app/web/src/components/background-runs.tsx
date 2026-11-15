"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { applicationApi } from "@/lib/api";
import { workspaceRetry } from "@/lib/workspace-retry";
import { elapsedLabel } from "@/lib/planning";
import { usePlanning, usePlanningClock } from "./planning-provider";
import { Modal } from "./ui";
type Run = {
  id: string;
  label: string;
  task_id: string | null;
  state: string;
  version: number;
  elapsed_seconds: number;
  cancellation_requested_at: string | null;
};
export function BackgroundRuns() {
  const [data, setData] = useState<{
      runs: Run[];
      server_now: string;
      truncated: boolean;
    } | null>(null),
    [failure, setFailure] = useState(""),
    [open, setOpen] = useState(false),
    [chosen, setChosen] = useState<Run | null>(null),
    [busy, setBusy] = useState(false);
  const { select } = usePlanning(),
    now = usePlanningClock(),
    live = useRef(true),
    lock = useRef(false);
  const load = useCallback(async () => {
    try {
      const result = await applicationApi<{
        runs: Run[];
        server_now: string;
        truncated: boolean;
      }>("application/background");
      if (live.current) {
        setData(result);
        setFailure("");
      }
    } catch (error) {
      if (live.current)
        setFailure(
          error instanceof Error
            ? error.message
            : "Background activity is unavailable.",
        );
    }
  }, []);
  useEffect(() => {
    live.current = true;
    const check = () => {
      if (document.visibilityState === "visible") void load();
    };
    check();
    const timer = setInterval(check, 15000);
    window.addEventListener("focus", check);
    return () => {
      live.current = false;
      clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, [load]);
  if (!data?.runs.length && !failure) return null;
  return (
    <section className="background-activity">
      <details
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>
          Background activity
          {data?.runs.some((r) => ["queued", "running"].includes(r.state))
            ? " · active"
            : ""}
        </summary>
        <p className="muted">
          Unattended elapsed time is separate from your focus time.
        </p>
        {failure && (
          <div className="error" role="alert">
            {failure}
            <button className="button" onClick={() => void load()}>
              Retry
            </button>
          </div>
        )}
        <ul className="linked-work-list">
          {data?.runs.map((run) => (
            <li key={run.id}>
              <strong>{run.label}</strong>
              <small>
                {run.state} ·{" "}
                <span role="timer" aria-live="off">
                  {elapsedLabel(
                    Number(run.elapsed_seconds) +
                      (run.state === "running"
                        ? Math.max(
                            0,
                            (now - Date.parse(data.server_now)) / 1000,
                          )
                        : 0),
                  )}
                </span>
                {run.cancellation_requested_at &&
                ["queued", "running"].includes(run.state)
                  ? " · cancellation requested"
                  : ""}
              </small>
              {run.task_id && (
                <button
                  className="text-link"
                  onClick={() => select(run.task_id)}
                >
                  Open task
                </button>
              )}
              {["queued", "running"].includes(run.state) &&
                !run.cancellation_requested_at && (
                  <button className="text-link" onClick={() => setChosen(run)}>
                    Request cancellation
                  </button>
                )}
            </li>
          ))}
        </ul>
        {data?.truncated && (
          <p className="muted">
            Showing the latest 40 runs; earlier history remains stored.
          </p>
        )}
      </details>
      <Modal
        open={!!chosen}
        preventDismiss={busy}
        onOpenChange={(value) => {
          if (!value) setChosen(null);
        }}
        title="Request background cancellation"
        description="The run stays active until its provider confirms that it stopped."
      >
        <p>{chosen?.label}</p>
        {failure && (
          <p className="error" role="alert">
            {failure}
          </p>
        )}
        <button
          className="button primary"
          disabled={busy}
          onClick={async () => {
            if (!chosen || lock.current) return;
            lock.current = true;
            setBusy(true);
            try {
              const body = { id: chosen.id, version: chosen.version };
              const retry = await workspaceRetry(
                "background-cancel:" + JSON.stringify(body),
              );
              await applicationApi("application/background/cancel", {
                method: "POST",
                body: JSON.stringify({ key: retry.key, ...body }),
              });
              retry.complete();
              setChosen(null);
              await load();
            } catch (error) {
              setFailure(
                error instanceof Error
                  ? error.message
                  : "Could not request cancellation.",
              );
            } finally {
              lock.current = false;
              setBusy(false);
            }
          }}
        >
          Request cancellation
        </button>
      </Modal>
    </section>
  );
}
