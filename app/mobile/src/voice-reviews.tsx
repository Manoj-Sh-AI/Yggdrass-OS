import { useState } from "react";
import { Text, View } from "react-native";
import { randomUUID } from "expo-crypto";
import { request } from "./api";
import { Button, ErrorText, Sheet, styles } from "./ui";
type Review = {
  id: string;
  version: number;
  payload: {
    operation: string;
    data: Record<string, unknown>;
    explanation: string;
  };
  current: Record<string, unknown> | null;
  blocked: string;
};
export function VoiceReviews() {
  const [open, setOpen] = useState(false);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    try {
      setReviews(await request<Review[]>("calls/reviews"));
      setError("");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not load voice proposals.",
      );
    }
  }
  async function decide(r: Review, decision: "accept" | "dismiss") {
    setBusy(true);
    try {
      await request(`calls/reviews/${r.id}`, {
        method: "POST",
        body: JSON.stringify({
          key: randomUUID(),
          version: r.version,
          decision,
        }),
      });
      await load();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "This proposal changed. Refresh before applying it.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button
        title="Review voice proposals"
        onPress={() => {
          setOpen(true);
          void load();
        }}
      />
      <Sheet
        visible={open}
        title="Voice proposals"
        onClose={() => setOpen(false)}
      >
        <Text style={styles.subtitle}>
          Nothing here is applied until you approve it. Destructive changes
          cannot be undone unless the application explicitly says so.
        </Text>
        <ErrorText message={error} />
        {!reviews.length && (
          <Text style={styles.text}>No voice proposals waiting.</Text>
        )}
        {reviews.map((r) => (
          <View key={r.id} style={{ gap: 12 }}>
            <Text style={styles.text}>{r.payload.operation}</Text>
            <Text style={styles.subtitle}>{r.payload.explanation}</Text>
            {Object.entries(r.payload.data).map(([key, value]) => (
              <Text key={key} selectable style={styles.subtitle}>
                {key}: {JSON.stringify(r.current?.[key] ?? null)} →{" "}
                {JSON.stringify(value)}
              </Text>
            ))}
            {r.payload.operation.endsWith(".remove") ||
            r.payload.operation.endsWith(".cancel") ? (
              <Text style={styles.error}>
                Removal cannot be undone. Current record:{" "}
                {JSON.stringify(r.current)}
              </Text>
            ) : null}
            <ErrorText message={r.blocked} />
            <Button
              title="Approve change"
              primary
              disabled={busy || !!r.blocked}
              onPress={() => void decide(r, "accept")}
            />
            <Button
              title="Reject change"
              disabled={busy}
              onPress={() => void decide(r, "dismiss")}
            />
          </View>
        ))}
        <Button title="Refresh proposals" onPress={() => void load()} />
      </Sheet>
    </>
  );
}
