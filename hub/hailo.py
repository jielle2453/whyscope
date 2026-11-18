"""Shared access to the Hailo-10H (ASUS UGen300) for `mode: hailo`.

The LLM path was verified on a UGen300 USB on 2026-11-13 (Windows 11, HailoRT 5.3.2, qwen2.5:1.5b HEF from
hailo-ollama); Whisper, yolov8s and the CLIP image encoder were verified in step 0 and share the same VDevice.
Numbers: docs/benchmarks.md and docs/hardware.md (step 9).

- One VDevice per process, and only ONE process can open the UGen300 (a second one gets LIBUSB_ERROR_ACCESS). With
  `hailo.worker` set, that process is `hub.hailo_worker` and the hub only talks HTTP to it.
- One VDevice for the whole process (Hailo's voice assistant shares one VDevice between Whisper and the LLM).
- One GenAI call at a time: two GenAI models must not generate in parallel on the same device, so every call goes
  through GENAI_LOCK.
- Prompts are raw ChatML text, not structured messages: that allows an assistant prefill ('{"explanation": "'),
  which keeps the output in JSON without long instructions. (Structured messages with content as a list of
  {'type': 'text'} parts made the model echo that structure, so content was a plain string in any case.)
- The system prompt and few-shot turns are the same for every question. They are prefilled once per language, saved
  with save_context(), and restored with load_context() before each question, so only the question is prefilled:
  about 1.7 s to the first token instead of 3.7 s. Every answer still starts from the same clean context.
  Qwen3 contexts are 147 MB (Qwen2.5: 44 MB) and take about 3 s to load over USB, so `hailo.llm_restore: auto`
  measures prefill against load on the first use of each prefix and keeps the faster one.
- Qwen2.5-1.5B, Qwen3-1.7B and Qwen3-VL-2B all use ChatML, so the hub's prompts stay the same; fit_turn() turns Qwen3's
  thinking off (empty think block) and visible() strips any think block from the output (2026-11-15).
- Only ONE GenAI LLM or VLM can be loaded on the device ("KV-Cache is already in use by another model"); Whisper, YOLO
  and CLIP fit next to it. A VLM (hailo.vlm_hef) can also serve as the text LLM (HailoLLM(vlm=True)).
- The HailoRT wheel exists for one Python version only (cp313 for HailoRT 5.3.2 on Windows). If the hub runs on another
  Python, set `hailo.worker` and start `python -m hub.hailo_worker` with the Python that has HailoRT: HailoLLMRemote
  then sends the same calls over localhost.
"""
import re
import threading
from collections import OrderedDict
from pathlib import Path

from .config import ROOT

GENAI_LOCK = threading.Lock()
_VDEV = None
_VDEV_LOCK = threading.Lock()
# Child requests come first on the one GenAI lock. A "high" call (a child's chat reply, AI guess, explanation, Whisper)
# counts itself here while it waits; a "low" call (a parent-assistant draft sentence) checks the count after every token
# and stops early (preempted) so the child never waits behind a whole draft sentence.
_HI_WAITING = 0
_HI_LOCK = threading.Lock()


def _hi_enter():
    global _HI_WAITING
    with _HI_LOCK:
        _HI_WAITING += 1


def _hi_leave():
    global _HI_WAITING
    with _HI_LOCK:
        _HI_WAITING = max(0, _HI_WAITING - 1)


def child_waiting() -> bool:
    return _HI_WAITING > 0


def available() -> bool:
    """True if the HailoRT Python package with GenAI support is importable."""
    try:
        import hailo_platform  # noqa: F401
        from hailo_platform.genai import LLM  # noqa: F401
        return True
    except Exception:
        return False


def hef_path(cfg: dict, key: str) -> Path:
    """Resolve cfg['hailo'][key] against the repo root; raise if unset or missing."""
    p = (cfg.get("hailo") or {}).get(key) or ""
    if not p:
        raise FileNotFoundError(f"config.yaml: hailo.{key} is not set")
    p = Path(p).expanduser()
    p = p if p.is_absolute() else ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"hailo.{key}: {p} does not exist")
    return p


def vdevice():
    """The hub's single VDevice (created on first use)."""
    global _VDEV
    with _VDEV_LOCK:
        if _VDEV is None:
            from hailo_platform import VDevice
            params = VDevice.create_params()
            params.group_id = "SHARED"   # hailo-apps SHARED_VDEVICE_GROUP_ID ("Do Not Change!")
            _VDEV = VDevice(params)
        return _VDEV


