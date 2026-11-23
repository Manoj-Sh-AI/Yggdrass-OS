import { useEffect, useState } from "react";
import { Alert, AppState, Linking, Text } from "react-native";
import * as Application from "expo-application";
import * as Updates from "expo-updates";
import { SERVER_ORIGIN } from "./server";
import {
  availableAndroidRelease,
  nativeUpdater,
  selfUpdater,
  type AndroidRelease,
} from "./self-update";
import { Button, ErrorText, Panel, styles } from "./ui";

export { availableAndroidRelease };

function describeStatus(last: string | null) {
  if (!last) return "";
  if (last.startsWith("updated:")) return `Last update: installed ${last.slice(8)}.`;
  if (last === "needs-tap") return "Last update is waiting for one tap in its notification.";
  if (last === "installing") return "An update is being installed.";
  if (last.startsWith("failed")) return "The last automatic update failed; it will retry.";
  return "";
}

/** Whether Android lets Yggdras install its own updates, plus the last result. */
function AutomaticUpdates() {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [last, setLast] = useState<string | null>(null);
  useEffect(() => {
    if (!nativeUpdater) return;
    const read = () => {
      void nativeUpdater!.canInstall().then(setAllowed).catch(() => {});
      void nativeUpdater!.lastStatus().then(setLast).catch(() => {});
    };
    read();
    // Re-read after returning from Android's "Install unknown apps" page.
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") read();
    });
    return () => subscription.remove();
  }, []);
  if (!nativeUpdater || !selfUpdater) return null;
  return (
    <>
      <Text style={styles.subtitle}>
        {allowed
          ? "Automatic Android updates: on. New versions install while the app is in the background with no call."
          : "Automatic Android updates need permission to install Yggdras updates."}
      </Text>
      {allowed === false && (
        <Button
          title="Allow Yggdras to install updates"
          onPress={() => nativeUpdater!.openInstallSettings()}
        />
      )}
      {describeStatus(last) ? (
        <Text style={styles.subtitle}>{describeStatus(last)}</Text>
      ) : null}
    </>
  );
}

export function AppUpdates() {
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const [native, setNative] = useState<AndroidRelease | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function check() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        `${SERVER_ORIGIN}/api/mobile-updates/android`,
      );
      if (!response.ok) throw new Error();
      setNative(availableAndroidRelease((await response.json()).release));
      void selfUpdater?.check(true);
      if (!Updates.isEnabled) {
        setMessage(
          "Screen updates are available in the installed release app.",
        );
        return;
      }
      const result = await Updates.checkForUpdateAsync();
      if (result.isAvailable) {
        await Updates.fetchUpdateAsync();
        setPending(true);
        setMessage("Screen update downloaded. Reload when you are ready.");
      } else {
        setMessage(
          pending
            ? "Screen update ready to apply."
            : "Your screens are up to date.",
        );
      }
    } catch {
      setError("Could not check for updates. Try again when connected.");
    } finally {
      setBusy(false);
    }
  }
  function reload() {
    Alert.alert(
      "Apply screen update?",
      "Save any drafts and finish your call before reloading.",
      [
        { text: "Later", style: "cancel" },
        {
          text: "Reload",
          onPress: () =>
            void Updates.reloadAsync().catch(() =>
              setError("Could not reload. Close and reopen the app."),
            ),
        },
      ],
    );
  }
  return (
    <Panel>
      <Text style={styles.text}>App updates</Text>
      <Text style={styles.subtitle}>
        Android {Application.nativeApplicationVersion || "development"} · build{" "}
        {Application.nativeBuildVersion || "development"}
      </Text>
      <Text style={styles.subtitle}>
        Screen updates can download and reload here. Android features use a new
        app package and Android's installer.
      </Text>
      <AutomaticUpdates />
      <Button
        title={busy ? "Checking updates…" : "Check for updates"}
        disabled={busy}
        onPress={() => void check()}
      />
      {message ? (
        <Text accessibilityRole="alert" style={styles.subtitle}>
          {message}
        </Text>
      ) : null}
      {pending && (
        <Button title="Reload to apply update" primary onPress={reload} />
      )}
      {native && (
        <Button
          title={`Download Android ${native.version}`}
          onPress={() =>
            void Linking.openURL(native.url).catch(() =>
              setError("Could not open the app download."),
            )
          }
        />
      )}
      <ErrorText message={error} />
    </Panel>
  );
}
