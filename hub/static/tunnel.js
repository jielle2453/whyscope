/* Whyscope encrypted tunnel, browser (and Node 22+) client. Classic script, no dependencies, no CDN.
 *
 *   <script src="/static/tunnel.js"></script>
 *   WhyscopeTunnel.setBundle(bundleObjectOrQrString);          // pairing bundle from `python -m hub.tunnel pair`
 *   const r = await tunnelFetch("/api/ask", {method: "POST", headers: {"content-type": "application/json"},
 *                                            body: JSON.stringify({text: "Why is the sky blue?", lang: "en"})});
 *   console.log(await r.json());
 *
 * Crypto: Noise_KK_25519_AESGCM_SHA256 (https://noiseprotocol.org/noise.html) written directly on the browser's WebCrypto
 * primitives (X25519, AES-GCM, HMAC-SHA-256); no new primitive is invented. It needs a secure context (https or
 * http://127.0.0.1) and a browser with WebCrypto X25519 (Chrome 133+, Firefox 130+, Safari 17+). The relay sees only the
 * ciphertext. Tests: relay/test/tunnel.test.js (Noise test vectors + interop with the Python hub).
 */
(function (root) {
  "use strict";
  const subtle = (root.crypto || require("node:crypto").webcrypto).subtle;
  const te = new TextEncoder(), td = new TextDecoder();
  const PROTOCOL = "Noise_KK_25519_AESGCM_SHA256";
  const CHUNK = 65535 - 16 - 1;             // plaintext bytes per Noise message (one more byte is the "last chunk" flag)
  const MAX_MESSAGE = 3 * 1024 * 1024;

  const cat = (...a) => { const o = new Uint8Array(a.reduce((n, x) => n + x.length, 0)); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };
  const hex = (u) => [...u].map((b) => b.toString(16).padStart(2, "0")).join("");
  const unhex = (s) => Uint8Array.from(s.match(/../g) || [], (h) => parseInt(h, 16));
  const b64u = (u) => btoa(String.fromCharCode(...u)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unb64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  const sha256 = async (d) => new Uint8Array(await subtle.digest("SHA-256", d));

  // ---- Noise primitives (spec sections 4 and 5) ----
  async function hmac(key, data) {
    const k = await subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return new Uint8Array(await subtle.sign("HMAC", k, data));
  }
  async function hkdf(ck, ikm) {                       // two outputs
    const t = await hmac(ck, ikm);
    const o1 = await hmac(t, Uint8Array.of(1));
    return [o1, await hmac(t, cat(o1, Uint8Array.of(2)))];
  }
  const PKCS8_X25519 = unhex("302e020100300506032b656e04220420");
  async function importPriv(raw) {
    const key = await subtle.importKey("pkcs8", cat(PKCS8_X25519, raw), { name: "X25519" }, true, ["deriveBits"]);
    return { key, pub: unb64u((await subtle.exportKey("jwk", key)).x) };
  }
  async function dh(priv, pubRaw) {
    const pub = await subtle.importKey("raw", pubRaw, { name: "X25519" }, false, []);
    return new Uint8Array(await subtle.deriveBits({ name: "X25519", public: pub }, priv.key, 256));
  }
  async function aesKey(k) { return subtle.importKey("raw", k, "AES-GCM", false, ["encrypt", "decrypt"]); }
  function nonce(n) { const b = new Uint8Array(12); new DataView(b.buffer).setBigUint64(4, BigInt(n)); return b; }

  class CipherState {
    constructor(k) { this.k = k ? aesKey(k) : null; this.n = 0; }
    async encrypt(ad, pt) {
      if (!this.k) return pt;
      const ct = await subtle.encrypt({ name: "AES-GCM", iv: nonce(this.n++), additionalData: ad, tagLength: 128 }, await this.k, pt);
      return new Uint8Array(ct);
    }
    async decrypt(ad, ct) {
      if (!this.k) return ct;
      const pt = await subtle.decrypt({ name: "AES-GCM", iv: nonce(this.n), additionalData: ad, tagLength: 128 }, await this.k, ct);
      this.n++;
      return new Uint8Array(pt);
    }
  }

  // The initiator (device) half of Noise_KK: pre-messages "-> s" "<- s", then "-> e, es, ss" and "<- e, ee, se".
  class NoiseKKInitiator {
    constructor(staticPriv32, remoteStatic32, prologue, ephemeralPriv32) {
      this.sRaw = staticPriv32; this.rs = remoteStatic32; this.prologue = prologue; this.eRaw = ephemeralPriv32 || null;
    }
    async mixHash(d) { this.h = await sha256(cat(this.h, d)); }
    async mixKey(ikm) { const [ck, k] = await hkdf(this.ck, ikm); this.ck = ck; this.cs = new CipherState(k); }
    async encryptAndHash(pt) { const ct = await this.cs.encrypt(this.h, pt); await this.mixHash(ct); return ct; }
    async decryptAndHash(ct) { const pt = await this.cs.decrypt(this.h, ct); await this.mixHash(ct); return pt; }

    async start() {
      const name = te.encode(PROTOCOL);
      this.h = name.length <= 32 ? cat(name, new Uint8Array(32 - name.length)) : await sha256(name);
      this.ck = this.h; this.cs = new CipherState(null);
      this.s = await importPriv(this.sRaw);
      await this.mixHash(this.prologue); await this.mixHash(this.s.pub); await this.mixHash(this.rs);
    }
    async writeMessage1(payload = new Uint8Array(0)) {
      if (this.eRaw) this.e = await importPriv(this.eRaw);
      else {
        const kp = await subtle.generateKey({ name: "X25519" }, true, ["deriveBits"]);
        this.e = { key: kp.privateKey, pub: new Uint8Array(await subtle.exportKey("raw", kp.publicKey)) };
      }
      await this.mixHash(this.e.pub);
      await this.mixKey(await dh(this.e, this.rs));        // es
      await this.mixKey(await dh(this.s, this.rs));        // ss
      return cat(this.e.pub, await this.encryptAndHash(payload));
    }
    async readMessage2(msg) {
      const re = msg.slice(0, 32);
      await this.mixHash(re);
      await this.mixKey(await dh(this.e, re));             // ee
      await this.mixKey(await dh(this.s, re));             // se
      const payload = await this.decryptAndHash(msg.slice(32));
      const [k1, k2] = await hkdf(this.ck, new Uint8Array(0));   // Split
      this.send = new CipherState(k1); this.recv = new CipherState(k2);
      return payload;
    }
  }

  // ---- application framing: a message is cut into chunks of flag byte + data, each its own Noise message ----
  async function seal(send, msg) {
    const out = [];
    for (let i = 0; i === 0 || i < msg.length; i += CHUNK) {
      const part = msg.subarray(i, i + CHUNK);
      out.push(await send.encrypt(new Uint8Array(0), cat(Uint8Array.of(i + CHUNK >= msg.length ? 1 : 0), part)));
    }
    return out;
  }
  function pack(meta, body) {
    const j = te.encode(JSON.stringify(meta)); const h = new Uint8Array(4);
    new DataView(h.buffer).setUint32(0, j.length);
    return cat(h, j, body || new Uint8Array(0));
  }
  function unpack(msg) {
    const n = new DataView(msg.buffer, msg.byteOffset).getUint32(0);
    if (n > msg.length - 4) throw new Error("bad message");
    return [JSON.parse(td.decode(msg.subarray(4, 4 + n))), msg.subarray(4 + n)];
  }

  class TunnelError extends Error { constructor(code) { super(code); this.code = code; } }

  // ---- the connection ----
  class Tunnel {
    constructor(bundle, opts = {}) {
      this.b = typeof bundle === "string" ? parseQr(bundle) : bundle;
      this.WS = opts.WebSocket || root.WebSocket;
      this.pending = new Map(); this.nextId = 1; this.tx = Promise.resolve(); this.rx = Promise.resolve(); this.buf = [];
      this.open = false;
    }
    async connect() {
      const b = this.b, d = b.device;
      const url = b.relay.replace(/^http/, "ws").replace(/\/$/, "") + "/v1/client/" + b.host_id;
      const ws = this.ws = new this.WS(url);
      ws.binaryType = "arraybuffer";
      const hello = new Promise((res, rej) => { this.onHello = { res, rej }; });
      ws.onopen = () => ws.send(JSON.stringify({ t: "hello", ticket: b.ticket }));
      ws.onerror = () => this.onHello && this.onHello.rej(new TunnelError("relay_unreachable"));
      ws.onclose = () => { this.open = false; this.failAll(this.lastError || "closed"); if (this.onHello) this.onHello.rej(new TunnelError(this.lastError || "closed")); };
      ws.onmessage = (ev) => { this.rx = this.rx.then(() => this.onMessage(ev.data)).catch((e) => this.fatal(e)); };
      await hello;                                           // relay said "ready" (ticket accepted, hub online)
      this.noise = new NoiseKKInitiator(unhex(d.priv), unhex(b.hub_pub),
        te.encode(`whyscope-v1|${b.host_id}|${d.id}`), this.testEphemeral);
      await this.noise.start();
      this.shake = new Promise((res, rej) => { this.onShake = { res, rej }; });
      ws.send(await this.noise.writeMessage1());
      await this.shake;
      this.open = true;
    }
    fatal(e) { this.lastError = this.lastError || "protocol_error"; try { this.ws.close(); } catch (_) {} }
    failAll(code) { for (const p of this.pending.values()) p.rej(new TunnelError(code)); this.pending.clear(); }
    async onMessage(data) {
      if (typeof data === "string") {
        const m = JSON.parse(data);
        if (m.t === "ready") { this.onHello.res(); this.onHello = null; }
        else if (m.t === "error") { this.lastError = m.error; if (this.onHello) { this.onHello.rej(new TunnelError(m.error)); this.onHello = null; } }
        return;
      }
      const frame = new Uint8Array(data);
      if (!this.noise.recv) { await this.noise.readMessage2(frame); this.onShake.res(); return; }
      const pt = await this.noise.recv.decrypt(new Uint8Array(0), frame);
      this.buf.push(pt.subarray(1));
      if (this.buf.reduce((n, x) => n + x.length, 0) > MAX_MESSAGE) throw new Error("message too large");
      if (pt[0] !== 1) return;
      const [meta, body] = unpack(cat(...this.buf)); this.buf = [];
      const p = this.pending.get(meta.id);
      if (p) { this.pending.delete(meta.id); p.res([meta, body]); }
    }
    request(method, path, headers, body) {
      const id = this.nextId++;
      const reply = new Promise((res, rej) => this.pending.set(id, { res, rej }));
      const msg = pack({ id, method, path, headers }, body);
      // sealing and sending are serialised so Noise nonces go out in order
      this.tx = this.tx.then(async () => { for (const f of await seal(this.noise.send, msg)) this.ws.send(f); }).catch((e) => this.fatal(e));
      return reply;
    }
    close() { try { this.ws.close(); } catch (_) {} }
  }

  function parseQr(s) { return JSON.parse(td.decode(unb64u(s.replace(/^WSP1:/, "")))); }

  // ---- tunnelFetch: fetch() over the tunnel ----
  let bundle = null, tunnel = null;
  function setBundle(b, persist) {           // persist=false: the caller (hub/static/conn.js) keeps the bundle itself
    bundle = typeof b === "string" ? parseQr(b) : b;
    if (tunnel) tunnel.close();
    tunnel = null;
    if (persist !== false) try { localStorage.setItem("whyscope_bundle", JSON.stringify(bundle)); } catch (_) {}
  }
  function getBundle() {
    if (!bundle) try { bundle = JSON.parse(localStorage.getItem("whyscope_bundle")); } catch (_) {}
    return bundle;
  }
  const errResponse = (status, code) => new Response(JSON.stringify({ error: code, detail: code }), { status, headers: { "content-type": "application/json" } });

  async function toBytes(body, headers) {
    if (body == null) return new Uint8Array(0);
    if (typeof body === "string") return te.encode(body);
    if (body instanceof Uint8Array) return body;
    if (body instanceof ArrayBuffer) return new Uint8Array(body);
    const r = new Request("http://x.invalid/", { method: "POST", body });   // Blob, FormData, URLSearchParams
    const ct = r.headers.get("content-type");
    if (ct && !headers["content-type"]) headers["content-type"] = ct;
    return new Uint8Array(await r.arrayBuffer());
  }

  async function tunnelFetch(path, options = {}) {
    const b = getBundle();
    if (!b) return errResponse(401, "not_paired");
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        if (!tunnel || !tunnel.open) { tunnel = new Tunnel(b); await tunnel.connect(); }
        const headers = {};
        new Headers(options.headers || {}).forEach((v, k) => { headers[k] = v; });
        const body = await toBytes(options.body, headers);
        const [meta, out] = await tunnel.request((options.method || "GET").toUpperCase(), path, headers, body);
        const nullBody = [101, 204, 205, 304].includes(meta.status);
        return new Response(nullBody ? null : out, { status: meta.status, headers: meta.headers });
      } catch (e) {
        tunnel = null;
        const code = e.code || "relay_unreachable";
        if (code === "hub_offline") return errResponse(503, "hub_offline");        // clear message for the UI
        if (code === "unauthorized") return errResponse(401, "unauthorized");      // revoked, expired or unknown device
        if (attempt === 1 || code === "protocol_error") return errResponse(503, code);
      }
    }
  }

  const api = { Tunnel, TunnelError, NoiseKKInitiator, tunnelFetch, setBundle, parseQr, seal, pack, unpack, hex, unhex, b64u };
  root.WhyscopeTunnel = api;
  root.tunnelFetch = tunnelFetch;
  if (typeof module !== "undefined") module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
