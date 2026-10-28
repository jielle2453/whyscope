// node scripts/stills.mjs 250,400,... -> .tmp/stills/f<frame>.jpg (quick visual QA, half size) and a contact sheet
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";
import fs from "node:fs";
const root = path.resolve(import.meta.dirname, "..");
const frames = process.argv[2].split(",").map(Number);
const out = path.join(root, ".tmp/stills");
fs.mkdirSync(out, { recursive: true });
const browserExecutable = fs.existsSync("C:/whyscope-chrome/chrome-headless-shell.exe") ? "C:/whyscope-chrome/chrome-headless-shell.exe" : undefined;
const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts"), publicDir: path.join(root, "public") });
const comp = await selectComposition({ serveUrl, id: "Film", browserExecutable, logLevel: "error" });
for (const f of frames) {
  await renderStill({ composition: comp, serveUrl, frame: f, output: path.join(out, `f${f}.jpg`), imageFormat: "jpeg", scale: Number(process.env.SCALE ?? 0.5), browserExecutable, logLevel: "error", timeoutInMS: 90000 });
  console.log("frame", f);
}
