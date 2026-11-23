import { useCallback, useEffect, useState } from "react";
import { Image, Pressable, Text, View } from "react-native";
import { request } from "./api";
import { APP_LOGOS } from "./app-logos";
import {
  Button,
  ErrorText,
  Field,
  Loading,
  Page,
  Panel,
  Sheet,
  colors,
  styles,
} from "./ui";

/** Same shapes as the web catalog (web/src/lib/catalog.ts). */
export type ConnectorStatus =
  "connected" | "available" | "needs_setup" | "unavailable";
export type Connector = {
  name: string;
  title: string;
  domain: string;
  enabled: boolean;
  missing_env: string[];
  tools: string[];
  group?: string;
  description?: string;
  status?: ConnectorStatus;
  tool_count?: number;
};
export type Skill = { name: string; description: string; domains: string[] };
type SkillDetail = Skill & { instructions: string };

export const humanize = (name: string) => {
  const words = name.replace(/[-_]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};
export const unlockedBy = (c: Pick<Connector, "domain">, skills: Skill[]) =>
  skills.filter((s) => s.domains.includes(c.domain)).map((s) => s.name);
export const statusOf = (c: Connector): ConnectorStatus =>
  c.status ||
  (c.missing_env.length
    ? "needs_setup"
    : c.enabled
      ? "connected"
      : "available");
export const connectorsFor = (s: Pick<Skill, "domains">, all: Connector[]) =>
  all
    .filter((c) => statusOf(c) === "connected" && s.domains.includes(c.domain))
    .map((c) => c.title);
export function connectorState(c: Connector) {
  const status = statusOf(c);
  if (status === "unavailable") return "Not available yet";
  if (status === "needs_setup") return "Needs setup on the laptop";
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
export function groupConnectors(all: Connector[], query = "") {
  const q = query.trim().toLowerCase();
  const groups = new Map<string, Connector[]>();
  for (const c of all) {
    const text = `${c.title} ${c.description || ""} ${c.group || ""}`;
    if (q && !text.toLowerCase().includes(q)) continue;
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

const failure = (e: unknown) =>
  e instanceof Error ? e.message : "The catalog is unavailable.";

function useCatalog(active: boolean) {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        request<Connector[]>("yggdras/connectors"),
        request<Skill[]>("yggdras/skills"),
      ]);
      setConnectors(c);
      setSkills(s);
      setError("");
    } catch (e) {
      setError(failure(e));
    }
  }, []);
  useEffect(() => {
    if (active) void load();
  }, [active, load]);
  return { connectors, setConnectors, skills, error, load };
}

function Tag({ label }: { label: string }) {
  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: colors.line,
        backgroundColor: "rgba(255, 255, 255, 0.05)",
        borderRadius: 7,
        paddingHorizontal: 9,
        paddingVertical: 3,
      }}
    >
      <Text style={{ color: colors.text, fontSize: 12 }}>{label}</Text>
    </View>
  );
}

function StatusDot({ status }: { status: ConnectorStatus }) {
  return (
    <View
      style={{
        width: 8,
        height: 8,
        borderRadius: 4,
        backgroundColor:
          status === "connected"
            ? colors.accent
            : status === "available"
              ? colors.muted
              : "transparent",
        borderWidth: 1,
        borderColor: colors.muted,
      }}
    />
  );
}

