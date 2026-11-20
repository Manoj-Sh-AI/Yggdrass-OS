import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AppState, Linking, Switch, Text, View } from "react-native";
import {
  callApi,
  callCommand,
  type Call,
  type CallPreferences,
  type CallSnapshot,
} from "./call-api";
import { VoiceTransport, type Access } from "./voice-transport";
import { Button, ErrorText, Field, Page, Panel, Sheet, styles } from "./ui";
import { VoiceReviews } from "./voice-reviews";
import { CallScreen } from "./call-screen";
import { MobileError, onSessionExpired, onSessionChanged, session } from "./api";
import { ringer } from "./calls";

type Context = {
  snapshot: CallSnapshot | null;
  error: string;
  refresh: () => Promise<void>;
  start: () => Promise<void>;
  state: string;
  busy: boolean;
};
const Context = createContext<Context | null>(null);
export const useCalls = () => useContext(Context)!;
export function CallProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<CallSnapshot | null>(null);
  const [ringing, setRinging] = useState<Call | null>(null);
  const [active, setActive] = useState<Call | null>(null);
  const current = useRef<Call | null>(null);
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [busy, setBusy] = useState(false);
  const [muted, setMuted] = useState(false);
  const [speaker, setSpeaker] = useState(false);
  const transport = useRef(new VoiceTransport());
  const live = useRef(true);
  // When the open call was answered, for the call screen's timer.
  const answeredAt = useRef<number | null>(null);
  const answeredId = active?.state === "answered" ? active.id : null;
  if (answeredId && answeredAt.current === null)
    answeredAt.current = Date.now();
  if (!answeredId) answeredAt.current = null;
  const busyRef = useRef(false);
  const reports = useRef(Promise.resolve());
  async function refresh() {
    try {
      const data = await callApi.snapshot();
      if (!live.current) return;
      setSnapshot(data);
      setPollError("");
      setRinging(
        data.calls.find(
          (c) => c.state === "ringing" && Date.parse(c.expires_at) > Date.now(),
        ) || null,
      );
      if (current.current) {
        const next = data.calls.find((c) => c.id === current.current!.id);
        if (!next || next.state !== "answered") {
          await transport.current.close();
          current.current = null;
          setActive(null);
          setState("idle");
        } else {
          current.current = next;
          setActive(next);
        }
      }
    } catch (e) {
      if (live.current)
        setPollError(e instanceof Error ? e.message : "Calls are unavailable.");
    }
  }
  function report(value: string) {
    setState(value);
    const task = reports.current
      .catch(() => {})
      .then(async () => {
        if (
          !current.current ||
          !["connected", "reconnecting", "failed", "ended"].includes(value)
        )
          return;
        const c = current.current;
        try {
          const next = await callCommand<Call>(`/${c.id}/media`, {
            version: c.version,
            state: value,
          });
          current.current = next;
          setActive(next);
        } catch {
          await refresh();
        }
      });
    reports.current = task;
    return task;
  }
  async function join(path: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const value = await callCommand<Call & Access>(path);
      current.current = value;
      setActive(value);
      setRinging(null);
      await ringer.stop(value.id);
      await transport.current.connect(value, (s) => {
        void report(s);
      });
    } catch (e) {
      setError(
        e instanceof MobileError && e.status === 409 && path.endsWith("/answer")
          ? ""
          : e instanceof Error
            ? e.message
            : "Could not connect.",
      );
      if (current.current) await report("failed");
    } finally {
      busyRef.current = false;
      setBusy(false);
      await refresh();
    }
  }
  useEffect(() => {
    live.current = true;
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === "active") void refresh();
    }, 2500);
    const app = AppState.addEventListener("change", (value) => {
      if (value === "active") void refresh();
    });
    async function link(url: string | null) {
      const match = url?.match(
        /^yggdras:\/\/calls\/([a-f0-9-]{36})\?action=(answer|decline)$/i,
      );
      if (!match) return;
      try {
        const data = await callApi.snapshot();
        const call = data.calls.find((c) => c.id === match[1]);
        if (
          !call ||
          call.state !== "ringing" ||
          Date.parse(call.expires_at) <= Date.now()
        ) {
          await ringer.stop(match[1]);
          return;
        }
        if (match[2] === "answer") await join(`/${call.id}/answer`);
        else {
          await callCommand(`/${call.id}/decline`);
          await ringer.stop(call.id);
          await refresh();
        }
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "This call is no longer available.",
        );
      }
    }
    const links = Linking.addEventListener("url", (e) => {
      void link(e.url);
    });
    void Linking.getInitialURL().then(link);
    const expired = onSessionExpired(() => {
      void transport.current.close();
      current.current = null;
      setActive(null);
      setRinging(null);
      setState("idle");
    });
    const changed = onSessionChanged(() => {
      void ringer.reconcile().catch(() => {});
      void refresh();
    });
    const stop = ringer.listen((url) => {
      if (url) void link(url);
      else void refresh();
    });
    return () => {
      live.current = false;
      clearInterval(timer);
      app.remove();
      links.remove();
      stop();
      expired();
      changed();
      void transport.current.close();
    };
  }, []);
  useEffect(() => {
    if (!ringing) return;
    // Rings until answered, declined, expired or answered on another device: each of
    // those clears `ringing`, and the cleanup stops the chime and the notification.
    if (!ringing.simulated) ringer.ringInApp(ringing.id, ringing.expires_at);
    const timer = setTimeout(
      () => setRinging(null),
      Math.max(0, Date.parse(ringing.expires_at) - Date.now()),
    );
    return () => {
      clearTimeout(timer);
      void ringer.stop(ringing.id).catch(() => {});
    };
  }, [ringing?.id, ringing?.expires_at]);
  useEffect(() => {
    // The call (and only the call screen) may show over the lock screen while it is answered.
    if (!answeredId) {
      ringer.overLockScreen(false);
      return;
    }
    ringer.overLockScreen(true);
    return () => ringer.overLockScreen(false);
  }, [answeredId]);
  async function end() {
    await report("ended");
    await transport.current.close();
    current.current = null;
    setActive(null);
    setState("idle");
    await refresh();
  }
  return (
    <Context.Provider
      value={{
        snapshot,
        error: error || pollError,
        refresh,
        start: () => join(""),
        state,
        busy,
      }}
    >
      {children}
      <Sheet
        visible={!!error && !ringing && active?.state !== "answered"}
        title="Call interrupted"
        onClose={() => setError("")}
      >
        <ErrorText message={error} />
        <Button title="Dismiss" onPress={() => setError("")} />
      </Sheet>
      <CallScreen
        visible={!!ringing}
        heading="INCOMING CALL"
        reason={
          ringing?.simulated
            ? "Silent simulation · no live voice"
            : ringing?.reason || "Yggdras check-in"
        }
        status="Ringing"
        error={error}
        controls={[
          {
            label: "Decline",
            glyph: "✕",
            tone: "end",
            onPress: () =>
              void callCommand(`/${ringing!.id}/decline`)
                .then(() => ringer.stop(ringing!.id))
                .then(refresh),
          },
          {
            label: "Answer",
            glyph: "✓",
            tone: "answer",
            disabled: busy,
            onPress: () => void join(`/${ringing!.id}/answer`),
          },
        ]}
      />
      <CallScreen
        visible={!ringing && !!active && active.state === "answered"}
        heading="CALL"
        reason={active?.reason || "Yggdras"}
        status={
          state === "simulated"
            ? "Simulation · no microphone or paid services"
            : state.replace(/_/g, " ")
        }
        since={answeredAt.current ?? undefined}
        error={error}
        controls={[
          {
            label: muted ? "Unmute" : "Mute",
            glyph: "⦸",
            active: muted,
            disabled: state === "simulated",
            onPress: () =>
              void transport.current
                .mute(!muted)
                .then(() => setMuted(!muted))
                .catch(() => setError("Microphone could not be changed.")),
          },
          {
            label: speaker ? "Speaker" : "Earpiece",
            glyph: ")))",
            active: speaker,
            disabled: state === "simulated",
            onPress: () =>
              void transport.current
                .speaker(!speaker)
                .then(() => setSpeaker(!speaker))
                .catch(() => setError("That audio output is unavailable.")),
          },
          {
            label: "End",
            glyph: "✕",
            tone: "end",
            onPress: () => void end(),
          },
        ]}
      />
    </Context.Provider>
  );
}

