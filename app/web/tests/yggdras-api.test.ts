import { afterEach, describe, expect, it, vi } from "vitest";
import { askYggdras, type YggdrasEvent } from "@/lib/yggdras-api";

function streamOf(chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("askYggdras", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("delivers whole events even when the network splits them", async () => {
    const card = { id: "abc123def456", tool: "offer_brain_fact", title: "File it" };
    const body = [
      `data: {"stage": "intake"}\n\nda`,
      `ta: {"card": ${JSON.stringify(card)}}\n\ndata: {"delta": "Hel`,
      `lo"}\n\ndata: {"done": "r1", "route": "quick"}\n\n`,
    ];
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith("auth/session")
        ? new Response(JSON.stringify({ csrf: "t" }), { status: 200 })
        : new Response(streamOf(body), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: YggdrasEvent[] = [];
    await askYggdras("hi", [], (e) => events.push(e));
    expect(events).toEqual([
      { stage: "intake" },
      { card },
      { delta: "Hello" },
      { done: "r1", route: "quick" },
    ]);
    const [, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Yggdress-CSRF"]).toBe("t");
  });

  it("reports a refused request plainly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("auth/session")
          ? new Response(JSON.stringify({ csrf: "t" }), { status: 200 })
          : new Response(JSON.stringify({ detail: "Sign in to continue." }), { status: 401 }),
      ),
    );
    await expect(askYggdras("hi", [], () => undefined)).rejects.toThrow("Sign in to continue.");
  });
});
