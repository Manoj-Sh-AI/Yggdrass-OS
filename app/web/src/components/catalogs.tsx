"use client";
import { useCallback, useEffect, useState } from "react";
import {
  CALLBACK_PATH,
  catalogApi,
  connectorState,
  connectorsFor,
  groupConnectors,
  humanize,
  statusOf,
  unlockedBy,
  type Connector,
  type Skill,
  type SkillDetail,
} from "@/lib/catalog";
import { APP_LOGOS } from "@/lib/app-logos";
import { Empty, Icon, Modal } from "./ui";

/** The app's own logo, bundled locally; a domain icon for servers Manoj added himself. */
function AppLogo({ c, fallback }: { c: Connector; fallback: string }) {
  const logo = APP_LOGOS[c.name];
  if (!logo)
    return (
      <span className="catalog-icon">
        <Icon name={fallback} size={18} />
      </span>
    );
  if (logo.kind === "letter")
    return (
      <span
        className="catalog-logo catalog-logo-letter"
        style={{ background: `#${logo.hex}` }}
        aria-hidden="true"
      >
        {logo.letter}
      </span>
    );
  return (
    <span className="catalog-logo" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="22" height="22" role="presentation">
        <path d={logo.d} fill={`#${logo.hex}`} />
      </svg>
    </span>
  );
}

const message = (e: unknown) =>
  e instanceof Error ? e.message : "The catalog is unavailable.";

/** Both pages show how connectors and skills meet, so each loads both lists. */
function useCatalog() {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    Promise.all([catalogApi.connectors(), catalogApi.skills()])
      .then(([c, s]) => {
        setConnectors(c);
        setSkills(s);
      })
      .catch((e) => setError(message(e)));
  }, []);
  useEffect(load, [load]);
  return { connectors, setConnectors, skills, error, load };
}

