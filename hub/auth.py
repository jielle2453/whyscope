"""Accounts, device tokens, PINs and pairing codes (docs/architecture.md, "Accounts and pairing").

* Every API call carries a device token (`Authorization: Bearer <token>`). Tokens are random 256-bit values, shown once
  (at pairing) and stored only as SHA-256 hashes. A device is a `wand` (bound to one child) or a `parent` (bound to a parent
  of one household). Revoking a device kills its token at once (and its relay key, see hub/tunnel.py).
* Parents have a PIN (scrypt, salted). Sensitive calls (export / clear data, revoke a device, settings, add a wand or invite a
  parent) need it again, sent as the `X-Whyscope-Pin` header. Five wrong PINs lock that parent for a minute.
* Pairing: a parent creates a one-time code (10 minutes) that is shown as a QR code; the scanning device redeems it once at
  POST /api/pair and receives its token. The QR also carries the hub's LAN URL and the relay pairing bundle (hub/tunnel.py).
* No token: refused, except on the hub machine itself (loopback, no relay, no cross-site Origin) while the config flag
  `auth.allow_localhost_dev` is true (default true so scripts and eval tools keep working): that call acts as the first
  household's parent (no PIN) and the first child.
"""
import hashlib
import hmac
import re
import secrets
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from .db import now

LOOPBACK = ("127.0.0.1", "::1", "localhost")
PIN_RE = re.compile(r"^\d{4,8}$")
PAIR_TTL_S = 600
VIA_HEADER, TUNNEL_DEV_HEADER, PIN_HEADER = "x-whyscope-via", "x-whyscope-tunnel-dev", "x-whyscope-pin"

# routes a wand may call (its own child only; the handlers scope by the token's child)
WAND_ROUTES = [("GET", r"/api/ping"), ("GET", r"/api/me"), ("GET", r"/healthz"), ("POST", r"/api/ask"), ("GET", r"/api/ask/[\w-]+"),
               ("POST", r"/api/reply"), ("GET", r"/api/deliveries"), ("POST", r"/api/deliveries/\d+/done")]
PUBLIC_PAGES = ("/", "/kid", "/parent", "/pair", "/favicon.ico")


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class Ctx:
    kind: str                      # "wand" | "parent" | "dev" (localhost, no token)
    household_id: int
    child_id: Optional[int] = None   # a wand's child
    parent_id: Optional[int] = None
    device: Optional[dict] = None


