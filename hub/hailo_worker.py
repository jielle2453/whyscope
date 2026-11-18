r"""UGen300 worker: the one process that owns the device, served over localhost HTTP.

Only one process can open the UGen300 (a second one gets LIBUSB_ERROR_ACCESS), and HailoRT 5.3.2 for Windows ships one
wheel (cp313) that the hub's other dependencies may not share. So the hub never touches the device: it talks to this
worker. Start it with the Python that has HailoRT:

    C:\whyscope-hailo-venv\Scripts\python -m hub.hailo_worker            # listens on 127.0.0.1:8711
    config.yaml:  hailo.worker: http://127.0.0.1:8711

On start it loads, on ONE VDevice, whichever of these config keys are set: hailo.vlm_hef, hailo.llm_hef,
hailo.whisper_hef, hailo.yolo_hef, hailo.clip_image_hef. A model that fails to load is reported in /info and the others
still work. Only one GenAI LLM/VLM fits on the device (one KV cache): with hailo.vlm_hef set and hailo.llm_hef empty or
the same file, the VLM (Qwen3-VL-2B) is also the text LLM for /complete; a different llm_hef next to a VLM fails to load.

    POST /info                                  -> {"name", "models": {"llm"|"whisper"|"yolo"|"clip_image": {...}}}
    POST /prime      {"prefix"}                 -> {"ok"}
    POST /complete   {"prefix","turn","max_new","stop","priority"} -> {"text", "preempted", "ms"}
                     priority "low" (parent drafts) stops at the next token when a child request waits for the device
    POST /transcribe?lang=en   body: raw float32 little-endian mono 16 kHz PCM            -> {"text", "ms"}
    POST /detect               body: JPEG                                                  -> {"boxes": [...], "ms"}
    POST /clip_image           body: JPEG                                                  -> {"embedding": [512], "ms"}
    POST /shutdown                              -> {"ok"}; releases the models and the device, then exits
    POST /describe             body: raw uint8 frame, VLM input shape (/info models.vlm.frame_shape) -> {"text", "ms"}

/detect and /clip_image take a JPEG (Content-Type image/jpeg; needs Pillow in this Python) or, when this Python has no
Pillow, an already preprocessed uint8 array (Content-Type application/x-raw-u8; the hub does that): /detect a 640x640x3
letterbox with ?scale=&ox=&oy= (to map boxes back to the original image), /clip_image a 224x224x3 crop.
boxes: [{"label" (COCO), "score", "box": [x1, y1, x2, y2] in original-image pixels}], best first.

GenAI calls (LLM, Whisper) run one at a time (hub.hailo.GENAI_LOCK); each vision model has its own lock. It binds to
127.0.0.1 only: nothing on the network can reach it.

Self-recovery (hub/ugen_guard.py, docs/ugen.md "If the UGen stops responding"): every device call runs under a
DeviceGuard. A device-level error (HAILO_LIBUSB_FAILURE, communication closed ...; or the same kind of HailoRT error 3
times in a row) makes the worker release every model and the VDevice and load them again with backoff; meanwhile device
calls get HTTP 503 {"error", "state": "recovering"|"degraded"|"busy", "retry_after"} at once. After 3 failed attempts it
stays "degraded" (replug the UGen300; it still retries every 60 s). Bad requests (HAILO_INVALID_ARGUMENT, an empty turn,
a wrong body) get HTTP 400 and never start a recovery.

    POST /info  also -> "health": {"state", "ok", "message", "recoveries", "failed_attempts", "last_error", ...}
    POST /recover                               -> rebuild now (or retry now when degraded, e.g. after a replug)
"""
import argparse
import io
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .config import load_config
from .hailo import HailoLLM, HailoVision, HailoWhisper
from .hailo_vision import CLIP_SIZE, YOLO_SIZE, clip_u8, letterbox
from .ugen_guard import DeviceGuard, Unavailable, classify

# recovery defaults (code, not config.yaml): hailo.recovery.{strikes, max_attempts, backoff_s, degraded_retry_s, hang_s}
RECOVERY = {"strikes": 3, "max_attempts": 3, "backoff_s": [2, 5, 15], "degraded_retry_s": 60, "hang_s": 90, "reprime": 2}


