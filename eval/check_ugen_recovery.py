"""UGen worker self-recovery, tested without the device: fake HailoRT classes stand in for hailo_platform, and a fake
LLM fails its load_context() with HAILO_LIBUSB_FAILURE after K calls (the 2026-11-18 incident). Exit code 1 on a failure.

Never opens the UGen300: hailo_platform is replaced by fakes before anything imports it, and the test worker listens on
a free port, not 8711. Safe to run while the real worker is up.

    C:\\whyscope-venv\\Scripts\\python.exe eval\\check_ugen_recovery.py [-v]

What it checks:
  1. classify(): LIBUSB / communication-closed / raw status 98 are "device"; invalid argument and Python request errors
     are "request"; timeouts and other HailoRT errors are "suspect".
  2. DeviceGuard: a device error -> recovering -> calls refused at once -> rebuilt -> ok (recoveries 1); bad requests
     never recover; 2 suspect errors then a success do not, 3 in a row do; N failed rebuilds -> degraded with a replug
     message; recover_now() after the "replug" -> ok; a start-up with no device -> degraded, then ok.
  3. HailoLLM keeps at most llm_ctx_max saved prefix contexts (LRU).
  4. The real worker HTTP server (hub.hailo_worker.main, models faked) + the hub's WorkerClient: /complete fails with
     LIBUSB after K calls, the next calls get HTTP 503 "recovering" in milliseconds (and the hub client fails fast
     without HTTP while it is known down), /info shows health and the recovery count, then /complete works again;
     an empty turn is HTTP 400 and does not recover; the hub's chat / compose / assistant helpers see the worker as down.
"""
import argparse
import json
import socket
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS, VERBOSE = [], False


def check(cond, what):
    if cond:
        if VERBOSE:
            print("ok  ", what)
    else:
        FAILS.append(what)
        print("FAIL", what)


