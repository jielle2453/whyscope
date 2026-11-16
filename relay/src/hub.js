// The relay core, one instance per home hub. Runs unchanged inside a Cloudflare Durable Object (src/index.js) or in
// plain Node (node-server.js, for a VPS or Docker). It forwards opaque binary frames between the hub (outbound
// WebSocket) and paired devices. It holds no key that decrypts anything and stores only the hub's Ed25519 public key
// and the hub's revocation list. Protocol: docs/relay.md.
//
// A socket is anything with send(), close(code, reason) and addEventListener("message" | "close"); `storage` has
// async get(key) / put(key, value).

export const MAX_FRAME = 70000;        // a Noise message is at most 65535 bytes; plus 4-byte connection id and slack
const MAX_CLIENTS = 8;                 // simultaneous device connections per hub
const HELLO_TIMEOUT_MS = 10000;
const FRAMES_PER_SEC = 100, FRAME_BURST = 300;            // per client connection, both directions
const BYTES_PER_SEC = 1_000_000, BYTE_BURST = 4_000_000;  // a 1 MB audio upload fits in the burst

const enc = new TextEncoder();
const hex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (s) => Uint8Array.from(s.match(/../g) || [], (h) => parseInt(h, 16));
const unb64u = (s) => { try { return Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0)); } catch { return new Uint8Array(0); } };
const json = (o) => JSON.stringify(o);

async function verifyEd25519(pubHex, sig, msg) {
  try {
    const key = await crypto.subtle.importKey("raw", unhex(pubHex), "Ed25519", false, ["verify"]);
    return await crypto.subtle.verify("Ed25519", key, sig, enc.encode(msg));
  } catch { return false; }
}

// The hub id is the first 16 bytes of SHA-256(hub public key): nobody can squat another hub's id.
export async function hubIdOf(pubHex) {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", unhex(pubHex))).slice(0, 16));
}

// A bad frame must never take the relay down: any error in a handler just closes that socket.
function on(ws, type, fn) {
  ws.addEventListener(type, (ev) => { Promise.resolve().then(() => fn(ev)).catch(() => { try { ws.close(1011, "error"); } catch {} }); });
}

class Bucket {
  constructor(rate, burst) { this.rate = rate; this.cap = burst; this.v = burst; this.t = Date.now(); }
  take(n) {
    const now = Date.now();
    this.v = Math.min(this.cap, this.v + ((now - this.t) / 1000) * this.rate); this.t = now;
    if (this.v < n) return false;
    this.v -= n; return true;
  }
}

export class HubCore {
  constructor(storage, debug = false) {
    this.storage = storage;
    this.debug = debug;                       // debug mode logs frame sizes only, never content
    this.host = null;                         // the authenticated hub socket
    this.clients = new Map();                 // connId -> { id, ws, dev, bucketF, bucketB }
    this.nextId = 1;
  }

  log(...a) { if (this.debug) console.log("[relay]", ...a); }

  // ---- hub side ----
  onHost(ws, hubId) {
    const nonce = hex(crypto.getRandomValues(new Uint8Array(16)));
    let authed = false;
    ws.send(json({ t: "challenge", nonce }));
    const timer = setTimeout(() => { if (!authed) ws.close(4003, "auth timeout"); }, HELLO_TIMEOUT_MS);
    on(ws, "message", async (ev) => {
      if (!authed) {
        if (typeof ev.data !== "string") return ws.close(4003, "bad hello");
        let h; try { h = JSON.parse(ev.data); } catch { return ws.close(4003, "bad hello"); }
        const stored = await this.storage.get("pub");
        const okId = typeof h.pub === "string" && /^[0-9a-f]{64}$/.test(h.pub) && (await hubIdOf(h.pub)) === hubId;
        const okKey = okId && (!stored || stored === h.pub);                       // trust on first use, then pinned
        const okSig = okKey && (await verifyEd25519(h.pub, unhex(h.sig || ""), `whyscope-host-v1|${hubId}|${nonce}`));
        if (!okSig) { ws.send(json({ t: "error", error: "unauthorized" })); return ws.close(4003, "unauthorized"); }
        if (!stored) await this.storage.put("pub", h.pub);
        clearTimeout(timer);
        authed = true;
        if (this.host) { this.closeClients("hub_restarted"); try { this.host.close(4000, "replaced"); } catch {} }
        this.host = ws;
        ws.send(json({ t: "ok" }));
        this.log("host connected");
        return;
      }
      if (this.host !== ws) return;
      if (typeof ev.data === "string") return this.onHostText(ev.data);
      const buf = new Uint8Array(ev.data);
      if (buf.length < 5 || buf.length > MAX_FRAME) return;
      const c = this.clients.get(new DataView(buf.buffer, buf.byteOffset).getUint32(0));
      if (!c) return;
      this.log("hub->client", c.id, buf.length - 4, "bytes");
      if (!c.bucketF.take(1) || !c.bucketB.take(buf.length)) return this.dropClient(c.id, 1008, "rate limit", true);
      c.ws.send(buf.subarray(4));
    });
    on(ws, "close", () => {
      clearTimeout(timer);
      if (this.host === ws) { this.host = null; this.closeClients("hub_offline"); this.log("host gone"); }
    });
  }