def _load(models, name, cfg, key, make):
    """Load one model if its config key is set; record the result (or the error) in `models`."""
    if not (cfg.get("hailo") or {}).get(key):
        return None
    t = time.perf_counter()
    try:
        obj = make(cfg)
        models[name] = {"loaded": True, "name": getattr(obj, "name", name), "load_s": round(time.perf_counter() - t, 2)}
        return obj
    except Exception as e:
        models[name] = {"loaded": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
        print(f"hailo worker: {name} failed to load: {models[name]['error']}", flush=True)
        return None


def _same(cfg, a, b) -> bool:
    from .hailo import hef_path
    try:
        return hef_path(cfg, a).resolve() == hef_path(cfg, b).resolve()
    except Exception:
        return False


def _pil(data: bytes):
    from PIL import Image, ImageOps   # not in every HailoRT venv
    return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")


class Models:
    """Everything loaded on the one VDevice, with the /info record of each model."""

    def __init__(self):
        self.info, self.llm, self.vlm, self.s2t, self.vis = {}, None, None, None, None

    def loaded(self) -> set:
        return {k for k, v in self.info.items() if v.get("loaded")}


def load_models(cfg) -> Models:
    """Load whichever hailo.*_hef keys are set, on ONE VDevice. A model that fails is recorded in .info, not raised."""
    m, t0 = Models(), time.perf_counter()
    models = m.info
    h = cfg.get("hailo") or {}
    same = bool(h.get("vlm_hef")) and (not h.get("llm_hef") or _same(cfg, "llm_hef", "vlm_hef"))
    if h.get("vlm_hef"):   # Qwen3-VL-2B: describe() and, when llm_hef is empty or the same file, the text LLM too
        m.vlm = _load(models, "vlm", cfg, "vlm_hef", lambda c: HailoLLM(c, "vlm_hef", vlm=True))
        if m.vlm is not None:
            models["vlm"]["frame_shape"] = m.vlm.frame_shape
    if same:
        m.llm = m.vlm
        models["llm"] = dict(models.get("vlm") or {"loaded": False, "error": "vlm failed"}, shared_with="vlm")
    else:
        m.llm = _load(models, "llm", cfg, "llm_hef", HailoLLM)
    m.s2t = _load(models, "whisper", cfg, "whisper_hef", HailoWhisper)
    m.vis = HailoVision(cfg)
    for key, hef_key in HailoVision.KEYS:
        if key in m.vis.models:
            models[key] = {"loaded": True, "name": m.vis.names[key], "load_s": m.vis.load_s[key]}
        elif key in m.vis.errors:
            models[key] = {"loaded": False, "error": m.vis.errors[key]}
            print(f"hailo worker: {key} failed to load: {m.vis.errors[key]}", flush=True)
    print("hailo worker: " + ", ".join(f"{k} {'ok %.1fs' % v['load_s'] if v['loaded'] else 'FAILED'}" for k, v in models.items())
          + f"; {time.perf_counter() - t0:.1f} s in all", flush=True)
    return m


def release_models(m: Models):
    """Release every model, then the VDevice, so a new VDevice can be made (or the next worker starts clean). On a dead
    link these calls fail fast with HAILO_LIBUSB_FAILURE; the errors are ignored."""
    from . import hailo as _h
    for obj in {id(o): o for o in (m.llm, m.vlm) if o is not None}.values():
        try:
            obj.release()
        except Exception:
            pass
    if m.s2t is not None:
        try:
            m.s2t.s2t.release()
        except Exception:
            pass
    for v in list((m.vis.models if m.vis is not None else {}).values()):
        try:
            v.cm_ctx.__exit__(None, None, None)
        except Exception:
            pass
    if m.vis is not None:
        m.vis.models.clear()
    m.llm = m.vlm = m.s2t = None
    with _h._VDEV_LOCK:
        vd, _h._VDEV = _h._VDEV, None
    if vd is not None:
        try:
            vd.release()
        except Exception:
            pass
    # a call still stuck on the dead device keeps the old lock; the rebuilt models get a free one
    _h.GENAI_LOCK = threading.Lock()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8711)
    args = ap.parse_args()
    cfg = load_config()
    h = cfg.get("hailo") or {}
    rc = {**RECOVERY, **(h.get("recovery") or {})}
    wanted = [k for k in ("vlm_hef", "llm_hef", "whisper_hef", "yolo_hef", "clip_image_hef") if h.get(k)]
    expected = set()                 # models that loaded the first time: a rebuild must bring all of them back
    n_reprime = max(0, int(rc["reprime"]))
    recent = deque(maxlen=max(1, n_reprime))   # prefixes in recent use, re-primed after a rebuild
    recent_lock = threading.Lock()
    last_info = {}                   # the /info models record of the last good load (shown while recovering)

    def build():
        m = load_models(cfg)
        try:
            if not expected:   # first load (or a start-up with the device missing): anything at all is a start
                if wanted and not m.loaded():
                    raise RuntimeError("no model loaded: " + "; ".join(str(v.get("error")) for v in m.info.values())[:300])
                expected.update(m.loaded())
            else:
                missing = expected - m.loaded()
                if missing:
                    raise RuntimeError(f"{', '.join(sorted(missing))} did not load again: "
                                       + "; ".join(str(m.info[k].get("error")) for k in sorted(missing))[:300])
                with recent_lock:
                    again = list(recent) if n_reprime else []
                for p in again:   # also proves that save_context / load_context work again
                    m.llm.prime(p)
        except Exception:
            release_models(m)
            raise
        last_info.clear()
        last_info.update(m.info)
        return m

    bo = rc["backoff_s"]
    guard = DeviceGuard(build, release_models, strikes=int(rc["strikes"]), max_attempts=int(rc["max_attempts"]),
                        backoff=tuple(float(x) for x in (bo if isinstance(bo, (list, tuple)) else [bo])),
                        degraded_retry_s=float(rc["degraded_retry_s"]), hang_s=float(rc["hang_s"])).start()
    print(f"hailo worker: {guard.message()}, http://127.0.0.1:{args.port}", flush=True)

    def need(obj, what, m):
        if obj is None:
            raise LookupError(f"{what} is not loaded: " + str((m.info.get(what) or {}).get("error") or "its hailo.*_hef is not set"))
        return obj

    def used(prefix):
        with recent_lock:
            if prefix in recent:
                recent.remove(prefix)
            recent.append(prefix)

    def info():
        st = guard.info()
        m = guard.models
        if m is not None and st["ok"]:
            models = m.info
            if m.llm is not None and "llm" in models:
                models["llm"]["restore"] = m.llm.stats
                models["llm"]["contexts"] = len(m.llm._ctx)
        else:   # recovering / degraded: nothing can run until the rebuild is done
            models = {k: {**v, "loaded": False, "paused": st["state"]} for k, v in last_info.items()}
        return {"name": (models.get("llm") or {}).get("name", ""), "models": models, "health": st}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _device(self, path, q, raw, ctype, m):
            """One device call (run under the guard)."""
            import numpy as np
            if path == "/describe":
                v = need(m.vlm, "vlm", m)
                if ctype != "application/x-raw-u8":
                    raise ImportError("this worker takes the frame as raw uint8 only")
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(v.frame_shape)
                return {"text": v.describe(frame, q.get("ask") or "")}
            if path == "/prime":
                prefix = json.loads(raw)["prefix"]
                need(m.llm, "llm", m).prime(prefix)
                used(prefix)
                return {"ok": True}
            if path == "/complete":
                body = json.loads(raw)
                if not str(body.get("turn") or "").strip():
                    raise ValueError("turn is empty")   # HailoRT would say "Prompt cannot be empty"
                r = need(m.llm, "llm", m).complete_ex(body["prefix"], body["turn"], int(body["max_new"]), body.get("stop"),
                                                      "low" if body.get("priority") == "low" else "high")
                used(body["prefix"])
                return r
            if path == "/transcribe":
                audio = np.frombuffer(raw[:len(raw) // 4 * 4], dtype="<f4").copy()   # writable
                return {"text": need(m.s2t, "whisper", m).transcribe(audio, q.get("lang") or "en")}
            if path == "/detect":
                need(m.vis.models.get("yolo"), "yolo", m)
                if ctype == "application/x-raw-u8":
                    lb = np.frombuffer(raw, dtype=np.uint8).reshape(YOLO_SIZE, YOLO_SIZE, 3)
                    scale, pad = float(q["scale"]), (float(q.get("ox", 0)), float(q.get("oy", 0)))
                else:
                    lb, scale, ox, oy = letterbox(_pil(raw))
                    pad = (ox, oy)
                return {"boxes": m.vis.detect(lb, scale, pad, float(q.get("thr", 0.25)))}
            # /clip_image
            need(m.vis.models.get("clip_image"), "clip_image", m)
            if ctype == "application/x-raw-u8":
                crop = np.frombuffer(raw, dtype=np.uint8).reshape(CLIP_SIZE, CLIP_SIZE, 3)
            else:
                crop = clip_u8(_pil(raw))
            return {"embedding": m.vis.clip_image(crop)}

        def do_POST(self):
            u = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            t = time.perf_counter()
            try:
                if u.path == "/info":
                    return self._send(info())
                if u.path == "/recover":   # e.g. after replugging the UGen while the worker is degraded
                    return self._send({"ok": True, "health": guard.recover_now("POST /recover")})
                if u.path == "/shutdown":   # release the models so the device is clean for the next worker
                    self._send({"ok": True})
                    threading.Thread(target=server.shutdown, daemon=True).start()
                    return
                if u.path not in DEVICE_PATHS:
                    return self._send({"error": "not found"}, 404)
                r = guard.call(lambda m: self._device(u.path, q, raw, ctype, m))
                return self._send({**r, "ms": int((time.perf_counter() - t) * 1000)})
            except Unavailable as e:   # recovering / degraded / busy: refuse at once, the hub falls back
                self._send({"error": str(e), "state": e.state, "retry_after": e.retry_after}, 503)
            except LookupError as e:
                self._send({"error": str(e)}, 503)
            except ImportError as e:
                self._send({"error": f"{e}; send Content-Type application/x-raw-u8 instead of a JPEG"}, 501)
            except Exception as e:
                kind = classify(e)
                self._send({"error": f"{type(e).__name__}: {str(e)[:300]}", "kind": kind}, 400 if kind == "request" else 500)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()
    # Graceful stop (POST /shutdown): release every model, then the VDevice, before the process ends. A worker that is
    # killed instead leaves its LLM on the device, and the next worker's LLM / VLM then fails to load with
    # HAILO_INTERNAL_FAILURE(8) until a process that opened the device exits normally (measured 2026-11-15).
    print("hailo worker: shutting down", flush=True)
    guard.close()


DEVICE_PATHS = ("/describe", "/prime", "/complete", "/transcribe", "/detect", "/clip_image")


if __name__ == "__main__":
    main()
