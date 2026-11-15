"use client";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { areas, areaOf } from "@/lib/data";
import { searchNotes } from "@/lib/repository";
import type { Flashcard, Note } from "@/lib/types";
import { useApp } from "./provider";
import { launchCapture } from "./shell";
import { NoteList } from "./notes";
import { Goals } from "./today";
import { Empty, Icon, Modal, Panel, relativeTime } from "./ui";
export function Graph({ notes }: { notes: Note[] }) {
  const { openNote } = useApp(),
    [zoom, setZoom] = useState(1),
    [offset, setOffset] = useState({ x: 0, y: 0 }),
    drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(
      null,
    ),
    moved = useRef(false);
  const nodes = useMemo(
    () =>
      notes.slice(0, 80).map((n, i) => {
        const angle = i * 2.39996,
          r = i === 0 ? 0 : Math.min(205, 60 + Math.sqrt(i) * 27);
        return {
          ...n,
          x: 360 + Math.cos(angle) * r * 1.3,
          y: 250 + Math.sin(angle) * r,
        };
      }),
    [notes],
  );
  const byId = new Map(nodes.map((n) => [n.id, n]));
  if (!notes.length)
    return (
      <Empty
        icon="Network"
        title="Every connection starts somewhere"
        detail="Capture a note and connect it to another thought."
      />
    );
  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        <span>
          <i /> {nodes.length} notes ·{" "}
          {nodes.reduce(
            (a, n) => a + n.links.filter((id) => byId.has(id)).length,
            0,
          )}{" "}
          connections
        </span>
        <div>
          <button
            className="icon-button"
            aria-label="Zoom out"
            onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}
          >
            <Icon name="Minus" size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Reset graph view"
            onClick={() => {
              setZoom(1);
              setOffset({ x: 0, y: 0 });
            }}
          >
            <Icon name="Scan" size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Zoom in"
            onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
          >
            <Icon name="Plus" size={17} />
          </button>
        </div>
      </div>
      <svg
        viewBox="0 0 720 500"
        className="graph-canvas"
        role="group"
        aria-label="Connected notes graph. Drag to pan. Use zoom buttons or scroll."
        onWheel={(e) =>
          setZoom((z) => Math.max(0.4, Math.min(2.5, z - e.deltaY * 0.001)))
        }
        onPointerDown={(e) => {
          if ((e.target as Element).closest("[data-node]")) return;
          const rect = e.currentTarget.getBoundingClientRect();
          drag.current = {
            x: (e.clientX * 720) / rect.width,
            y: (e.clientY * 500) / rect.height,
            ox: offset.x,
            oy: offset.y,
          };
          moved.current = false;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const rect = e.currentTarget.getBoundingClientRect();
          moved.current = true;
          setOffset({
            x:
              drag.current.ox + (e.clientX * 720) / rect.width - drag.current.x,
            y:
              drag.current.oy +
              (e.clientY * 500) / rect.height -
              drag.current.y,
          });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        <defs>
          <radialGradient id="graph-glow">
            <stop stopColor="#5e8be7" stopOpacity=".13" />
            <stop offset="1" stopColor="#5e8be7" stopOpacity="0" />
          </radialGradient>
          <pattern
            id="graph-dots"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="1" cy="1" r=".6" fill="#b3c8ed" opacity=".12" />
          </pattern>
        </defs>
        <rect width="720" height="500" fill="url(#graph-dots)" />
        <circle cx="360" cy="250" r="230" fill="url(#graph-glow)" />
        <g
          transform={`translate(${offset.x + 360 * (1 - zoom)} ${offset.y + 250 * (1 - zoom)}) scale(${zoom})`}
        >
          {nodes.flatMap((n) =>
            n.links.map((id) => {
              const to = byId.get(id);
              return (
                to && (
                  <line
                    key={`${n.id}-${id}`}
                    x1={n.x}
                    y1={n.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={areaOf(n.area).color}
                    strokeOpacity=".32"
                    strokeWidth="1.5"
                  />
                )
              );
            }),
          )}
          {nodes.map((n) => (
            <g
              key={n.id}
              data-node="true"
              role="button"
              tabIndex={0}
              aria-label={`Open ${n.title}`}
              className="graph-node"
              onClick={() => openNote(n.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openNote(n.id);
                }
              }}
            >
              <circle
                cx={n.x}
                cy={n.y}
                r="22"
                fill={areaOf(n.area).color}
                fillOpacity=".08"
              />
              <circle
                cx={n.x}
                cy={n.y}
                r="10"
                fill={areaOf(n.area).color}
                stroke={areaOf(n.area).color}
                strokeWidth="5"
                strokeOpacity=".15"
              />
              <text
                x={n.x}
                y={n.y + 34}
                textAnchor="middle"
                fill="#d9e4f5"
                fontSize="11"
              >
                {n.title.length > 26 ? n.title.slice(0, 24) + "…" : n.title}
              </text>
            </g>
          ))}
        </g>
      </svg>
      <div className="graph-caption">
        <Icon name="MousePointer2" size={13} /> Drag to explore · select a note
        to open {notes.length > 80 && "· showing the first 80 notes"}
      </div>
    </div>
  );
}
function Timeline({ notes }: { notes: Note[] }) {
  const { openNote } = useApp();
  const [limit, setLimit] = useState(15),
    sentinel = useRef<HTMLDivElement>(null);
  const sorted = useMemo(
    () => [...notes].sort((a, b) => b.updated.localeCompare(a.updated)),
    [notes],
  );
  useEffect(() => {
    setLimit(15);
  }, [notes]);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting)
        setLimit((n) => Math.min(n + 15, sorted.length));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [limit, sorted.length]);
  if (!sorted.length)
    return (
      <Empty
        icon="History"
        title="Your story starts here"
        detail="Dated notes will appear along this timeline."
      />
    );
  return (
    <div className="area-timeline">
      {sorted.slice(0, limit).map((n, i) => (
        <div className="timeline-item" key={n.id}>
          <span
            className="timeline-marker"
            style={{ background: areaOf(n.area).color }}
          />
          {(i === 0 ||
            sorted[i - 1].updated.slice(0, 10) !== n.updated.slice(0, 10)) && (
            <h3>
              {new Date(n.updated).toLocaleDateString("en", {
                weekday: "long",
                month: "long",
                day: "numeric",
              })}
            </h3>
          )}
          <button onClick={() => openNote(n.id)}>
            <span className="timeline-time">
              {new Date(n.updated).toLocaleTimeString("en", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <div>
              <strong>{n.title}</strong>
              <p>{n.description}</p>
              <small>{n.tags.map((t) => `#${t}`).join(" · ")}</small>
            </div>
            <Icon name="ArrowUpRight" size={16} />
          </button>
        </div>
      ))}
      <div ref={sentinel} />
      {limit < sorted.length && (
        <button
          className="button load-more"
          onClick={() => setLimit((n) => n + 15)}
        >
          Load more
        </button>
      )}
    </div>
  );
}
export function ReviewDialog({
  cards,
  open,
  onClose,
}: {
  cards: Flashcard[];
  open: boolean;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(0),
    [flipped, setFlipped] = useState(false),
    [correct, setCorrect] = useState(0),
    startX = useRef(0);
  useEffect(() => {
    if (open) {
      setIndex(0);
      setCorrect(0);
      setFlipped(false);
    }
  }, [open]);
  const ended = index >= cards.length;
  function score(right: boolean) {
    if (!flipped || ended) return;
    setCorrect((c) => c + (right ? 1 : 0));
    setIndex((i) => i + 1);
    setFlipped(false);
  }
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (
        e.code === "Space" &&
        !ended &&
        (e.target as HTMLElement).tagName !== "BUTTON"
      ) {
        e.preventDefault();
        setFlipped((v) => !v);
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        score(true);
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        score(false);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open, flipped, index, ended]);
  return (
    <Modal
      open={open}
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
      title="A little practice"
      description="Flip to reveal. Swipe right for correct, left to practice again."
    >
      {!cards.length ? (
        <Empty
          title="No flashcards in this area yet"
          detail="Try the German or University area to explore a review session."
        />
      ) : ended ? (
        <div className="review-result">
          <span className="result-icon">
            <Icon name="PartyPopper" size={36} />
          </span>
          <h3>A little stronger than before.</h3>
          <p>
            <strong>
              {correct} / {cards.length}
            </strong>{" "}
            cards correct · {Math.round((correct / cards.length) * 100)}%
          </p>
          <p className="muted">Small repetitions become lasting knowledge.</p>
          <button className="button primary" onClick={onClose}>
            Finish session
            <Icon name="Check" size={17} />
          </button>
        </div>
      ) : (
        <>
          <div className="review-count">
            <span>
              {index + 1} of {cards.length}
            </span>
            <span>{correct} correct</span>
          </div>
          <button
            className={`flashcard ${flipped ? "flipped" : ""}`}
            onClick={() => setFlipped((v) => !v)}
            onTouchStart={(e) => {
              startX.current = e.touches[0].clientX;
            }}
            onTouchEnd={(e) => {
              const dx = e.changedTouches[0].clientX - startX.current;
              if (Math.abs(dx) > 60) {
                e.preventDefault();
                score(dx > 0);
              }
            }}
            aria-label={`${flipped ? "Definition" : "Term"}: ${flipped ? cards[index].back : cards[index].front}. Activate to flip.`}
          >
            <small>{flipped ? "DEFINITION" : "TERM"}</small>
            <strong>{flipped ? cards[index].back : cards[index].front}</strong>
            <span>
              <Icon name="RotateCcw" size={14} /> Click or press Space to flip
            </span>
          </button>
          <div className="review-actions">
            <button
              className="button"
              disabled={!flipped}
              onClick={() => score(false)}
            >
              <Icon name="ArrowLeft" size={17} />
              Practice again
            </button>
            <button
              className="button primary"
              disabled={!flipped}
              onClick={() => score(true)}
            >
              Got it
              <Icon name="ArrowRight" size={17} />
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
export function AreaPage({ id }: { id: string }) {
  const { state } = useApp(),
    area = areas.find((a) => a.id === id),
    [tab, setTab] = useState("notes"),
    [query, setQuery] = useState(""),
    [debounced, setDebounced] = useState(""),
    [tag, setTag] = useState(""),
    [review, setReview] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 150);
    return () => clearTimeout(t);
  }, [query]);
  const all = useMemo(
    () => searchNotes(state.notes, "", id),
    [state.notes, id],
  );
  const notes = useMemo(
    () => searchNotes(all, debounced, undefined, tag),
    [all, debounced, tag],
  );
  const tags = [...new Set(all.flatMap((n) => n.tags))].sort();
  if (!area)
    return (
      <Empty
        title="This life area isn’t here"
        detail="Choose an area from the sidebar."
      />
    );
  return (
    <div
      className="standard-page area-page"
      style={{ "--accent": area.color } as CSSProperties}
    >
      <div className="page-intro">
        <div>
          <span className="eyebrow">A LITTLE ROOM FOR</span>
          <h1>
            <span className="page-area-icon">
              <Icon name={area.icon} size={29} />
            </span>
            {area.name}
          </h1>
          <p>{area.description}</p>
        </div>
        <div className="page-actions">
          <button className="button" onClick={() => setReview(true)}>
            <Icon name="Layers" size={17} />
            Review
          </button>
          <button
            className="button primary"
            onClick={() => launchCapture("note")}
          >
            <Icon name="Plus" size={17} />
            New note
          </button>
        </div>
      </div>
      <div className="area-overview">
        <span>
          <strong>{all.length}</strong> notes
        </span>
        <span>
          <strong>{all.reduce((s, n) => s + n.links.length, 0)}</strong>{" "}
          connections
        </span>
        <span>
          <strong>
            {state.tasks.filter((t) => t.area === id && !t.done).length}
          </strong>{" "}
          open tasks
        </span>
        <span className="area-overview-tail">
          <Icon name="Sprout" size={15} /> Every thought adds up.
        </span>
      </div>
      <div className="area-layout">
        <Panel className="area-main">
          <div className="area-toolbar">
            <div className="tabs" role="tablist" aria-label="Area view">
              {[
                { id: "notes", label: "Notes", icon: "List" },
                { id: "graph", label: "Graph", icon: "Network" },
                { id: "timeline", label: "Timeline", icon: "History" },
              ].map((t) => (
                <button
                  key={t.id}
                  id={`tab-${t.id}`}
                  role="tab"
                  aria-selected={tab === t.id}
                  aria-controls="area-content"
                  onClick={() => setTab(t.id)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                      e.preventDefault();
                      const opts = ["notes", "graph", "timeline"];
                      const target =
                        opts[
                          (opts.indexOf(tab) +
                            (e.key === "ArrowRight" ? 1 : 2)) %
                            3
                        ];
                      setTab(target);
                      document.getElementById(`tab-${target}`)?.focus();
                    }
                  }}
                >
                  <Icon name={t.icon} size={16} />
                  {t.label}
                </button>
              ))}
            </div>
            <span className="muted">{notes.length} thoughts</span>
          </div>
          <div className="notes-filters">
            <div className="filter-input">
              <Icon name="Search" size={17} />
              <input
                aria-label="Search area notes"
                placeholder="Find a thought…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <select
              aria-label="Filter by tag"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
            >
              <option value="">All tags</option>
              {tags.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </div>
          <div role="tabpanel" id="area-content" aria-labelledby={`tab-${tab}`}>
            {tab === "notes" ? (
              <NoteList notes={notes} />
            ) : tab === "graph" ? (
              <Graph notes={notes} />
            ) : (
              <Timeline notes={notes} />
            )}
          </div>
        </Panel>
        <div className="area-side">
          <Panel title="Growing steadily">
            <Goals area={id} />
          </Panel>
          <Panel title="A moment to reconnect">
            <div className="review-prompt">
              <Icon name="BookOpen" size={28} />
              <h3>Make it stick.</h3>
              <p>
                A few minutes of practice today. A little more knowledge
                tomorrow.
              </p>
              <button className="button" onClick={() => setReview(true)}>
                Review flashcards
                <Icon name="ArrowRight" size={15} />
              </button>
            </div>
          </Panel>
        </div>
      </div>
      <ReviewDialog
        cards={state.cards.filter((c) => c.area === id)}
        open={review}
        onClose={() => setReview(false)}
      />
    </div>
  );
}
