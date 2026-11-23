import { describe, expect, it } from "vitest";
import { workspaceRetry } from "../src/lib/workspace-retry";

describe("linked-work request recovery", () => {
  it("reuses an uncertain command after remount without storing private text", async () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };
    const first = await workspaceRetry(
      "private note: deadline and personal objective",
      undefined,
      storage,
    );
    const remounted = await workspaceRetry(
      "private note: deadline and personal objective",
      undefined,
      storage,
    );
    expect(remounted.key).toBe(first.key);
    expect(JSON.stringify([...values])).not.toMatch(
      /private|deadline|objective/,
    );
    remounted.complete();
    expect(
      (
        await workspaceRetry(
          "private note: deadline and personal objective",
          undefined,
          storage,
        )
      ).key,
    ).not.toBe(first.key);
  });
  it("keeps independent operations separate and survives unavailable storage", async () => {
    const storage = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {},
      removeItem: () => {},
    };
    const original = await workspaceRetry("request", undefined, storage);
    expect((await workspaceRetry("request", original.key, storage)).key).toBe(
      original.key,
    );
    expect(
      (await workspaceRetry("another request", undefined, storage)).key,
    ).not.toBe(original.key);
    expect(() => original.complete()).not.toThrow();
  });
});