def hash_token(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_pin(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def lan_ip() -> str:
    """This machine's LAN address (the UDP connect sends nothing)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def route_class(method: str, path: str) -> str:
    """public | local | wand | parent: who may call this route (deny by default: unknown routes are parent-only)."""
    if method in ("GET", "HEAD") and (path in PUBLIC_PAGES or path.startswith("/static/")):
        return "public"
    if method == "POST" and path == "/api/pair":
        return "public"
    if path == "/setup" or path.startswith("/api/setup"):
        return "local"
    if method == "OPTIONS":
        return "public"
    if any(m == method and re.fullmatch(p, path) for m, p in WAND_ROUTES):
        return "wand"
    return "parent"


class Auth:
    def __init__(self, db, cfg: dict):
        self.db = db
        c = cfg.get("auth") or {}
        self.allow_dev = bool(c.get("allow_localhost_dev", True))
        self.lan_url_cfg = (c.get("lan_url") or "").rstrip("/")
        self.pair_ttl = int(c.get("pair_ttl_s", PAIR_TTL_S))
        self._seen, self._fails, self._ip_fails = {}, {}, {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ requests
    @staticmethod
    def is_local(request) -> bool:
        """From the hub machine itself: loopback, not forwarded by the relay tunnel or a proxy."""
        h = request.headers
        host = request.client.host if request.client else ""
        return host in LOOPBACK and VIA_HEADER not in h and "x-forwarded-for" not in h

    def dev_ok(self, request) -> bool:
        if not self.allow_dev or not self.is_local(request):
            return False
        origin = request.headers.get("origin")   # a web page of another origin must not borrow the localhost access
        return not origin or urlparse(origin).netloc == request.headers.get("host", "")

    def authenticate(self, request) -> Ctx:
        """The caller's context, or AuthError (401 / 403)."""
        h = request.headers
        auth = h.get("authorization") or ""
        if not auth:
            if self.dev_ok(request):
                hh = self.db.default_household_id()
                return Ctx("dev", hh)
            raise AuthError(401, "auth_required")
        scheme, _, tok = auth.partition(" ")
        if scheme.lower() != "bearer" or not tok.strip():
            raise AuthError(401, "auth_required")
        d = self.db.device_by_token(hash_token(tok.strip()))
        if not d:
            raise AuthError(401, "bad_token")
        if d["revoked"]:
            raise AuthError(401, "revoked")
        if h.get(VIA_HEADER) == "tunnel" and (not d.get("tunnel_id") or d["tunnel_id"] != h.get(TUNNEL_DEV_HEADER)):
            raise AuthError(403, "tunnel_mismatch")   # a relay device may only carry its own token
        with self._lock:
            if time.monotonic() - self._seen.get(d["id"], -999) > 30:
                self._seen[d["id"]] = time.monotonic()
                self.db.device_touch(d["id"])
        return Ctx(d["kind"], d["household_id"], d.get("child_id") if d["kind"] == "wand" else None, d.get("parent_id"), d)

    # ------------------------------------------------------------ PIN
    def require_pin(self, request, ctx: Ctx):
        """Parents only: the PIN of the parent behind this device (the `dev` context is exempt)."""
        if ctx.kind == "dev":
            return
        if ctx.kind != "parent" or not ctx.parent_id:
            raise AuthError(403, "parent_only")
        pin = request.headers.get(PIN_HEADER, "")
        if not pin:
            raise AuthError(403, "pin_required")
        with self._lock:
            n, until = self._fails.get(ctx.parent_id, (0, 0))
            if until > time.monotonic():
                raise AuthError(429, "pin_locked")
        p = self.db.parent_get(ctx.parent_id)
        if not p or not hmac.compare_digest(hash_pin(pin, p["pin_salt"]), p["pin_hash"]):
            with self._lock:
                n = self._fails.get(ctx.parent_id, (0, 0))[0] + 1
                self._fails[ctx.parent_id] = (0, time.monotonic() + 60) if n >= 5 else (n, 0)
            raise AuthError(403, "pin_wrong")
        with self._lock:
            self._fails.pop(ctx.parent_id, None)

    def make_parent(self, hh: int, name: str, pin: str) -> int:
        name = (name or "").strip()
        if not name or len(name) > 40:
            raise AuthError(400, "name_required")
        if not PIN_RE.match(pin or ""):
            raise AuthError(400, "pin_format")   # 4 to 8 digits
        salt = secrets.token_bytes(16)
        return self.db.parent_add(hh, name, salt, hash_pin(pin, salt))

    # ------------------------------------------------------------ pairing
    def lan_url(self, request) -> str:
        """Where a phone on the home network reaches this hub."""
        if self.lan_url_cfg:
            return self.lan_url_cfg
        srv = request.scope.get("server") or ("127.0.0.1", 8000)
        return f"{request.url.scheme}://{lan_ip()}:{srv[1]}"

    def create_pairing(self, hh: int, kind: str, child_id=None, parent_id=None, name="", lan_url="", store=None) -> dict:
        """A one-time code and the URL a QR code carries: <lan>/pair#c=<code>&h=<lan url>&b=<relay bundle, if a relay is set>."""
        if kind not in ("wand", "parent"):
            raise AuthError(400, "bad_kind")
        self.sweep(store)
        code = secrets.token_urlsafe(9)
        tunnel_id, bundle = None, None
        if store is not None and store.relay:
            b = store.pair(name or kind, "kid" if kind == "wand" else "parent")
            tunnel_id, bundle = b["device"]["id"], b
        expires = (datetime.now() + timedelta(seconds=self.pair_ttl)).isoformat(timespec="seconds")
        self.db.pair_add(hash_token(code), hh, kind, child_id, parent_id, name, expires, tunnel_id)
        frag = f"c={code}&h={lan_url}" + (f"&b={_qr_string(bundle)}" if bundle else "")
        return {"code": code, "kind": kind, "url": f"{lan_url}/pair#{frag}", "expires": expires,
                "expires_in": self.pair_ttl, "relay": bool(bundle)}

    def sweep(self, store=None):
        """Forget old codes; an unused code's relay key is revoked so a dropped QR code leaves nothing behind."""
        for tid in self.db.pair_sweep():
            if store is not None:
                try:
                    store.revoke(tid)
                except Exception:
                    pass

    def _throttle(self, ip: str):
        with self._lock:
            n, until = self._ip_fails.get(ip, (0, 0))
            if until > time.monotonic():
                raise AuthError(429, "too_many_tries")

    def _fail(self, ip: str):
        with self._lock:
            n = self._ip_fails.get(ip, (0, 0))[0] + 1
            self._ip_fails[ip] = (0, time.monotonic() + 60) if n >= 10 else (n, 0)

    def redeem(self, code: str, name: str = None, pin: str = None, ip: str = "") -> dict:
        """The scanning device trades the one-time code for its token (returned once)."""
        self._throttle(ip)
        row = self.db.pair_get(hash_token((code or "").strip())) if code else None
        if not row or row["used"] or row["expires"] < now():
            self._fail(ip)
            raise AuthError(404, "invalid_code")
        parent_id = row["parent_id"]
        if row["kind"] == "parent" and not parent_id:      # an invitation: the new parent chooses a name and a PIN
            if not (name or "").strip() or not pin:
                raise AuthError(422, "need_profile")
            if not PIN_RE.match(pin):
                raise AuthError(400, "pin_format")
        if not self.db.pair_take(hash_token(code.strip())):
            raise AuthError(404, "invalid_code")
        hh = row["household_id"]
        if row["kind"] == "parent" and not parent_id:
            parent_id = self.make_parent(hh, name, pin)
        tok = new_token()
        if row["kind"] == "wand":
            ch = self.db.child_get(row["child_id"]) or {}
            dname = row["name"] or f"Wand for {ch.get('name', 'child')}"
        else:
            dname = f"{(self.db.parent_get(parent_id) or {}).get('name', 'Parent')}'s phone"
        did = self.db.device_add(hh, row["kind"], dname, hash_token(tok), row["child_id"], parent_id, row["tunnel_id"])
        return {"token": tok, "device": {"id": did, "kind": row["kind"], "name": dname}, "household_id": hh,
                "child_id": row["child_id"], "parent_id": parent_id}


def _qr_string(bundle: dict) -> str:
    from .tunnel import qr_string
    return qr_string(bundle)
