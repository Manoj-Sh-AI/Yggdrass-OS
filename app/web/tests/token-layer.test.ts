import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { countViolations } from "../scripts/lint-tokens.mjs";
import { surfaceClass } from "@/components/primitives/surface";

const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
const theme = tokens.slice(tokens.indexOf("@theme inline {"), tokens.indexOf("@layer base {"));
const declared = (prefix: string) =>
  [...theme.matchAll(new RegExp(`^\\s*--${prefix}-([a-z0-9-]+):`, "gm"))]
    .map((m) => m[1])
    .filter((name) => name !== "*" && !name.includes("--"));

describe("token layer (closed value space)", () => {
  it("resets Tailwind's palette, radii, shadows and type so nothing else exists", () => {
    for (const ns of ["color", "radius", "shadow", "text", "font-weight"])
      expect(theme).toContain(`--${ns}-*: initial;`);
  });
  it("has exactly five radii plus full", () => {
    expect(declared("radius")).toEqual(["xs", "sm", "md", "lg", "xl", "full"]);
  });
  it("has exactly four shadows", () => {
    expect(declared("shadow")).toEqual(["xs", "sm", "md", "lg"]);
  });
  it("has the cited type scale", () => {
    expect(declared("text").filter((n) => !n.endsWith("line-height"))).toEqual([
      "xs", "sm", "base", "lg", "xl", "2xl", "3xl",
    ]);
  });
  it("uses @theme inline (plain @theme breaks dark mode)", () => {
    expect(tokens).toMatch(/@theme inline \{/);
    expect(tokens).not.toMatch(/@theme \{/);
  });
  it("defines one primary and one ring, and no accent hue", () => {
    expect(tokens.match(/^\s*--primary:/gm)).toHaveLength(1);
    expect(tokens.match(/^\s*--ring:/gm)).toHaveLength(1);
    expect(tokens).toMatch(/--accent: var\(--surface-2\);/);
  });
  it("keeps the measured scrim and the hardcoded -webkit- blur in step", () => {
    expect(tokens).toMatch(/--scrim: rgba\(0, 0, 0, 0\.66\);/);
    const glass = readFileSync(new URL("../src/styles/primitives.css", import.meta.url), "utf8");
    expect(tokens).toMatch(/--panel-blur: 16px;/);
    expect(tokens).toMatch(/--panel-saturate: 180%;/);
    expect(glass).toContain("-webkit-backdrop-filter: blur(16px) saturate(180%);");
    expect(glass).toMatch(/prefers-reduced-transparency: no-preference/);
  });
});

describe("token lint", () => {
  it("flags the brief's examples", () => {
    const tsx = `<div className="bg-[#123456] p-[13px] rounded-[7px] bg-blue-500 border-zinc-800" style={{ color: "red" }} />`;
    expect(countViolations(tsx, "x.tsx")).toEqual({
      "raw-hex": 1,
      "arbitrary-value": 3,
      "palette-class": 2,
      "inline-style-colour": 1,
    });
  });
  it("allows tokens, var() arbitraries and layout arbitraries", () => {
    const tsx = `<div className="bg-surface-1 text-text-2 rounded-lg p-4 h-[var(--row-h)] top-[50%] max-w-[calc(100%-2rem)]" href="#add" />`;
    expect(countViolations(tsx, "x.tsx")).toEqual({});
  });
  it("ignores colours mentioned in CSS comments", () => {
    expect(countViolations("/* was #ffffff */ .a { color: var(--text-1); }", "a.css")).toEqual({});
  });
});

describe("Surface primitive", () => {
  it("maps levels onto the ladder", () => {
    expect(surfaceClass(0, "none", false)).toContain("bg-surface-0");
    expect(surfaceClass(3, "lg", false)).toContain("shadow-lg");
    expect(surfaceClass(1, "xl", true)).toContain("surface-glass");
  });
  it("refuses glass on anything but a panel", () => {
    expect(() => surfaceClass(2, "md", true)).toThrow(/panels/);
  });
});
