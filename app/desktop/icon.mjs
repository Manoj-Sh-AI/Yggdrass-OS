// Yggdras.ico from the exterior (navy) logo: a white rounded tile at the sizes
// Windows uses for the taskbar, title bar, Explorer and Alt-Tab.
import { tile } from "../web/scripts/brand-assets.mjs";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const source = fileURLToPath(new URL("../mobile/assets/brand/logo-exterior.png", import.meta.url));
const sizes = [16, 24, 32, 48, 64, 128, 256];
const images = await Promise.all(
  sizes.map(async (size) => (await tile(source, size, 0.8, "#ffffff", 0.22)).toBuffer()),
);
const header = Buffer.alloc(6 + 16 * sizes.length);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
sizes.forEach((size, i) => {
  const entry = 6 + 16 * i;
  header.writeUInt8(size === 256 ? 0 : size, entry);
  header.writeUInt8(size === 256 ? 0 : size, entry + 1);
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(images[i].length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += images[i].length;
});
await writeFile(new URL("./dist/Yggdras.ico", import.meta.url), Buffer.concat([header, ...images]));
