// Token lint (Phase A8): values outside src/styles/tokens.css are not allowed.
//   raw hex colours, rgb()/hsl() colours, arbitrary design values (bg-[#..],
//   p-[13px], rounded-[7px], text-[..], shadow-[..] ...), Tailwind palette
//   classes (blue-500, zinc-800 ...) and colours in inline style={{}}.
// Ratchet: scripts/lint-tokens-baseline.json records today's per-file counts of
// the legacy CSS. A NEW file with any violation, or a file whose count RISES, is
// a warning locally and an ERROR when CI=1 (the build runs it as prebuild).
// Lower the baseline as legacy files migrate: node scripts/lint-tokens.mjs --update
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const BASELINE = join(ROOT, "scripts/lint-tokens-baseline.json");
// The token layer itself is the one place raw values may live.
const EXEMPT = new Set(["src/styles/tokens.css"]);

export const RULES = {
  // Anchors (href="#add", to="#top") are not colours.
  "raw-hex": /(?<![\w&/-])(?<!(?:href|to)=["'`])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g,
  "raw-rgb-hsl": /\b(?:rgba?|hsla?|oklch|oklab)\(/g,
  "arbitrary-value":
    /(?<![\w-])(?:bg|text|border(?:-[trblxy])?|ring|outline|fill|stroke|shadow|rounded(?:-[trbl]{1,2})?|p[xytrbl]?|m[xytrbl]?|gap(?:-[xy])?|space-[xy]|leading|tracking|font|duration|ease|delay)-\[(?!var\(|length:var\()/g,
  "palette-class":
    /(?<![\w-])(?:bg|text|border|ring|outline|fill|stroke|from|via|to|divide|placeholder|caret|accent|decoration|shadow)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|black|white)(?:-\d{2,3})?(?![\w-])/g,
  "inline-style-colour": /style=\{\{[^}]*\b(?:color|background|backgroundColor|borderColor|fill|stroke)\s*:/g,
};

export function countViolations(text, path) {
  const counts = {};
  for (const [rule, pattern] of Object.entries(RULES)) {
    if (rule === "inline-style-colour" && !path.endsWith(".tsx")) continue;
    // A CSS comment may mention a hex value; only declarations count.
    const source = path.endsWith(".css") ? text.replace(/\/\*[\s\S]*?\*\//g, "") : text;
    const n = (source.match(pattern) || []).length;
    if (n) counts[rule] = n;
  }
  return counts;
}

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(css|tsx|ts)$/.test(name) && !/\.(test|d)\.tsx?$/.test(name) ? [path] : [];
  });
}

function scan() {
  const result = {};
  for (const path of files(join(ROOT, "src"))) {
    const rel = relative(ROOT, path).replace(/\\/g, "/");
    if (EXEMPT.has(rel)) continue;
    const counts = countViolations(readFileSync(path, "utf8"), rel);
    if (Object.keys(counts).length) result[rel] = counts;
  }
  return result;
}

if (import.meta.url === new URL(`file:///${process.argv[1].replace(/\\/g, "/")}`).href) {
  const current = scan();
  if (process.argv.includes("--update")) {
    writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
    console.log(`Token lint baseline written for ${Object.keys(current).length} files.`);
    process.exit(0);
  }
  const baseline = JSON.parse(readFileSync(BASELINE, "utf8"));
  const problems = [];
  for (const [file, counts] of Object.entries(current))
    for (const [rule, n] of Object.entries(counts)) {
      const allowed = baseline[file]?.[rule] ?? 0;
      if (n > allowed) problems.push(`${file}: ${rule} ${n} (baseline ${allowed})`);
    }
  const total = Object.values(current).flatMap(Object.values).reduce((a, b) => a + b, 0);
  if (!problems.length) {
    console.log(`Token lint: no new violations (${total} legacy values left to migrate).`);
    process.exit(0);
  }
  const strict = process.env.CI === "1" || process.env.CI === "true";
  console[strict ? "error" : "warn"](
    `Token lint ${strict ? "ERROR" : "warning"}: values outside the token layer.\n  ` +
      problems.join("\n  ") +
      "\nUse src/styles/tokens.css tokens or src/components/primitives. Missing a value? Ask; never invent one.",
  );
  process.exit(strict ? 1 : 0);
}
