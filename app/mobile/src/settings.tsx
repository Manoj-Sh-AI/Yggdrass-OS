import { useState } from "react";
import { Alert, Text, View } from "react-native";
import { PlanningLibrary } from "./planning-library";
import { api, session } from "./api";
import { dayKey } from "./dates";
import { Button, ErrorText, Field, Page, Panel, styles } from "./ui";
import { usePlanning, useWorkspace } from "./workspace";
import { AppUpdates } from "./updates";

export function Settings({
  active,
  onLogout,
}: {
  active: boolean;
  onLogout: () => void;
}) {
  const { timezone, setTimezone } = useWorkspace();
  const [zone, setZone] = useState(timezone);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { snapshot, changed } = usePlanning(
    dayKey(new Date(), timezone).slice(0, 7),
    active,
  );
  async function saveZone() {
    try {
      new Intl.DateTimeFormat("en", { timeZone: zone }).format();
      await setTimezone(zone);
      setError("");
    } catch {
      setError("Choose a named timezone, such as Europe/Berlin.");
    }
  }
  async function logout() {
    setBusy(true);
    setError("");
    try {
      await api.logout();
      onLogout();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not sign out. Reconnect and retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function ensure() {
    setBusy(true);
    try {
      const day = dayKey(new Date(), timezone);
      await api.plan("ensure", { start: day, end: day, timezone });
      changed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not prepare routines.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page
      title="Settings"
      subtitle="A quiet workspace, connected to your application."
    >
      <Panel>
        <Text style={styles.label}>Connected application</Text>
        <Text selectable style={styles.text}>
          {session()?.origin}
        </Text>
        <Text style={styles.subtitle}>
          Changes use the same records as your website and desktop app. Notes
          stay on your PC; the phone accesses them through its application API.
        </Text>
      </Panel>
      <Panel>
        <Field
          label="Timezone"
          value={zone}
          onChangeText={setZone}
          autoCapitalize="none"
        />
        <Button title="Save timezone" onPress={() => void saveZone()} />
      </Panel>
      <PlanningLibrary snapshot={snapshot} changed={changed} />
      <AppUpdates />
      <Panel>
        <Button
          title="Prepare today’s routines"
          disabled={busy}
          onPress={() => void ensure()}
        />
      </Panel>
      <Panel>
        <Text style={styles.text}>Calls and notifications</Text>
        <Text style={styles.subtitle}>
          Live calling and Android push need your LiveKit and Firebase setup. No
          background ringing or voice connection is claimed before that setup is
          verified.
        </Text>
        <Text style={styles.subtitle}>
          iPhone calls are deferred. Notification permission will be requested
          only when you choose to enable a configured service.
        </Text>
      </Panel>
      <Panel>
        <Text style={styles.text}>Privacy</Text>
        <Text style={styles.subtitle}>
          Notes and Graph follow your account’s privacy settings. Sensitive
          details require Show; voice excludes sensitive notes. Database, Brain
          and model credentials remain on your server. The phone stores its own
          revocable sign-in token securely.
        </Text>
      </Panel>
      <ErrorText message={error} />
      <Button
        title="Sign out"
        disabled={busy}
        onPress={() =>
          Alert.alert(
            "Sign out?",
            "This revokes the phone session. Reconnect to sign in again.",
            [
              { text: "Stay signed in", style: "cancel" },
              { text: "Sign out", onPress: () => void logout() },
            ],
          )
        }
      />
    </Page>
  );
}