def chatml(msgs: list) -> str:
    """Qwen2.5 chat template (ChatML) for plain-string messages."""
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in msgs)


def stopper(spec):
    """Stop rule as data, so it can also cross to the worker: {"quote": '"', "ends": "。！？", "n": 1}.
    True once the text contains `quote`, or `n` sentence ends. A callable is returned unchanged."""
    if not spec or callable(spec):
        return spec
    q, ends, n = spec.get("quote") or "", spec.get("ends") or "", int(spec.get("n") or 0)
    return lambda out: bool(q and q in out) or bool(n and sum(out.count(c) for c in ends) >= n)


NO_THINK = "<think>\n\n</think>\n\n"   # Qwen3 chat template with enable_thinking=False: an empty think block
_THINK_RE = re.compile(r"<think>.*?(?:</think>\s*|$)", re.S)
_ASSISTANT = "<|im_start|>assistant\n"


def model_family(name: str) -> str:
    """'qwen3-vl' | 'qwen3' | 'qwen2' from a HEF file name (the hailo-ollama Qwen2.5 blob is a bare sha256 name)."""
    n = (name or "").lower().replace("_", "-")
    if "qwen3-vl" in n:
        return "qwen3-vl"
    return "qwen3" if "qwen3" in n else "qwen2"


def visible(text: str) -> str:
    """Model text without think blocks (closed or still open) and without end-of-turn tokens."""
    return _THINK_RE.sub("", text or "").replace("<|im_end|>", "").replace("<|endoftext|>", "")


def fit_turn(turn: str, family: str) -> str:
    """All three models use ChatML. Qwen3 (text) is a hybrid thinking model: the generation prompt gets an empty think
    block, which is how its own template turns thinking off. Qwen2.5 and Qwen3-VL-2B-Instruct (no thinking mode) are
    unchanged. Any assistant prefill after the generation prompt (compose's '{"explanation": "') stays after the block."""
    if family != "qwen3":
        return turn
    i = turn.rfind(_ASSISTANT)
    if i < 0 or turn[i + len(_ASSISTANT):].startswith("<think>"):
        return turn
    j = i + len(_ASSISTANT)
    return turn[:j] + NO_THINK + turn[j:]


