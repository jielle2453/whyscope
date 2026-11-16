// The same relay core as a plain Node server: for any VPS or Docker, or for local tests where workerd cannot run.
//   node node-server.js [--port 8787] [--state relay-state.json] [--debug]
// Put it behind TLS (Caddy, nginx, a cloud load balancer) in production; it holds no secrets, only hub public keys.
import http from "node:http";
import fs from "node:fs";
import { WebSocketServer } from "ws";
import { HubCore, MAX_FRAME } from "./src/hub.js";

const arg = (n, d) => { const i = process.argv.indexOf(n); return i < 0 ? d : process.argv[i + 1] ?? true; };
const port = Number(arg("--port", process.env.PORT || 8787));
const stateFile = arg("--state", process.env.RELAY_STATE || "relay-state.json");
const debug = process.argv.includes("--debug") || process.env.DEBUG_FRAMES === "1";
const host = arg("--host", process.env.HOST || "127.0.0.1");

let state = {};
try { state = JSON.parse(fs.readFileSync(stateFile, "utf8")); } catch {}
const save = () => fs.writeFileSync(stateFile, JSON.stringify(state));
const storageFor = (id) => ({
  async get(k) { return state[id]?.[k]; },
  async put(k, v) { (state[id] ??= {})[k] = v; save(); },
});

const cores = new Map();
const server = http.createServer((req, res) => { res.end("whyscope relay\n"); });
const wss = new WebSocketServer({ noServer: true, maxPayload: MAX_FRAME });
server.on("upgrade", (req, socket, head) => {
  const m = req.url.split("?")[0].match(/^\/v1\/(host|client)\/([0-9a-f]{32})$/);
  if (!m) return socket.destroy();
  wss.handleUpgrade(req, socket, head, (ws) => {
    ws.binaryType = "arraybuffer";
    let core = cores.get(m[2]);
    if (!core) cores.set(m[2], (core = new HubCore(storageFor(m[2]), debug)));
    if (m[1] === "host") core.onHost(ws, m[2]); else core.onClient(ws, m[2]);
  });
});
server.listen(port, host, () => console.log(`whyscope relay listening on ${host}:${port}`));
