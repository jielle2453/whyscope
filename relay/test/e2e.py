"""End-to-end test: Node relay (node-server.js, same core as the Worker) + hub/tunnel.py + Python client + JS client
(hub/static/tunnel.js under Node). Needs the hub running on http://127.0.0.1:8000. From the repo root:
  C:\\whyscope-venv\\Scripts\\python.exe relay\\test\\e2e.py
"""
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hub import tunnel as T  # noqa: E402

PORT = 8791
RELAY = f"ws://127.0.0.1:{PORT}"
Q = "Why is the sky blue?"
tmp = Path(tempfile.mkdtemp(prefix="wsrelay-"))
env = {**os.environ, "WHYSCOPE_TUNNEL_DIR": str(tmp / "keys"), "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(ROOT)}
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name, extra)


def cli(*args):
    return subprocess.run([sys.executable, "-m", "hub.tunnel", *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)


def pair(name, role="parent"):
    out = cli("pair", "--device", name, "--role", role).stdout
    return json.loads(out[:out.index("\nQR string")])


def hs(h):   # /healthz also carries live counters (last latencies), compare the static part
    return {k: h.get(k) for k in ("ok", "mode", "entries", "language", "safety_categories", "compose_backend")}


def stable(a):   # fields that must be identical between direct and tunnelled answers
    return {k: a.get(k) for k in ("status", "object", "topic", "first_sentence", "explanation", "ask_back", "sensitive_category")}


async def main():
    direct = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60)
    relay_log = open(tmp / "relay.log", "w")
    relay = subprocess.Popen(["node", "node-server.js", "--port", str(PORT), "--state", str(tmp / "state.json"), "--debug"],
                             cwd=ROOT / "relay", stdout=relay_log, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    cli("--relay", RELAY, "list")                                      # saves the relay URL, creates keys
    wand, parent = pair("Wand", "kid"), pair("Mum phone", "parent")
    tun = subprocess.Popen([sys.executable, "-m", "hub.tunnel", "--hub", "http://127.0.0.1:8000"], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=open(tmp / "tunnel.log", "w"))
    time.sleep(3)
    try:
        # ---- Python client vs direct
        d_health = direct.get("/healthz").json()
        d_ask = direct.post("/api/ask?wait=1", json={"text": Q, "lang": "en", "wait": 1}).json()
        async with T.TunnelClient(parent) as t:
            st, _, body = await t.fetch("GET", "/healthz")
            check("python client GET /healthz same as direct", st == 200 and hs(json.loads(body)) == hs(d_health))
            st, _, body = await t.fetch("POST", "/api/ask?wait=1", json_body={"text": Q, "lang": "en", "wait": 1})
            p_ask = json.loads(body)
            check("python client POST /api/ask same answer as direct", st == 200 and stable(p_ask) == stable(d_ask),
                  repr(p_ask.get("first_sentence")))
            st, _, body = await t.fetch("GET", "/api/data/export")
            check("parent device can export data", st == 200)
            big = bytes(range(256)) * 4096                                  # 1 MB multipart-ish body round trip
            st, _, body = await t.fetch("POST", "/api/ask", body=big, headers={"content-type": "application/octet-stream"})
            check("1 MB upload goes through and the hub answers (not a tunnel failure)", st in (200, 400, 415, 422, 500), str(st))
            # concurrent requests on one session
            rs = await asyncio.gather(*[t.fetch("GET", "/healthz") for _ in range(10)])
            check("10 concurrent requests on one session", all(r[0] == 200 for r in rs))
        # ---- kid role scope
        async with T.TunnelClient(wand) as t:
            st, _, _ = await t.fetch("GET", "/api/data/export")
            check("kid device refused /api/data/export (403)", st == 403, str(st))
            st, _, _ = await t.fetch("GET", "/healthz")
            check("kid device may GET /healthz", st == 200)
        # ---- JS client (what the browser runs)
        (tmp / "parent.json").write_text(json.dumps(parent))
        r = subprocess.run(["node", str(ROOT / "relay/test/js_client.mjs"), str(tmp / "parent.json"), Q, "20"],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        js = json.loads(r.stdout) if r.returncode == 0 else {}
        check("JS client GET /healthz same as direct", hs(js.get("healthz", {}).get("body", {})) == hs(d_health), r.stderr[-300:])
        check("JS client POST /api/ask same answer as direct", stable(js.get("ask", {}).get("body", {})) == stable(d_ask))
        # ---- latency
        async with T.TunnelClient(parent) as t:
            await t.fetch("GET", "/healthz")
            via = []
            for _ in range(20):
                a = time.perf_counter(); await t.fetch("GET", "/healthz"); via.append((time.perf_counter() - a) * 1000)
        dr = []
        for _ in range(20):
            a = time.perf_counter(); direct.get("/healthz"); dr.append((time.perf_counter() - a) * 1000)
        print(f"LATENCY GET /healthz p50 direct {statistics.median(dr):.1f} ms | python via relay {statistics.median(via):.1f} ms"
              f" | JS via relay {statistics.median(js['latency_ms']):.1f} ms | added (python) {statistics.median(via) - statistics.median(dr):.1f} ms")
        # ---- refused: forged ticket, tampered ticket, unknown relay id
        import cryptography.hazmat.primitives.asymmetric.ed25519 as ed
        forged = dict(wand, ticket=T.sign_ticket(ed.Ed25519PrivateKey.generate(), wand["host_id"], wand["device"]["id"]))
        for name, b in (("ticket signed by a stranger", forged), ("garbage ticket", dict(wand, ticket="v1.x.y")),
                        ("other hub id", dict(wand, host_id="0" * 32))):
            try:
                async with T.TunnelClient(b):
                    check(f"refused: {name}", False)
            except Exception as e:
                check(f"refused: {name}", str(e) == "unauthorized", str(e)[:40])
        # wrong device key: valid ticket for the device, but the attacker lacks the device's static key
        evil = json.loads(json.dumps(wand)); evil["device"]["priv"] = pair("scratch")["device"]["priv"]
        try:
            async with T.TunnelClient(evil) as t:
                await asyncio.wait_for(t.fetch("GET", "/healthz"), 5)
            check("refused: stolen ticket without the device key", False)
        except Exception as e:
            check("refused: stolen ticket without the device key", True, type(e).__name__)
        # ---- revocation
        victim = pair("Lost phone")
        async with T.TunnelClient(victim) as t:
            check("device works before revoke", (await t.fetch("GET", "/healthz"))[0] == 200)
            print(cli("revoke", "--device", "Lost phone").stdout.strip())
            await asyncio.sleep(2.5)
            try:
                await asyncio.wait_for(t.fetch("GET", "/healthz"), 5)
                check("live session of revoked device is cut", False)
            except Exception as e:
                check("live session of revoked device is cut", True, type(e).__name__)
        try:
            async with T.TunnelClient(victim):
                check("revoked device refused on reconnect", False)
        except T.TunnelError as e:
            check("revoked device refused on reconnect", str(e) == "unauthorized", str(e))
        # ---- hub offline
        tun.terminate(); tun.wait(); time.sleep(1)
        try:
            async with T.TunnelClient(parent):
                check("hub offline reported", False)
        except T.TunnelError as e:
            check("hub offline reported", str(e) == "hub_offline", str(e))
        r = subprocess.run(["node", str(ROOT / "relay/test/js_client.mjs"), str(tmp / "parent.json"), Q, "1"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        print("JS client while hub offline exit:", r.returncode, (r.stderr or r.stdout)[:120].replace("\n", " "))
    finally:
        for p in (tun, relay):
            if p.poll() is None:
                p.terminate()
        time.sleep(0.5)
        relay_log.close()
    # ---- plaintext check
    log = (tmp / "relay.log").read_text(encoding="utf-8", errors="replace")
    state = (tmp / "state.json").read_text()
    sizes = [l for l in log.splitlines() if "bytes" in l]
    leaks = [w for w in ("sky", "Why is", "blue", "Rayleigh", p_ask.get("first_sentence", "@@")[:12]) if w in log or w in state]
    check("relay log has frame sizes", len(sizes) > 20, f"{len(sizes)} size lines, e.g. {sizes[3]!r}")
    check("question/answer text absent from relay log and relay state", not leaks, f"checked {len(log)} log bytes; leaks={leaks}")
    shutil.copy(tmp / "relay.log", ROOT / "relay" / "test" / "last-relay.log")
    print(f"\n{sum(results)}/{len(results)} checks passed")
    shutil.rmtree(tmp, ignore_errors=True)
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
