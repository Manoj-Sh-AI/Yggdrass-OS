"use client";
import { useRef, useState } from "react";
import { askYggdras, yggdrasApi, type YggdrasCard } from "@/lib/yggdras-api";
import { ApprovalQueue } from "./yggdras-cards";

type Turn = { role: "user" | "assistant"; content: string; stage?: string };

/** Talk to Yggdras: the reply streams in, and anything risky or worth filing comes back as a
 * card above the conversation, where it can't be missed. */
export function YggdrasPanel() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [cards, setCards] = useState<YggdrasCard[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);

  async function send() {
    const question = text.trim();
    if (!question || busy) return;
    setText("");
    setError("");
    setBusy(true);
    const history = turns.map(({ role, content }) => ({ role, content }));
    setTurns((t) => [...t, { role: "user", content: question }, { role: "assistant", content: "", stage: "thinking" }]);
    abort.current = new AbortController();
    try {
      await askYggdras(
        question,
        history,
        (event) => {
          if ("card" in event) setCards((c) => [event.card, ...c]);
          else if ("delta" in event)
            setTurns((t) => {
              const last = t[t.length - 1];
              return [...t.slice(0, -1), { ...last, content: last.content + event.delta, stage: undefined }];
            });
          else if ("stage" in event)
            setTurns((t) => [...t.slice(0, -1), { ...t[t.length - 1], stage: event.stage }]);
          else if ("error" in event && event.error) setError(event.error);
        },
        abort.current.signal,
      );
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Yggdras is unavailable.");
    } finally {
      setBusy(false);
      yggdrasApi.cards().then(setCards).catch(() => undefined);
    }
  }

  return (
    <section className="ygg-panel" aria-label="Yggdras">
      <ApprovalQueue cards={cards} setCards={setCards} />
      <div className="ygg-turns">
        {turns.map((turn, i) => (
          <p key={i} className={`ygg-turn ygg-${turn.role}`}>
            {turn.content || (turn.stage ? `Yggdras is ${turn.stage === "intake" ? "reading" : turn.stage}…` : "")}
          </p>
        ))}
      </div>
      {error && <p className="ygg-error" role="alert">{error}</p>}
      <form
        className="ygg-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          aria-label="Message Yggdras"
          placeholder="Ask Yggdras, or tell him what's on your mind"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          maxLength={12000}
        />
        <button className="button primary" disabled={busy || !text.trim()}>
          {busy ? "Working…" : "Send"}
        </button>
        {busy && (
          <button type="button" className="button" onClick={() => abort.current?.abort()}>
            Stop
          </button>
        )}
      </form>
    </section>
  );
}