export function Connectors({ active }: { active: boolean }) {
  const { connectors, skills, error, load } = useCatalog(active);
  const [query, setQuery] = useState("");
  const groups = connectors ? groupConnectors(connectors, query) : [];
  const connected = (connectors || []).filter(
    (c) => statusOf(c) === "connected",
  ).length;
  return (
    <Page
      title="Connectors"
      subtitle="Apps Yggdras can reach once you sign in on the laptop. It reads them only for the task at hand and asks before changing anything."
    >
      <ErrorText message={error} />
      {error && <Button title="Try again" onPress={() => void load()} />}
      {!error && !connectors && <Loading />}
      {connectors && (
        <>
          <Field
            label={`Find an app · ${connected} connected of ${connectors.length}`}
            value={query}
            onChangeText={setQuery}
            autoCorrect={false}
          />
          {groups.map(({ group, items }) => (
            <View key={group} style={{ gap: 8 }}>
              <Text style={[styles.label, { marginBottom: 0, marginLeft: 4 }]}>
                {group}
              </Text>
              <Panel>
                {items.map((c, index) => {
                  const status = statusOf(c);
                  const using = unlockedBy(c, skills || []);
                  return (
                    <View
                      key={c.name}
                      accessible
                      accessibilityLabel={`${c.title}. ${connectorState(c)}.`}
                      style={{
                        gap: 4,
                        paddingTop: index ? 12 : 0,
                        borderTopWidth: index ? 1 : 0,
                        borderTopColor: colors.line,
                        opacity: status === "unavailable" ? 0.65 : 1,
                      }}
                    >
                      <View
                        style={{
                          flexDirection: "row",
                          alignItems: "center",
                          gap: 10,
                        }}
                      >
                        {APP_LOGOS[c.name] ? (
                          <Image
                            source={APP_LOGOS[c.name]}
                            accessibilityIgnoresInvertColors
                            style={{ width: 32, height: 32, borderRadius: 8 }}
                          />
                        ) : (
                          <StatusDot status={status} />
                        )}
                        <Text style={[styles.text, { flex: 1, fontSize: 16 }]}>
                          {c.title}
                        </Text>
                        <Text style={[styles.subtitle, { fontSize: 12 }]}>
                          {connectorState(c)}
                        </Text>
                      </View>
                      {c.description ? (
                        <Text style={[styles.subtitle, { fontSize: 13 }]}>
                          {c.description}
                        </Text>
                      ) : null}
                      {status === "connected" && (
                        <Text style={[styles.subtitle, { fontSize: 12 }]}>
                          {using.length
                            ? `Used by ${using.map(humanize).join(", ")}`
                            : "No skill uses this app yet"}
                        </Text>
                      )}
                    </View>
                  );
                })}
              </Panel>
            </View>
          ))}
          <Text style={[styles.subtitle, { fontSize: 13 }]}>
            Connect, disconnect and switch apps on the laptop, under Connectors.
          </Text>
        </>
      )}
    </Page>
  );
}

export function Skills({ active }: { active: boolean }) {
  const { connectors, skills, error, load } = useCatalog(active);
  const [open, setOpen] = useState<SkillDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  async function show(name: string) {
    setDetailError("");
    try {
      setOpen(await request<SkillDetail>(`yggdras/skills/${name}`));
    } catch (e) {
      setDetailError(failure(e));
    }
  }
  return (
    <Page
      title="Skills"
      subtitle="The know-how Yggdras loads when a task needs it. Skills are reviewed code, so they change through pull requests, not here."
    >
      <ErrorText message={error || detailError} />
      {error && <Button title="Try again" onPress={() => void load()} />}
      {!error && !skills && <Loading />}
      {skills?.map((s) => {
        const linked = connectorsFor(s, connectors || []);
        return (
          <Pressable
            key={s.name}
            accessibilityRole="button"
            accessibilityLabel={`Open ${humanize(s.name)}`}
            onPress={() => void show(s.name)}
            style={({ pressed }) => ({ opacity: pressed ? 0.8 : 1 })}
          >
            <Panel>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.text, { fontSize: 17 }]}>
                    {humanize(s.name)}
                  </Text>
                  <Text style={[styles.subtitle, { fontSize: 12 }]}>
                    {s.name}
                  </Text>
                </View>
                <Text style={{ color: colors.muted, fontSize: 20 }}>›</Text>
              </View>
              <Text style={styles.subtitle}>{s.description}</Text>
              <View style={styles.row}>
                {s.domains.map((d) => (
                  <Tag key={d} label={d} />
                ))}
                {linked.map((t) => (
                  <Tag key={t} label={`${t} connector`} />
                ))}
              </View>
            </Panel>
          </Pressable>
        );
      })}
      <Sheet
        visible={!!open}
        title={open ? humanize(open.name) : "Skill"}
        onClose={() => setOpen(null)}
      >
        {open && (
          <>
            <Text style={styles.subtitle}>{open.description}</Text>
            <View style={styles.row}>
              {open.domains.map((d) => (
                <Tag key={d} label={d} />
              ))}
            </View>
            <Panel>
              <Text style={styles.label}>Instructions</Text>
              <Text
                selectable
                style={[styles.text, { fontSize: 14, lineHeight: 22 }]}
              >
                {open.instructions}
              </Text>
            </Panel>
          </>
        )}
      </Sheet>
    </Page>
  );
}
