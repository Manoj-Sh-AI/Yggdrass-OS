// Measures the black scrim alpha each scene needs so text tokens clear 4.5:1
// (WCAG 2.x relative luminance) against the scene's LIGHTEST region, not its average.
// Region = the brightest WINDOW x WINDOW box (mean linear luminance) at 1920px width.
// Run: node scripts/measure-scrim.mjs  (reads public/scenes/*-1920.webp)
import sharp from "sharp";
import { readdirSync } from "node:fs";

const WINDOW = 48;
const TARGET = 4.5;
const TEXT = { "text-1": "#FAF9F5", "text-2": "#C2C0B6", "text-3": "#9C9A92" };
const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

async function lightest(file) {
  const { data, info } = await sharp(file).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const { width: w, height: h } = info;
  // Summed-area table over sRGB channels; the composite with black is linear in sRGB
  // space (browsers blend in sRGB), so we keep the region's mean sRGB colour.
  const S = [0, 1, 2].map(() => new Float64Array((w + 1) * (h + 1)));
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++) {
    const i = (y + 1) * (w + 1) + (x + 1);
    S[c][i] = data[(y * w + x) * 3 + c] + S[c][i - 1] + S[c][i - (w + 1)] - S[c][i - (w + 1) - 1];
  }
  let best = { l: -1 };
  for (let y = 0; y + WINDOW <= h; y += 4) for (let x = 0; x + WINDOW <= w; x += 4) {
    const top = y * (w + 1), bottom = (y + WINDOW) * (w + 1);
    const rgb = [0, 1, 2].map((c) => {
      const s = S[c];
      const sum = s[bottom + x + WINDOW] - s[top + x + WINDOW] - s[bottom + x] + s[top + x];
      return sum / (WINDOW * WINDOW);
    });
    const l = lum(rgb);
    if (l > best.l) best = { l, rgb, x, y, w, h };
  }
  return best;
}

function needed(rgb, text) {
  const t = lum(hex(text));
  for (let a = 0; a <= 1.0001; a += 0.01) {
    const over = rgb.map((c) => c * (1 - a));
    if (ratio(t, lum(over)) >= TARGET) return Math.round(a * 100) / 100;
  }
  return null;
}

const files = readdirSync("public/scenes").filter((f) => f.endsWith("-1920.webp")).sort();
const rows = [];
for (const f of files) {
  const r = await lightest("public/scenes/" + f);
  const row = { scene: f.replace("-1920.webp", ""), region: `x${r.x} y${r.y} (${r.w}x${r.h})`,
    rgb: r.rgb.map((c) => Math.round(c)).join(","), unscrimmed: ratio(lum(hex(TEXT["text-1"])), r.l).toFixed(2) };
  for (const [k, v] of Object.entries(TEXT)) row[k] = needed(r.rgb, v);
  rows.push(row);
}
console.table(rows);
// Panel check: --panel-bg = surface-1 at 92% over the scrimmed lightest region.
const SCRIM = Number(process.env.SCRIM || 0.66);
const surface1 = hex("#262624");
let worst = Infinity;
for (const f of files) {
  const r = await lightest("public/scenes/" + f);
  const under = r.rgb.map((c) => c * (1 - SCRIM));
  const panel = surface1.map((c, i) => 0.92 * c + 0.08 * under[i]);
  worst = Math.min(worst, ratio(lum(hex(TEXT["text-3"])), lum(panel)));
}
console.log(`text-3 on a 92% panel over the worst scrimmed region (scrim ${SCRIM}): ${worst.toFixed(2)}:1`);
for (const k of Object.keys(TEXT)) {
  const night = Math.max(...rows.filter((r) => r.scene.includes("-night-")).map((r) => r[k]));
  const all = Math.max(...rows.map((r) => r[k]));
  console.log(`${k}: night scenes need ${night}, all scenes need ${all}`);
}
