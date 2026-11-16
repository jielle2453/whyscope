/* Whyscope connection layer, shared by kid.html, parent.html and pair.html. Classic script, no dependencies.
 *
 *   <script src="/static/conn.js" data-role="wand"></script>          (role: "wand" or "parent")
 *   const r = await WhyConn.fetch("/api/ask", {method: "POST", body: fd});   // fetch(), with the token, over the best route
 *
 * Route: the page keeps the hub's LAN address, its device token and (if the hub has a relay) the relay pairing bundle in
 * localStorage (one record per role, so a parent phone and a wand do not overwrite each other). Each call goes DIRECT to the
 * LAN address when that answers a ping within ~300 ms; otherwise through the encrypted relay with tunnelFetch
 * (hub/static/tunnel.js); if neither works the call fails with `response.offline === true` and the page can keep the
 * question in the curiosity jar (an IndexedDB queue below). The mode is shown as a small badge: Home / Away (encrypted) /
 * Offline (and "Not paired" / "Revoked" when the hub says no).
 */
(function (root) {
  "use strict";
  const script = document.currentScript;
  const ROLE = (script && script.dataset.role) || "parent";
  const PROBE_MS = 300, PROBE_TTL = 8000, PING_EVERY = 10000;
  const keyOf = (role) => "whyscope_" + role;

  const LABELS = {
    en: { home: "Home", away: "Away (encrypted)", offline: "Offline", connecting: "Connecting", unpaired: "Not paired", revoked: "Revoked" },
    zh: { home: "在家", away: "外出（加密）", offline: "離線", connecting: "連線中", unpaired: "尚未配對", revoked: "已撤銷" },
  };
  let lang = "en", mode = "connecting", cfg = null, route = null, probedAt = 0, bundleSet = null;
  const listeners = [], badges = [];

  function read(role) { try { return JSON.parse(localStorage.getItem(keyOf(role))) || null; } catch (e) { return null; } }
  function store(role, c) { try { localStorage.setItem(keyOf(role), JSON.stringify(c)); } catch (e) {} }
  cfg = read(ROLE);

  function parseBundle(s) {
    if (!s) return null;
    if (typeof s === "object") return s;
    try {
      const b = s.replace(/^WSP1:/, "").replace(/-/g, "+").replace(/_/g, "/");
      return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b + "=".repeat((4 - (b.length % 4)) % 4)), (c) => c.charCodeAt(0))));
    } catch (e) { return null; }
  }

  function label() { return (LABELS[lang] || LABELS.en)[mode] || mode; }
  function paint() {
    badges.forEach((el) => { el.textContent = label(); el.dataset.mode = mode; el.setAttribute("aria-label", label()); });
  }
  function setMode(m) {
    if (m === mode) return;
    mode = m; paint();
    listeners.forEach((f) => { try { f(m); } catch (e) {} });
  }

  async function withTimeout(url, opts, ms) {
    const ac = new AbortController(), t = setTimeout(() => ac.abort(), ms);
    try { return await fetch(url, Object.assign({}, opts, { signal: ac.signal })); } finally { clearTimeout(t); }
  }
  const base = () => (cfg && cfg.hub ? cfg.hub.replace(/\/$/, "") : location.origin);
  const authHeaders = () => (cfg && cfg.token ? { Authorization: "Bearer " + cfg.token } : {});

  // does the LAN address answer within ~300 ms? (any HTTP answer counts, even a 401: the hub is there)
  async function probeHome() {
    try { const r = await withTimeout(base() + "/api/ping", { cache: "no-store", headers: authHeaders() }, PROBE_MS); return r.status < 500; }
    catch (e) { return false; }
  }

  function offlineResponse(why) {
    const r = new Response(JSON.stringify({ detail: "offline", why: why || "" }), { status: 503, headers: { "content-type": "application/json" } });
    r.offline = true;
    return r;
  }
  function seen(resp, via) {
    if (resp.status === 401) setMode(cfg && cfg.token ? "revoked" : "unpaired");   // the hub says no: revoked token / no token
    else setMode(via);
    return resp;
  }

  async function tunnel(path, opts) {
    if (!cfg || !cfg.bundle || !root.tunnelFetch || !root.isSecureContext) return null;   // WebCrypto X25519 needs a secure context
    if (bundleSet !== cfg.bundle) { root.WhyscopeTunnel.setBundle(cfg.bundle, false); bundleSet = cfg.bundle; }
    const r = await root.tunnelFetch(path, opts);
    if (r && r.status === 503) return null;                      // relay unreachable / hub offline / protocol error
    if (r && r.status === 401 && cfg.token) {                     // the relay refused this device's key (revoked) ...
      const j = await r.clone().json().catch(() => ({}));
      if (j.error === "unauthorized") return r;
    }
    return r;
  }

  async function doFetch(path, opts) {
    opts = Object.assign({}, opts || {});
    const h = new Headers(opts.headers || {});
    if (cfg && cfg.token) h.set("Authorization", "Bearer " + cfg.token);
    if (opts.pin) { h.set("X-Whyscope-Pin", opts.pin); delete opts.pin; }
    opts.headers = h;
    if (!opts.cache) opts.cache = "no-store";
    // 1. home: the LAN address, if it answered a ping recently (or answers one now)
    if (route === null || Date.now() - probedAt > PROBE_TTL) { route = (await probeHome()) ? "home" : "away"; probedAt = Date.now(); }
    if (route === "home") {
      try { return seen(await fetch(base() + path, opts), "home"); }
      catch (e) { route = "away"; probedAt = Date.now(); }
    }
    // 2. away: the encrypted relay
    try {
      const r = await tunnel(path, opts);
      if (r) return seen(r, "away");
    } catch (e) { /* fall through */ }
    // 3. the LAN address once more (the ping may just have been slow), then give up
    if (route !== "home") {
      try { const r = await withTimeout(base() + path, opts, 4000); route = "home"; probedAt = Date.now(); return seen(r, "home"); } catch (e) { /* offline */ }
    }
    route = null;
    setMode("offline");
    return offlineResponse();
  }

  // ---- the curiosity jar: questions a wand could not send, kept on the device (text + small audio) ----
  const jar = (function () {
    const mem = [];
    let dbp = null;
    function open() {
      if (dbp) return dbp;
      dbp = new Promise((res) => {
        try {
          const rq = indexedDB.open("whyscope_jar", 1);
          rq.onupgradeneeded = () => rq.result.createObjectStore("q", { keyPath: "id", autoIncrement: true });
          rq.onsuccess = () => res(rq.result);
          rq.onerror = () => res(null);
        } catch (e) { res(null); }
      });
      return dbp;
    }
    const tx = async (m, f) => {
      const db = await open();
      if (!db) return null;
      return new Promise((res) => {
        try { const t = db.transaction("q", m), s = t.objectStore("q"), rq = f(s); t.oncomplete = () => res(rq && rq.result !== undefined ? rq.result : true); t.onerror = t.onabort = () => res(null); }
        catch (e) { res(null); }
      });
    };
    return {
      MAX: 20, MAX_AUDIO: 400 * 1024,
      async add(item) { if ((await this.count()) >= this.MAX) return false; const ok = await tx("readwrite", (s) => s.add(item)); if (ok === null) { mem.push(Object.assign({ id: Date.now() }, item)); } return true; },
      async list() { const r = await tx("readonly", (s) => s.getAll()); return (r && r !== true ? r : []).concat(mem).sort((a, b) => (a.ts < b.ts ? -1 : 1)); },
      async remove(id) { const i = mem.findIndex((x) => x.id === id); if (i >= 0) mem.splice(i, 1); else await tx("readwrite", (s) => s.delete(id)); },
      async count() { return (await this.list()).length; },
    };
  })();

  const api = {
    ROLE,
    fetch: doFetch,
    jar,
    parseBundle,
    store, read,
    cfg: () => cfg,
    save(c) { cfg = Object.assign({}, cfg || {}, c); store(ROLE, cfg); route = null; bundleSet = null; },
    clear() { try { localStorage.removeItem(keyOf(ROLE)); } catch (e) {} cfg = null; route = null; },
    get mode() { return mode; },
    get kind() { return cfg && cfg.token ? ROLE : "dev"; },
    onMode(f) { listeners.push(f); },
    setLang(l) { lang = l === "zh" ? "zh" : "en"; paint(); },
    label,
    badge(el) { for (let i = badges.length - 1; i >= 0; i--) if (!badges[i].isConnected) badges.splice(i, 1); if (el && !badges.includes(el)) badges.push(el); paint(); },
    /** Re-check the route now (the badge follows). */
    async ping() { route = null; return doFetch("/api/ping"); },
    start() {
      api.ping();
      setInterval(() => { if (!document.hidden) api.ping(); }, PING_EVERY);
      root.addEventListener("online", () => api.ping());
    },
  };
  root.WhyConn = api;
})(window);