class HailoLLM:
    """A GenAI LLM HEF on the Hailo-10H: Qwen2.5-1.5B-Instruct, Qwen3-1.7B-Instruct, or Qwen3-VL-2B-Instruct used as the
    text model (vlm=True: the VLM class with no frames; the same object then also serves describe()).

    Measured on the UGen300 at 1.5 A (docs/ugen.md): only ONE GenAI LLM/VLM can be loaded per device ("KV-Cache is
    already in use by another model"), so a VLM and a separate text LLM never fit together; Whisper, YOLO and CLIP do."""

    def __init__(self, cfg: dict, key: str = "llm_hef", vlm: bool = False):
        from hailo_platform.genai import LLM, VLM
        self.cfg = cfg
        h = cfg.get("hailo") or {}
        path = hef_path(cfg, key)
        self.is_vlm = vlm
        with GENAI_LOCK:
            self.llm = VLM(vdevice(), str(path)) if vlm else LLM(vdevice(), str(path))
        self.name = path.name
        self.family = h.get("llm_family") or model_family(path.name)
        # "context": save the prefilled prefix once and load it per call (Qwen2.5: 44 MB, about 0.3 s); "prefill": prefill
        # prefix + turn in one pass every call (cheaper when the saved context is big: Qwen3 contexts are 147 MB, a
        # load takes about 3 s over USB); "auto" measures both on the first use of each prefix.
        self.restore_mode = str(h.get("llm_restore") or "auto")
        # prefix text -> saved context, or None when this prefix is prefilled every call. LRU, at most llm_ctx_max
        # prefixes (each saved Qwen2.5 context is 44 MB of host memory; the hub uses 8 fixed prefixes: chat, guess,
        # compose and the parent assistant, en + zh). An evicted prefix is prefilled and saved again on its next use.
        self._ctx = OrderedDict()
        self.ctx_max = max(1, int(h.get("llm_ctx_max") or 8))
        self.stats = {}  # prefix length -> {"prefill_s", "load_s", "mode"} (shown in the worker's /info)
        self.frame_shape = [int(x) for x in self.llm.input_frame_shape()] if vlm else None

    def _gen(self, prompt, **kw):
        return self.llm.generate(prompt=prompt, frames=[], **kw) if self.is_vlm else self.llm.generate(prompt=prompt, **kw)

    def _gen_all(self, prompt, **kw):
        return self.llm.generate_all(prompt=prompt, frames=[], **kw) if self.is_vlm else self.llm.generate_all(prompt=prompt, **kw)

    def _restore(self, prefix: str) -> bool:
        """Get the device context ready for `prefix` (call under GENAI_LOCK). True: the saved context is loaded and only
        the turn needs prefilling; False: the context is clear and the caller sends prefix + turn in one pass."""
        import time
        if prefix in self._ctx:
            self._ctx.move_to_end(prefix)
            ctx = self._ctx[prefix]
            if ctx is None:
                self.llm.clear_context()
                return False
            self.llm.load_context(ctx)
            return True
        if self.restore_mode == "prefill":
            self._remember(prefix, None)
            self.llm.clear_context()
            return False
        self.llm.clear_context()
        t = time.perf_counter()
        # end the prefix at its last <|im_end|>: the one token generated here is the newline that follows it
        self._gen_all(prefix.rstrip("\n"), do_sample=False, max_generated_tokens=1)
        prefill_s = time.perf_counter() - t
        ctx = self.llm.save_context()
        t = time.perf_counter()
        self.llm.load_context(ctx)
        load_s = time.perf_counter() - t
        keep = self.restore_mode == "context" or load_s < prefill_s
        self._remember(prefix, ctx if keep else None)
        self.stats[str(len(prefix))] = {"prefill_s": round(prefill_s, 2), "load_s": round(load_s, 2),
                                        "mode": "context" if keep else "prefill"}
        if not keep:
            self.llm.clear_context()
        return keep

    def _remember(self, prefix: str, ctx):
        self._ctx[prefix] = ctx
        self._ctx.move_to_end(prefix)
        while len(self._ctx) > self.ctx_max:
            self._ctx.popitem(last=False)

    def prefixes(self) -> list:
        """Known prefixes, least recently used first (the worker re-primes the recent ones after a recovery)."""
        return list(self._ctx.keys())

    def release(self):
        """Free the saved contexts and the model on the device (errors from a dead device are the caller's to ignore)."""
        self._ctx.clear()
        llm, self.llm = self.llm, None
        if llm is not None:
            llm.release()

    def prime(self, prefix: str):
        """Prefill and save a prefix ahead of the first question (hub start-up)."""
        with GENAI_LOCK:
            self._restore(prefix)

    def complete(self, prefix: str, turn: str, max_new: int, stop=None, priority: str = "high") -> str:
        """Raw ChatML completion: restore `prefix`, then stream `turn`; stop early once stop(text so far) is true."""
        return self.complete_ex(prefix, turn, max_new, stop, priority)["text"]

    def complete_ex(self, prefix: str, turn: str, max_new: int, stop=None, priority: str = "high") -> dict:
        """complete() plus {"preempted": True} when a "low" call stopped because a child request was waiting."""
        h = self.cfg.get("hailo") or {}
        stop = stopper(stop)
        out, preempted, low = "", False, priority == "low"
        if not low:
            _hi_enter()
        try:
            with GENAI_LOCK:
                if not low:
                    _hi_leave()
                    low = None   # already counted out
                elif child_waiting():
                    return {"text": "", "preempted": True}
                turn = fit_turn(turn, self.family)
                prompt = turn if self._restore(prefix) else prefix + turn
                with self._gen(prompt, temperature=float(h.get("temperature", 0.1)),
                               seed=int(h.get("seed", 42)), max_generated_tokens=int(max_new)) as gen:
                    for tok in gen:
                        out += tok
                        if stop and stop(visible(out)):
                            break
                        if low and child_waiting():
                            preempted = True
                            break
        finally:
            if low is False:   # a high call that never got the lock (an error before it)
                _hi_leave()
        return {"text": visible(out), "preempted": preempted}

    # the hub sends its own instruction (hub/vision.py DESCRIBE_EN); this is the worker's default for direct calls
    DESCRIBE_EN = ("What is the main thing in this picture, not counting any person? Answer with a short noun phrase only, "
                   "like 'a striped umbrella'.")

    def describe(self, frame, ask: str = "", max_new: int = 12) -> str:
        """VLM only: one frame (uint8, self.frame_shape) -> a short English noun phrase (child priority)."""
        import numpy as np
        if not self.is_vlm:
            raise LookupError("the loaded GenAI model is not a VLM")
        h = self.cfg.get("hailo") or {}
        frame = np.array(frame, dtype=np.uint8, order="C").reshape(self.frame_shape)   # a writable copy (HailoRT needs it)
        prompt = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": ask or self.DESCRIBE_EN}]}]
        out = ""
        _hi_enter()
        entered = True
        try:
            with GENAI_LOCK:
                _hi_leave()
                entered = False
                self.llm.clear_context()
                with self.llm.generate(prompt=prompt, frames=[frame], temperature=float(h.get("temperature", 0.1)),
                                       seed=int(h.get("seed", 42)), max_generated_tokens=int(max_new)) as gen:
                    for tok in gen:
                        out += tok
                        if "\n" in visible(out):
                            break
                self.llm.clear_context()   # the next text call restores its own prefix anyway
        finally:
            if entered:
                _hi_leave()
        return visible(out).strip().splitlines()[0].strip() if visible(out).strip() else ""


