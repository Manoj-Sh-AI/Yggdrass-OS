import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api } from "./api";
import { Button, ErrorText, Loading, Panel, Sheet, styles } from "./ui";
import { useWorkspace } from "./workspace";

type Review = Awaited<ReturnType<typeof api.reviews>>["reviews"][number];
export function Reviews({ onClose }: { onClose: () => void }) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const { changed } = useWorkspace();
  async function load() {
    setLoading(true);
    try {
      setReviews((await api.reviews()).reviews);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load changes.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function decide(review: Review, decision: "accept" | "dismiss") {
    setBusy(true);
    setError("");
    try {
      await api.resolve(review.id, review.version, decision);
      setReviews((all) => all.filter((r) => r.id !== review.id));
      changed();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "This proposal changed. Refresh before deciding.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet visible title="Review changes" onClose={onClose}>
      <ErrorText message={error} />
      {loading && <Loading />}
      <Button title="Refresh proposals" onPress={() => void load()} />
      {!loading && !reviews.length && (
        <Text style={styles.subtitle}>
          Nothing is waiting for your approval.
        </Text>
      )}
      {reviews.map((review) => (
        <Panel key={review.id}>
          <Text style={styles.label}>
            {review.agent_id} · {review.payload.operation}
          </Text>
          <Text style={styles.text}>{review.payload.explanation}</Text>
          {review.current && (
            <View>
              <Text style={styles.label}>Now</Text>
              <Text selectable style={styles.text}>
                {JSON.stringify(review.current, null, 2)}
              </Text>
            </View>
          )}
          <Text style={styles.label}>Proposed</Text>
          <Text selectable style={styles.text}>
            {JSON.stringify(review.payload.data, null, 2)}
          </Text>
          {review.payload.operation.endsWith(".remove") && (
            <Text style={styles.error}>
              This removes the item from your active calendar. No Undo is
              offered here.
            </Text>
          )}
          <ErrorText message={review.blocked} />
          <View style={styles.row}>
            <Button
              title="Approve change"
              primary
              disabled={busy || !!review.blocked}
              onPress={() => void decide(review, "accept")}
            />
            <Button
              title="Reject change"
              disabled={busy}
              onPress={() => void decide(review, "dismiss")}
            />
          </View>
        </Panel>
      ))}
    </Sheet>
  );
}
