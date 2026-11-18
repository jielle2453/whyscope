"""Device health for the UGen worker (hub/hailo_worker.py): tell a failing device from a bad request, and rebuild the
models and the VDevice when the device fails, instead of failing every call until someone replugs it.

Why (2026-11-18, docs/ugen.md "If the UGen stops responding"): after about 146 /complete calls a load_context() write
failed with HAILO_LIBUSB_FAILURE(98), and every later LLM call failed the same way while /info (which never touches the
device) still answered. The worker kept the dead LLM object, so the hub's chat, AI guess and parent drafts all failed.

States:  ok -> recovering (release everything, rebuild with backoff) -> ok | degraded (gave up: replug the UGen; a slow
retry still runs, and POST /recover forces one now). While not ok, every device call is refused at once with
Unavailable (HTTP 503 {"state": ...}), so the hub falls back right away instead of waiting for a timeout.

classify(exc):
  "device"  : the link or the device is gone (LIBUSB failure, communication closed, driver / RPC / control failures):
              recover now.
  "suspect" : any other HailoRT error (timeout, internal failure, invalid operation ...): recover once `strikes` of
              them come in a row with no success in between.
  "request" : the request was bad (HAILO_INVALID_ARGUMENT, e.g. an empty prompt; a non-HailoRT Python error such as a
              bad body or a wrong array size): never a reason to recover, and it does not reset the strike count.

Pure Python (no HailoRT import), so eval/check_ugen_recovery.py tests it with fake models.
"""
import threading
import time

# status names / texts that mean the USB link or the device itself is gone (HailoRT 5.3.2 status table)
DEVICE_MARKERS = (
    "HAILO_LIBUSB_FAILURE", "LIBUSB_ERROR", "HAILO_COMMUNICATION_CLOSED", "HailoCommunicationClosedException",
    "HAILO_DRIVER_OPERATION_FAILED", "HailoRTDriverOperationFailedException", "HAILO_DRIVER_TIMEOUT",
    "HAILO_DRIVER_INVALID_RESPONSE", "HAILO_DEVICE_NOT_CONNECTED", "HAILO_RPC_FAILED", "HAILO_CONNECTION_REFUSED",
    "HAILO_FW_CONTROL_FAILURE", "HailoRTFirmwareControlFailedException", "HAILO_INVALID_CONTROL_RESPONSE",
    "HAILO_GET_CONTROL_RESPONSE_FAIL", "HAILO_STREAM_ABORT", "HailoRTStreamAborted", "Lost communication",
    "device is not reachable", "Communication closed failure", "error: 98 ", "error: 62 ",
)
REQUEST_MARKERS = ("HAILO_INVALID_ARGUMENT", "HailoRTInvalidArgumentException", "Invalid argument")
# the same, as hailo_status numbers (HailoRT 5.3.2): 98 LIBUSB_FAILURE, 62 COMMUNICATION_CLOSED, 36 DRIVER_OPERATION_FAILED,
# 87 DRIVER_TIMEOUT, 85 DRIVER_INVALID_RESPONSE, 96 DEVICE_NOT_CONNECTED, 77 RPC_FAILED, 89 CONNECTION_REFUSED,
# 18 FW_CONTROL_FAILURE, 17 INVALID_CONTROL_RESPONSE, 44 GET_CONTROL_RESPONSE_FAIL, 63 STREAM_ABORT; 2 INVALID_ARGUMENT
DEVICE_CODES = {98, 62, 36, 87, 85, 96, 77, 89, 18, 17, 44, 63}
REQUEST_CODES = {2}
# Python errors from parsing the request or shaping its data (before or around the device call)
REQUEST_TYPES = (ValueError, KeyError, TypeError, LookupError, ImportError, UnicodeError)


def _chain(exc):
    seen = []
    while exc is not None and len(seen) < 6 and exc not in seen:
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def _is_hailo(exc) -> bool:
    for e in _chain(exc):
        names = [c.__name__ for c in type(e).__mro__] + [type(e).__module__ or ""]
        if any("hailo" in n.lower() for n in names) or "HAILO_" in str(e) or "libhailort" in str(e):
            return True
    return False


def _status_code(exc):
    """The numeric hailo_status of a raw _pyhailort.HailoRTStatusException (not every HailoRT call wraps it, e.g.
    LLM() creation), else None."""
    for e in _chain(exc):
        if type(e).__name__ == "HailoRTStatusException" and e.args:
            try:
                return int(e.args[0])
            except (TypeError, ValueError):
                return None
    return None


