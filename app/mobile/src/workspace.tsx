import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AppState } from "react-native";
import * as SecureStore from "expo-secure-store";
import { api } from "./api";
import { monthRange } from "./dates";
import type { Snapshot } from "./types";

const Context = createContext({
  timezone: "Europe/Berlin",
  setTimezone: async (_v: string) => {},
  revision: 0,
  changed: () => {},
});
const cache = new Map<string, { at: number; value: Promise<Snapshot> }>();
export function Workspace({ children }: { children: ReactNode }) {
  const [timezone, updateTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Berlin",
  );
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    void SecureStore.getItemAsync("yggdras.mobile.timezone")
      .then((value) => {
        if (value) {
          new Intl.DateTimeFormat("en", { timeZone: value });
          updateTimezone(value);
        }
      })
      .catch(() => {});
  }, []);
  const setTimezone = useCallback(async (value: string) => {
    await SecureStore.setItemAsync("yggdras.mobile.timezone", value);
    updateTimezone(value);
  }, []);
  const value = useMemo(
    () => ({
      timezone,
      setTimezone,
      revision,
      changed: () => {
        cache.clear();
        setRevision((n) => n + 1);
      },
    }),
    [timezone, revision, setTimezone],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useWorkspace = () => useContext(Context);
export function usePlanning(month: string, active: boolean) {
  const { timezone, revision, changed } = useWorkspace();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!active) return;
    let live = true;
    const load = async () => {
      setLoading(true);
      setError("");
      const range = monthRange(month);
      const key = `${month}:${timezone}:${revision}`;
      let entry = cache.get(key);
      if (!entry || Date.now() - entry.at > 15000) {
        entry = {
          at: Date.now(),
          value: api.planning(range.start, range.end, timezone),
        };
        cache.set(key, entry);
      }
      try {
        const data = await entry.value;
        if (live) setSnapshot(data);
      } catch (e) {
        cache.delete(key);
        if (live)
          setError(
            e instanceof Error ? e.message : "Could not load your workspace.",
          );
      } finally {
        if (live) setLoading(false);
      }
    };
    void load();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        cache.clear();
        void load();
      }
    });
    return () => {
      live = false;
      subscription.remove();
    };
  }, [month, timezone, revision, retry, active]);
  return {
    snapshot,
    error,
    loading,
    refresh: () => {
      cache.clear();
      setRetry((n) => n + 1);
    },
    changed,
  };
}