class WorkerUnavailable(RuntimeError):
    """The worker is down, recovering the UGen, or degraded: the caller should use its fallback right away."""


# worker url -> (monotonic time until which calls fail fast, why). Set when the worker says it is recovering / degraded /
# busy (HTTP 503 with "state"), or cannot be reached; cleared by a good /info. Shared by every client of that worker
# (chat, compose, assistant, ASR, vision), so one failed call spares the others the wait. /info always goes through.
_DOWN = {}
DOWN_HOLD_S = {"recovering": 3.0, "busy": 5.0, "degraded": 10.0, "unreachable": 10.0}


def _mark_down(url: str, state: str, why: str, hold: float = None):
    import time
    why = why if why.startswith("UGen") else f"UGen {state}: {why}"
    _DOWN[url] = (time.monotonic() + (DOWN_HOLD_S.get(state, 3.0) if hold is None else hold), why)


def worker_down(cfg_or_url) -> str:
    """Why the worker is known to be unusable right now ("" when it is not): lets callers skip a call they would lose."""
    import time
    url = cfg_or_url if isinstance(cfg_or_url, str) else str((cfg_or_url.get("hailo") or {}).get("worker") or "")
    hit = _DOWN.get(url.rstrip("/")) if url else None
    return hit[1] if hit and time.monotonic() < hit[0] else ""


