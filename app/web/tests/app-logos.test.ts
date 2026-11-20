import { describe, expect, it } from "vitest";
import { APP_LOGOS } from "@/lib/app-logos";

describe("bundled app logos", () => {
  it("covers every directory app and stays local", () => {
    for (const id of ["gmail", "google-calendar", "notion", "github", "slack", "microsoft-365"])
      expect(APP_LOGOS[id]).toBeDefined();
    expect(Object.keys(APP_LOGOS)).toHaveLength(22);
    for (const logo of Object.values(APP_LOGOS)) {
      expect(logo.hex).toMatch(/^[0-9A-F]{6}$/i);
      if (logo.kind === "path") expect(logo.d).not.toMatch(/https?:/);
    }
  });
});
