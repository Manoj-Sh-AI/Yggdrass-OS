import { useEffect, useState } from "react";
import { Alert, AppState, Text, View } from "react-native";
import { randomUUID } from "expo-crypto";
import { request } from "./api";
import { Button, ErrorText, Page, Panel, styles } from "./ui";
type Run = {
  id: string;
  version: number;
  label: string;
  state: string;
  elapsed_seconds: number;
  cancellation_requested_at: string | null;
};
export function BackgroundJobs({ active }: { active: boolean }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  async function refresh() {
    try {
      const value = await request<{ runs: Run[] }>(
        "application/background?limit=40",
      );
      setRuns(value.runs);
      setError("");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not load background jobs.",
      );
    } finally {
      setLoaded(true);
    }
  }
  useEffect(() => {
    if (!active) return;
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === "active") void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [active]);
  async function cancel(run: Run) {
    setBusy(true);
    try {
      await request("application/background/cancel", {
        method: "POST",
        body: JSON.stringify({
          key: randomUUID(),
          id: run.id,
          version: run.version,
        }),
      });
      await refresh();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "The job changed. Refresh before canceling.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page
      title="Background jobs"
      subtitle="These clocks measure unattended work, not your focus time."
    >
      <Button title="Refresh background jobs" onPress={() => void refresh()} />
      <ErrorText message={error} />
      {loaded && !runs.length && (
        <Panel>
          <Text style={styles.text}>No background jobs yet.</Text>
        </Panel>
      )}
      {runs.map((run) => (
        <Panel key={run.id}>
          <Text style={styles.text}>{run.label}</Text>
          <Text style={styles.subtitle}>
            {run.state} · {Math.floor(run.elapsed_seconds / 60)} min elapsed
          </Text>
          {["queued", "running"].includes(run.state) && (
            <Button
              title={
                run.cancellation_requested_at
                  ? "Cancellation requested"
                  : "Request cancellation"
              }
              disabled={busy || !!run.cancellation_requested_at}
              onPress={() =>
                Alert.alert(
                  "Cancel this job?",
                  "The executor will receive a cancellation request. It may need time to stop safely.",
                  [
                    { text: "Keep running", style: "cancel" },
                    {
                      text: "Request cancellation",
                      onPress: () => void cancel(run),
                    },
                  ],
                )
              }
            />
          )}
        </Panel>
      ))}
    </Page>
  );
}
