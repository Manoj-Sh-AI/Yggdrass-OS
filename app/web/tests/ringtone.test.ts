import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  RING_VOLUME,
  resetRingtone,
  startRingtone,
  unlockOnFirstGesture,
} from "@/lib/ringtone";

function fakeContext() {
  const ramps: [string, number][] = [];
  const source = {
    buffer: null as unknown,
    loop: false,
    connect: vi.fn((node) => node),
    start: vi.fn(),
    stop: vi.fn(),
  };
  const gain = {
    gain: {
      value: 0,
      setValueAtTime: vi.fn(),
      cancelScheduledValues: vi.fn(),
      exponentialRampToValueAtTime: vi.fn((v: number) => ramps.push(["exp", v])),
      linearRampToValueAtTime: vi.fn((v: number) => ramps.push(["lin", v])),
    },
    connect: vi.fn((node) => node),
  };
  const ctx = {
    state: "running",
    currentTime: 1,
    destination: {},
    resume: vi.fn(() => Promise.resolve()),
    createBufferSource: vi.fn(() => source),
    createGain: vi.fn(() => gain),
  };
  return { ctx: ctx as unknown as AudioContext, source, ramps };
}
const flush = () => new Promise((r) => setTimeout(r, 0));

describe("ringtone", () => {
  beforeEach(() => resetRingtone());

  it("fades in, loops, and stops when told", async () => {
    const { ctx, source, ramps } = fakeContext();
    const stop = startRingtone(
      () => ctx,
      async () => ({}) as AudioBuffer,
    );
    await flush();
    expect(source.loop).toBe(true);
    expect(source.start).toHaveBeenCalled();
    expect(ramps[0]).toEqual(["exp", RING_VOLUME]);
    stop();
    expect(source.stop).toHaveBeenCalled();
    expect(ramps.at(-1)).toEqual(["lin", 0]);
  });

  it("never starts if stopped before the sound loaded", async () => {
    const { ctx, source } = fakeContext();
    const stop = startRingtone(
      () => ctx,
      async () => ({}) as AudioBuffer,
    );
    stop();
    await flush();
    expect(source.start).not.toHaveBeenCalled();
  });

  it("stays silent, without throwing, when the sound cannot load", async () => {
    const { ctx, source } = fakeContext();
    const stop = startRingtone(
      () => ctx,
      () => Promise.reject(new Error("offline")),
    );
    await flush();
    expect(source.start).not.toHaveBeenCalled();
    stop();
  });

  it("unlocks audio on the first gesture and can be removed", () => {
    const { ctx } = fakeContext();
    const listeners = new Map<string, () => void>();
    const target = {
      addEventListener: vi.fn((name: string, fn: () => void) => listeners.set(name, fn)),
      removeEventListener: vi.fn((name: string) => listeners.delete(name)),
    };
    const remove = unlockOnFirstGesture(target as never, () => ctx);
    listeners.get("pointerdown")!();
    expect(ctx.resume).toHaveBeenCalled();
    remove();
    expect(listeners.size).toBe(0);
  });

  it("ships the same chime file as the Android app", () => {
    const web = readFileSync("public/sounds/yggdras_ring.wav");
    const mobile = readFileSync("../mobile/assets/sounds/yggdras_ring.wav");
    expect(web.subarray(0, 4).toString()).toBe("RIFF");
    expect(web.equals(mobile)).toBe(true);
  });
});
