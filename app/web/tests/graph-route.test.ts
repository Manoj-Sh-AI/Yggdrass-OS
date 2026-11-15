import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "../src/app/api/graph-viewer/[asset]/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const request = () =>
  new NextRequest("http://localhost/api/graph-viewer/graph.html", {
    headers: { Cookie: "app=session" },
  });
it("protects private graph HTML and injects only the presentation adapter", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response("<html><head></head><body>existing renderer</body></html>", {
        headers: { "content-type": "text/html" },
      }),
    );
  vi.stubGlobal("fetch", fetch);
  vi.stubEnv("YGGDRESS_API_URL", "http://localhost:9999");
  const result = await GET(request(), {
    params: Promise.resolve({ asset: "graph.html" }),
  });
  expect(fetch.mock.calls[0][0]).toBe(
    "http://localhost:9999/v1/graph/assets/graph.html",
  );
  expect(fetch.mock.calls[0][1].headers).toEqual({ Cookie: "app=session" });
  expect(fetch.mock.calls[0][1].redirect).toBe("error");
  expect(result.headers.get("cache-control")).toBe("no-store");
  expect(result.headers.get("content-security-policy")).toContain(
    "connect-src 'none'",
  );
  expect(await result.text()).toContain('src="/graph-embed.js"');
});
it("refuses unknown asset paths before contacting the backend", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const result = await GET(request(), {
    params: Promise.resolve({ asset: "../.env" }),
  });
  expect(result.status).toBe(404);
  expect(fetch).not.toHaveBeenCalled();
});
it("keeps sign-in failures private and preserves binary assets", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("private error", { status: 401 })),
  );
  const denied = await GET(request(), {
    params: Promise.resolve({ asset: "graph.html" }),
  });
  expect(denied.status).toBe(401);
  expect(await denied.text()).not.toContain("private error");
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3]), {
          headers: { "content-type": "font/woff2" },
        }),
      ),
  );
  const font = await GET(request(), {
    params: Promise.resolve({ asset: "inter-latin-400-normal.woff2" }),
  });
  expect(new Uint8Array(await font.arrayBuffer())).toEqual(
    new Uint8Array([1, 2, 3]),
  );
});
