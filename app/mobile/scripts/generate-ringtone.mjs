// Generates the Yggdras ringtone: an original, license-free soft bell chime.
// One 3-second cycle (three rising notes, then a resting tail) that loops cleanly.
// The same file is bundled for Android (notification channel sound) and the web app.
// Run from app/mobile:  node scripts/generate-ringtone.mjs
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RATE = 44100;
const SECONDS = 3;
const PEAK = 0.5; // about -6 dBFS: present, never harsh
// E5, G#5, B5: a gentle major arpeggio, then rest.
const NOTES = [
  { at: 0.0, hz: 659.25 },
  { at: 0.2, hz: 830.61 },
  { at: 0.4, hz: 987.77 },
];
const ATTACK = 0.03; // soft raised-cosine attack, no click
const DECAY = 0.55; // seconds for the bell to fall to 1/e
const PARTIALS = [
  [1, 1],
  [2, 0.22],
  [3, 0.06],
];
const TAIL_FADE = 0.4; // guarantees exact silence at the loop point

export function synthesize() {
  const total = RATE * SECONDS;
  const samples = new Float32Array(total);
  for (const note of NOTES) {
    const start = Math.round(note.at * RATE);
    for (let i = start; i < total; i++) {
      const t = (i - start) / RATE;
      const attack =
        t < ATTACK ? 0.5 - 0.5 * Math.cos((Math.PI * t) / ATTACK) : 1;
      let value = 0;
      for (const [multiple, weight] of PARTIALS)
        // Higher partials fade faster, like a real bell.
        value +=
          weight *
          Math.sin(2 * Math.PI * note.hz * multiple * t) *
          Math.exp(-t / (DECAY / multiple));
      samples[i] += attack * value;
    }
  }
  const fadeStart = total - Math.round(TAIL_FADE * RATE);
  for (let i = fadeStart; i < total; i++)
    samples[i] *= 0.5 + 0.5 * Math.cos((Math.PI * (i - fadeStart)) / (total - fadeStart));
  let max = 0;
  for (const s of samples) max = Math.max(max, Math.abs(s));
  for (let i = 0; i < total; i++) samples[i] = (samples[i] / max) * PEAK;
  return samples;
}

export function wav(samples) {
  const data = samples.length * 2;
  const buffer = Buffer.alloc(44 + data);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + data, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20); // PCM
  buffer.writeUInt16LE(1, 22); // mono
  buffer.writeUInt32LE(RATE, 24);
  buffer.writeUInt32LE(RATE * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(data, 40);
  samples.forEach((s, i) =>
    buffer.writeInt16LE(Math.round(Math.max(-1, Math.min(1, s)) * 32767), 44 + i * 2),
  );
  return buffer;
}

const here = dirname(fileURLToPath(import.meta.url));
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const file = wav(synthesize());
  // Android raw resource names allow only lowercase letters, digits and underscores.
  for (const target of [
    join(here, "../assets/sounds/yggdras_ring.wav"),
    join(here, "../../web/public/sounds/yggdras_ring.wav"),
  ]) {
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, file);
    console.log("wrote", target, file.length, "bytes");
  }
}
