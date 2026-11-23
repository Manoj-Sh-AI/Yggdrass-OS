import { describe, expect, it } from "vitest";
import {
  heldHeight,
  sendState,
  showNewlineHint,
  submitModeFor,
} from "@/features/chat/composer/logic";
import { rowsFor } from "@/features/chat/composer/composer";

const base = { empty: true, blockedReason: "", isSending: false, isRunning: false, lastError: "" };

describe("send button: six states (B5)", () => {
  it("is idle with an empty draft and ready with a draft", () => {
    expect(sendState(base)).toBe("idle");
    expect(sendState({ ...base, empty: false })).toBe("ready");
  });
  it("is blocked, with its reason, whatever the draft", () => {
    expect(sendState({ ...base, empty: false, blockedReason: "You're offline." })).toBe("blocked");
  });
  it("stops while sending and while generating", () => {
    expect(sendState({ ...base, empty: false, isSending: true })).toBe("sending");
    expect(sendState({ ...base, isSending: true, isRunning: true })).toBe("generating");
  });
  it("offers retry after a failed run, until a new draft is typed", () => {
    expect(sendState({ ...base, lastError: "No key." })).toBe("error");
    expect(sendState({ ...base, empty: false, lastError: "No key." })).toBe("ready");
  });
});

describe("composer sizing (B4)", () => {
  it("grows freely and shrinks only when the value is empty", () => {
    let held = heldHeight(0, 40, "one line");
    held = heldHeight(held, 64, "a wrapped second line");
    expect(heldHeight(held, 40, "shorter again")).toBe(64); // no flicker mid-sentence
    expect(heldHeight(held, 40, "")).toBe(0); // cleared: shrink
  });
  it("holds the height as whole rows", () => {
    expect(rowsFor(0)).toBe(1);
    expect(rowsFor(12 + 22.4 * 3)).toBe(3);
  });
});

describe("keyboard and hints (B6)", () => {
  it("uses Enter to send except on touch, where Send submits", () => {
    expect(submitModeFor(false)).toBe("enter");
    expect(submitModeFor(true)).toBe("none");
  });
  it("shows the Shift+Enter hint only on first run or first wrap, once", () => {
    expect(showNewlineHint(false, false, false, true)).toBe(true);
    expect(showNewlineHint(false, false, true, false)).toBe(true);
    expect(showNewlineHint(true, false, true, true)).toBe(false);
    expect(showNewlineHint(false, true, true, true)).toBe(false); // touch: no hint
  });
});
