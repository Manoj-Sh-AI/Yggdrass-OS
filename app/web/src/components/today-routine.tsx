"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { routineHttp } from "@/lib/routine-http";
import type { RoutineAction, RoutineStore } from "@/lib/routines";
import { RoutineExecutionCard } from "./routine-execution-card";
import { Panel } from "./ui";
export function TodayRoutine() {
  const [store, setStore] = useState<RoutineStore | null>(null),
    [pending, setPending] = useState(false),
    [error, setError] = useState(""),
    [reload, setReload] = useState(0);
  const busy = useRef(false);
  useEffect(() => {
    let active = true;
    routineHttp
      .load()
      .then((s) => {
        if (active) {
          setStore(s);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [reload]);
  const action = useCallback(async (action: RoutineAction) => {
    if (busy.current) return false;
    busy.current = true;
    setPending(true);
    setError("");
    try {
      setStore(await routineHttp.command(action));
      return true;
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not save execution. Your draft is unchanged.",
      );
      return false;
    } finally {
      busy.current = false;
      setPending(false);
    }
  }, []);
  if (!store)
    return (
      <Panel title="Routine execution" className="routine-loading">
        {error ? (
          <>
            <p role="alert" className="error">
              {error}
            </p>
            <button className="button" onClick={() => setReload((n) => n + 1)}>
              Retry loading routine
            </button>
          </>
        ) : (
          <p role="status">Loading application data…</p>
        )}
      </Panel>
    );
  return (
    <RoutineExecutionCard
      definition={store.definition}
      execution={store.execution}
      onAction={action}
      pending={pending}
      error={error}
    />
  );
}
