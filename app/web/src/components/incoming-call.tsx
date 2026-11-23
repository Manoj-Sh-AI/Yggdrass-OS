"use client";
import {
  analyserFor,
  type OrbState,
  rms,
  VoiceOrb,
} from "@/features/voice/orb";
import { useEffect, useRef, useState } from "react";
import { ApiError, applicationApi } from "@/lib/api";
import { startRingtone, unlockOnFirstGesture } from "@/lib/ringtone";
import { Icon, Modal } from "./ui";
type Call = {
  id: string;
  state: string;
  version: number;
  expires_at: string;
  answered_by: string;
  simulated: boolean;
  reason?: string;
};
type Access = Call & { url: string; token: string };
function identity() {
  const prior = sessionStorage.getItem("yggdras.window");
  if (prior) return prior;
  const id = "web-" + crypto.randomUUID();
  sessionStorage.setItem("yggdras.window", id);
  return id;
}
/** The shared durable call service owns records; the media SDK owns connection truth. */
export function IncomingCall() {
  const [ringing, setRinging] = useState<Call | null>(null);
  const [active, setActive] = useState<Call | null>(null);
  const [recoverable, setRecoverable] = useState<Call | null>(null);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [muted, setMuted] = useState(false);
  const current = useRef<Call | null>(null);
  const room = useRef<import("livekit-client").Room | null>(null);
  const audio = useRef<HTMLMediaElement[]>([]);
  // Voice orb (Phase F): one analyser on the mic, one on Yggdras's voice.
  const audioContext = useRef<AudioContext | null>(null);
  const [mic, setMic] = useState<AnalyserNode | null>(null);
  const [voice, setVoice] = useState<AnalyserNode | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const analyse = (stream: MediaStream) => {
    audioContext.current ??= new AudioContext();
    return analyserFor(audioContext.current, stream);
  };
  const keys = useRef(new Map<string, string>());
  // Stops the ringtone the moment Answer or Decline is pressed, before the server replies.
  const silence = useRef<() => void>(() => {});
  async function command<T>(path: string, data: object = {}) {
    const fingerprint = JSON.stringify([path, data]);
    const key = keys.current.get(fingerprint) || crypto.randomUUID();
    keys.current.set(fingerprint, key);
    const result = await applicationApi<T>("calls" + path, {
      method: "POST",
      body: JSON.stringify({ key, device: identity(), ...data }),
    });
    keys.current.delete(fingerprint);
    return result;
  }
  async function closeAudio() {
    const previous = room.current;
    room.current = null;
    previous?.removeAllListeners();
    await previous?.disconnect();
    for (const element of audio.current) {
      element.pause();
      element.remove();
    }
    audio.current = [];
    setMic(null);
    setVoice(null);
    setSpeaking(false);
    await audioContext.current?.close().catch(() => {});
    audioContext.current = null;
  }
  async function refresh() {
    const result = await applicationApi<{
      calls: Call[];
      capabilities: { voice_ready: boolean };
    }>("calls");
    setReady(result.capabilities.voice_ready);
    setRinging(
      result.calls.find(
        (c) => c.state === "ringing" && Date.parse(c.expires_at) > Date.now(),
      ) || null,
    );
    if (current.current) {
      const next = result.calls.find((c) => c.id === current.current!.id);
      if (!next || next.state !== "answered") {
        current.current = null;
        setActive(null);
        await closeAudio();
      } else {
        current.current = next;
        setActive(next);
      }
    }
  }
  async function report(state: string) {
    setStatus(state);
    if (
      !current.current ||
      !["connected", "reconnecting", "failed", "ended"].includes(state)
    )
      return;
    const call = current.current;
    try {
      const next = await command<Call>(`/${call.id}/media`, {
        state,
        version: call.version,
      });
      current.current = next;
      setActive(next);
    } catch {
      await refresh();
    }
  }
  async function join(path: string) {
    if (busy) return;
    silence.current();
    setBusy(true);
    setError("");
    try {
      const access = await command<Access>(path);
      current.current = access;
      setActive(access);
      setRinging(null);
      if (access.simulated) {
        setStatus("Simulation · no microphone or paid services");
        return;
      }
      if (!access.url.startsWith("wss://"))
        throw new Error("A secure voice connection is required.");
      const { Room, RoomEvent, ConnectionState, Track } =
        await import("livekit-client");
      const connected = new Room();
      room.current = connected;
      const check = () => {
        if (
          connected.state === ConnectionState.Connected &&
          [...connected.remoteParticipants.values()].some((p) => p.isAgent) &&
          connected.localParticipant.isMicrophoneEnabled
        )
          void report("connected");
        else setStatus("Waiting for Yggdras…");
      };
      connected.on(RoomEvent.ParticipantConnected, check);
      connected.on(RoomEvent.Reconnecting, () => void report("reconnecting"));
      connected.on(RoomEvent.Reconnected, check);
      connected.on(RoomEvent.Disconnected, () => void report("ended"));
      connected.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const element = track.attach();
          audio.current.push(element);
          document.body.appendChild(element);
          setVoice(analyse(new MediaStream([track.mediaStreamTrack])));
        }
      });
      setStatus("Connecting…");
      await connected.connect(access.url, access.token);
      await connected.localParticipant.setMicrophoneEnabled(true);
      const local = connected.localParticipant.getTrackPublication(
        Track.Source.Microphone,
      )?.track?.mediaStreamTrack;
      if (local) setMic(analyse(new MediaStream([local])));
      check();
    } catch (failure) {
      setRinging(null);
      setError(
        failure instanceof ApiError
          ? failure.status === 409 && path.endsWith("/answer")
            ? ""
            : failure.message
          : "Voice could not connect. Check microphone permission and try again.",
      );
      if (current.current) await report("failed");
      await closeAudio();
    } finally {
      setBusy(false);
    }
  }
  // Speaking when Yggdras's voice is audible; it is only a state switch, so 10 checks
  // a second are enough (the orb itself animates at its own rate).
  useEffect(() => {
    if (!voice) return;
    const bytes = new Uint8Array(voice.fftSize);
    const timer = setInterval(() => {
      voice.getByteTimeDomainData(bytes);
      setSpeaking(rms(bytes) > 0.02);
    }, 100);
    return () => clearInterval(timer);
  }, [voice]);
  const orbState: OrbState =
    !active || active.simulated
      ? "idle"
      : speaking
        ? "speaking"
        : status === "Connecting…" || status === "Waiting for Yggdras…"
          ? "thinking"
          : muted
            ? "idle"
            : "listening";
  useEffect(() => {
    let mounted = true;
    const source = new EventSource("/api/backend/calls/events");
    source.onmessage = (event) => {
      if (!mounted) return;
      const data = JSON.parse(event.data) as {
        calls: Call[];
        capabilities: { voice_ready: boolean };
      };
      setReady(data.capabilities.voice_ready);
      setRecoverable(
        data.calls.find(
          (c) => c.state === "answered" && c.answered_by === identity(),
        ) || null,
      );
      setRinging(
        data.calls.find(
          (c) => c.state === "ringing" && Date.parse(c.expires_at) > Date.now(),
        ) || null,
      );
      if (current.current) {
        const next = data.calls.find((c) => c.id === current.current!.id);
        if (!next || next.state !== "answered") {
          current.current = null;
          setActive(null);
          void closeAudio();
        } else {
          current.current = next;
          setActive(next);
        }
      }
    };
    source.addEventListener("expired", () => {
      setReady(false);
      source.close();
      void closeAudio();
      setActive(null);
    });
    source.onerror = () => {
      if (current.current) setStatus("Reconnecting to your application…");
    };
    return () => {
      mounted = false;
      source.close();
      void closeAudio();
    };
  }, []);
  useEffect(() => unlockOnFirstGesture(window), []);
  // Rings until answered, declined, expired (45 s) or answered on another device:
  // each of those clears `ringing`, and the cleanup stops the sound at once.
  useEffect(() => {
    if (!ringing || ringing.simulated) return;
    const stop = startRingtone();
    silence.current = stop;
    return () => {
      stop();
      silence.current = () => {};
    };
  }, [ringing?.id, ringing?.simulated]);
  useEffect(() => {
    if (!ringing) return;
    const timer = setTimeout(
      () => setRinging(null),
      Math.max(0, Date.parse(ringing.expires_at) - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [ringing?.id, ringing?.expires_at]);
  return (
    <>
      {ready && !active && !ringing && (
        <button
          className="ygg-call-button"
          onClick={() =>
            recoverable
              ? void command(`/${recoverable.id}/end`).then(() => {
                  setRecoverable(null);
                  return refresh();
                })
              : void join("")
          }
          disabled={busy}
        >
          {recoverable ? "End previous call" : "Call Yggdras"}
        </button>
      )}
      <Modal
        open={!!ringing}
        onOpenChange={() => {}}
        title="Yggdras"
        description={
          ringing?.simulated
            ? "Silent simulation. No real call."
            : ringing?.reason || "Yggdras check-in"
        }
        preventDismiss
      >
        <div className="call-incoming">
          <span className="call-avatar" aria-hidden="true">
            <Icon name="Sprout" size={34} />
          </span>
          <p className="call-incoming-label">Incoming call</p>
        </div>
        <div className="call-ring-actions">
          <div className="call-action">
            <button
              className="call-round call-decline"
              aria-label="Decline"
              onClick={() => {
                silence.current();
                void command(`/${ringing!.id}/decline`)
                  .then(refresh)
                  .catch(() =>
                    setError("This invitation is no longer active."),
                  );
              }}
            >
              <Icon name="PhoneOff" size={24} />
            </button>
            <span>Decline</span>
          </div>
          <div className="call-action">
            <button
              className="call-round call-answer"
              aria-label="Answer"
              disabled={busy}
              onClick={() => void join(`/${ringing!.id}/answer`)}
            >
              <Icon name="Phone" size={24} />
            </button>
            <span>Answer</span>
          </div>
        </div>
      </Modal>
      {active?.state === "answered" && (
        <div className="ygg-in-call call-bar" role="status">
          <VoiceOrb
            size={36}
            showLabel={false}
            state={orbState}
            analyser={orbState === "speaking" ? voice : mic}
          />
          <span className="call-bar-text">
            <strong>{active.reason || "Yggdras"}</strong>
            <small>{status}</small>
          </span>
          <button
            className="call-round small"
            aria-label={muted ? "Unmute" : "Mute"}
            aria-pressed={muted}
            disabled={active.simulated}
            onClick={() =>
              void room.current?.localParticipant
                .setMicrophoneEnabled(muted)
                .then(() => setMuted(!muted))
                .catch(() => setError("Microphone permission is unavailable."))
            }
          >
            <Icon name={muted ? "MicOff" : "Mic"} size={18} />
          </button>
          <button
            className="call-round small call-decline"
            aria-label="End call"
            onClick={() =>
              void report("ended")
                .then(closeAudio)
                .then(() => {
                  current.current = null;
                  setActive(null);
                })
            }
          >
            <Icon name="PhoneOff" size={18} />
          </button>
        </div>
      )}
      {error && (
        <p className="ygg-error ygg-call-error" role="alert">
          {error}
          <button onClick={() => setError("")}>Dismiss</button>
        </p>
      )}
    </>
  );
}
