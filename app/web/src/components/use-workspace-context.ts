"use client";
import { useCallback, useEffect, useState } from "react";
import { connectionsApi } from "@/lib/workspace-connections";

export function useWorkspaceContext<T>(
  path: string,
  active = true,
  revision = "",
) {
  const [generation, setGeneration] = useState(0);
  const [state, setState] = useState<{
    path: string;
    data: T | null;
    error: string;
    loading: boolean;
    enabled: boolean;
  }>({ path, data: null, error: "", loading: active, enabled: true });
  const refresh = useCallback(() => setGeneration((value) => value + 1), []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState((previous) => ({
      path,
      data: previous.path === path ? previous.data : null,
      error: "",
      loading: true,
      enabled: true,
    }));
    void (async () => {
      try {
        const capability = await connectionsApi.capabilities(controller.signal);
        const data = capability.linked_work
          ? await connectionsApi.read<T>(path, controller.signal)
          : null;
        if (!controller.signal.aborted)
          setState({
            path,
            data,
            error: "",
            loading: false,
            enabled: capability.linked_work,
          });
      } catch (error) {
        if (!controller.signal.aborted)
          setState({
            path,
            data: null,
            error:
              error instanceof Error
                ? error.message
                : "Linked work could not be loaded.",
            loading: false,
            enabled: true,
          });
      }
    })();
    return () => controller.abort();
  }, [path, active, revision, generation]);
  useEffect(() => {
    if (!active) return;
    window.addEventListener("yggdress:connections-changed", refresh);
    window.addEventListener("yggdress:planning-changed", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("yggdress:connections-changed", refresh);
      window.removeEventListener("yggdress:planning-changed", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [active, refresh]);
  return {
    ...(state.path === path
      ? state
      : { data: null, error: "", loading: true, enabled: true }),
    refresh,
  };
}