def wait_for(pred, timeout=10.0, step=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


# ---------------------------------------------------------------- fake hailo_platform (never the real one)
MOD = "hailo_platform.pyhailort.pyhailort"


def _exc(name, base=Exception):
    return type(name, (base,), {"__module__": MOD})


HailoRTException = _exc("HailoRTException")
HailoCommunicationClosedException = _exc("HailoCommunicationClosedException", HailoRTException)
HailoRTInvalidArgumentException = _exc("HailoRTInvalidArgumentException", HailoRTException)
HailoRTTimeout = _exc("HailoRTTimeout", HailoRTException)
HailoRTStatusException = _exc("HailoRTStatusException")


def libusb():
    """What pyhailort raises for HAILO_LIBUSB_FAILURE (ExceptionWrapper.create_exception_from_status, unknown code)."""
    try:
        raise HailoRTStatusException(98)
    except HailoRTStatusException as raw:
        try:
            raise HailoRTException("libhailort failed with error: 98 (HAILO_LIBUSB_FAILURE)") from raw
        except HailoRTException as e:
            return e


DEV = {"load_ctx_calls": 0, "fail_after": None, "dead": False, "vdev_ok": True, "llms": 0, "released": 0}


class FakeVDevice:
    @staticmethod
    def create_params():
        return types.SimpleNamespace(group_id=None)

    def __init__(self, params=None):
        if not DEV["vdev_ok"]:
            raise libusb()

    def release(self):
        DEV["released"] += 1


class _Gen:
    def __init__(self, toks):
        self.toks = toks

    def __enter__(self):
        return iter(self.toks)

    def __exit__(self, *a):
        return False


class FakeLLM:
    def __init__(self, vdevice, path, *a, **k):
        DEV["llms"] += 1
        self.dead = False

    def _io(self):
        if self.dead or DEV["dead"]:
            raise libusb()

    def generate_all(self, prompt, **kw):
        self._io()
        return "\n"

    def generate(self, prompt, **kw):
        self._io()
        if not prompt:
            raise HailoRTInvalidArgumentException("Invalid argument. See hailort.log for more information")
        return _Gen(["Plants ", "drink ", "light."])

    def save_context(self):
        self._io()
        return b"\x01" * 64

    def load_context(self, ctx):
        DEV["load_ctx_calls"] += 1
        if DEV["fail_after"] is not None and DEV["load_ctx_calls"] > DEV["fail_after"]:
            DEV["dead"] = True   # the link is gone for this LLM object and every later call
        self._io()

    def clear_context(self):
        self._io()

    def release(self):
        DEV["released"] += 1


def install_fake_hailo():
    pkg = types.ModuleType("hailo_platform")
    pkg.__path__ = []
    pkg.VDevice = FakeVDevice
    genai = types.ModuleType("hailo_platform.genai")
    genai.LLM, genai.VLM, genai.VDevice = FakeLLM, FakeLLM, FakeVDevice
    genai.Speech2Text, genai.Speech2TextTask = object, object
    pyh = types.ModuleType("hailo_platform.pyhailort")
    pyh.__path__ = []
    inner = types.ModuleType(MOD)
    for c in (HailoRTException, HailoCommunicationClosedException, HailoRTInvalidArgumentException, HailoRTTimeout):
        setattr(inner, c.__name__, c)
    sys.modules.update({"hailo_platform": pkg, "hailo_platform.genai": genai, "hailo_platform.pyhailort": pyh, MOD: inner})


# ---------------------------------------------------------------- 1. classify
def test_classify():
    from hub.ugen_guard import classify
    check(classify(libusb()) == "device", "LIBUSB failure is a device error")
    check(classify(HailoCommunicationClosedException("Communication closed failure. Check server-client connection"))
          == "device", "communication closed is a device error")
    check(classify(HailoRTStatusException(98)) == "device", "raw status 98 is a device error")
    check(classify(HailoRTInvalidArgumentException("Invalid argument. See hailort.log for more information")) == "request",
          "invalid argument is a request error")
    check(classify(HailoRTStatusException(2)) == "request", "raw status 2 (invalid argument) is a request error")
    check(classify(ValueError("cannot reshape array of size 3 into shape (640,640,3)")) == "request", "reshape error is a request error")
    check(classify(KeyError("prefix")) == "request", "missing field is a request error")
    check(classify(json.JSONDecodeError("x", "", 0)) == "request", "bad JSON is a request error")
    check(classify(HailoRTTimeout("Received a timeout - hailort has failed because a timeout had occurred")) == "suspect",
          "a HailoRT timeout is suspect")
    check(classify(HailoRTException("libhailort failed with error: 8 (HAILO_INTERNAL_FAILURE)")) == "suspect",
          "internal failure is suspect")


# ---------------------------------------------------------------- 2. DeviceGuard
def test_guard():
    from hub.ugen_guard import DeviceGuard, Unavailable
    built, released = [], []
    plan = {"fail_builds": 0}

    def build():
        if plan["fail_builds"] > 0:
            plan["fail_builds"] -= 1
            raise libusb()
        built.append(object())
        return built[-1]

    g = DeviceGuard(build, released.append, strikes=3, backoff=(0.01,), max_attempts=3, degraded_retry_s=0,
                    log=lambda m: None).start()
    check(g.state == "ok" and len(built) == 1, "guard starts ok")

    # bad requests never recover
    for e in [HailoRTInvalidArgumentException("Invalid argument"), ValueError("bad"), KeyError("turn")] * 4:
        try:
            g.call(lambda m, e=e: (_ for _ in ()).throw(e))
        except Exception:
            pass
    check(g.state == "ok" and g.recoveries == 0 and len(built) == 1, "12 bad requests: no recovery")

    # suspect errors: 2 then a success -> nothing; 3 in a row -> recovery
    for _ in range(2):
        try:
            g.call(lambda m: (_ for _ in ()).throw(HailoRTTimeout("timeout")))
        except HailoRTTimeout:
            pass
    g.call(lambda m: "fine")
    check(g.state == "ok" and g.strikes == 0, "2 timeouts then a success: no recovery, strikes reset")
    for _ in range(3):
        try:
            g.call(lambda m: (_ for _ in ()).throw(HailoRTTimeout("timeout")))
        except (HailoRTTimeout, Unavailable):
            pass
    check(wait_for(lambda: g.state == "ok" and g.recoveries == 1), "3 timeouts in a row: recovered once")
    check(len(released) == 1 and len(built) == 2, "the old models were released, new ones built")

    # a device error -> recovering, calls refused at once, then ok
    gate = threading.Event()
    real_build = g.build

    def slow_build():
        gate.wait(5)
        return real_build()
    g.build = slow_build
    try:
        g.call(lambda m: (_ for _ in ()).throw(libusb()))
    except HailoRTException:
        pass
    check(g.state == "recovering", "one LIBUSB failure: recovering at once")
    t = time.perf_counter()
    try:
        g.call(lambda m: "never runs")
        check(False, "a call while recovering is refused")
    except Unavailable as e:
        check(e.state == "recovering" and time.perf_counter() - t < 0.05, f"a call while recovering is refused fast ({e})")
    gate.set()
    check(wait_for(lambda: g.state == "ok" and g.recoveries == 2), "recovered after the LIBUSB failure")
    g.build = real_build
    check(g.call(lambda m: m is built[-1]), "calls get the rebuilt models")

    # recovery fails max_attempts times -> degraded, says replug; recover_now after the replug -> ok
    plan["fail_builds"] = 99
    try:
        g.call(lambda m: (_ for _ in ()).throw(libusb()))
    except HailoRTException:
        pass
    check(wait_for(lambda: g.state == "degraded"), "3 failed rebuilds: degraded")
    check("replug" in g.message().lower(), f"degraded message says replug: {g.message()!r}")
    check(g.info()["failed_attempts"] >= 3, "failed attempts are counted")
    try:
        g.call(lambda m: 1)
        check(False, "degraded refuses calls")
    except Unavailable as e:
        check(e.state == "degraded", "degraded refuses calls with state degraded")
    plan["fail_builds"] = 0   # the user replugged the UGen
    g.recover_now("test replug")
    check(wait_for(lambda: g.state == "ok"), "recover_now after the replug: ok again")
    check(g.recoveries == 3, f"recovery count is 3 ({g.recoveries})")
    g.close()

    # the device is missing at start-up: degraded (slow retry), then it comes up by itself
    plan["fail_builds"] = 5
    g2 = DeviceGuard(build, released.append, backoff=(0.01,), max_attempts=2, degraded_retry_s=0.05,
                     log=lambda m: None).start()
    check(g2.state in ("recovering", "degraded"), "no device at start-up: not ok")
    check(wait_for(lambda: g2.state == "ok"), "the slow retry brings it up once the device is back")
    g2.close()


# ---------------------------------------------------------------- 3. LRU of saved contexts
def test_lru(hef):
    from hub.hailo import HailoLLM
    llm = HailoLLM({"hailo": {"llm_hef": str(hef), "llm_restore": "context", "llm_ctx_max": 3}})
    for i in range(6):
        llm.prime(f"<|im_start|>system\nprefix {i}<|im_end|>\n")
    keys = llm.prefixes()
    check(len(keys) == 3 and "prefix 5" in keys[-1] and "prefix 3" in keys[0], f"saved contexts capped at 3, LRU order ({len(keys)})")
    llm.prime("<|im_start|>system\nprefix 3<|im_end|>\n")   # touch the oldest: it becomes the newest
    llm.prime("<|im_start|>system\nprefix 6<|im_end|>\n")
    keys = llm.prefixes()
    check("prefix 3" in keys[-2] and not any("prefix 4" in k for k in keys), "a used prefix is kept, the least recent goes")
    llm.release()


# ---------------------------------------------------------------- 4. worker HTTP + hub client
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_worker(hef):
    import hub.hailo as H
    import hub.hailo_worker as W
    port = free_port()
    assert port != 8711
    cfg = {"hailo": {"llm_hef": str(hef), "llm_restore": "context", "worker": f"http://127.0.0.1:{port}",
                     "recovery": {"backoff_s": [1.0], "max_attempts": 2, "degraded_retry_s": 0, "reprime": 2}}}

    def fake_load_models(c):
        m = W.Models()
        m.llm = H.HailoLLM(c)   # the real HailoLLM on the fake genai LLM
        m.info["llm"] = {"loaded": True, "name": "fake-qwen.hef", "load_s": 0.0}
        m.vis = types.SimpleNamespace(models={})
        return m

    W.load_models, W.load_config = fake_load_models, (lambda: cfg)
    argv, sys.argv = sys.argv, ["hailo_worker", "--port", str(port)]
    th = threading.Thread(target=W.main, daemon=True)
    th.start()
    client = H.WorkerClient(cfg)
    check(wait_for(lambda: _try(client.info), 10), "test worker answers /info")
    sys.argv = argv
    info = client.info()
    check((info.get("health") or {}).get("state") == "ok", "/info health ok at start")

    llm = H.HailoLLMRemote(cfg)
    prefix = "<|im_start|>system\nYou are kind.<|im_end|>\n"
    turn = "<|im_start|>user\nWhy?<|im_end|>\n<|im_start|>assistant\n"
    DEV.update(load_ctx_calls=0, fail_after=5, dead=False, vdev_ok=True)
    texts = [llm.complete(prefix, turn, 8, {"ends": ".", "n": 1}) for _ in range(4)]
    check(all(t == "Plants drink light." for t in texts), "4 good completions")

    # an empty turn: HTTP 400, no recovery
    try:
        llm.complete(prefix, "  ", 8)
        check(False, "empty turn is refused")
    except RuntimeError as e:
        check("HTTP 400" in str(e) and not isinstance(e, H.WorkerUnavailable), f"empty turn -> HTTP 400 ({e})")
    check(client.info()["health"]["recoveries"] == 0 and client.info()["health"]["state"] == "ok",
          "a bad request does not start a recovery")

    # the device fails (LIBUSB on load_context): HTTP 500 for that call, then 503 recovering at once
    errs = []
    for _ in range(3):
        try:
            llm.complete(prefix, turn, 8)
        except RuntimeError as e:
            errs.append(e)
    check(len(errs) >= 1 and "LIBUSB" in str(errs[0]), f"the failing call reports the LIBUSB error ({errs[:1]})")
    h = client.info()["health"]
    check(h["state"] in ("recovering", "ok") and (h["state"] == "ok" or h["last_error"]["kind"] == "device"),
          f"/info health after the failure: {h['state']}, last error {(h.get('last_error') or {}).get('kind')}")
    DEV.update(dead=False, fail_after=None)   # the rebuilt LLM gets a working link
    H._DOWN.clear()
    t = time.perf_counter()
    try:
        llm.complete(prefix, turn, 8)
        fast = None
    except H.WorkerUnavailable as e:
        fast = (time.perf_counter() - t, str(e))
    check(fast is not None and fast[0] < 0.5 and "recovering" in fast[1], f"a call while recovering gets 503 recovering fast {fast}")
    t = time.perf_counter()
    try:
        llm.complete(prefix, turn, 8)
        check(False, "the hub client fails fast while the worker is known down")
    except H.WorkerUnavailable as e:
        check(time.perf_counter() - t < 0.01 and "UGen recovering" in str(e), f"no HTTP while known down ({e})")
    check(bool(H.worker_down(cfg)), "worker_down() is set for chat / compose / assistant")

    # hub helpers see it (no full pipeline: tiny stand-ins with the same attributes)
    import hub.chat as C
    from hub.assistant import ParentAssistant
    comp = types.SimpleNamespace(backend="hailo", ready=True, llm=llm)
    p = types.SimpleNamespace(cfg=cfg, composer=comp)
    check(bool(C._ugen_down(p)), "chat sees the worker down (canned line at once)")
    pa = ParentAssistant.__new__(ParentAssistant)
    pa.p = p
    check(pa.llm_ready() is False, "parent assistant pauses while the worker is down")

    check(wait_for(lambda: client.info()["health"]["state"] == "ok", 10), "worker recovered by itself")
    h = client.info()["health"]
    check(h["recoveries"] == 1, f"/info health.recoveries == 1 ({h['recoveries']})")
    check(not H.worker_down(cfg), "a good /info clears the hub's down mark")
    check(pa.llm_ready() is True, "parent assistant resumes")
    check(llm.complete(prefix, turn, 8, {"ends": ".", "n": 1}) == "Plants drink light.", "completions work after the recovery")
    check(client.info()["models"]["llm"].get("contexts", 0) >= 1, "the recent prefix was re-primed / saved again")

    # a rebuild that keeps failing: degraded, says replug; /recover after the replug -> ok
    DEV.update(fail_after=0, load_ctx_calls=0, vdev_ok=False)
    real_load = W.load_models

    def no_device(c):
        H.vdevice()   # raises LIBUSB while vdev_ok is False
        return real_load(c)
    W.load_models = no_device
    try:
        llm.complete(prefix, turn, 8)
    except RuntimeError:
        pass
    check(wait_for(lambda: client.info()["health"]["state"] == "degraded", 10), "rebuild keeps failing: degraded")
    h = client.info()["health"]
    check("replug" in h["message"].lower(), f"degraded message: {h['message']!r}")
    m = client.info()["models"]["llm"]
    check(m["loaded"] is False and m.get("paused") == "degraded", "/info models show the LLM paused while degraded")
    DEV.update(fail_after=None, dead=False, vdev_ok=True)   # replugged
    W.load_models = real_load
    client.post("/recover", {}, 5)
    check(wait_for(lambda: client.info()["health"]["state"] == "ok", 10), "POST /recover after the replug: ok")
    H._DOWN.clear()
    check(llm.complete(prefix, turn, 8, {"ends": ".", "n": 1}) == "Plants drink light.", "completions work again")
    client.post("/shutdown", {}, 5)
    th.join(10)
    check(not th.is_alive(), "test worker shut down")


def _try(f):
    try:
        f()
        return True
    except Exception:
        return False


def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    VERBOSE = ap.parse_args().verbose
    install_fake_hailo()
    with tempfile.TemporaryDirectory() as d:
        hef = Path(d) / "fake-qwen2.5-1.5b.hef"
        hef.write_bytes(b"not a real HEF")
        for name, fn in (("classify", test_classify), ("guard", test_guard), ("lru", lambda: test_lru(hef)),
                         ("worker", lambda: test_worker(hef))):
            t = time.perf_counter()
            try:
                fn()
            except Exception as e:
                import traceback
                traceback.print_exc()
                FAILS.append(f"{name}: crashed: {type(e).__name__}: {e}")
            print(f"{name}: done in {time.perf_counter() - t:.1f} s")
    print(f"\n{len(FAILS)} failures" + (":\n  " + "\n  ".join(FAILS) if FAILS else ""))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
