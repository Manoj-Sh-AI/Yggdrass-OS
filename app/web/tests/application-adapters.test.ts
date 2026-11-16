import { afterEach, describe, expect, it, vi } from "vitest";
import type { BrainNote } from "../src/lib/brain-adapter";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});
function network(...responses: Response[]) {
  const fetch = vi.fn();
  responses.forEach((response) => fetch.mockResolvedValueOnce(response));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const note = {
  id: "synthetic-note",
  version: "opaque-fixture-token",
  title: "Synthetic",
  description: "Fiction",
  content: "Visible replacement",
  tags: ["sample"],
  links: [],
  also: [],
  backlinks: [],
  area: "cross",
  shelfId: "14-inbox",
  source: "mock",
  slug: "synthetic-note",
  updated: "2026-11-08T12:00:00Z",
} as BrainNote;

describe("application and Brain HTTP boundaries", () => {
  it("reads mock shelves through the same-origin port without browser persistence", async () => {
    const fetch = network(
      json({ mode: "mock", integrationBlocked: true, shelves: [] }),
    );
    const { brainAdapter } = await import("../src/lib/brain-adapter");
    expect((await brainAdapter.tree()).integrationBlocked).toBe(true);
    expect(fetch).toHaveBeenCalledWith(
      "/api/backend/brain/tree",
      expect.objectContaining({
        credentials: "same-origin",
        cache: "no-store",
      }),
    );
  });
  it("replaces visible fields with the opaque Brain version; never sends history or relationships", async () => {
    const fetch = network(
      json({ csrf: "session-csrf" }),
      json({ mode: "mock", note }),
    );
    const { brainAdapter } = await import("../src/lib/brain-adapter");
    await brainAdapter.replace(note);
    const [url, request] = fetch.mock.calls[1];
    expect(url).toBe("/api/backend/brain/notes/synthetic-note");
    expect(request.method).toBe("PUT");
    expect(request.headers["X-Yggdress-CSRF"]).toBe("session-csrf");
    expect(JSON.parse(request.body)).toEqual({
      version: note.version,
      title: note.title,
      description: note.description,
      content: note.content,
      tags: note.tags,
    });
  });
  it("retains stale-update status and reload message for the drawer", async () => {
    network(
      json({ csrf: "session-csrf" }),
      json(
        { detail: "This note changed elsewhere. Reload the latest note." },
        409,
      ),
    );
    const { brainAdapter } = await import("../src/lib/brain-adapter");
    await expect(brainAdapter.replace(note)).rejects.toMatchObject({
      status: 409,
      message: expect.stringContaining("Reload"),
    });
  });
  it("requests a preview and submits its exact token/version with explicit confirmation", async () => {
    const preview = {
      token: "preview-token",
      noteId: note.id,
      version: note.version,
      title: note.title,
      content: note.content,
    };
    const fetch = network(
      json({ csrf: "session-csrf" }),
      json({ mode: "mock", preview }),
      json({ mode: "mock", deleted: true }),
    );
    const { brainAdapter } = await import("../src/lib/brain-adapter");
    await brainAdapter.previewDelete(note);
    await brainAdapter.confirmDelete(preview);
    expect(fetch.mock.calls[1][0]).toContain("/delete-preview");
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      version: note.version,
    });
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({
      version: note.version,
      token: "preview-token",
      confirmed: true,
    });
  });
  it("reports a service outage instead of falling back to local notes", async () => {
    network(json({ detail: "Lia is unavailable." }, 503));
    const { brainAdapter } = await import("../src/lib/brain-adapter");
    await expect(brainAdapter.notes()).rejects.toMatchObject({
      status: 503,
      message: "Lia is unavailable.",
    });
  });
  it("redirects expired private requests to sign-in", async () => {
    network(json({ detail: "Sign in to continue." }, 401));
    const assign = vi.fn();
    vi.stubGlobal("window", { location: { assign } });
    const { applicationApi } = await import("../src/lib/api");
    await expect(applicationApi("application/tasks")).rejects.toMatchObject({
      status: 401,
    });
    expect(assign).toHaveBeenCalledWith("/login");
  });
  it("login does not fetch a session before authentication", async () => {
    const fetch = network(json({ authenticated: true, csrf: "new-session" }));
    const { applicationApi } = await import("../src/lib/api");
    await applicationApi("auth/login", {
      method: "POST",
      body: JSON.stringify({ password: "synthetic-test-input-only" }),
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/backend/auth/login");
  });
});
