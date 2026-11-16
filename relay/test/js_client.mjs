// Node driver for tunnel.js (the same file the browser uses): node js_client.mjs <bundle.json> <question>
// Prints {healthz, ask, latency_ms: [...]} as JSON. Used by e2e.py.
import fs from "node:fs";
import { createRequire } from "node:module";
const T = createRequire(import.meta.url)("../../hub/static/tunnel.js");

const [, , file, question, n = "20"] = process.argv;
T.setBundle(JSON.parse(fs.readFileSync(file, "utf8")));
const out = {};
let r = await tunnelFetch("/healthz");
out.healthz = { status: r.status, body: await r.json() };
r = await tunnelFetch("/api/ask?wait=1", { method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ text: question, lang: "en", wait: 1 }) });
out.ask = { status: r.status, body: await r.json() };
out.latency_ms = [];
for (let i = 0; i < Number(n); i++) {
  const t = performance.now(); r = await tunnelFetch("/healthz"); await r.text();
  out.latency_ms.push(performance.now() - t);
}
console.log(JSON.stringify(out));
process.exit(0);
