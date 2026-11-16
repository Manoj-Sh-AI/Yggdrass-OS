import sharp from "../web/node_modules/sharp/lib/index.js";
import { readFile, writeFile } from "node:fs/promises";
const png = await sharp(await readFile(new URL("./icon.svg", import.meta.url))).png().toBuffer();
const header = Buffer.alloc(22);
header.writeUInt16LE(1, 2); header.writeUInt16LE(1, 4);
header.writeUInt16LE(1, 10); header.writeUInt16LE(32, 12);
header.writeUInt32LE(png.length, 14); header.writeUInt32LE(22, 18);
await writeFile(new URL("./dist/Yggdras.ico", import.meta.url), Buffer.concat([header, png]));
