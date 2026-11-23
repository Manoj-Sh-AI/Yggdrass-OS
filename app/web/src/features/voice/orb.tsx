"use client";
/**
 * The voice orb (UI brief Phase F): one web component shared by every surface; each
 * surface's native window (Windows WebView2, Android overlay) only hosts it.
 *
 * - Four states that differ on two channels each, never colour alone: idle (still,
 *   muted), listening (ring follows the mic), thinking (a rotating arc, linear: "machine
 *   working", amplitude ignored), speaking (ring follows the voice). The state is also
 *   text, announced politely.
 * - Canvas 2D; the animation loop runs ONLY while listening, thinking or speaking, and
 *   never with reduced motion (OS setting or the app's own), which shows a still orb
 *   plus the text. Idle draws once.
 * - Loudness is one number per frame: RMS of time-domain bytes (127/128 = silence) with
 *   a fast-attack, slow-release envelope [proposal]. fftSize 512, smoothing 0.4.
 * - Colours are read from token utilities, never written here.
 *
 * Timings are the brief's [proposal] values, kept in ORB below; none is a product value.
 */
import { useEffect, useRef, useState } from "react";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

export const ORB = {
  fftSize: 512, // [derived] one scalar needs few bins
  smoothing: 0.4, // [proposal] 0.3-0.5; 0.8 (default) lags
  attack: 0.5, // [proposal] envelope: snaps up
  release: 0.08, // [proposal] settles down
  thinkingPeriodMs: 1600, // [proposal] 1.2-2 s, linear
  reactiveFps: 60, // listening/speaking
  calmFps: 30, // thinking
} as const;

export const STATE_TEXT: Record<OrbState, string> = {
  idle: "Ready",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

const STATE_TONE: Record<OrbState, string> = {
  idle: "text-text-3",
  listening: "text-info",
  thinking: "text-warning",
  speaking: "text-success",
};

/** Loudness 0-1 from getByteTimeDomainData bytes. */
export function rms(bytes: ArrayLike<number>): number {
  if (!bytes.length) return 0;
  let sum = 0;
  for (let i = 0; i < bytes.length; i++) {
    const v = (bytes[i] - 128) / 128;
    sum += v * v;
  }
  return Math.min(1, Math.sqrt(sum / bytes.length));
}

/** One envelope step: fast attack, slow release. */
export function follow(level: number, target: number): number {
  return level + (target > level ? ORB.attack : ORB.release) * (target - level);
}

/** Whether the loop may run: never idle, never with reduced motion. */
export function animates(state: OrbState, reduced: boolean): boolean {
  return !reduced && state !== "idle";
}

function prefersReduced(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true ||
    document.documentElement.dataset.motion === "reduced"
  );
}

export function useReducedMotion(): boolean {
  // Read on the first render, so not even one animated frame starts under reduced motion.
  const [reduced, setReduced] = useState(prefersReduced);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () =>
      setReduced(
        query.matches || document.documentElement.dataset.motion === "reduced",
      );
    update();
    query.addEventListener("change", update); // a mid-session OS change is honoured
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-motion"],
    });
    return () => {
      query.removeEventListener("change", update);
      observer.disconnect();
    };
  }, []);
  return reduced;
}

/** An analyser for a mic or voice stream, set up for one loudness number per frame. */
export function analyserFor(
  context: AudioContext,
  stream: MediaStream,
): AnalyserNode {
  const analyser = context.createAnalyser();
  analyser.fftSize = ORB.fftSize;
  analyser.smoothingTimeConstant = ORB.smoothing;
  context.createMediaStreamSource(stream).connect(analyser);
  return analyser;
}

function tokenColor(element: HTMLElement): string {
  return getComputedStyle(element).color || "currentColor";
}

type Props = {
  state: OrbState;
  analyser?: AnalyserNode | null; // mic while listening, the voice while speaking
  size?: number; // CSS pixels
  showLabel?: boolean;
};

export function VoiceOrb({
  state,
  analyser = null,
  size = 56,
  showLabel = true,
}: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const tone = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    el.width = el.height = Math.round(size * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const colour = tone.current ? tokenColor(tone.current) : "currentColor";
    const centre = size / 2;
    const base = size * 0.3;
    const bytes = new Uint8Array(analyser?.fftSize ?? ORB.fftSize);
    let level = 0;
    let frame = 0;
    let last = 0;
    const draw = (time: number) => {
      ctx.clearRect(0, 0, size, size);
      ctx.fillStyle = colour;
      ctx.strokeStyle = colour;
      ctx.globalAlpha = state === "idle" ? 0.55 : 0.9;
      ctx.beginPath();
      ctx.arc(centre, centre, base, 0, Math.PI * 2);
      ctx.fill();
      if (state === "listening" || state === "speaking") {
        if (analyser && !reduced) {
          analyser.getByteTimeDomainData(bytes);
          level = follow(level, rms(bytes) * 3);
        }
        ctx.globalAlpha = 0.45;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centre, centre, base + 3 + level * size * 0.16, 0, Math.PI * 2);
        ctx.stroke();
      } else if (state === "thinking") {
        const turn = reduced
          ? 0
          : ((time % ORB.thinkingPeriodMs) / ORB.thinkingPeriodMs) *
            Math.PI *
            2;
        ctx.globalAlpha = 0.8;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(centre, centre, base + 5, turn, turn + Math.PI * 0.6);
        ctx.stroke();
      }
    };
    if (!animates(state, reduced)) {
      draw(0); // one still frame: idle, or any state under reduced motion
      return;
    }
    const interval =
      1000 / (state === "thinking" ? ORB.calmFps : ORB.reactiveFps);
    const loop = (time: number) => {
      if (time - last >= interval - 1) {
        last = time;
        draw(time);
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [state, analyser, size, reduced]);

  return (
    <span className="inline-flex items-center gap-2" data-orb-state={state}>
      <span
        ref={tone}
        className={`relative inline-grid ${STATE_TONE[state]}`}
        style={{ width: size, height: size }}
      >
        <canvas
          ref={canvas}
          aria-hidden
          style={{ width: size, height: size }}
        />
      </span>
      <span
        aria-live="polite"
        className={showLabel ? "text-xs text-text-2" : "sr-only"}
      >
        {STATE_TEXT[state]}
      </span>
    </span>
  );
}
