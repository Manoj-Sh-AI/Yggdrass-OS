import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
const tokens = read("../src/styles/tokens.css");
const globals = read("../src/app/globals.css");

describe("motion (A5 applied)", () => {
  it("motion utilities use only the duration tokens and the practical easing", () => {
    const blocks = [...tokens.matchAll(/@utility motion-([a-z]+) \{([^}]*)\}/g)];
    expect(blocks.map((b) => b[1])).toEqual(["xshort", "short", "medium", "long", "xlong"]);
    for (const [, name, body] of blocks) {
      expect(body).toContain(`var(--duration-${name})`);
      expect(body).toContain("var(--ease-practical)");
      expect(body).not.toMatch(/\d+m?s\b/);
    }
  });
  it("reduced motion turns every transition and animation off app-wide", () => {
    const rule = globals.slice(globals.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(rule).toMatch(/animation: none !important/);
    expect(rule).toMatch(/transition: none !important/);
  });
  it("components carry no raw Tailwind duration classes", () => {
    for (const f of ["sheet", "dialog", "button"]) {
      const src = read(`../src/components/primitives/${f}.tsx`);
      expect(src).not.toMatch(/\bduration-\d+/);
      expect(src).toMatch(/motion-(short|medium|long|xlong)/);
    }
  });
});
