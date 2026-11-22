"use client";

import { useEffect, useRef, useState } from "react";

export default function RoutineResponse() {
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const value = location.hash.slice(1);
    if (/^[A-Za-z0-9_-]{32}\.[0-9a-f]{64}$/.test(value)) setToken(value);
    else setMessage("This reminder action is unavailable.");
    // The capability never goes to the page server or referrer.
    history.replaceState(null, "", location.pathname);
  }, []);
  async function respond(action: "started" | "not_yet") {
    setPending(true);
    try {
      const result = await fetch("/api/backend/routine-delivery/respond", {
        method: "POST",
        credentials: "omit",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, action }),
      });
      if (!result.ok) {
        if ([403, 409, 410].includes(result.status)) setToken("");
        throw new Error((await result.json()).detail || "Please try again.");
      }
      setMessage(
        action === "started"
          ? "Started. Your reminder is acknowledged."
          : "Noted. The scheduled check-in stays in place.",
      );
      setToken("");
    } catch (error) {
      setMessage(
        error instanceof TypeError
          ? "Connection unavailable. Try again."
          : String((error as Error).message),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <main
      className="panel"
      style={{ maxWidth: "28rem", margin: "12vh auto", padding: "1.5rem" }}
    >
      <h1>Task reminder</h1>
      {token && (
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            className="primary-button"
            style={{ minHeight: 48 }}
            disabled={pending}
            onClick={() => respond("started")}
          >
            Started
          </button>
          <button
            style={{ minHeight: 48 }}
            disabled={pending}
            onClick={() => respond("not_yet")}
          >
            Not yet
          </button>
        </div>
      )}
      <p role="status">{message}</p>
      <a href="/today">Open Today</a>
    </main>
  );
}
