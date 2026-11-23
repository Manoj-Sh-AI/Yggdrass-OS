// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { animates, follow, ORB, rms, STATE_TEXT, VoiceOrb } from "@/features/voice/orb";

let rafCalls = 0;
beforeEach(() => {
  rafCalls = 0;
  vi.stubGlobal("requestAnimationFrame", () => ++rafCalls);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    setTransform() {}, clearRect() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
  })) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.motion;
});
const motion = (reduce: boolean) =>
  vi.stubGlobal("matchMedia", () => ({ matches: reduce, addEventListener() {}, removeEventListener() {} }));

describe("loudness", () => {
  it("is 0 for silence (128) and grows with swing", () => {
    expect(rms(new Uint8Array(512).fill(128))).toBe(0);
    expect(rms(Uint8Array.from({ length: 512 }, (_, i) => (i % 2 ? 0 : 255)))).toBeGreaterThan(0.95);
  });
  it("snaps up and settles down (asymmetric envelope)", () => {
    expect(follow(0, 1)).toBe(ORB.attack);
    expect(follow(1, 0)).toBeCloseTo(1 - ORB.release);
  });
});

describe("states", () => {
  it("the loop runs only when not idle and motion is allowed", () => {
    expect(animates("idle", false)).toBe(false);
    expect(animates("listening", true)).toBe(false);
    expect(animates("thinking", false)).toBe(true);
  });
  it("announces each state as text (never colour or motion alone)", () => {
    motion(false);
    for (const state of ["idle", "listening", "thinking", "speaking"] as const) {
      const { unmount } = render(<VoiceOrb state={state} />);
      expect(screen.getByText(STATE_TEXT[state]).getAttribute("aria-live")).toBe("polite");
      unmount();
    }
  });
  it("idle draws one still frame and starts no loop", () => {
    motion(false);
    render(<VoiceOrb state="idle" />);
    expect(rafCalls).toBe(0);
  });
  it("listening starts the loop; reduced motion (OS or app setting) never does", () => {
    motion(false);
    const { unmount } = render(<VoiceOrb state="listening" />);
    expect(rafCalls).toBe(1);
    unmount();
    rafCalls = 0;
    motion(true);
    render(<VoiceOrb state="thinking" />);
    expect(rafCalls).toBe(0);
    cleanup();
    motion(false);
    document.documentElement.dataset.motion = "reduced";
    render(<VoiceOrb state="speaking" />);
    expect(rafCalls).toBe(0);
  });
});
