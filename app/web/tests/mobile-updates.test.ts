import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "../src/app/api/mobile-updates/[...path]/route";

afterEach(() => vi.unstubAllGlobals());
describe("mobile update proxy", () => {
  it("passes runtime and signed manifest headers without forwarding user cookies", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response('{"id":"invented"}', {
          headers: {
            "expo-signature": 'sig="invented"',
            "expo-protocol-version": "1",
            "content-type": "application/expo+json",
          },
        }),
      );
    vi.stubGlobal("fetch", fetch);
    const request = new NextRequest(
      "https://app.test/api/mobile-updates/manifest",
      {
        headers: {
          "expo-platform": "android",
          "expo-runtime-version": "a".repeat(40),
          Cookie: "private-session",
        },
      },
    );
    const response = await GET(request, {
      params: Promise.resolve({ path: ["manifest"] }),
    });
    expect(response.headers.get("expo-signature")).toBe('sig="invented"');
    const headers = fetch.mock.calls[0][1].headers as Headers;
    expect(headers.get("expo-runtime-version")).toBe("a".repeat(40));
    expect(headers.get("cookie")).toBeNull();
  });
  it("preserves the no-update response with an empty body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    const response = await GET(
      new NextRequest("https://app.test/api/mobile-updates/manifest"),
      { params: Promise.resolve({ path: ["manifest"] }) },
    );
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });
  it("rejects unauthenticated publishing and unrecognized download paths", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const publish = new NextRequest(
      "https://app.test/api/mobile-updates/publish",
      { method: "POST" },
    );
    expect(
      (await POST(publish, { params: Promise.resolve({ path: ["publish"] }) }))
        .status,
    ).toBe(401);
    expect(
      (
        await GET(
          new NextRequest("https://app.test/api/mobile-updates/private-key"),
          { params: Promise.resolve({ path: ["private-key"] }) },
        )
      ).status,
    ).toBe(404);
    expect(fetch).not.toHaveBeenCalled();
  });
});
