// Generates every logo asset from the two source images Manoj chose:
//   app/mobile/assets/brand/logo-exterior.png  navy mark on white: app icons, favicon
//   app/mobile/assets/brand/logo-interior.png  silver mark on charcoal: inside the apps
// Run from app/web after changing either source: node scripts/brand-assets.mjs
// (The desktop .ico is made at desktop build time by app/desktop/icon.mjs.)
import sharp from "sharp";
import { mkdir } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

const app = new URL("../../", import.meta.url);
const at = (path) => fileURLToPath(new URL(path, app));
const EXTERIOR = at("mobile/assets/brand/logo-exterior.png");
const INTERIOR = at("mobile/assets/brand/logo-interior.png");

/** The mark cropped tight from its plain background. */
async function mark(source) {
  return sharp(source).trim({ threshold: 30 }).png().toBuffer();
}

/** `size` square of `background`, mark centred at `height` share of the side. */
export async function tile(source, size, height, background, radius = 0) {
  const fitted = await sharp(await mark(source))
    .resize({ height: Math.round(size * height) })
    .png()
    .toBuffer();
  let image = sharp({
    create: { width: size, height: size, channels: 4, background },
  }).composite([{ input: fitted, gravity: "centre" }]);
  if (radius) {
    const r = Math.round(size * radius);
    const mask = Buffer.from(
      `<svg width="${size}" height="${size}"><rect width="${size}" height="${size}" rx="${r}" ry="${r}"/></svg>`,
    );
    image = sharp(await image.png().toBuffer()).composite([
      { input: mask, blend: "dest-in" },
    ]);
  }
  return image.png();
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const white = "#ffffff";
  const charcoal = (await sharp(INTERIOR).extract({ left: 4, top: 4, width: 1, height: 1 }).raw().toBuffer()).toJSON().data;
  const dark = { r: charcoal[0], g: charcoal[1], b: charcoal[2], alpha: 1 };
  await mkdir(at("web/public/brand"), { recursive: true });
  const outputs = [
    // Phone launcher (legacy square) and Android adaptive foreground: the mark
    // stays inside the 66% safe circle so no launcher mask crops it.
    [EXTERIOR, 1024, 0.7, white, 0, "mobile/assets/brand/icon.png"],
    [EXTERIOR, 1024, 0.5, white, 0, "mobile/assets/brand/adaptive-foreground.png"],
    // Website favicon and Apple touch icon (Next.js app-router file conventions).
    [EXTERIOR, 512, 0.76, white, 0.22, "web/src/app/icon.png"],
    [EXTERIOR, 180, 0.7, white, 0, "web/src/app/apple-icon.png"],
    // Interior brand mark: phone sign-in and the website sidebar / sign-in.
    [INTERIOR, 256, 0.78, dark, 0, "mobile/assets/brand/logo-mark.png"],
    [INTERIOR, 256, 0.78, dark, 0, "web/public/brand/logo-mark.png"],
  ];
  for (const [source, size, height, background, radius, target] of outputs) {
    await (await tile(source, size, height, background, radius)).toFile(at(target));
    console.log("wrote", target);
  }
}