export function Calls() {
  const { snapshot, error, refresh, start, busy } = useCalls();
  const [preferences, setPreferences] = useState<CallPreferences | null>(null);
  const [localError, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [snooze, setSnooze] = useState("5");
  useEffect(() => {
    void callApi
      .preferences()
      .then(setPreferences)
      .catch((e) => setError(e.message));
  }, []);
  async function save() {
    if (!preferences) return;
    try {
      await callApi.savePreferences(preferences);
      setPreferences(await callApi.preferences());
      setSaved("Call preferences saved.");
      setError("");
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not save. Refresh before trying again.",
      );
    }
  }
  return (
    <Page title="Calls" subtitle="One conversation, on the device you choose.">
      <Panel>
        <Text style={styles.text}>
          {snapshot?.capabilities.voice_ready
            ? snapshot.capabilities.simulated
              ? "Simulation service"
              : "Voice service ready"
            : "Live activation is off"}
        </Text>
        <Text style={styles.subtitle}>
          LiveKit and Firebase must be configured before real calls or remote
          ringing. Your local laptop must stay awake.
        </Text>
        <Button
          title="Call Yggdras"
          primary
          disabled={busy || !snapshot?.capabilities.voice_ready}
          onPress={() => void start()}
        />
        <Button title="Refresh calls" onPress={() => void refresh()} />
      </Panel>
      <Panel>
        <Text style={styles.text}>This phone</Text>
        <SessionNotice expiresAt={session()?.expires_at} />
        <Button
          title="Enable incoming calls"
          disabled={!snapshot?.capabilities.push_ready}
          onPress={() =>
            void ringer
              .register()
              .then(() => setSaved("Phone registered for incoming calls."))
              .catch((e) => setError(e.message))
          }
        />
        <Button
          title="Disable incoming calls"
          onPress={() =>
            void ringer
              .disable()
              .then(() => setSaved("Incoming calls disabled on this phone."))
              .catch((e) => setError(e.message))
          }
        />
        <Button
          title="Android call display settings"
          onPress={() => ringer.fullScreenSettings()}
        />
      </Panel>
      {preferences && (
        <Panel>
          <Text style={styles.text}>Scheduled check-ins</Text>
          {(
            [
              "scheduled",
              "calendar_starts",
              "calendar_ends",
              "routines",
            ] as const
          ).map((key) => (
            <View key={key} style={styles.row}>
              <Text style={styles.text}>
                {
                  {
                    scheduled: "Scheduled calls",
                    calendar_starts: "Calendar starts",
                    calendar_ends: "Calendar ends",
                    routines: "Routine times",
                  }[key]
                }
              </Text>
              <Switch
                accessibilityLabel={key}
                value={preferences[key]}
                onValueChange={(v) =>
                  setPreferences((p) => p && { ...p, [key]: v })
                }
              />
            </View>
          ))}
          <Field
            label="Call timezone"
            value={preferences.timezone}
            onChangeText={(v) =>
              setPreferences((p) => p && { ...p, timezone: v })
            }
          />
          <Field
            label="Quiet hours start (HH:mm)"
            value={preferences.quiet_start}
            onChangeText={(v) =>
              setPreferences((p) => p && { ...p, quiet_start: v })
            }
          />
          <Field
            label="Quiet hours end (HH:mm)"
            value={preferences.quiet_end}
            onChangeText={(v) =>
              setPreferences((p) => p && { ...p, quiet_end: v })
            }
          />
          <Button title="Save call preferences" onPress={() => void save()} />
          <Button
            title="Reload call preferences"
            onPress={() =>
              void callApi
                .preferences()
                .then(setPreferences)
                .catch((e) => setError(e.message))
            }
          />
          <Field
            label="Call me in minutes"
            value={snooze}
            onChangeText={setSnooze}
            keyboardType="number-pad"
          />
          <Button
            title="Schedule check-in"
            onPress={() =>
              void callApi
                .schedule({ minutes: Number(snooze) })
                .then(() =>
                  setSaved(
                    "Check-in saved. Delivery waits for live activation.",
                  ),
                )
                .catch((e) => setError(e.message))
            }
          />
        </Panel>
      )}
      <ErrorText message={error || localError} />
      {saved && (
        <Text accessibilityLiveRegion="polite" style={styles.subtitle}>
          {saved}
        </Text>
      )}
      {snapshot?.calls
        .filter((c) => c.state === "answered")
        .map((c) => (
          <Button
            key={c.id}
            title="End active call"
            onPress={() =>
              void callCommand(`/${c.id}/end`)
                .then(refresh)
                .catch((e) => setError(e.message))
            }
          />
        ))}
      <VoiceReviews />
      <Panel>
        <Text style={styles.text}>Recent calls</Text>
        {!snapshot?.calls.length && (
          <Text style={styles.subtitle}>No calls yet.</Text>
        )}
        {snapshot?.calls.map((c) => (
          <View key={c.id}>
            <Text style={styles.text}>
              {c.state}
              {c.simulated ? " · simulation" : ""}
            </Text>
            <Text style={styles.subtitle}>
              {new Date(c.created_at).toLocaleString()}
            </Text>
            {!!c.summary && <Text style={styles.subtitle}>{c.summary}</Text>}
          </View>
        ))}
      </Panel>
    </Page>
  );
}

/**
 * The phone only rings while its sign-in is valid (the backend stops pushing to a
 * device whose session expired), so say plainly until when that is.
 */
export function SessionNotice({
  expiresAt,
  now = Date.now(),
}: {
  expiresAt?: string;
  now?: number;
}) {
  const at = expiresAt ? Date.parse(expiresAt) : NaN;
  if (!Number.isFinite(at)) return null;
  const when = new Date(at).toLocaleString(undefined, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  });
  return (
    <Text style={styles.subtitle}>
      {at <= now
        ? "Your sign-in on this phone has expired, so it will not ring. Sign in again."
        : `Rings this phone until ${when}, when your sign-in ends. Sign in again before then to keep receiving calls.`}
    </Text>
  );
}
