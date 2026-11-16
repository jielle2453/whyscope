"""Encrypted tunnel from the home hub to paired devices through the Whyscope relay (docs/relay.md).

The hub dials OUT to the relay (WebSocket /v1/host/<hostId>) and, for every device the relay announces, runs a
Noise_KK_25519_AESGCM_SHA256 handshake (static keys exchanged at pairing, ephemeral keys per session). Decrypted requests
{id, method, path, headers, body} are forwarded to the local hub (http://127.0.0.1:8000) and the response is sent back
encrypted. The relay only ever sees opaque frames.

CLI (run from the repo root):
  python -m hub.tunnel --relay ws://127.0.0.1:8787              run the tunnel
  python -m hub.tunnel pair --device "Wand" [--role kid|parent]  print a pairing bundle (JSON + QR-ready string)
  python -m hub.tunnel revoke --device "Wand"                    revoke a device (a running tunnel picks it up)
  python -m hub.tunnel list
Keys live in <data folder>/tunnel/ (the folder of the database path in config.yaml). Private keys are never printed,
except the device's own key inside a pairing bundle (that is how it reaches the device).
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import random
import secrets
import struct
import sys
import time
from pathlib import Path

import httpx
import websockets
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from noise.connection import Keypair, NoiseConnection

PROTOCOL = b"Noise_KK_25519_AESGCM_SHA256"
NOISE_MAX = 65535
CHUNK = NOISE_MAX - 16 - 1          # plaintext bytes per Noise message (1 byte is the "final chunk" flag)
MAX_MESSAGE = 3 * 1024 * 1024       # largest request/response body accepted (audio uploads are about 1 MB)
TICKET_DAYS = 365
KID_ALLOWED = [("POST", "/api/ask"), ("GET", "/api/ask/"), ("POST", "/api/reply"), ("GET", "/healthz"),
               ("GET", "/api/settings"), ("POST", "/api/settings"), ("GET", "/api/memory"), ("GET", "/static/"),
               ("GET", "/api/ping"), ("GET", "/api/me"), ("GET", "/api/deliveries"), ("POST", "/api/deliveries/")]
# (the hub's own auth, hub/auth.py, is stricter still: a wand token reaches only its child's ask / reply / deliveries)
VIA_HEADER, DEV_HEADER = "x-whyscope-via", "x-whyscope-tunnel-dev"   # set here on every forwarded request; never taken from a device
DROP_REQ_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "accept-encoding", VIA_HEADER, DEV_HEADER}
DROP_RESP_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive", "date", "server"}


# ---------------------------------------------------------------- small helpers
def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def raw_pub(k) -> bytes:
    return k.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)


def raw_priv(k) -> bytes:
    return k.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())


def host_id_of(ed_pub: bytes) -> str:
    """The hub id is the first 16 bytes of SHA-256(hub Ed25519 public key): self-certifying, cannot be squatted."""
    return hashlib.sha256(ed_pub).hexdigest()[:32]


def sign_ticket(ed_priv: ed25519.Ed25519PrivateKey, host_id: str, device_id: str, days=TICKET_DAYS) -> str:
    body = b64u(json.dumps({"d": device_id, "e": int(time.time() + days * 86400)}, separators=(",", ":")).encode())
    return f"v1.{body}." + b64u(ed_priv.sign(f"whyscope-ticket-v1|{host_id}|{body}".encode()))


def prologue(host_id: str, device_id: str) -> bytes:
    return f"whyscope-v1|{host_id}|{device_id}".encode()


# ---------------------------------------------------------------- Noise channel + framing
class Channel:
    """One Noise_KK session. `initiator` is the device; the hub is the responder."""

    def __init__(self, initiator: bool, my_static: bytes, their_static: bytes, pro: bytes):
        n = NoiseConnection.from_name(PROTOCOL)
        (n.set_as_initiator if initiator else n.set_as_responder)()
        n.set_keypair_from_private_bytes(Keypair.STATIC, my_static)
        n.set_keypair_from_public_bytes(Keypair.REMOTE_STATIC, their_static)
        n.set_prologue(pro)
        n.start_handshake()
        self.n, self.initiator, self.buf = n, initiator, bytearray()

    @property
    def ready(self) -> bool:
        return self.n.handshake_finished

    def hello(self) -> bytes:               # initiator: -> e, es, ss
        return self.n.write_message(b"")

    def accept(self, frame: bytes) -> bytes:   # responder: reads -> e, es, ss and answers <- e, ee, se
        self.n.read_message(frame)
        return self.n.write_message(b"")

    def finish(self, frame: bytes):         # initiator: reads the answer
        self.n.read_message(frame)

    def seal(self, msg: bytes) -> list:
        """One application message -> Noise frames (each plaintext chunk = flag byte + data, flag 1 = last chunk)."""
        parts = [msg[i:i + CHUNK] for i in range(0, len(msg), CHUNK)] or [b""]
        return [self.n.encrypt(bytes([i == len(parts) - 1]) + p) for i, p in enumerate(parts)]

    def feed(self, frame: bytes):
        """Decrypt one frame; returns the complete message when the last chunk arrived, else None."""
        pt = self.n.decrypt(frame)
        if not pt:
            raise ValueError("empty chunk")
        self.buf += pt[1:]
        if len(self.buf) > MAX_MESSAGE:
            raise ValueError("message too large")
        if pt[0] == 1:
            m, self.buf = bytes(self.buf), bytearray()
            return m
        return None


def pack(meta: dict, body: bytes = b"") -> bytes:
    j = json.dumps(meta, separators=(",", ":")).encode()
    return struct.pack(">I", len(j)) + j + body


def unpack(msg: bytes):
    n = struct.unpack(">I", msg[:4])[0]
    if n > len(msg) - 4:
        raise ValueError("bad message")
    return json.loads(msg[4:4 + n]), msg[4 + n:]


# ---------------------------------------------------------------- key store
class Store:
    def __init__(self, folder=None):
        folder = folder or os.environ.get("WHYSCOPE_TUNNEL_DIR")      # the env var is for tests
        if folder is None:
            from .config import load_config, resolve
            folder = resolve(load_config(), "db").parent / "tunnel"
        self.dir = Path(folder)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.host = self._load_host()
        self.ed = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.host["ed_priv"]))
        self.xk = bytes.fromhex(self.host["x_priv"])
        self.host_id = host_id_of(raw_pub(self.ed))

    def _write(self, name, obj):
        p = self.dir / name
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1)

    def _read(self, name, default):
        try:
            return json.loads((self.dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _load_host(self):
        h = self._read("host.json", None)
        if not h:
            h = {"ed_priv": raw_priv(ed25519.Ed25519PrivateKey.generate()).hex(),
                 "x_priv": raw_priv(x25519.X25519PrivateKey.generate()).hex(), "relay": ""}
            self._write("host.json", h)
        return h

    @property
    def relay(self):
        return self.host.get("relay", "")

    def set_relay(self, url):
        self.host["relay"] = url
        self._write("host.json", self.host)

    @property
    def x_pub(self) -> bytes:
        return raw_pub(x25519.X25519PrivateKey.from_private_bytes(self.xk))

    @property
    def ed_pub(self) -> bytes:
        return raw_pub(self.ed)

    def devices(self) -> dict:
        return self._read("devices.json", {})

    def revoked(self) -> list:
        return self._read("revoked.json", [])

    def pair(self, name, role="parent", relay=None) -> dict:
        priv = x25519.X25519PrivateKey.generate()
        dev_id = secrets.token_hex(8)
        devs = self.devices()
        devs[dev_id] = {"name": name, "role": role, "pub": raw_pub(priv).hex(), "created": int(time.time())}
        self._write("devices.json", devs)
        return {"v": 1, "relay": relay or self.relay, "host_id": self.host_id, "hub_pub": self.x_pub.hex(),
                "device": {"id": dev_id, "name": name, "role": role, "priv": raw_priv(priv).hex(), "pub": raw_pub(priv).hex()},
                "ticket": sign_ticket(self.ed, self.host_id, dev_id)}

    def revoke(self, name_or_id) -> list:
        devs, rev, hit = self.devices(), self.revoked(), []
        for d, v in list(devs.items()):
            if name_or_id in (d, v["name"]):
                hit.append(d)
                del devs[d]
                rev.append(d)
        self._write("devices.json", devs)
        self._write("revoked.json", sorted(set(rev)))
        return hit


def qr_string(bundle: dict) -> str:
    return "WSP1:" + b64u(json.dumps(bundle, separators=(",", ":")).encode())


def parse_qr_string(s: str) -> dict:
    return json.loads(unb64u(s.split(":", 1)[1]))


# ---------------------------------------------------------------- the hub side
def allowed(role: str, method: str, path: str, body: bytes) -> bool:
    if not path.startswith("/") or path.startswith("//") or ".." in path or "\\" in path:
        return False
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return False
    if role != "kid":
        return True
    p = path.split("?")[0]
    if not any(m == method and (p == pre or (pre.endswith("/") and p.startswith(pre))) for m, pre in KID_ALLOWED):
        return False
    if p == "/api/settings" and method == "POST":      # a child device may only change the language
        try:
            return set(json.loads(body or b"{}")) <= {"language"}
        except ValueError:
            return False
    return True


class Tunnel:
    def __init__(self, store: Store, relay: str, hub_url="http://127.0.0.1:8000", debug=False):
        self.store, self.relay, self.hub_url, self.debug = store, relay.rstrip("/"), hub_url.rstrip("/"), debug
        self.sessions = {}      # relay connection id -> (Channel, device record, asyncio.Lock)
        self.http = None
        self.ws = None

    def log(self, *a):
        print("[tunnel]", *a, file=sys.stderr, flush=True)

    async def run(self):
        self.http = httpx.AsyncClient(base_url=self.hub_url, timeout=60)
        delay = 1.0
        while True:
            try:
                await self.once()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log(f"relay connection lost ({type(e).__name__}: {e}); retry in {delay:.0f}s")
            await asyncio.sleep(delay * (0.5 + random.random()))
            delay = min(delay * 2, 30)

    async def once(self):
        url = f"{self.relay}/v1/host/{self.store.host_id}"
        async with websockets.connect(url, max_size=1 << 17, ping_interval=20) as ws:
            ch = json.loads(await ws.recv())
            msg = f"whyscope-host-v1|{self.store.host_id}|{ch['nonce']}".encode()
            await ws.send(json.dumps({"t": "hello", "pub": self.store.ed_pub.hex(), "sig": self.store.ed.sign(msg).hex()}))
            ok = json.loads(await ws.recv())
            if ok.get("t") != "ok":
                raise RuntimeError(f"relay refused the hub: {ok}")
            self.ws, self.sessions = ws, {}
            self.log("connected to relay as hub", self.store.host_id)
            watcher = asyncio.create_task(self.watch_revocations())
            try:
                async for m in ws:
                    if isinstance(m, str):
                        await self.on_text(json.loads(m))
                    else:
                        await self.on_frame(struct.unpack(">I", m[:4])[0], m[4:])
            finally:
                watcher.cancel()
                self.ws = None

    async def watch_revocations(self):
        last = None
        while True:
            rev = self.store.revoked()
            if rev != last:
                last = rev
                await self.ws.send(json.dumps({"t": "revoke", "devices": rev}))
                for c, (_, dev, _) in list(self.sessions.items()):
                    if dev["id"] in rev:
                        self.sessions.pop(c, None)
            await asyncio.sleep(1)

    async def on_text(self, m):
        if m.get("t") == "open":
            dev_id = m["dev"]
            dev = self.store.devices().get(dev_id)
            if not dev or dev_id in self.store.revoked():
                self.log("refusing unknown or revoked device", dev_id)
                return await self.ws.send(json.dumps({"t": "close", "c": m["c"]}))
            ch = Channel(False, self.store.xk, bytes.fromhex(dev["pub"]), prologue(self.store.host_id, dev_id))
            self.sessions[m["c"]] = (ch, {**dev, "id": dev_id}, asyncio.Lock())
        elif m.get("t") == "close":
            self.sessions.pop(m["c"], None)

    async def drop(self, c):
        self.sessions.pop(c, None)
        await self.ws.send(json.dumps({"t": "close", "c": c}))

    async def on_frame(self, c, frame):
        s = self.sessions.get(c)
        if not s:
            return
        ch, dev, lock = s
        try:
            if not ch.ready:
                return await self.ws.send(struct.pack(">I", c) + ch.accept(frame))
            msg = ch.feed(frame)
        except Exception as e:       # bad handshake, bad ciphertext, oversize: end this session only
            self.log(f"session {c} dropped: {type(e).__name__}")
            return await self.drop(c)
        if msg is not None:
            asyncio.create_task(self.handle(c, ch, dev, lock, msg))

    async def handle(self, c, ch, dev, lock, msg):
        rid = None
        try:
            meta, body = unpack(msg)
            rid, method, path = meta["id"], meta["method"].upper(), meta["path"]
            if not allowed(dev["role"], method, path, body):
                status, headers, out = 403, {"content-type": "application/json"}, b'{"detail":"not allowed for this device"}'
            else:
                hdr = {k: v for k, v in (meta.get("headers") or {}).items() if k.lower() not in DROP_REQ_HEADERS}
                # the hub must know this came through the relay (so it never treats it as the hub machine itself) and from
                # which relay device: it only accepts that device's own paired token (hub/auth.py)
                hdr[VIA_HEADER], hdr[DEV_HEADER] = "tunnel", dev["id"]
                r = await self.http.request(method, path, headers=hdr, content=body or None)
                status, out = r.status_code, r.content
                headers = {k: v for k, v in r.headers.items() if k.lower() not in DROP_RESP_HEADERS}
            reply = pack({"id": rid, "status": status, "headers": headers}, out)
        except Exception as e:
            self.log(f"request failed: {type(e).__name__}")
            reply = pack({"id": rid, "status": 502, "headers": {"content-type": "application/json"}},
                         b'{"detail":"hub error"}')
        async with lock:             # Noise nonces must be used in send order
            if self.sessions.get(c, (None,))[0] is ch and self.ws:
                for f in ch.seal(reply):
                    await self.ws.send(struct.pack(">I", c) + f)


# ---------------------------------------------------------------- a Python client (tests, tools)
class TunnelError(Exception):
    pass


class TunnelClient:
    """Device side in Python: `async with TunnelClient(bundle) as t: await t.fetch("GET", "/healthz")`."""

    def __init__(self, bundle: dict):
        self.b, self.pending, self.ws, self.ch = bundle, {}, None, None
        self.lock, self.next = asyncio.Lock(), 1

    async def __aenter__(self):
        b = self.b
        self.ws = await websockets.connect(f"{b['relay'].rstrip('/')}/v1/client/{b['host_id']}", max_size=1 << 17)
        await self.ws.send(json.dumps({"t": "hello", "ticket": b["ticket"]}))
        ctl = json.loads(await self.ws.recv())
        if ctl.get("t") != "ready":
            await self.ws.close()
            raise TunnelError(ctl.get("error", "refused"))
        d = b["device"]
        self.ch = Channel(True, bytes.fromhex(d["priv"]), bytes.fromhex(b["hub_pub"]), prologue(b["host_id"], d["id"]))
        await self.ws.send(self.ch.hello())
        self.ch.finish(await self.ws.recv())
        self.task = asyncio.create_task(self._reader())
        return self

    async def __aexit__(self, *a):
        self.task.cancel()
        await self.ws.close()

    async def _reader(self):
        err = "closed"
        try:
            async for m in self.ws:
                if isinstance(m, str):
                    err = json.loads(m).get("error", "closed")
                    break
                msg = self.ch.feed(m)
                if msg is not None:
                    meta, body = unpack(msg)
                    fut = self.pending.pop(meta["id"], None)
                    if fut:
                        fut.set_result((meta["status"], meta["headers"], body))
        except Exception as e:
            err = type(e).__name__
        for fut in self.pending.values():
            if not fut.done():
                fut.set_exception(TunnelError(err))

    async def fetch(self, method, path, body=b"", headers=None, json_body=None):
        """Returns (status, headers, body bytes)."""
        if json_body is not None:
            body, headers = json.dumps(json_body).encode(), {**(headers or {}), "content-type": "application/json"}
        rid = self.next
        self.next += 1
        fut = self.pending[rid] = asyncio.get_running_loop().create_future()
        async with self.lock:
            for f in self.ch.seal(pack({"id": rid, "method": method, "path": path, "headers": headers or {}}, body)):
                await self.ws.send(f)
        return await fut


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m hub.tunnel", description=__doc__.split("\n")[0])
    ap.add_argument("--relay", help="relay URL, e.g. wss://relay.example.workers.dev or ws://127.0.0.1:8787 (saved for next time)")
    ap.add_argument("--host-id", help="optional; must equal the id derived from the hub key (printed at start)")
    ap.add_argument("--hub", default="http://127.0.0.1:8000", help="local hub URL")
    ap.add_argument("--debug", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("pair", help="print a pairing bundle for a new device")
    p.add_argument("--device", required=True)
    p.add_argument("--role", choices=["parent", "kid"], default="parent")
    p.add_argument("--relay", dest="relay2")
    r = sub.add_parser("revoke", help="revoke a device by name or id")
    r.add_argument("--device", required=True)
    sub.add_parser("list", help="list paired devices")
    a = ap.parse_args(argv)
    store = Store()
    if a.host_id and a.host_id != store.host_id:
        sys.exit(f"--host-id {a.host_id} does not match this hub's key (its id is {store.host_id})")
    if a.relay:
        store.set_relay(a.relay)
    if a.cmd == "pair":
        if a.relay2:
            store.set_relay(a.relay2)
        if not store.relay:
            sys.exit("no relay URL yet: pass --relay")
        bundle = store.pair(a.device, a.role)
        print(json.dumps(bundle, indent=1))
        print("\nQR string:\n" + qr_string(bundle))
        print("\nThis bundle contains the device's private key: show it only to that device, in the same room.", file=sys.stderr)
    elif a.cmd == "revoke":
        hit = store.revoke(a.device)
        print("revoked:", hit or "nothing matched")
    elif a.cmd == "list":
        rev = set(store.revoked())
        for d, v in store.devices().items():
            print(d, v["name"], v["role"])
        for d in rev:
            print(d, "(revoked)")
    else:
        if not store.relay:
            sys.exit("no relay URL yet: pass --relay")
        print(f"hub id {store.host_id}", flush=True)
        try:
            asyncio.run(Tunnel(store, store.relay, a.hub, a.debug).run())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
