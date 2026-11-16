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
"""
import argparse
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .config import load_config
from .hailo import HailoLLM, HailoVision, HailoWhisper
from .hailo_vision import CLIP_SIZE, YOLO_SIZE, clip_u8, letterbox


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8711)
    args = ap.parse_args()
    cfg = load_config()
    models, t0 = {}, time.perf_counter()
    h = cfg.get("hailo") or {}
    same = bool(h.get("vlm_hef")) and (not h.get("llm_hef") or _same(cfg, "llm_hef", "vlm_hef"))
    vlm = None
    if h.get("vlm_hef"):   # Qwen3-VL-2B: describe() and, when llm_hef is empty or the same file, the text LLM too
        vlm = _load(models, "vlm", cfg, "vlm_hef", lambda c: HailoLLM(c, "vlm_hef", vlm=True))
        if vlm is not None:
            models["vlm"]["frame_shape"] = vlm.frame_shape
    if same:
        llm = vlm
        models["llm"] = dict(models.get("vlm") or {"loaded": False, "error": "vlm failed"}, shared_with="vlm")
    else:
        llm = _load(models, "llm", cfg, "llm_hef", HailoLLM)
    s2t = _load(models, "whisper", cfg, "whisper_hef", HailoWhisper)
    vis = HailoVision(cfg)
    for key, hef_key in HailoVision.KEYS:
        if key in vis.models:
            models[key] = {"loaded": True, "name": vis.names[key], "load_s": vis.load_s[key]}
        elif key in vis.errors:
            models[key] = {"loaded": False, "error": vis.errors[key]}
            print(f"hailo worker: {key} failed to load: {vis.errors[key]}", flush=True)
    print("hailo worker: " + ", ".join(f"{k} {'ok %.1fs' % v['load_s'] if v['loaded'] else 'FAILED'}" for k, v in models.items())
          + f"; {time.perf_counter() - t0:.1f} s in all, http://127.0.0.1:{args.port}", flush=True)

    def need(obj, what):
        if obj is None:
            raise LookupError(f"{what} is not loaded: " + str((models.get(what) or {}).get("error") or "its hailo.*_hef is not set"))
        return obj

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

        def do_POST(self):
            u = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            t = time.perf_counter()
            ms = lambda: int((time.perf_counter() - t) * 1000)  # noqa: E731
            try:
                if u.path == "/info":
                    if llm is not None and getattr(llm, "stats", None):
                        models["llm"]["restore"] = llm.stats
                    return self._send({"name": (models.get("llm") or {}).get("name", ""), "models": models})
                if u.path == "/describe":
                    import numpy as np
                    v = need(vlm, "vlm")
                    if ctype != "application/x-raw-u8":
                        raise ImportError("this worker takes the frame as raw uint8 only")
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape(v.frame_shape)
                    return self._send({"text": v.describe(frame, q.get("ask") or ""), "ms": ms()})
                if u.path == "/prime":
                    need(llm, "llm").prime(json.loads(raw)["prefix"])
                    return self._send({"ok": True})
                if u.path == "/complete":
                    body = json.loads(raw)
                    r = need(llm, "llm").complete_ex(body["prefix"], body["turn"], int(body["max_new"]), body.get("stop"),
                                                     "low" if body.get("priority") == "low" else "high")
                    return self._send({**r, "ms": ms()})
                if u.path == "/transcribe":
                    import numpy as np
                    audio = np.frombuffer(raw[:len(raw) // 4 * 4], dtype="<f4").copy()   # writable
                    return self._send({"text": need(s2t, "whisper").transcribe(audio, q.get("lang") or "en"), "ms": ms()})
                if u.path == "/detect":
                    need(vis.models.get("yolo"), "yolo")
                    if ctype == "application/x-raw-u8":
                        import numpy as np
                        lb = np.frombuffer(raw, dtype=np.uint8).reshape(YOLO_SIZE, YOLO_SIZE, 3)
                        scale, pad = float(q["scale"]), (float(q.get("ox", 0)), float(q.get("oy", 0)))
                    else:
                        lb, scale, ox, oy = letterbox(_pil(raw))
                        pad = (ox, oy)
                    return self._send({"boxes": vis.detect(lb, scale, pad, float(q.get("thr", 0.25))), "ms": ms()})
                if u.path == "/clip_image":
                    need(vis.models.get("clip_image"), "clip_image")
                    if ctype == "application/x-raw-u8":
                        import numpy as np
                        crop = np.frombuffer(raw, dtype=np.uint8).reshape(CLIP_SIZE, CLIP_SIZE, 3)
                    else:
                        crop = clip_u8(_pil(raw))
                    return self._send({"embedding": vis.clip_image(crop), "ms": ms()})
                if u.path == "/shutdown":   # release the models so the device is clean for the next worker
                    self._send({"ok": True})
                    threading.Thread(target=server.shutdown, daemon=True).start()
                    return
                self._send({"error": "not found"}, 404)
            except LookupError as e:
                self._send({"error": str(e)}, 503)
            except ImportError as e:
                self._send({"error": f"{e}; send Content-Type application/x-raw-u8 instead of a JPEG"}, 501)
            except Exception as e:
                self._send({"error": f"{type(e).__name__}: {str(e)[:300]}"}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()
    # Graceful stop (POST /shutdown): release every model, then the VDevice, before the process ends. A worker that is
    # killed instead leaves its LLM on the device, and the next worker's LLM / VLM then fails to load with
    # HAILO_INTERNAL_FAILURE(8) until a process that opened the device exits normally (measured 2026-11-15).
    print("hailo worker: shutting down", flush=True)
    for obj in {id(o): o for o in (llm, vlm, s2t) if o is not None}.values():
        for attr in ("llm", "s2t"):
            try:
                getattr(getattr(obj, attr, None), "release", lambda: None)()
            except Exception:
                pass
    for m in list(vis.models.values()):
        try:
            m.cm_ctx.__exit__(None, None, None)
        except Exception:
            pass
    try:
        from . import hailo as _h
        if _h._VDEV is not None:
            _h._VDEV.release()
    except Exception:
        pass


if __name__ == "__main__":
    main()
