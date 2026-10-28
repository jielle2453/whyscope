// Reads scenes.json + public/audio/narr-XX.wav (if present) and writes src/timeline.json
import fs from "node:fs";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "..");
const scenes = JSON.parse(fs.readFileSync(path.join(root, "scenes.json"), "utf8"));
function wavSeconds(file) {
  if (!fs.existsSync(file)) return 0;
  const b = fs.readFileSync(file);
  let o = 12, rate = 0, ch = 1, bits = 16;
  while (o + 8 <= b.length) {
    const id = b.toString("ascii", o, o + 4), sz = b.readUInt32LE(o + 4);
    if (id === "fmt ") { ch = b.readUInt16LE(o + 10); rate = b.readUInt32LE(o + 12); bits = b.readUInt16LE(o + 22); }
    if (id === "data") return sz / (rate * ch * (bits / 8));
    o += 8 + sz + (sz % 2);
  }
  return 0;
}
let start = 0;
const beats = scenes.beats.map((b) => {
  const nid = String(b.id).padStart(2, "0");
  const narrFile = path.join(root, "public/audio", `narr-${nid}.wav`);
  const narrSec = wavSeconds(narrFile);
  const needed = narrSec ? b.narrDelay + narrSec + scenes.padSeconds : 0;
  const seconds = Math.max(b.seconds, needed);
  const frames = Math.round(seconds * scenes.fps);
  const out = { ...b, narrSec, hasNarr: narrSec > 0, frames, start };
  start += frames;
  return out;
});
const tl = { fps: scenes.fps, width: scenes.width, height: scenes.height, total: start, beats };
fs.writeFileSync(path.join(root, "src/timeline.json"), JSON.stringify(tl, null, 1));
console.log(`timeline: ${start} frames = ${(start / scenes.fps).toFixed(1)}s`);