def classify(exc) -> str:
    """'device' | 'suspect' | 'request' (see the module doc)."""
    text = " ".join(f"{type(e).__name__}: {e}" for e in _chain(exc))
    code = _status_code(exc)
    if any(m in text for m in DEVICE_MARKERS) or code in DEVICE_CODES:
        return "device"
    if any(m in text for m in REQUEST_MARKERS) or code in REQUEST_CODES:
        return "request"
    if _is_hailo(exc):
        return "suspect"
    if isinstance(exc, (TimeoutError, OSError)):   # a socket / USB-level timeout outside HailoRT's own exceptions
        return "suspect"
    if isinstance(exc, REQUEST_TYPES):
        return "request"
    return "request"   # our own bugs (AttributeError ...) are not the device's fault either


class Unavailable(Exception):
    """The device is not usable right now: `state` is "recovering", "degraded" or "busy"."""

    def __init__(self, state: str, message: str, retry_after: float = 2.0):
        super().__init__(message)
        self.state, self.retry_after = state, retry_after


class DeviceGuard:
    """Runs device calls, watches their errors, and rebuilds the models when the device fails.

    build()          -> a models object (raises if the device or a model that must be there does not come up)
    release(models)  -> frees the models and the VDevice; must not raise for a dead device (errors are ignored)
    """

    def __init__(self, build, release, *, strikes: int = 3, backoff=(2.0, 5.0, 15.0), max_attempts: int = 3,
                 degraded_retry_s: float = 60.0, drain_s: float = 20.0, hang_s: float = 90.0, log=None,
                 clock=time.monotonic):
        self.build, self.release = build, release
        self.strikes_max, self.backoff, self.max_attempts = max(1, int(strikes)), tuple(backoff) or (0.0,), max(1, int(max_attempts))
        self.degraded_retry_s, self.drain_s, self.hang_s = degraded_retry_s, drain_s, hang_s
        self.log = log or (lambda msg: print("hailo worker: " + msg, flush=True))
        self.clock = clock
        self.models = None
        self.state = "starting"
        self.recoveries = 0          # successful rebuilds since start
        self.failed_attempts = 0     # failed rebuild attempts since start
        self.attempt = 0             # attempt number of the recovery in progress
        self.strikes = 0
        self.last_error = None       # {"kind", "error", "at"}
        self.last_recovery = None    # {"reason", "ok", "s", "at", "error"?}
        self._since = clock()
        self._lock = threading.Lock()
        self._inflight = {}          # token -> start time
        self._wake = threading.Event()
        self._closed = False
        self._thread = None

    # ------------------------------------------------------------------ life cycle
    def start(self):
        """First load (worker start-up). A failure here leaves the guard degraded, with the slow retry running."""
        try:
            self.models = self.build()
            self._set("ok")
        except Exception as e:
            self.last_error = {"kind": "device", "error": _short(e), "at": time.time()}
            self.log(f"device did not come up: {_short(e)}")
            self._set("recovering")
            self._spawn("start-up failed", first_attempt_done=True)
        return self

    def close(self):
        """Stop recovering and release what is loaded (worker shutdown)."""
        self._closed = True
        self._wake.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=30)   # a rebuild in progress (about 15 s of model loading) releases what it made
        m, self.models = self.models, None
        if m is not None:
            self._release(m)

    # ------------------------------------------------------------------ calls
    def call(self, fn):
        """fn(models) under watch. Raises Unavailable when the device is not usable; re-raises fn's own errors."""
        token = object()
        with self._lock:
            if self.state != "ok":
                raise Unavailable(self.state, self.message(), self._retry_after())
            busy = self._busy_s()
            if self.hang_s and busy > self.hang_s:
                raise Unavailable("busy", f"UGen busy: a device call has been running for {busy:.0f} s", 5.0)
            models = self.models
            self._inflight[token] = self.clock()
        try:
            out = fn(models)
        except Unavailable:
            raise
        except Exception as e:
            self.failed(e)
            raise
        else:
            with self._lock:
                self.strikes = 0
            return out
        finally:
            with self._lock:
                self._inflight.pop(token, None)

    def failed(self, exc) -> str:
        """Record a device-call error; start a recovery when it calls for one. Returns the kind."""
        kind = classify(exc)
        with self._lock:
            self.last_error = {"kind": kind, "error": _short(exc), "at": time.time()}
            if kind == "request" or self.state != "ok":
                return kind
            self.strikes += 1
            go = kind == "device" or self.strikes >= self.strikes_max
            if go:
                self.state, self._since, self.attempt = "recovering", self.clock(), 0
        if go:
            self.log(f"{kind} error ({_short(exc)}): releasing the models and the VDevice, then rebuilding")
            self._spawn(f"{kind}: {_short(exc)}")
        return kind

    def recover_now(self, reason: str = "manual") -> dict:
        """POST /recover: rebuild now (ok -> recovering), or cut a degraded wait short (after a replug)."""
        alive = self._thread is not None and self._thread.is_alive()
        with self._lock:
            new = self.state == "ok" or not alive
            if new:
                self.state, self._since, self.attempt = "recovering", self.clock(), 0
        if new:
            self._spawn(reason)
        else:
            self._wake.set()   # a recovery / degraded retry is waiting: try now
        return self.info()

    # ------------------------------------------------------------------ status
    def message(self) -> str:
        if self.state == "ok":
            return "UGen ok"
        if self.state == "recovering":
            return (f"UGen recovering (attempt {max(1, self.attempt)}/{self.max_attempts}) after: "
                    f"{(self.last_error or {}).get('error', 'a device error')}")
        if self.state == "degraded":
            retry = (f"or wait for the retry every {self.degraded_retry_s:.0f} s" if self.degraded_retry_s
                     else "no automatic retry")
            return (f"UGen degraded: {self.max_attempts} recovery attempts failed. Unplug and replug the UGen300 (then "
                    f"POST /recover, {retry}; restart the worker if that fails)")
        return f"UGen {self.state}"

    def info(self) -> dict:
        with self._lock:
            return {"state": self.state, "ok": self.state == "ok", "message": self.message(),
                    "since_s": round(self.clock() - self._since, 1), "recoveries": self.recoveries,
                    "failed_attempts": self.failed_attempts, "attempt": self.attempt, "strikes": self.strikes,
                    "busy_s": round(self._busy_s(), 1), "last_error": self.last_error, "last_recovery": self.last_recovery}

    # ------------------------------------------------------------------ internals
    def _busy_s(self) -> float:
        return (self.clock() - min(self._inflight.values())) if self._inflight else 0.0

    def _retry_after(self) -> float:
        return float(self.degraded_retry_s if self.state == "degraded" else self.backoff[0] or 1.0)

    def _set(self, state):
        with self._lock:
            self.state, self._since = state, self.clock()

    def _spawn(self, reason, first_attempt_done=False):
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2)   # a recovery that just set "ok" is only logging: let it end, then start a new one
            if t.is_alive():
                return          # still rebuilding: it serves this failure too
        self._wake.clear()
        self._thread = threading.Thread(target=self._recover, args=(reason, first_attempt_done), daemon=True,
                                        name="ugen-recover")
        self._thread.start()

    def _sleep(self, s) -> bool:
        """Wait s seconds (cut short by recover_now / close). False once closed."""
        if s > 0:
            self._wake.wait(s)
        self._wake.clear()
        return not self._closed

    def _release(self, m):
        try:
            self.release(m)
        except Exception as e:   # a dead device fails its release calls; that is expected
            self.log(f"release: {_short(e)}")

    def _recover(self, reason, first_attempt_done=False):
        t0 = self.clock()
        deadline = t0 + self.drain_s   # let calls already on the device finish (they fail fast on a dead link)
        while self._inflight and self.clock() < deadline and not self._closed:
            time.sleep(0.05)
        old, self.models = self.models, None
        if old is not None:
            self._release(old)
        attempts = 1 if first_attempt_done else 0
        if first_attempt_done:
            self.failed_attempts += 1
        while not self._closed:
            if attempts >= self.max_attempts:
                if self.state != "degraded":
                    self._set("degraded")
                    self.log(self.message())
                if not self.degraded_retry_s or not self._sleep(self.degraded_retry_s):
                    return
            else:
                with self._lock:
                    self.attempt = attempts + 1
                if not self._sleep(self.backoff[min(attempts, len(self.backoff) - 1)]):
                    return
            try:
                models = self.build()
            except Exception as e:
                attempts += 1
                self.failed_attempts += 1
                self.last_recovery = {"reason": reason, "ok": False, "s": round(self.clock() - t0, 1),
                                      "at": time.time(), "error": _short(e)}
                self.log(f"recovery attempt {attempts} failed: {_short(e)}")
                continue
            if self._closed:
                self._release(models)
                return
            self.last_recovery = {"reason": reason, "ok": True, "s": round(self.clock() - t0, 1), "at": time.time()}
            self.log(f"recovered in {self.clock() - t0:.1f} s (recovery {self.recoveries + 1})")
            with self._lock:
                self.models, self.strikes, self.attempt = models, 0, 0
                self.recoveries += 1
                self.state, self._since = "ok", self.clock()
            return


def _short(e) -> str:
    return f"{type(e).__name__}: {str(e)[:240]}"
