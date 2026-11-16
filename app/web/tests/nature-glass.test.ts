import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { seed } from "../src/lib/data";
import { browserRepository, isState, STORAGE_KEY } from "../src/lib/repository";

const css = readFileSync(
  new URL("../src/app/open-air.css", import.meta.url),
  "utf8",
);
const token = (name: string) =>
  css.match(new RegExp(`--${name}:\\s*([^;]+);`))![1].trim();
const rgb = (hex: string) =>
  hex
    .slice(1)
    .match(/../g)!
    .map((value) => parseInt(value, 16));
const composite = (foreground: number[], alpha: number, background: number[]) =>
  foreground.map((v, i) => v * alpha + background[i] * (1 - alpha));
const luminance = (color: number[]) =>
  color
    .map((v) => v / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    .reduce((n, v, i) => n + v * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a: number[], b: number[]) =>
  (Math.max(luminance(a), luminance(b)) + 0.05) /
  (Math.min(luminance(a), luminance(b)) + 0.05);

describe("open-air glass reading and controls", () => {
  it("keeps text readable even over a white scene, including the brightest glass highlight", () => {
    const base = token("glass-rgb").split(",").map(Number);
    const fill = composite(base, Number(token("glass-alpha")), [255, 255, 255]);
    const highlight = token("glass-highlight")
      .match(/[\d.]+/g)!
      .map(Number);
    const brightest = composite(highlight.slice(0, 3), highlight[3], fill);
    for (const name of ["text", "muted", "faint"]) {
      expect(
        contrast(rgb(token(name)), brightest),
        name,
      ).toBeGreaterThanOrEqual(4.5);
      expect(contrast(rgb(token(name)), base), name).toBeGreaterThanOrEqual(
        4.5,
      );
    }
    expect(
      contrast(rgb(token("control-border")), rgb(token("control-fill"))),
    ).toBeGreaterThanOrEqual(3);
    expect(
      contrast(rgb(token("focus-ring")), brightest),
    ).toBeGreaterThanOrEqual(3);
  });
  it("retains older preferences and validates the new optional accessibility setting", async () => {
    const state = seed();
    delete state.preferences.reducedTransparency;
    expect(isState(state)).toBe(true);
    const values = new Map([[STORAGE_KEY, JSON.stringify(state)]]);
    const repository = browserRepository({
      getItem: (key) => values.get(key) || null,
      setItem: (key, value) => {
        values.set(key, value);
      },
    });
    const loaded = await repository.load();
    loaded.preferences.reducedTransparency = true;
    await repository.save(loaded);
    expect((await repository.load()).preferences.reducedTransparency).toBe(
      true,
    );
    expect(
      isState({
        ...loaded,
        preferences: { ...loaded.preferences, reducedTransparency: "yes" },
      }),
    ).toBe(false);
  });
});
