"use client";
import { useEffect, useRef, useState } from "react";
import { listen, yggdrasApi, type HubEvent, type RoomAccess } from "@/lib/yggdras-api";

/** This window's name for "who answered" (each tab and the desktop window is one device). */
function windowId() {
  try {
    const saved = sessionStorage.getItem("yggdras.window");
    if (saved) return saved;
    const made = `web-${crypto.randomUUID().slice(0, 8)}`;
    sessionStorage.setItem("yggdras.window", made);
    return made;
  } catch {
    return "web";
  }
}

/** A soft two-tone ring made in the page (no audio file), until answered or stopped. */
function ringer() {
  let context: AudioContext | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  const beep = () => {
    if (!context) return;
    for (const [freq, at] of [[660, 0], [880, 0.25]] as const) {
      const osc = context.createOscillator();
      const gain = context.createGain();
      osc.frequency.value = freq;
      gain.gain.value = 0.08;
      osc.connect(gain).connect(context.destination);
      osc.start(context.currentTime + at);
      osc.stop(context.currentTime + at + 0.2);
    }
  };
  return {
    start() {
      try {
        context = new AudioContext();
        beep();
        timer = setInterval(beep, 2000);
      } catch {
        context = null; // autoplay blocked: the screen still rings visibly
      }
    },
    stop() {
      if (timer) clearInterval(timer);
      void context?.close();
      context = null;
      timer = null;
    },
  };
}

type Ringing = { id: string; reason: string };

/** Mounted once in the shell: when Yggdras calls, every open window rings; the first to
 * answer takes the call and the others stop. */
export function IncomingCall() {
  const [ringing, setRinging] = useState<Ringing | null>(null);
  const [room, setRoom] = useState<(RoomAccess & { id: string }) | null>(null);
  const [error, setError] = useState("");
  const ring = useRef(ringer());

  useEffect(() => {
    const stop = listen((event: HubEvent) => {
      if (event.type !== "call") return;
      if (event.state === "ringing") {
        setRinging({ id: event.id, reason: event.reason || "Yggdras is calling" });
        ring.current.start();
      } else {
        ring.current.stop();
        setRinging((current) => (current?.id === event.id ? null : current));
        if (event.state === "ended") setRoom((r) => (r?.id === event.id ? null : r));
      }
    });
    const tone = ring.current;
    return () => {
      stop();
      tone.stop();
    };
  }, []);

  async function answer() {
    if (!ringing) return;
    ring.current.stop();
    try {
      const access = await yggdrasApi.answer(ringing.id, windowId());
      setRoom({ ...access, id: ringing.id });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Another device took the call.");
    }
    setRinging(null);
  }

  async function startCall() {
    try {
      const call = await yggdrasApi.callYggdras();
      setRoom(call);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Yggdras could not be called.");
    }
  }

  return (
    <>
      {ringing && (
        <div className="ygg-ring" role="alertdialog" aria-label="Incoming call from Yggdras">
          <div className="ygg-ring-card">
            <p className="ygg-ring-who">Yggdras</p>
            <p className="ygg-ring-why">{ringing.reason}</p>
            <div className="ygg-ring-actions">
              <button className="ygg-answer" onClick={() => void answer()} autoFocus>
                Answer
              </button>
              <button
                className="ygg-decline"
                onClick={() => {
                  ring.current.stop();
                  void yggdrasApi.decline(ringing.id);
                  setRinging(null);
                }}
              >
                Decline
              </button>
            </div>
          </div>
        </div>
      )}
      {room && (
        <div className="ygg-in-call" role="status">
          <span>
            On a call with Yggdras{room.simulated ? " (simulated: voice keys not set up yet)" : ""}
          </span>
          <button className="ygg-decline" onClick={() => void yggdrasApi.end(room.id).then(() => setRoom(null))}>
            End
          </button>
        </div>
      )}
      {!room && !ringing && (
        <button className="ygg-call-button" onClick={() => void startCall()} aria-label="Call Yggdras">
          Call Yggdras
        </button>
      )}
      {error && (
        <p className="ygg-error ygg-call-error" role="alert" onClick={() => setError("")}>
          {error}
        </p>
      )}
    </>
  );
}
