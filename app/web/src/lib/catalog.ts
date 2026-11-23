import { applicationApi } from "./api";

export type ConnectorStatus =
  "connected" | "available" | "needs_setup" | "unavailable";

/** One app in the directory, or one of Manoj's own servers (connectors.py `Catalog.view`). */
export type Connector = {
  name: string;
  title: string;
  domain: string;
  enabled: boolean;
  missing_env: string[];
  tools: string[];
  group?: string;
  description?: string;
  auth?: "dcr" | "client" | "unavailable" | "file";
  status?: ConnectorStatus;
  setup?: string;
  tool_count?: number;
  connected_at?: number | null;
};

/** A skill card: frontmatter only (skill_registry.py). */
export type Skill = { name: string; description: string; domains: string[] };
export type SkillDetail = Skill & { instructions: string };

export const catalogApi = {
  connectors: () => applicationApi<Connector[]>("yggdras/connectors"),
  switch: (name: string, enabled: boolean) =>
    applicationApi<Connector>(`yggdras/connectors/${name}`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  connect: (name: string) =>
    applicationApi<{ authorize_url: string }>(
      `yggdras/connectors/${name}/connect`,
      { method: "POST", body: "{}" },
    ),
  disconnect: (name: string) =>
    applicationApi<Connector>(`yggdras/connectors/${name}/disconnect`, {
      method: "POST",
      body: "{}",
    }),
  skills: () => applicationApi<Skill[]>("yggdras/skills"),
  skill: (name: string) =>
    applicationApi<SkillDetail>(`yggdras/skills/${name}`),
};

/** Where an app sends Manoj back after signing in; vendors that need their own OAuth app
 * must list exactly this address. */
export const CALLBACK_PATH = "/api/backend/connectors/callback";

/** A connector's tools stay locked until a skill in its domain is loaded (tool_gate.py). */
export function unlockedBy(
  connector: Pick<Connector, "domain">,
  skills: Skill[],
) {
  return skills
    .filter((s) => s.domains.includes(connector.domain))
    .map((s) => s.name);
}

/** The connectors whose tools a skill can unlock. */
export function connectorsFor(
  skill: Pick<Skill, "domains">,
  connectors: Connector[],
) {
  return connectors
    .filter((c) => c.status === "connected" && skill.domains.includes(c.domain))
    .map((c) => c.title);
}

export function statusOf(c: Connector): ConnectorStatus {
  if (c.status) return c.status;
  if (c.missing_env.length) return "needs_setup";
  return c.enabled ? "connected" : "available";
}

export function connectorState(c: Connector) {
  const status = statusOf(c);
  if (status === "unavailable") return "Not available yet";
  if (status === "needs_setup")
    return c.missing_env.length
      ? `Needs ${c.missing_env.join(", ")} in .env`
      : "Needs setup";
  if (status === "available") return "Not connected";
  const count = c.tool_count ?? c.tools.length;
  if (!c.enabled) return "Connected · switched off";
  return `Connected · ${count} tool${count === 1 ? "" : "s"}`;
}

const ORDER: ConnectorStatus[] = [
  "connected",
  "available",
  "needs_setup",
  "unavailable",
];

/** Groups in directory order; within a group, connected apps first, unavailable last. */
export function groupConnectors(all: Connector[], query = "") {
  const q = query.trim().toLowerCase();
  const groups = new Map<string, Connector[]>();
  for (const c of all) {
    const text =
      `${c.title} ${c.description || ""} ${c.group || ""}`.toLowerCase();
    if (q && !text.includes(q)) continue;
    const g = c.group || "Your own";
    groups.set(g, [...(groups.get(g) || []), c]);
  }
  return [...groups.entries()].map(([group, items]) => ({
    group,
    items: [...items].sort(
      (a, b) => ORDER.indexOf(statusOf(a)) - ORDER.indexOf(statusOf(b)),
    ),
  }));
}

/** "send-email" → "Send email". */
export function humanize(name: string) {
  const words = name.replace(/[-_]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
