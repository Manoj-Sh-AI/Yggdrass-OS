import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST as proxyPost } from "@/app/api/backend/[...path]/route";
import { POST as webviewPost } from "@/app/api/mobile-session/route";

const origin = "https://app.example.test";
const token = "a".repeat(43);
beforeEach(() => {
  vi.stubEnv("YGGDRESS_ORIGIN", origin);
  vi.stubEnv("YGGDRESS_API_URL", "http://127.0.0.1:8912");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
describe("Android routine reminder routes", () => {
  it("forwards each reminder route to the application API", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const device = "0b6e7a8c-1f2d-4e3a-9b8c-7d6e5f4a3b2c";
    for (const path of [
      ["routine-delivery", "android", "status"],
      ["routine-delivery", "android", "devices", device],
    ]) {
      const req = new NextRequest(`${origin}/api/backend/${path.join("/")}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const response = await GET(req, { params: Promise.resolve({ path }) });
      expect(response.status).toBe(200);
    }
    const urls = fetchMock.mock.calls.map((c) => (c as unknown as [string])[0]);
    expect(urls).toEqual([
      "http://127.0.0.1:8912/v1/routine-delivery/android/status",
      `http://127.0.0.1:8912/v1/routine-delivery/android/devices/${device}`,
    ]);
  });
  it("still refuses an Android path that is not on the list", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const path = ["routine-delivery", "android", "everything"];
    const req = new NextRequest(`${origin}/api/backend/${path.join("/")}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const response = await GET(req, { params: Promise.resolve({ path }) });
    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("mobile application proxy", () => {
  it("forwards a device bearer to the application API, never the Brain service", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ tasks: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const req = new NextRequest(`${origin}/api/backend/application/tasks`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const response = await GET(req, {
      params: Promise.resolve({ path: ["application", "tasks"] }),
    });
    expect(response.status).toBe(200);
    expect(
      (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[0],
    ).toBe("http://127.0.0.1:8912/v1/application/tasks");
    expect(
      (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers,
    ).toMatchObject({ Authorization: `Bearer ${token}` });
  });
  it("mobile sign-in retains origin checks and the server login guard", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ token, expires_at: "2099-01-01T00:00:00Z" }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const req = new NextRequest(`${origin}/api/backend/mobile/auth/login`, {
      method: "POST",
      headers: { Origin: origin, "Content-Type": "application/json" },
      body: JSON.stringify({ password: "invented fixture" }),
    });
    expect(
      (
        await proxyPost(req, {
          params: Promise.resolve({ path: ["mobile", "auth", "login"] }),
        })
      ).status,
    ).toBe(200);
    expect(
      (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers,
    ).toMatchObject({ "X-Yggdress-Login": "1" });
    const invalid = new NextRequest(`${origin}/api/backend/mobile/auth/login`, {
      method: "POST",
      headers: { Origin: "https://other.test" },
      body: "{}",
    });
    expect(
      (
        await proxyPost(invalid, {
          params: Promise.resolve({ path: ["mobile", "auth", "login"] }),
        })
      ).status,
    ).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("establishes an HttpOnly WebView cookie by POST without credentials in navigation URLs", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response("{}", {
          headers: {
            "Set-Cookie":
              "yggdress_session=synthetic; Path=/; HttpOnly; Secure; SameSite=Strict",
          },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const response = await webviewPost(
      new NextRequest(`${origin}/api/mobile-session?view=notes`, {
        method: "POST",
        headers: { Origin: origin, Authorization: `Bearer ${token}` },
      }),
    );
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`${origin}/notes`);
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(
      (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers,
    ).toMatchObject({ Authorization: `Bearer ${token}` });
    expect(
      (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[0],
    ).not.toContain(token);
  });
  it("refuses arbitrary WebView redirects or missing device authentication", async () => {
    expect(
      (
        await webviewPost(
          new NextRequest(`${origin}/api/mobile-session?view=notes`, {
            method: "POST",
            headers: { Origin: origin },
          }),
        )
      ).status,
    ).toBe(403);
    expect(
      (
        await webviewPost(
          new NextRequest(
            `${origin}/api/mobile-session?view=https://other.test`,
            {
              method: "POST",
              headers: { Origin: origin, Authorization: `Bearer ${token}` },
            },
          ),
        )
      ).status,
    ).toBe(404);
  });
});

it("supports Android form POST without a token in the navigation URL", async () => {
  const fetchMock = vi.fn(
    async () =>
      new Response("{}", {
        headers: {
          "Set-Cookie": "yggdress_session=synthetic; Path=/; HttpOnly",
        },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const response = await webviewPost(
    new NextRequest(`${origin}/api/mobile-session?view=graph`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Origin: "null",
      },
      body: new URLSearchParams({ token }).toString(),
    }),
  );
  expect(response.status).toBe(303);
  expect(response.headers.get("location")).toBe(`${origin}/graph`);
  expect(
    (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers,
  ).toMatchObject({ Authorization: `Bearer ${token}` });
});
