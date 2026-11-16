# Whyscope encrypted relay

The hub (laptop + ASUS UGen300) stays at home. The child's device (wand or phone browser, later an app) and the parent's
phone reach it from anywhere through a small relay on the internet. The relay forwards ciphertext it cannot read. The hub
connects OUT to the relay, so the home router needs no port forwarding.

```
 device (browser/app)                relay (Cloudflare Worker + Durable Object)              hub (home)
 hub/static/tunnel.js   --wss-->   /v1/client/<hubId>   <opaque frames>   /v1/host/<hubId>  <--wss--   hub/tunnel.py
        '------------- Noise_KK end-to-end channel (the relay is not a party) -----------------'   -> http://127.0.0.1:8000
```

## Files

| File | Role |
|---|---|
| `relay/src/hub.js` | relay core, one instance per hub (auth, forwarding, limits, revocation). Runs in a Durable Object or in Node |
| `relay/src/index.js`, `relay/wrangler.toml` | Cloudflare Worker + Durable Object glue |
| `relay/node-server.js` | the same core as a plain Node server (VPS, Docker, local tests) |
| `hub/tunnel.py` | hub side: outbound WebSocket, Noise sessions, forwarding to the local hub; CLI `pair`, `revoke`, `list`; `TunnelClient` for tests |
| `hub/static/tunnel.js`, `tunnel-test.html` | browser client: `tunnelFetch(path, options)`; test page at `/static/tunnel-test.html` |
| `relay/test/` | `tunnel.test.js` (JS, known-answer), `test_tunnel.py` (Python unit), `e2e.py` (everything through a live relay), `kat.json` |

## Protocol

**Identities.** The hub has an Ed25519 key (signs relay logins and device tickets) and an X25519 static key (Noise).
The hub id is `hex(SHA-256(Ed25519 public key))[:32]`, so a hub id cannot be squatted: whoever registers it must hold the key.
Each device has its own X25519 static key, created at pairing.

**Pairing (same room).** `python -m hub.tunnel pair --device "Wand" [--role kid|parent]` prints a JSON bundle and a QR-ready string
`WSP1:<base64url json>`: hub X25519 public key, relay URL, hub id, the device's id and keypair, and a relay ticket. The
bundle contains the device's private key, so it is shown only to that device. A `kid` device is limited by the hub to the
child endpoints (ask, reply, healthz, language, memory read, static); `parent` can use the whole API.

**Hub login.** WebSocket `/v1/host/<hubId>`. The relay sends a random nonce; the hub answers
`{pub, sig = Ed25519(whyscope-host-v1|hubId|nonce)}`. The relay checks that `hubId` is the hash of `pub`, that `pub` equals
the key stored on first registration (trust on first use, then pinned), and the signature.

**Device login.** WebSocket `/v1/client/<hubId>`; the first message is `{ticket}` (never in the URL, so it is not in access logs).
A ticket is `v1.<b64url {d: deviceId, e: expiry}>.<b64url Ed25519 signature by the hub>`, valid 365 days. The relay verifies the
signature with the stored hub key, expiry and the revocation list, then tells the hub `{t:"open", c:<connection id>, dev}` and the
device `{t:"ready"}`. If the hub is not connected the device gets `{t:"error", error:"hub_offline"}` (after the ticket check, so
strangers learn nothing).

**Forwarding.** Device to relay: binary frames. Hub to relay: binary frames prefixed with the 4-byte connection id the relay
assigned. The relay strips or adds the id and passes the bytes on. Control messages are JSON text frames (`open`, `close`,
`revoke`, `error`). Frames are at most about 70 KB; per connection about 100 frames/s and 1 MB/s (burst 4 MB, so a 1 MB audio upload
fits); 8 simultaneous devices per hub. Violations close that connection only.

**Encryption.** `Noise_KK_25519_AESGCM_SHA256` (X25519, AES-256-GCM, SHA-256, HKDF), pattern `-> e, es, ss` / `<- e, ee, se`,
device = initiator, hub = responder, both static keys known from pairing. Prologue `whyscope-v1|hubId|deviceId`. Forward secrecy
from the ephemeral keys, mutual authentication from the static keys. Hub: the vetted `noiseprotocol` package. Browser: Noise written
directly on WebCrypto (X25519, AES-GCM, HMAC), checked byte for byte against `noiseprotocol` (`relay/test/kat.json`). The channel is
independent of TLS.

**Application layer (inside the channel).** A message is `u32 header length | JSON header | raw body`. Request header
`{id, method, path, headers}`, response header `{id, status, headers}`, body bytes raw (no base64). A message is cut into
chunks of at most 65,518 plaintext bytes (Noise limit 65,535), each prefixed with a flag byte (1 = last chunk), each its own
Noise message. Maximum message 3 MB. Requests are handled concurrently (matched by `id`); the hub forwards them to
`http://127.0.0.1:8000` unchanged and does not forward `Host`, `Content-Length` or hop-by-hop headers.

**Revocation.** `python -m hub.tunnel revoke --device "Lost phone"` removes the device's key from the hub (so no Noise handshake
can succeed for it any more) and adds its id to `revoked.json`. A running tunnel notices within a second, pushes the list
to the relay, which stores it, cuts that device's live connections and refuses its ticket from then on.

## Threat model

