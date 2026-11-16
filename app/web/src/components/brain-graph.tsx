"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { applicationApi } from "@/lib/api";
import { Icon } from "./ui";
import { useApp } from "./provider";
import { WorkGraph } from "./work-graph";

type Summary = { nodes: number; links: number; source: string };
export function BrainGraphPage() {
  const router = useRouter();
  const { state: appState } = useApp();
  const frame = useRef<HTMLIFrameElement>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [paused, setPaused] = useState(true);
  const [dimension, setDimension] = useState("3d");
  const [generation, setGeneration] = useState(0);
  const [layer, setLayer] = useState<"brain" | "work">("brain");
  const load = useCallback(async () => {
    setReady(false);
    setError("");
    setSummary(null);
    setPaused(true);
    try {
      setSummary(await applicationApi<Summary>("graph/status"));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Your graph could not be loaded.",
      );
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load, generation]);
  useEffect(() => {
    if (!summary || ready || error) return;
    const timeout = setTimeout(() => {
      setReady(true);
      setError(
        "The graph is taking longer than expected. Please retry, or try 2D.",
      );
    }, 45000);
    return () => clearTimeout(timeout);
  }, [summary, ready, error]);
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (
        event.origin !== window.location.origin ||
        event.source !== frame.current?.contentWindow
      )
        return;
      const data = event.data;
      if (!data || data.type !== "yggdras:graph") return;
      if (data.event === "ready") {
        setReady(true);
        setError("");
      }
      if (data.event === "error") {
        setReady(true);
        setError("The 3D viewer could not start. Try 2D or reload the graph.");
      }
      if (
        data.event === "open-note" &&
        typeof data.slug === "string" &&
        /^[a-zA-Z0-9_-]{1,200}$/.test(data.slug)
      )
        router.push(`/notes?note=${encodeURIComponent(data.slug)}`);
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [router]);
  const retry = () => setGeneration((value) => value + 1);
  useEffect(() => {
    if (ready)
      frame.current?.contentWindow?.postMessage(
        {
          type: "yggdras:graph-appearance",
          reducedTransparency: !!appState.preferences.reducedTransparency,
          reducedMotion: appState.preferences.reducedMotion,
        },
        window.location.origin,
      );
  }, [
    ready,
    appState.preferences.reducedTransparency,
    appState.preferences.reducedMotion,
  ]);
  const toggleRotation = () => {
    frame.current?.contentWindow?.postMessage(
      { type: "yggdras:graph-control", paused: !paused },
      window.location.origin,
    );
    setPaused(!paused);
  };
  return (
    <section className="brain-graph-page" aria-labelledby="graph-title">
      <div className="brain-graph-heading">
        <div>
          <h1 id="graph-title">Graph</h1>
        </div>
        <div className="brain-graph-actions">
          <button
            className="button"
            aria-pressed={layer === "brain"}
            onClick={() => setLayer("brain")}
          >
            Brain
          </button>
          <button
            className="button"
            aria-pressed={layer === "work"}
            onClick={() => setLayer("work")}
          >
            Work connections
          </button>
          {layer === "brain" && (
            <>
              <button
                className="button"
                aria-pressed={paused}
                disabled={!ready || dimension !== "3d"}
                onClick={toggleRotation}
              >
                <Icon name={paused ? "Orbit" : "SquareCheck"} size={15} />
                {paused ? "Resume rotation" : "Pause rotation"}
              </button>
              <button className="button" onClick={retry}>
                <Icon name="RefreshCw" size={15} />
                Reload
              </button>
            </>
          )}
        </div>
      </div>
      {layer === "work" ? (
        <WorkGraph />
      ) : (
        <>
          <div className="brain-graph-meta" aria-live="polite">
            <span>
              <Icon name="Network" size={14} />
              Brain graph
            </span>
            {summary && (
              <>
                <span>{summary.nodes} notes</span>
                <span>{summary.links} connections</span>
              </>
            )}
            <span className="brain-graph-readonly">Read only</span>
          </div>
          {error && (
            <div className="error-banner brain-graph-error" role="alert">
              <Icon name="CircleAlert" size={17} />
              <span>{error}</span>
              <button
                className="button"
                onClick={() => {
                  setDimension("2d");
                  retry();
                }}
              >
                Try 2D
              </button>
              <button className="button" onClick={retry}>
                Retry
              </button>
            </div>
          )}
          <div className="brain-graph-stage" aria-busy={!ready && !error}>
            {!ready && !error && (
              <div className="brain-graph-loading" role="status">
                <div className="brain-graph-loading-mark">
                  <Icon name="Orbit" size={30} />
                </div>
                <strong>Loading graph</strong>
                <p>Opening your Brain graph…</p>
              </div>
            )}
            {summary && (
              <iframe
                key={`${generation}-${dimension}`}
                ref={frame}
                title="Interactive Brain graph and note details"
                src={`/api/graph-viewer/graph.html#dim=${dimension}&theme=dark&style=classic`}
                sandbox="allow-scripts allow-same-origin"
                referrerPolicy="no-referrer"
                onError={() => {
                  setReady(true);
                  setError("Your graph could not be opened. Please retry.");
                }}
              />
            )}
            {!summary && error && (
              <div className="brain-graph-unavailable">
                <Icon name="Network" size={42} />
                <h2>Your graph is taking a moment</h2>
                <p>
                  Your notes are safe. Reconnect to the Brain viewer and try
                  again.
                </p>
                <button className="button primary" onClick={retry}>
                  Reload graph
                </button>
              </div>
            )}
          </div>
          <div className="brain-graph-hint">
            <span>
              <Icon name="MousePointer2" size={13} />
              Drag to orbit · Scroll to zoom · Select a note to explore
            </span>
          </div>
        </>
      )}
    </section>
  );
}