class WorkerClient:
    """Localhost HTTP client for `python -m hub.hailo_worker` (cfg['hailo']['worker']); never goes through a proxy."""

    def __init__(self, cfg: dict):
        import urllib.request
        self.url = str(cfg["hailo"]["worker"]).rstrip("/")
        self._open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

    def post(self, path: str, body=None, timeout: float = 120, ctype: str = "application/json"):
        """POST `body` (a dict -> JSON, or raw bytes with `ctype`); returns the decoded JSON reply. Raises
        WorkerUnavailable at once while the worker is known to be down (see _DOWN), RuntimeError for other errors."""
        import json
        import socket
        import urllib.error
        import urllib.request
        if path not in ("/info", "/recover", "/shutdown"):   # device calls only
            why = worker_down(self.url)
            if why:
                raise WorkerUnavailable(f"worker {path}: {why}")
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(self.url + path, data, {"Content-Type": ctype})
        try:
            with self._open(req, timeout=timeout) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:   # keep the worker's own message
            try:
                rep = json.loads(e.read())
            except Exception:
                rep = {}
            msg, state = rep.get("error"), rep.get("state")
            if e.code == 503 and state:   # the worker's device guard: recovering / degraded / busy
                _mark_down(self.url, state, str(msg or ""), min(float(rep.get("retry_after") or 3), DOWN_HOLD_S.get(state, 3.0)))
                raise WorkerUnavailable(f"worker {path} -> HTTP 503 ({state}): {msg}") from None
            raise RuntimeError(f"worker {path} -> HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, ConnectionError) as e:   # not running (Windows takes ~2 s to refuse localhost)
            _mark_down(self.url, "unreachable", f"{type(e).__name__}: {str(e)[:120]}")
            raise WorkerUnavailable(f"worker {path}: cannot reach {self.url}: {e}") from None
        except (TimeoutError, socket.timeout) as e:
            if timeout >= 20:   # a long wait ran out: the worker is stuck, so the next callers fall back at once
                _mark_down(self.url, "busy", f"no reply in {timeout:g} s")   # (a short /describe or /info wait is no sign)
            raise WorkerUnavailable(f"worker {path}: no reply in {timeout:g} s") from e
        if path == "/info":
            h = out.get("health") or {}
            if h.get("state") and h["state"] != "ok":
                _mark_down(self.url, h["state"], str(h.get("message") or ""))
            else:
                _DOWN.pop(self.url, None)
        return out

    def info(self, timeout: float = 10) -> dict:
        return self.post("/info", {}, timeout)


class HailoLLMRemote:
    """HailoLLM's interface, served by `python -m hub.hailo_worker` at cfg['hailo']['worker'] (localhost only)."""

    def __init__(self, cfg: dict):
        self.client = WorkerClient(cfg)
        info = self.client.info()
        llm = (info.get("models") or {}).get("llm") or {}
        if not llm.get("loaded", bool(info.get("name"))):
            raise RuntimeError("worker has no LLM loaded: " + str(llm.get("error") or "hailo.llm_hef not set"))
        self.name = (llm.get("name") or info.get("name") or "llm") + " (worker)"

    def _post(self, path: str, body: dict, timeout: float = 120):
        return self.client.post(path, body, timeout)

    def prime(self, prefix: str):
        self._post("/prime", {"prefix": prefix})

    def complete(self, prefix: str, turn: str, max_new: int, stop=None, priority: str = "high") -> str:
        return self.complete_ex(prefix, turn, max_new, stop, priority)["text"]

    def complete_ex(self, prefix: str, turn: str, max_new: int, stop=None, priority: str = "high") -> dict:
        """{"text", "preempted"}. priority "low" (parent drafts) yields to any child request at the worker. A worker
        started before priorities existed ignores the field and never reports "preempted"."""
        if callable(stop):
            raise TypeError("HailoLLMRemote needs the stop rule as a dict (see stopper)")
        r = self._post("/complete", {"prefix": prefix, "turn": turn, "max_new": int(max_new), "stop": stop,
                                     "priority": priority})
        return {"text": r.get("text", ""), "preempted": bool(r.get("preempted"))}


class HailoWhisper:
    """Whisper on the Hailo-10H. `audio` is float32 mono 16 kHz in [-1, 1]."""

    def __init__(self, cfg: dict):
        from hailo_platform.genai import Speech2Text
        path = hef_path(cfg, "whisper_hef")
        with GENAI_LOCK:
            self.s2t = Speech2Text(vdevice(), str(path))
        self.name = path.name

    def transcribe(self, audio, lang: str = "en") -> str:
        import numpy as np
        from hailo_platform.genai import Speech2TextTask
        data = np.array(audio, dtype="<f4")   # writable copy
        _hi_enter()   # a child is talking: a parent draft in flight stops at its next token
        entered = True
        try:
            with GENAI_LOCK:
                _hi_leave()
                entered = False
                segs = self.s2t.generate_all_segments(audio_data=data, task=Speech2TextTask.TRANSCRIBE,
                                                      language=lang or "en", timeout_ms=15000)
        finally:
            if entered:
                _hi_leave()
        return "".join(s.text for s in (segs or [])).strip().replace("�", "")   # Whisper-Small can emit broken UTF-8


class HailoWhisperRemote:
    """HailoWhisper's interface over the worker. Wire format of POST /transcribe?lang=xx: the request body is raw
    float32 little-endian mono 16 kHz PCM (what the hub's decoder already produces), the reply {"text", "ms"}."""

    def __init__(self, cfg: dict):
        self.client = WorkerClient(cfg)
        self.name = "whisper (worker)"
        self.ms = None   # worker-side time of the last call

    def transcribe(self, audio, lang: str = "en") -> str:
        import numpy as np
        r = self.client.post(f"/transcribe?lang={lang or 'en'}", np.asarray(audio, dtype="<f4").tobytes(), 30,
                             "application/octet-stream")
        self.ms = r.get("ms")
        return str(r.get("text", ""))


class _Infer:
    """One single-input HEF through the InferModel API, outputs as FLOAT32 (from eval/ugen/hailo_models.py)."""

    def __init__(self, hef: str, timeout_ms: int = 10000):
        import numpy as np
        from hailo_platform import FormatType
        self.timeout = timeout_ms
        self.m = vdevice().create_infer_model(hef)
        for o in self.m.outputs:
            o.set_format_type(FormatType.FLOAT32)
        self.inp = self.m.input()
        self.out_names = list(self.m.output_names)
        self.cm_ctx = self.m.configure()
        self.cm = self.cm_ctx.__enter__()
        self._np = np

    def run(self, arr_u8):
        np = self._np
        arr = np.array(arr_u8, dtype=np.uint8, order="C")   # a writable copy (HailoRT rejects read-only buffers)
        outs = {o.name: np.empty(o.shape, dtype=np.float32) for o in self.m.outputs}
        b = self.cm.create_bindings(input_buffers={self.inp.name: arr}, output_buffers=outs)
        self.cm.run([b], self.timeout)
        return {n: b.output(n).get_buffer() for n in self.out_names}


class HailoVision:
    """yolov8s (COCO detection) and the CLIP ViT-B/32 image encoder on the Hailo-10H. Each model is optional and fails
    on its own: `errors` says why one is missing. Inputs are already preprocessed uint8 arrays (hub/hailo_vision.py).
    One lock per model; vision calls need not wait for GenAI calls (step 0: interleaving is safe)."""

    KEYS = (("yolo", "yolo_hef"), ("clip_image", "clip_image_hef"))

    def __init__(self, cfg: dict):
        self.models, self.errors, self.load_s, self.names = {}, {}, {}, {}
        self.locks = {k: threading.Lock() for k, _ in self.KEYS}
        import time
        for key, hef_key in self.KEYS:
            if not (cfg.get("hailo") or {}).get(hef_key):
                continue
            t = time.perf_counter()
            try:
                path = hef_path(cfg, hef_key)
                self.models[key] = _Infer(str(path))
                self.names[key] = path.name
                self.load_s[key] = round(time.perf_counter() - t, 2)
            except Exception as e:
                self.errors[key] = f"{type(e).__name__}: {str(e)[:200]}"

    def _run(self, key, arr):
        if key not in self.models:
            raise RuntimeError(f"{key} is not loaded on the device")
        with self.locks[key]:
            return list(self.models[key].run(arr).values())[0]

    def detect(self, letterboxed, scale, pad, thr: float = 0.25) -> list:
        """640x640x3 uint8 letterbox -> [{"label", "score", "box"}] in original-image pixels."""
        from .hailo_vision import decode_nms
        return decode_nms(self._run("yolo", letterboxed), scale, pad, thr)

    def clip_image(self, crop224) -> list:
        """224x224x3 uint8 -> 512 floats, L2-normalised."""
        from .hailo_vision import l2
        return l2(self._run("clip_image", crop224)).tolist()


class HailoVisionRemote:
    """HailoVision's interface over the worker. Sends the preprocessed arrays as raw bytes (the worker's venv may
    have no Pillow); POST /detect?scale=&ox=&oy= takes 640x640x3 uint8, POST /clip_image takes 224x224x3 uint8."""

    def __init__(self, cfg: dict):
        self.client = WorkerClient(cfg)
        self.ms = {}   # worker-side time of the last call per endpoint

    def detect(self, letterboxed, scale, pad, thr: float = 0.25) -> list:
        import numpy as np
        r = self.client.post(f"/detect?scale={scale}&ox={pad[0]}&oy={pad[1]}&thr={thr}",
                             np.ascontiguousarray(letterboxed, dtype=np.uint8).tobytes(), 20, "application/x-raw-u8")
        self.ms["detect"] = r.get("ms")
        return r["boxes"]

    def clip_image(self, crop224) -> list:
        import numpy as np
        r = self.client.post("/clip_image", np.ascontiguousarray(crop224, dtype=np.uint8).tobytes(), 20,
                             "application/x-raw-u8")
        self.ms["clip_image"] = r.get("ms")
        return r["embedding"]

    def describe(self, frame, timeout: float = 8, ask: str = "") -> str:
        """POST /describe: one uint8 frame in the VLM's input shape (worker /info models.vlm.frame_shape, H x W x 3)
        -> a short English noun phrase ("a red balloon"). `ask` replaces the worker's default instruction."""
        import numpy as np
        from urllib.parse import quote
        a = np.ascontiguousarray(frame, dtype=np.uint8)
        q = f"/describe?h={a.shape[0]}&w={a.shape[1]}" + (f"&ask={quote(ask)}" if ask else "")
        r = self.client.post(q, a.tobytes(), timeout, "application/x-raw-u8")
        self.ms["describe"] = r.get("ms")
        return str(r.get("text", ""))