  async onHostText(text) {
    let m; try { m = JSON.parse(text); } catch { return; }
    if (m.t === "revoke" && Array.isArray(m.devices)) {
      const list = m.devices.filter((d) => typeof d === "string").slice(0, 1000);
      await this.storage.put("revoked", list);
      for (const c of [...this.clients.values()]) if (list.includes(c.dev)) this.dropClient(c.id, 4004, "revoked", true);
    } else if (m.t === "close" && this.clients.has(m.c)) {
      this.dropClient(m.c, 1000, "closed by hub", false);
    }
  }

  // ---- device side ----
  onClient(ws, hubId) {
    let c = null;
    const timer = setTimeout(() => { if (!c) ws.close(4003, "hello timeout"); }, HELLO_TIMEOUT_MS);
    const refuse = (error, code) => { ws.send(json({ t: "error", error })); ws.close(code, error); };
    on(ws, "message", async (ev) => {
      if (!c) {
        if (typeof ev.data !== "string") return ws.close(4003, "bad hello");
        let h; try { h = JSON.parse(ev.data); } catch { return ws.close(4003, "bad hello"); }
        const dev = await this.checkTicket(hubId, h.ticket);
        if (!dev) return refuse("unauthorized", 4003);
        if (!this.host) return refuse("hub_offline", 4001);
        if (this.clients.size >= MAX_CLIENTS) return refuse("too_many_clients", 4005);
        clearTimeout(timer);
        c = { id: this.nextId++, ws, dev, bucketF: new Bucket(FRAMES_PER_SEC, FRAME_BURST), bucketB: new Bucket(BYTES_PER_SEC, BYTE_BURST) };
        this.clients.set(c.id, c);
        this.host.send(json({ t: "open", c: c.id, dev }));
        ws.send(json({ t: "ready" }));
        this.log("client open", c.id);
        return;
      }
      if (typeof ev.data === "string" || !this.host) return;
      const n = ev.data.byteLength;
      if (n === 0 || n > MAX_FRAME - 4) return this.dropClient(c.id, 1009, "frame too large", true);
      if (!c.bucketF.take(1) || !c.bucketB.take(n)) return this.dropClient(c.id, 1008, "rate limit", true);
      this.log("client->hub", c.id, n, "bytes");
      const out = new Uint8Array(4 + n);
      new DataView(out.buffer).setUint32(0, c.id);
      out.set(new Uint8Array(ev.data), 4);
      this.host.send(out);
    });
    on(ws, "close", () => {
      clearTimeout(timer);
      if (c && this.clients.get(c.id) === c) this.dropClient(c.id, 1000, "bye", true);
    });
  }

  // A ticket is "v1.<b64url json {d: device id, e: expiry unix s}>.<b64url Ed25519 signature>", signed by the hub.
  async checkTicket(hubId, ticket) {
    if (typeof ticket !== "string") return null;
    const [v, body, sig] = ticket.split(".");
    const pub = await this.storage.get("pub");
    if (v !== "v1" || !body || !sig || !pub) return null;
    if (!(await verifyEd25519(pub, unb64u(sig), `whyscope-ticket-v1|${hubId}|${body}`))) return null;
    let t; try { t = JSON.parse(new TextDecoder().decode(unb64u(body))); } catch { return null; }
    if (typeof t.d !== "string" || !(t.e > Date.now() / 1000)) return null;
    if (((await this.storage.get("revoked")) || []).includes(t.d)) return null;
    return t.d;
  }

  dropClient(id, code, reason, tellHub) {
    const c = this.clients.get(id);
    if (!c) return;
    this.clients.delete(id);
    try { c.ws.close(code, reason); } catch {}
    if (tellHub && this.host) try { this.host.send(json({ t: "close", c: id })); } catch {}
  }

  closeClients(error) {
    for (const c of this.clients.values()) {
      try { c.ws.send(json({ t: "error", error })); c.ws.close(4001, error); } catch {}
    }
    this.clients.clear();
  }
}