| Who | Can | Cannot |
|---|---|---|
| Relay operator or Cloudflare (honest-but-curious or breached) | see hub id, device ids, connection times, frame sizes and timing, IP addresses; drop or delay frames (denial of service) | read or alter any request or response (AEAD); impersonate the hub or a device (no static keys); learn what was asked |
| Network attacker on any link | the same as above, less | anything, even if TLS is stripped: the Noise layer is the real protection |
| Stranger who finds a hub id | try to connect | pass the ticket check; with a stolen ticket still fail the Noise handshake without the device key |
| Stolen or lost device | use its keys until revoked | after `revoke`: connect (ticket refused, hub has no key) |
| Malicious relay or active attacker who replays or reorders frames | break the session | decrypt anything: Noise nonces reject replay, reordering and tampering, and the hub drops that session |
| Someone who gets the hub's data folder | everything | (the keys live in `<data>/tunnel/`; protect that folder like the database) |

Not protected: traffic analysis (sizes and timing of questions and answers leak a little, e.g. an audio upload is roughly
1 MB); availability; a compromised device or hub. The relay stores only the hub public key and the list of revoked device ids.
Debug mode (`DEBUG_FRAMES=1` / `--debug`) logs frame sizes only; the test `relay/test/e2e.py` greps the captured log and state
for the question text and answer text and finds nothing.

## What the relay sees

Hub id (a hash), device id (random), when each connects and disconnects, IP addresses (as any server does), number and size of
frames, and timing. Never: question text, answers, audio, images, headers, URLs or paths, device names, roles, child's name.

## Run locally

```
cd relay && npm install
node node-server.js --port 8787 --debug          # Node host of the relay core (same code as the Worker)
npx wrangler dev --ip 127.0.0.1 --port 8787       # or the real Worker runtime (WRANGLER_SEND_METRICS=false)
cd .. && C:\whyscope-venv\Scripts\python.exe -m hub.tunnel --relay ws://127.0.0.1:8787
C:\whyscope-venv\Scripts\python.exe -m hub.tunnel pair --device Wand     # paste into /static/tunnel-test.html
```

Tests: `cd relay && npm test` (JS), `python -m unittest relay.test.test_tunnel` and `python relay/test/e2e.py` from the repo root
(needs the hub on :8000). Python packages: `noiseprotocol`, `cryptography`, `websockets` (+ `httpx`, already used).

## Deploy to Cloudflare later (account steps for the team)

1. Create a Cloudflare account (free plan works: Workers and SQLite-backed Durable Objects are on the free plan; check current limits).
2. `cd relay && npx wrangler login` (a person does this in a browser; accept Cloudflare's terms there).
3. `npx wrangler deploy` creates the Worker `whyscope-relay` and the `Hub` Durable Object (migration `v1` is in `wrangler.toml`).
   The URL is `https://whyscope-relay.<account>.workers.dev`; a custom domain is optional.
4. On the hub: `python -m hub.tunnel --relay wss://whyscope-relay.<account>.workers.dev` (saved), then pair devices again
   (bundles contain the relay URL). Run the tunnel at boot (scheduled task or service) next to the hub.
5. Before real families: set up usage alerts, keep `DEBUG_FRAMES` at `0`, and read Cloudflare's WebSocket and Durable Object limits.
   Hibernation is not used: a connected hub keeps its Durable Object active (duration billing), which matters at scale. Moving
   to the WebSocket Hibernation API is the first optimisation (see below).

## Moving the relay elsewhere (any VPS, Docker)

The relay holds no content and no decryption keys, so moving it loses nothing but the pinned hub keys, which a hub re-registers on
first connect (and the revocation list, which the hub pushes on every connect). To move: run `node node-server.js` anywhere
(Node 20+; `--port`, `--host 0.0.0.0`, `--state /data/relay-state.json`), put it behind TLS (Caddy or nginx with WebSocket
proxying), then `python -m hub.tunnel --relay wss://new.example` and re-pair (or edit the relay URL in bundles). A minimal image:

```
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src ./src
COPY node-server.js ./
ENV HOST=0.0.0.0 PORT=8787 RELAY_STATE=/data/relay-state.json
VOLUME /data
CMD ["node", "node-server.js"]
```

The Node host keeps hub state in one process, so run exactly one instance.

## Known limits and next steps

- `wrangler dev` could not be run on the development laptop (Windows Application Control blocks `workerd.exe`), so the relay core
  was tested through `node-server.js`. The Worker glue (`src/index.js`, about 30 lines) and WebCrypto Ed25519 inside workerd are
  untested until the first `wrangler dev` or deploy on a machine that allows it.
- Tickets last 365 days and there is no renewal yet. A renewal call inside the channel is the natural next step.
- The relay has no per-hub quota beyond the per-connection limits; add per-hub daily byte caps before opening to many families.
- The QR image and pairing UI are a later step; the bundle string is QR-ready (about 900 characters).
- Replace the pinned-key trust-on-first-use by deployment-time registration if the relay ever hosts hubs for strangers.

## Pairing from the app (2026-11-15)

The hub now creates the relay bundles itself: the QR codes on the setup page and on the parent page (add wand / invite parent) carry
the `pair --role kid|parent` bundle, so one scan works at home and away. Run `python -m hub.tunnel --relay ws://...` once (it saves the
relay URL) and keep the tunnel running; revoking a device on the parent page revokes its relay key. The tunnel marks forwarded
requests (`x-whyscope-via`, `x-whyscope-tunnel-dev`) so the hub treats them as remote and binds a token to its relay device.
