"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { applicationApi } from "@/lib/api";
import { usePlanning } from "./planning-provider";
import { dateInZone } from "@/lib/planning";
type Node = {
  id: string;
  kind: string;
  title: string;
  status: string;
  slug?: string;
  starts_on?: string;
  starts_at?: string;
};
type Graph = {
  nodes: Node[];
  edges: { source: string; target: string; relation: string }[];
  root: string;
  truncated: boolean;
};
export function WorkGraph() {
  const { select, setDay, timezone } = usePlanning();
  const [roots, setRoots] = useState<Node[]>([]),
    [root, setRoot] = useState(""),
    [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [graph, setGraph] = useState<Graph | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [rootsLoading, setRootsLoading] = useState(true),
    [selected, setSelected] = useState<Node | null>(null),
    [depth, setDepth] = useState(1),
    [completed, setCompleted] = useState(false),
    [zoom, setZoom] = useState(1),
    [offset, setOffset] = useState({ x: 0, y: 0 }),
    [focused, setFocused] = useState(0),
    [generation, setGeneration] = useState(0);
  const [viewport, setViewport] = useState({ width: 800, height: 540 });
  const svg = useRef<SVGSVGElement>(null),
    loadedKey = useRef(""),
    drag = useRef<{ x: number; y: number; left: number; top: number } | null>(
      null,
    );
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 180);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    const abort = new AbortController();
    setRootsLoading(true);
    void applicationApi<{ roots: Node[] }>(
      "application/work-graph/roots?" + new URLSearchParams({ query: search }),
      { signal: abort.signal },
    )
      .then((data) => {
        setRoots(data.roots);
        setError("");
        setRoot((old) => old || data.roots[0]?.id || "");
      })
      .catch((error) => {
        if (!abort.signal.aborted) setError(error.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setRootsLoading(false);
      });
    return () => abort.abort();
  }, [search, generation]);
  useEffect(() => {
    if (!root) return;
    const abort = new AbortController();
    const requestKey = `${root}:${depth}:${completed}`;
    const changed = loadedKey.current !== requestKey;
    if (changed) {
      setLoading(true);
      setSelected(null);
    }
    void applicationApi<Graph>(
      "application/work-graph?" +
        new URLSearchParams({
          root,
          depth: String(depth),
          include_completed: String(completed),
        }),
      { signal: abort.signal },
    )
      .then((data) => {
        setGraph(data);
        setFocused((previous) =>
          Math.min(previous, Math.max(0, data.nodes.length - 1)),
        );
        setSelected((previous) =>
          previous
            ? data.nodes.find((node) => node.id === previous.id) || null
            : null,
        );
        setError("");
        if (changed) {
          setZoom(1);
          setOffset({ x: 0, y: 0 });
        }
        loadedKey.current = requestKey;
      })
      .catch((error) => {
        if (!abort.signal.aborted) {
          setError(error.message);
          setGraph(null);
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [root, depth, completed, generation]);
  const refresh = useCallback(() => setGeneration((value) => value + 1), []);
  useEffect(() => {
    const poll = () => {
      if (document.visibilityState === "visible") refresh();
    };
    const timer = setInterval(poll, 30000);
    window.addEventListener("focus", poll);
    window.addEventListener("yggdress:tasks-changed", refresh);
    window.addEventListener("yggdress:connections-changed", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", poll);
      window.removeEventListener("yggdress:tasks-changed", refresh);
      window.removeEventListener("yggdress:connections-changed", refresh);
    };
  }, [refresh]);
  const ordered = graph
    ? [...graph.nodes].sort((a, b) =>
        a.id === root ? -1 : b.id === root ? 1 : a.title.localeCompare(b.title),
      )
    : [];
  const points = new Map(
    ordered.map((node, index) => [
      node.id,
      index === 0
        ? { x: 400, y: 270 }
        : {
            x:
              400 +
              Math.cos(
                ((index - 1) * Math.PI * 2) / Math.max(1, ordered.length - 1),
              ) *
                (ordered.length > 25 ? 205 : 180),
            y:
              270 +
              Math.sin(
                ((index - 1) * Math.PI * 2) / Math.max(1, ordered.length - 1),
              ) *
                200,
          },
    ]),
  );
  const positions = Array.from(points.values());
  const minX = Math.min(400, ...positions.map((p) => p.x)),
    maxX = Math.max(400, ...positions.map((p) => p.x));
  const minY = Math.min(270, ...positions.map((p) => p.y)),
    maxY = Math.max(270, ...positions.map((p) => p.y));
  const viewWidth = Math.max(320, maxX - minX + 180),
    viewHeight = Math.max(260, maxY - minY + 160);
  const unitScale = Math.max(
    0.1,
    Math.min(viewport.width / viewWidth, viewport.height / viewHeight),
  );
  useEffect(() => {
    if (!svg.current) return;
    const element = svg.current;
    const observer = new ResizeObserver(() => {
      const rect = element.getBoundingClientRect();
      if (rect.width && rect.height)
        setViewport({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [graph?.root, graph?.nodes.length]);
  return (
    <section className="work-graph panel" aria-label="Application work graph">
      <div className="work-graph-tools">
        <label>
          Find a starting item
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Note, task, or event"
          />
        </label>
        <label>
          Start from
          <select
            aria-label="Work graph starting item"
            value={root}
            onChange={(event) => setRoot(event.target.value)}
          >
            {!roots.some((node) => node.id === root) && root && (
              <option value={root}>Selected item</option>
            )}
            {roots.map((node) => (
              <option key={node.id} value={node.id}>
                {node.title} · {node.kind}
              </option>
            ))}
          </select>
        </label>
        <label>
          Depth
          <select
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
          >
            <option value={1}>Direct connections</option>
            <option value={2}>Two steps</option>
          </select>
        </label>
        <label className="work-graph-completed">
          <input
            type="checkbox"
            checked={completed}
            onChange={(event) => setCompleted(event.target.checked)}
          />
          Include completed work
        </label>
      </div>
      {error && (
        <div role="alert" className="error">
          <p>{error}</p>
          <button className="button" onClick={refresh}>
            Retry work graph
          </button>
        </div>
      )}
      {(loading || (rootsLoading && !graph)) && (
        <p role="status">Loading linked work…</p>
      )}
      {!root && !loading && !rootsLoading && !error && (
        <p>
          No application work is linked yet. Create or link work from a saved
          note to begin.
        </p>
      )}
      {graph && (
        <>
          <div className="work-graph-controls">
            <button
              className="button"
              aria-label="Zoom work graph out"
              onClick={() => setZoom((value) => Math.max(0.5, value - 0.2))}
            >
              −
            </button>
            <button
              className="button"
              aria-label="Zoom work graph in"
              onClick={() => setZoom((value) => Math.min(2.5, value + 0.2))}
            >
              +
            </button>
            <button
              className="button"
              onClick={() => {
                setZoom(1);
                setOffset({ x: 0, y: 0 });
              }}
            >
              Reset view
            </button>
            <span>
              {graph.nodes.length} items · {graph.edges.length} links
            </span>
          </div>
          <div className="work-graph-layout">
            <svg
              ref={svg}
              className="work-graph-canvas"
              viewBox={`${(minX + maxX - viewWidth) / 2} ${(minY + maxY - viewHeight) / 2} ${viewWidth} ${viewHeight}`}
              role="group"
              aria-label="Linked application work; drag empty space to pan, use zoom controls"
              onPointerDown={(event) => {
                if ((event.target as Element).closest("[data-work-node]"))
                  return;
                event.currentTarget.setPointerCapture(event.pointerId);
                drag.current = {
                  x: event.clientX,
                  y: event.clientY,
                  left: offset.x,
                  top: offset.y,
                };
              }}
              onPointerMove={(event) => {
                if (!drag.current) return;
                const scale = 1 / unitScale;
                setOffset({
                  x:
                    drag.current.left +
                    (event.clientX - drag.current.x) * scale,
                  y:
                    drag.current.top + (event.clientY - drag.current.y) * scale,
                });
              }}
              onPointerUp={() => {
                drag.current = null;
              }}
              onPointerCancel={() => {
                drag.current = null;
              }}
            >
              <g
                transform={`translate(${offset.x} ${offset.y}) translate(400 270) scale(${zoom}) translate(-400 -270)`}
              >
                {graph.edges.map((edge, index) => {
                  const a = points.get(edge.source),
                    b = points.get(edge.target);
                  return a && b ? (
                    <line key={index} x1={a.x} y1={a.y} x2={b.x} y2={b.y}>
                      <title>{edge.relation.replaceAll("_", " ")}</title>
                    </line>
                  ) : null;
                })}
                {ordered.map((node, index) => {
                  const point = points.get(node.id)!;
                  return (
                    <g
                      key={node.id}
                      data-work-node={node.id}
                      role="button"
                      aria-label={`${node.title}, ${node.kind}${node.status ? ", " + node.status : ""}`}
                      aria-pressed={selected?.id === node.id}
                      tabIndex={focused === index ? 0 : -1}
                      onFocus={() => setFocused(index)}
                      onClick={() => setSelected(node)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelected(node);
                        } else if (
                          [
                            "ArrowRight",
                            "ArrowDown",
                            "ArrowLeft",
                            "ArrowUp",
                          ].includes(event.key)
                        ) {
                          event.preventDefault();
                          const next =
                            (index +
                              (["ArrowRight", "ArrowDown"].includes(event.key)
                                ? 1
                                : -1) +
                              ordered.length) %
                            ordered.length;
                          setFocused(next);
                          svg.current
                            ?.querySelectorAll<SVGGElement>("[data-work-node]")
                            [next]?.focus();
                        }
                      }}
                      transform={`translate(${point.x},${point.y})`}
                      className={`work-graph-node ${node.kind} ${selected?.id === node.id ? "selected" : ""}`}
                    >
                      <circle r={(node.id === root ? 20 : 12) / unitScale} />
                      {(ordered.length <= 8 ||
                        node.id === root ||
                        selected?.id === node.id ||
                        focused === index) && (
                        <text
                          style={{ fontSize: 12 / unitScale }}
                          y={(node.id === root ? 38 : 30) / unitScale}
                          textAnchor="middle"
                        >
                          {node.title.length > 17
                            ? node.title.slice(0, 16) + "…"
                            : node.title}
                        </text>
                      )}
                      <title>{node.title}</title>
                    </g>
                  );
                })}
              </g>
            </svg>
            <aside className="work-graph-detail" aria-live="polite">
              {selected ? (
                <>
                  <small>{selected.kind.replaceAll("_", " ")}</small>
                  <h2>{selected.title}</h2>
                  {selected.status && (
                    <p>{selected.status.replaceAll("_", " ")}</p>
                  )}
                  {selected.kind === "note" &&
                    selected.slug &&
                    !["archived", "missing"].includes(selected.status) && (
                      <Link
                        className="button"
                        href={`/notes?note=${encodeURIComponent(selected.slug)}`}
                      >
                        Open note
                      </Link>
                    )}
                  {selected.kind === "task" && (
                    <button
                      className="button"
                      onClick={() => select(selected.id.split(":")[1])}
                    >
                      Open task
                    </button>
                  )}
                  {["event", "date_item", "availability"].includes(
                    selected.kind,
                  ) && (
                    <Link
                      className="button"
                      href="/calendar"
                      onClick={() => {
                        const date =
                          selected.starts_on ||
                          (selected.starts_at
                            ? dateInZone(selected.starts_at, timezone)
                            : undefined);
                        if (date) setDay(date);
                      }}
                    >
                      Open calendar
                    </Link>
                  )}
                  <button
                    className="text-link"
                    onClick={() => setRoot(selected.id)}
                  >
                    Explore from here
                  </button>
                </>
              ) : (
                <p>Select an item to inspect its context.</p>
              )}
            </aside>
          </div>
          <details className="work-graph-list">
            <summary>Browse connections as a list</summary>
            <ul>
              {ordered.map((node) => (
                <li key={node.id}>
                  <button
                    className="text-link"
                    onClick={() => setSelected(node)}
                  >
                    {node.title} · {node.kind.replaceAll("_", " ")}
                  </button>
                </li>
              ))}
            </ul>
          </details>
          {graph.truncated && (
            <p className="muted">
              This neighborhood is bounded to keep the view responsive. Select
              an item to explore another neighborhood.
            </p>
          )}
          <p className="muted">
            These are application relationships. Lia’s existing Brain graph is
            unchanged.
          </p>
        </>
      )}
    </section>
  );
}
