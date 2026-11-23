"use client";
import { useState } from "react";
import { yggdrasApi, type YggdrasCard } from "@/lib/yggdras-api";

/** One card waiting on Manoj: what changes, exactly, and two big buttons. */
export function ApprovalCard({
  card,
  settled,
}: {
  card: YggdrasCard;
  settled: (id: string, outcome: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [correction, setCorrection] = useState("");
  async function act(kind: "approve" | "reject") {
    setBusy(true);
    setError("");
    try {
      if (kind === "approve") {
        const out = await yggdrasApi.approve(card.id);
        settled(card.id, out.undo ? "approved-undoable" : "approved");
      } else {
        await yggdrasApi.reject(card.id, correction);
        settled(card.id, "rejected");
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <article
      className="ygg-card"
      aria-label={`Waiting for you: ${card.title}`}
      data-offer={card.offer || undefined}
    >
      <header>
        <span className="ygg-card-badge">
          {card.offer ? "Worth filing?" : "Needs your approval"}
        </span>
        <h3>{card.title}</h3>
        {card.reasons.length > 0 && (
          <p className="ygg-card-reasons">Why it waits: {card.reasons.join("; ")}</p>
        )}
      </header>
      {card.old_text !== null && (
        <div className="ygg-diff ygg-old">
          <span>Now</span>
          <p>{card.old_text}</p>
        </div>
      )}
      {card.new_text !== null && (
        <div className="ygg-diff ygg-new">
          <span>{card.old_text !== null ? "After" : "Adds"}</span>
          <p>{card.new_text}</p>
        </div>
      )}
      {(card.links_added.length > 0 || card.links_removed.length > 0) && (
        <p className="ygg-links">
          {card.links_added.length > 0 && <>Links added: {card.links_added.join(", ")}. </>}
          {card.links_removed.length > 0 && <>Links removed: {card.links_removed.join(", ")}.</>}
        </p>
      )}
      {card.warning && (
        <p className="ygg-warning" role="note">
          {card.warning}
        </p>
      )}
      {correcting && (
        <label className="ygg-correction">
          What should Yggdras do differently? (optional)
          <textarea value={correction} onChange={(e) => setCorrection(e.target.value)} maxLength={2000} />
        </label>
      )}
      {error && <p className="ygg-error" role="alert">{error}</p>}
      <div className="ygg-actions">
        <button className="ygg-approve" disabled={busy} onClick={() => void act("approve")}>
          {card.offer ? "File it" : "Approve"}
        </button>
        <button
          className="ygg-reject"
          disabled={busy}
          onClick={() => (correcting ? void act("reject") : setCorrecting(true))}
        >
          {correcting ? "Reject" : "Reject…"}
        </button>
      </div>
    </article>
  );
}

/** Everything waiting on Manoj, first and impossible to miss; Undo for the last action. */
export function ApprovalQueue({
  cards,
  setCards,
}: {
  cards: YggdrasCard[];
  setCards: (update: (cards: YggdrasCard[]) => YggdrasCard[]) => void;
}) {
  const [canUndo, setCanUndo] = useState(false);
  const [note, setNote] = useState("");
  const waiting = cards.filter((c) => c.state === "waiting");
  return (
    <section className="ygg-queue" aria-live="polite" aria-label="Waiting for your approval">
      {waiting.length > 0 && (
        <h2 className="ygg-queue-title">
          {waiting.length} waiting for you
        </h2>
      )}
      {waiting.map((card) => (
        <ApprovalCard
          key={card.id}
          card={card}
          settled={(id, outcome) => {
            setCards((all) => all.map((c) => (c.id === id ? { ...c, state: outcome } : c)));
            setCanUndo(outcome === "approved-undoable");
            setNote(outcome.startsWith("approved") ? "Done." : "Rejected; nothing changed.");
          }}
        />
      ))}
      {(canUndo || note) && (
        <div className="ygg-after">
          {note && <span>{note}</span>}
          {canUndo && (
            <button
              className="button"
              onClick={async () => {
                await yggdrasApi.undo();
                setCanUndo(false);
                setNote("Undone.");
              }}
            >
              Undo
            </button>
          )}
        </div>
      )}
    </section>
  );
}
