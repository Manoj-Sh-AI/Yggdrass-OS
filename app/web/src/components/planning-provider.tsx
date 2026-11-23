"use client";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { applicationApi } from "@/lib/api";
import {
  dateInZone,
  addDays,
  monthDays,
  type PlanningSnapshot,
  type PlanningOperation,
  type CommandResult,
} from "@/lib/planning";

type Context = {
  data: PlanningSnapshot | null;
  day: string;
  setDay: (day: string) => void;
  timezone: string;
  setTimezone: (value: string) => void;
  busy: boolean;
  error: string;
  notice: string;
  refresh: () => Promise<void>;
  run: (
    op: PlanningOperation,
    data?: Record<string, unknown>,
    id?: string,
    version?: number,
  ) => Promise<CommandResult>;
  selected: string | null;
  select: (id: string | null) => void;
};
const Context = createContext<Context | null>(null);
const ClockContext = createContext(0);
export function PlanningProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<PlanningSnapshot | null>(null),
    [day, setDay] = useState("2026-01-01"),
    [timezone, setTimezone] = useState("Europe/Berlin"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [now, setNow] = useState(0),
    [selected, select] = useState<string | null>(null),
    [mounted, setMounted] = useState(false);
  const lock = useRef(false),
    sequence = useRef(0),
    clockOffset = useRef(0),
    retry = useRef(new Map<string, string>());
  const range = monthDays(day),
    start = addDays(range[0], -7),
    end = range[41];
  const refresh = useCallback(async () => {
    const request = ++sequence.current;
    const range = { start, end, timezone };
    await applicationApi("application/planning/commands", {
      method: "POST",
      body: JSON.stringify({
        key: crypto.randomUUID(),
        op: "ensure",
        data: range,
      }),
    });
    const next = await applicationApi<PlanningSnapshot>(
      `application/planning?${new URLSearchParams(range)}`,
    );
    if (request === sequence.current) {
      clockOffset.current = Date.parse(next.server_now) - Date.now();
      setData(next);
      setNow(Date.now() + clockOffset.current);
      setError("");
    }
  }, [start, end, timezone]);
  useEffect(() => {
    setDay(dateInZone(new Date(), "Europe/Berlin"));
    setMounted(true);
  }, []);
  useEffect(() => {
    if (!mounted) return;
    const load = () => void refresh().catch((e) => setError(e.message));
    load();
    const timer = setInterval(load, 30000);
    const resume = () => {
      if (document.visibilityState === "visible") load();
    };
    window.addEventListener("focus", load);
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("yggdress:tasks-changed", load);
    return () => {
      ++sequence.current;
      clearInterval(timer);
      window.removeEventListener("focus", load);
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("yggdress:tasks-changed", load);
    };
  }, [refresh, mounted]);
  useEffect(() => {
    const tick = setInterval(
      () => setNow(Date.now() + clockOffset.current),
      1000,
    );
    return () => clearInterval(tick);
  }, []);
  const run = useCallback(
    async (
      op: PlanningOperation,
      body: Record<string, unknown> = {},
      id?: string,
      version?: number,
    ) => {
      if (lock.current)
        throw new Error("Please wait for the current change to finish.");
      lock.current = true;
      setBusy(true);
      setError("");
      setNotice("Saving…");
      const identity = JSON.stringify({ op, data: body, id, version });
      const key = retry.current.get(identity) || crypto.randomUUID();
      retry.current.set(identity, key);
      try {
        const result = await applicationApi<CommandResult>(
          "application/planning/commands",
          {
            method: "POST",
            body: JSON.stringify({ key, op, data: body, id, version }),
          },
        );
        retry.current.delete(identity);
        setNotice("Saved to PostgreSQL.");
        try {
          await refresh();
        } catch (e) {
          setError(
            `Saved, but the view could not refresh. ${e instanceof Error ? e.message : "Try Refresh."}`,
          );
        }
        window.dispatchEvent(new Event("yggdress:planning-changed"));
        return result;
      } catch (e) {
        setNotice("");
        const message =
          e instanceof Error
            ? e.message
            : "Could not save. Your draft is unchanged.";
        setError(message);
        throw e;
      } finally {
        lock.current = false;
        setBusy(false);
      }
    },
    [refresh],
  );
  const value = useMemo(
    () => ({
      data,
      day,
      setDay,
      timezone,
      setTimezone,
      busy,
      error,
      notice,
      refresh,
      run,
      selected,
      select,
    }),
    [data, day, timezone, busy, error, notice, refresh, run, selected],
  );
  return (
    <Context.Provider value={value}>
      <ClockContext.Provider value={now}>{children}</ClockContext.Provider>
    </Context.Provider>
  );
}
export function usePlanning() {
  const value = useContext(Context);
  if (!value) throw new Error("Missing planning provider");
  return value;
}
export function usePlanningClock() {
  return useContext(ClockContext);
}