function Heading({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="page-intro">
      <div>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function Problem({ error, retry }: { error: string; retry: () => void }) {
  return (
    <div className="catalog-problem panel" role="alert">
      <span>{error}</span>
      <button className="button" onClick={retry}>
        Try again
      </button>
    </div>
  );
}

const DOMAIN_ICON: Record<string, string> = {
  email: "MessageCircle",
  messages: "MessageCircle",
  calendar: "Calendar",
  files: "Folder",
  documents: "NotebookPen",
  spreadsheets: "SquareCheck",
  projects: "SquareCheck",
  "tasks-external": "SquareCheck",
  code: "Code",
  design: "Sparkles",
  automation: "Network",
};

function ConnectorCard({
  c,
  skills,
  busy,
  refused,
  onConnect,
  onDisconnect,
  onToggle,
}: {
  c: Connector;
  skills: Skill[];
  busy: boolean;
  refused: string;
  onConnect: () => void;
  onDisconnect: () => void;
  onToggle: () => void;
}) {
  const status = statusOf(c);
  const skillNames = unlockedBy(c, skills);
  const [setupOpen, setSetupOpen] = useState(false);
  const callback =
    typeof window === "undefined"
      ? CALLBACK_PATH
      : `${window.location.origin}${CALLBACK_PATH}`;
  return (
    <li className={`panel catalog-card catalog-status-${status}`}>
      <div className="catalog-card-head">
        <AppLogo c={c} fallback={DOMAIN_ICON[c.domain] || "Plug"} />
        <div className="catalog-card-title">
          <h2>{c.title}</h2>
          <small>{connectorState(c)}</small>
        </div>
        {status === "connected" && (
          <button
            role="switch"
            aria-checked={c.enabled}
            aria-label={`${c.enabled ? "Switch off" : "Switch on"} ${c.title}`}
            disabled={busy}
            className={`switch ${c.enabled ? "on" : ""}`}
            onClick={onToggle}
          >
            <span />
          </button>
        )}
      </div>
      {c.description && <p className="catalog-description">{c.description}</p>}
      {status === "connected" && (
        <p className="catalog-note">
          {skillNames.length
            ? `Used by ${skillNames.map(humanize).join(", ")}.`
            : "No skill uses this app yet, so Yggdras will not call it."}{" "}
          Changes always wait for your approval.
        </p>
      )}
      {status === "needs_setup" && setupOpen && (
        <div className="catalog-setup">
          <p>{c.setup || "This app needs its own sign-in app first."}</p>
          {c.missing_env.length > 0 && (
            <p>
              Then add these to your <code>.env</code> and restart Yggdras:{" "}
              {c.missing_env.map((n) => (
                <code key={n}>{n}</code>
              ))}
            </p>
          )}
          <p>
            Redirect address: <code>{callback}</code>
          </p>
        </div>
      )}
      <div className="catalog-actions">
        {status === "available" && (
          <button
            className="button primary"
            disabled={busy}
            onClick={onConnect}
          >
            {busy ? "Opening sign-in…" : "Connect"}
          </button>
        )}
        {status === "connected" && c.auth !== "file" && (
          <button className="button" disabled={busy} onClick={onDisconnect}>
            Disconnect
          </button>
        )}
        {status === "needs_setup" && (
          <button
            className="button"
            aria-expanded={setupOpen}
            onClick={() => setSetupOpen((v) => !v)}
          >
            {setupOpen ? "Hide setup" : "How to set up"}
          </button>
        )}
        {status === "unavailable" && (
          <button className="button" disabled>
            Not available yet
          </button>
        )}
      </div>
      {refused && (
        <p className="catalog-refused" role="alert">
          {refused}
        </p>
      )}
    </li>
  );
}

export function ConnectorCatalog() {
  const { connectors, setConnectors, skills, error, load } = useCatalog();
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [waiting, setWaiting] = useState("");
  const [refused, setRefused] = useState<Record<string, string>>({});
  const replace = (next: Connector) =>
    setConnectors(
      (all) => all && all.map((x) => (x.name === next.name ? next : x)),
    );
  async function act(c: Connector, work: () => Promise<void>) {
    setBusy(c.name);
    setRefused((r) => ({ ...r, [c.name]: "" }));
    try {
      await work();
    } catch (e) {
      setRefused((r) => ({ ...r, [c.name]: message(e) }));
    } finally {
      setBusy("");
    }
  }
  // After a sign-in opens in another tab or the system browser, look for the result
  // when Manoj comes back, and every few seconds for two minutes.
  useEffect(() => {
    if (!waiting) return;
    const check = () =>
      catalogApi
        .connectors()
        .then((all) => {
          setConnectors(all);
          if (all.find((c) => c.name === waiting)?.status === "connected")
            setWaiting("");
        })
        .catch(() => undefined);
    const timer = setInterval(check, 3000);
    const stop = setTimeout(() => setWaiting(""), 120000);
    window.addEventListener("focus", check);
    return () => {
      clearInterval(timer);
      clearTimeout(stop);
      window.removeEventListener("focus", check);
    };
  }, [waiting, setConnectors]);
  const groups = connectors ? groupConnectors(connectors, query) : [];
  const connectedCount = (connectors || []).filter(
    (c) => statusOf(c) === "connected",
  ).length;
  return (
    <div className="catalog-page">
      <Heading
        title="Connectors"
        detail="Apps Yggdras can reach once you sign in. It reads them only for the task at hand, saves nothing on its own, and asks before changing anything."
      />
      {error && <Problem error={error} retry={load} />}
      {!error && !connectors && <p className="muted">Loading connectors…</p>}
      {connectors && (
        <div className="catalog-toolbar">
          <label className="catalog-search">
            <Icon name="Search" size={16} />
            <input
              type="search"
              placeholder="Find an app"
              aria-label="Find an app"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <span className="muted">
            {connectedCount} connected · {connectors.length} apps
          </span>
        </div>
      )}
      {waiting && (
        <p className="catalog-waiting" role="status">
          Finish signing in to{" "}
          {connectors?.find((c) => c.name === waiting)?.title} in the window
          that opened. This page updates when you are done.
        </p>
      )}
      {groups.map(({ group, items }) => (
        <section key={group} className="catalog-group" aria-label={group}>
          <h2 className="catalog-group-title">{group}</h2>
          <ul className="catalog-grid">
            {items.map((c) => (
              <ConnectorCard
                key={c.name}
                c={c}
                skills={skills || []}
                busy={busy === c.name}
                refused={refused[c.name] || ""}
                onConnect={() =>
                  void act(c, async () => {
                    const { authorize_url } = await catalogApi.connect(c.name);
                    window.open(authorize_url, "_blank", "noopener,noreferrer");
                    setWaiting(c.name);
                  })
                }
                onDisconnect={() =>
                  void act(c, async () =>
                    replace(await catalogApi.disconnect(c.name)),
                  )
                }
                onToggle={() =>
                  void act(c, async () =>
                    replace(await catalogApi.switch(c.name, !c.enabled)),
                  )
                }
              />
            ))}
          </ul>
        </section>
      ))}
      {connectors && groups.length === 0 && (
        <div className="panel">
          <Empty
            icon="Search"
            title="No app matches"
            detail="Try another name."
          />
        </div>
      )}
    </div>
  );
}

export function SkillCatalog() {
  const { connectors, skills, error, load } = useCatalog();
  const [open, setOpen] = useState<SkillDetail | null>(null);
  const [opening, setOpening] = useState("");
  const [detailError, setDetailError] = useState("");
  async function show(name: string) {
    setOpening(name);
    setDetailError("");
    try {
      setOpen(await catalogApi.skill(name));
    } catch (e) {
      setDetailError(message(e));
    } finally {
      setOpening("");
    }
  }
  return (
    <div className="catalog-page">
      <Heading
        title="Skills"
        detail="The know-how Yggdras loads when a task needs it. Skills are reviewed code, so they change through pull requests, not here."
      />
      {error && <Problem error={error} retry={load} />}
      {detailError && (
        <Problem error={detailError} retry={() => setDetailError("")} />
      )}
      {!error && !skills && <p className="muted">Loading skills…</p>}
      {skills && skills.length === 0 && (
        <div className="panel">
          <Empty icon="BookOpen" title="No skills installed" />
        </div>
      )}
      {skills && skills.length > 0 && (
        <ul className="catalog-grid" aria-label="Skills">
          {skills.map((s) => {
            const linked = connectorsFor(s, connectors || []);
            return (
              <li key={s.name}>
                <button
                  className="panel catalog-card catalog-card-button"
                  onClick={() => void show(s.name)}
                  aria-busy={opening === s.name}
                  data-dialog-origin={opening === s.name ? "" : undefined}
                >
                  <div className="catalog-card-head">
                    <span className="catalog-icon">
                      <Icon name="BookOpen" size={18} />
                    </span>
                    <div className="catalog-card-title">
                      <h2>{humanize(s.name)}</h2>
                      <small>{s.name}</small>
                    </div>
                    <Icon
                      name="ArrowRight"
                      size={16}
                      className="catalog-arrow"
                    />
                  </div>
                  <p className="catalog-description">{s.description}</p>
                  <div className="chips">
                    {s.domains.map((d) => (
                      <span key={d} className="tag">
                        {d}
                      </span>
                    ))}
                    {linked.map((t) => (
                      <span key={t} className="tag catalog-linked">
                        <Icon name="Plug" size={11} /> {t}
                      </span>
                    ))}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <Modal
        open={!!open}
        onOpenChange={(v) => !v && setOpen(null)}
        title={open ? humanize(open.name) : "Skill"}
        description={open?.description}
        wide
      >
        {open && (
          <div className="catalog-skill-detail">
            <div className="chips">
              {open.domains.map((d) => (
                <span key={d} className="tag">
                  {d}
                </span>
              ))}
            </div>
            <h3>Instructions</h3>
            <pre className="catalog-instructions">{open.instructions}</pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
