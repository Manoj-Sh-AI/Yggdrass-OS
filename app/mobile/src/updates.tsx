import { useState } from "react";
import { Alert, Linking, Text } from "react-native";
import * as Application from "expo-application";
import * as Updates from "expo-updates";
import { SERVER_ORIGIN } from "./server";
import { Button, ErrorText, Panel, styles } from "./ui";

type AndroidRelease = {
  version: string;
  versionCode: number;
  sha256: string;
  url: string;
};
export function availableAndroidRelease(value: unknown): AndroidRelease | null {
  if (!value || typeof value !== "object") return null;
  const release = value as AndroidRelease;
  if (
    !Number.isSafeInteger(release.versionCode) ||
    release.versionCode < 1 ||
    !/^\d+\.\d+\.\d+$/.test(release.version) ||
    !/^[a-f0-9]{64}$/.test(release.sha256) ||
    release.url !==
      `${SERVER_ORIGIN}/api/mobile-updates/apk/${release.sha256}.apk`
  )
    return null;
  return release.versionCode > Number(Application.nativeBuildVersion || 0)
    ? release
    : null;
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
