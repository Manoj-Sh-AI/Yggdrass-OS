import sharp from "sharp";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
const sources = JSON.parse(
  await readFile(new URL("./scene-sources.json", import.meta.url), "utf8"),
);
await mkdir(`${root}public/scenes`, { recursive: true });
const manifest = [];
for (const source of sources) {
  const variants = [];
  for (const width of [480, 960, 1920]) {
    const filename = `${source.key}-${width}.webp`;
    const result = await sharp(source.path)
      .resize(width, Math.round((width * 9) / 16), { fit: "cover" })
      .webp({ quality: width === 1920 ? 83 : 78 })
      .toFile(`${root}public/scenes/${filename}`);
    variants.push({ width, src: `/scenes/${filename}`, bytes: result.size });
  }
  manifest.push({
    key: source.key,
    season: source.key.split("-")[0],
    phase: source.key.split("-")[1],
    weather: source.key.split("-")[2],
    variants,
  });
}
await writeFile(
  `${root}public/scenes/manifest.json`,
  JSON.stringify(
    {
      version: 1,
      generated: true,
      viewpoint:
        "Fixed alpine lake master, generated with imagegen; reference-edited seasonal/time/weather variants.",
      scenes: manifest,
    },
    null,
    2,
  ),
);
const tiles = await Promise.all(
  sources.map(async (s) => {
    const image = await sharp(s.path).resize(320, 180).toBuffer();
    const label = Buffer.from(
      `<svg width="320" height="24"><rect width="320" height="24" fill="#101827"/><text x="8" y="16" fill="white" font-size="12" font-family="Arial">${s.key}</text></svg>`,
    );
    return sharp({
      create: { width: 320, height: 204, channels: 3, background: "#101827" },
    })
      .composite([
        { input: image, top: 0, left: 0 },
        { input: label, top: 180, left: 0 },
      ])
      .png()
      .toBuffer();
  }),
);
await sharp({
  create: { width: 1280, height: 1224, channels: 3, background: "#101827" },
})
  .composite(
    tiles.map((input, i) => ({
      input,
      left: (i % 4) * 320,
      top: Math.floor(i / 4) * 204,
    })),
  )
  .png()
  .toFile(`${root}public/scenes/contact-sheet.png`);
console.log(`Optimized ${manifest.length} scenes into three responsive sizes.`);
