import { useEffect, useState } from "react";
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StatusBar,
  Text,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { onSessionExpired, restore, session, signIn } from "./src/api";
import { BackgroundJobs } from "./src/background-ui";
import { CallProvider, Calls, useCalls } from "./src/call-ui";
import { useSelfUpdate } from "./src/self-update";
import { Calendar } from "./src/calendar";
import { Connectors, Skills } from "./src/catalogs";
import { Chat } from "./src/chat";
import { Embedded } from "./src/embedded";
import { Scenery } from "./src/scenery";
import { Settings } from "./src/settings";
import { routinePush } from "./src/routine-push";
import { Tasks, Today } from "./src/tasks";
import {
  Button,
  ErrorText,
  Field,
  Loading,
  Page,
  Panel,
  Sheet,
  styles,
  colors,
} from "./src/ui";
import { Workspace } from "./src/workspace";
import { DEV_USB, SERVER_ORIGIN } from "./src/server";

type Tab =
  | "today"
  | "tasks"
  | "calendar"
  | "chat"
  | "more"
  | "notes"
  | "graph"
  | "settings"
  | "calls"
  | "background"
  | "connectors"
  | "skills";
const moreTabs: Tab[] = [
  "notes",
  "graph",
  "connectors",
  "skills",
  "settings",
  "calls",
  "background",
];
/** Native updates install only while no call is ringing or in progress. */
function SelfUpdate() {
  useSelfUpdate(useCalls().callBusy);
  return null;
}
function Application() {
  const [ready, setReady] = useState(false);
  const [reauthenticate, setReauthenticate] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState("");
  const [origin, setOrigin] = useState(SERVER_ORIGIN);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("today");
  const [visited, setVisited] = useState<Tab[]>(["today"]);
  useEffect(
    () =>
      onSessionExpired(() => {
        if (ready) {
          setError(
            "Your session expired. Sign in again; your open drafts are preserved.",
          );
          setReauthenticate(true);
        }
      }),
    [ready],
  );
  useEffect(() => {
    let live = true;
    void restore()
      .then((value) => {
        if (live) setReady(!!value);
      })
      .catch((e) => {
        if (live) {
          setError(e.message);
          setOrigin(session()?.origin || origin);
        }
      })
      .finally(() => {
        if (live) setRestoring(false);
      });
    return () => {
      live = false;
    };
  }, []);
  const selected = (value: Tab) =>
    tab === value || (value === "more" && moreTabs.includes(tab));
  function open(value: Tab) {
    setVisited((all) => (all.includes(value) ? all : [...all, value]));
    setTab(value);
  }
  useEffect(() => {
    if (!ready) return;
    return routinePush.listen(
      () => open("today"),
      (message) => Alert.alert("Reminder response", message),
    );
  }, [ready]);
  async function login() {
    setBusy(true);
    setError("");
    try {
      await signIn(origin, password);
      setPassword("");
      setReauthenticate(false);
      setReady(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }
  if (restoring)
    return (
      <View style={[styles.screen, { justifyContent: "center" }]}>
        <Loading />
      </View>
    );
  if (!ready)
    return (
      <Page title="">
        <View style={{ height: 40 }} />
        <Panel>
          <Image
            source={require("./assets/brand/logo-mark.png")}
            accessibilityIgnoresInvertColors
            style={{ width: 56, height: 56, borderRadius: 14, marginBottom: 6 }}
          />
          <Text style={eyebrow}>YOUR PERSONAL WORKSPACE</Text>
          <Text
            accessibilityRole="header"
            style={[styles.title, { fontSize: 27 }]}
          >
            Welcome to Yggdras
          </Text>
          <Text style={[styles.subtitle, { marginBottom: 6 }]}>
            A little clarity, wherever you are.
          </Text>
          <Field
            label="Application address"
            value={origin}
            onChangeText={setOrigin}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
          <Field
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            textContentType="password"
            autoCapitalize="none"
            onSubmitEditing={() => void login()}
          />
          <ErrorText message={error} />
          <Button
            title={busy ? "Signing in…" : "Sign in"}
            primary
            disabled={busy || !password}
            onPress={() => void login()}
          />
          {session() && (
            <Button
              title="Retry saved connection"
              onPress={() => {
                setError("");
                void restore()
                  .then((value) => setReady(!!value))
                  .catch((e) => setError(e.message));
              }}
            />
          )}
        </Panel>
        <Text style={styles.subtitle}>
          {DEV_USB
            ? "Developer build: http://127.0.0.1:3000 works over USB with adb reverse."
            : "Connects to your hosted Yggdras over HTTPS. Change the address only if it moved."}
        </Text>
      </Page>
    );
  return (
    <Workspace>
      <CallProvider>
        <SelfUpdate />
        <View style={styles.screen}>
          <Sheet
            visible={reauthenticate}
            title="Sign in again"
            onClose={() => setReauthenticate(false)}
          >
            <Text style={styles.subtitle}>Your open drafts stay in place.</Text>
            <Field
              label="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoCapitalize="none"
            />
            <ErrorText message={error} />
            <Button
              title={busy ? "Signing in…" : "Sign in"}
              primary
              disabled={busy || !password}
              onPress={() => void login()}
            />
          </Sheet>
          {visited.map((value) => (
            <View
              key={value}
              style={{ flex: 1, display: value === tab ? "flex" : "none" }}
            >
              {value === "today" && (
                <Today active={tab === value} openNotes={() => open("notes")} />
              )}
              {value === "tasks" && <Tasks active={tab === value} />}
              {value === "calendar" && <Calendar active={tab === value} />}
              {value === "chat" && <Chat active={tab === value} />}
              {value === "calls" && <Calls />}
              {value === "connectors" && <Connectors active={tab === value} />}
              {value === "skills" && <Skills active={tab === value} />}
              {value === "background" && (
                <BackgroundJobs active={tab === value} />
              )}
              {(value === "notes" || value === "graph") && (
                <Embedded view={value} active={tab === value} />
              )}
              {value === "settings" && (
                <Settings
                  active={tab === value}
                  onLogout={() => {
                    setReady(false);
                    setTab("today");
                    setVisited(["today"]);
                  }}
                />
              )}
              {value === "more" && (
                <Page title="Your workspace">
                  <Panel>
                    {(
                      [
                        ["notes", "Notes", "Your brain, note by note"],
                        ["graph", "Graph", "How your notes connect"],
                        [
                          "connectors",
                          "Connectors",
                          "Services Yggdras can reach",
                        ],
                        ["skills", "Skills", "What Yggdras knows how to do"],
                        ["calls", "Calls", "Talk with Yggdras"],
                        [
                          "background",
                          "Background jobs",
                          "Work running for you",
                        ],
                        ["settings", "Settings", "Account and preferences"],
                      ] as const
                    ).map(([value, label, hint], index) => (
                      <Pressable
                        key={value}
                        accessibilityRole="button"
                        accessibilityLabel={label}
                        onPress={() => open(value)}
                        style={({ pressed }) => ({
                          flexDirection: "row",
                          alignItems: "center",
                          minHeight: 56,
                          paddingVertical: 8,
                          borderTopWidth: index ? 1 : 0,
                          borderTopColor: colors.line,
                          opacity: pressed ? 0.7 : 1,
                        })}
                      >
                        <View style={{ flex: 1 }}>
                          <Text style={styles.text}>{label}</Text>
                          <Text style={[styles.subtitle, { fontSize: 12 }]}>
                            {hint}
                          </Text>
                        </View>
                        <Text style={{ color: colors.muted, fontSize: 20 }}>
                          ›
                        </Text>
                      </Pressable>
                    ))}
                  </Panel>
                </Page>
              )}
            </View>
          ))}
          <View
            accessibilityRole="tablist"
            style={{
              flexDirection: "row",
              marginHorizontal: 12,
              marginBottom: 10,
              marginTop: 4,
              padding: 4,
              borderRadius: 20,
              borderWidth: 1,
              borderColor: colors.glassBorder,
              backgroundColor: colors.glass,
            }}
          >
            {(["today", "tasks", "calendar", "chat", "more"] as const).map(
              (value) => (
                <Pressable
                  key={value}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: selected(value) }}
                  onPress={() => open(value)}
                  style={({ pressed }) => ({
                    flex: 1,
                    minHeight: 48,
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: 16,
                    backgroundColor: selected(value)
                      ? "rgba(255, 255, 255, 0.1)"
                      : "transparent",
                    opacity: pressed ? 0.7 : 1,
                  })}
                >
                  <Text
                    style={{
                      fontSize: 13,
                      fontWeight: selected(value) ? "600" : "400",
                      color: selected(value) ? colors.text : colors.muted,
                    }}
                  >
                    {value[0].toUpperCase() + value.slice(1)}
                  </Text>
                </Pressable>
              ),
            )}
          </View>
        </View>
      </CallProvider>
    </Workspace>
  );
}
const eyebrow = {
  fontSize: 10,
  letterSpacing: 1.6,
  fontWeight: "600" as const,
  color: colors.muted,
};
export default function App() {
  return (
    <SafeAreaProvider>
      <View style={styles.root}>
        <Scenery />
        <SafeAreaView style={styles.screen}>
          <StatusBar
            barStyle="light-content"
            translucent
            backgroundColor="transparent"
          />
          <KeyboardAvoidingView
            style={{ flex: 1 }}
            behavior={Platform.OS === "ios" ? "padding" : undefined}
          >
            <Application />
          </KeyboardAvoidingView>
        </SafeAreaView>
      </View>
    </SafeAreaProvider>
  );
}
