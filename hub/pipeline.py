"""Pipeline (spec section 8): listen -> safety -> vision -> recall -> compose -> log.

Two phases (product pass 1, B): `ask_first` returns as soon as recall/safety is done (the first sentence is spoken
at once), the compose step runs in a background thread and is collected with `poll` / `wait`.
`ask` keeps the old blocking behaviour (both phases) for scripts and tests.
Audio and image bytes are used in memory only and never persisted.
"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import db as dbm
from . import wording
from .compose import Composer
from .config import load_config, resolve
from .emoji import emoji_for
from .listen import Listener
from .memory import Memory
from .recall import Recall
from .safety import Safety
from .vision import Vision

UNSURE = "我不確定，我們一起去問爸爸媽媽好嗎？"
NOT_HEARD = "我沒聽清楚，再說一次好嗎？"
NO_QUESTION = "你想問我什麼呢？"
PENDING_TTL_S = 300


def _ms(t0) -> int:
    return int((time.perf_counter() - t0) * 1000)


class Pipeline:
    def __init__(self, cfg: dict = None, preload_models: bool = True):
        self.cfg = cfg or load_config()
        self.db = dbm.DB(resolve(self.cfg, "db"))
        self.db.purge(int(self.db.setting_get("retention_days", self.cfg.get("retention_days", 30))))
        self.memory = Memory(self.db)
        self.safety = Safety(self.cfg)
        self.recall = Recall(self.cfg)
        self.listener = Listener(self.cfg)
        self.vision = Vision(self.cfg)
        self.composer = Composer(self.cfg)
        self.lock = threading.Lock()  # one child, one device: serialise recall / safety / ASR
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._pending = {}            # pending_id -> {"done": Event, "result": dict|None, "ts": float}
        self._plock = threading.Lock()
        self._answered = 0            # answered questions so far (for the reaction cadence)
        self._last_bridge = False     # did the previous answer use a bridge? (<= 1 in 2)
        if preload_models:
            threading.Thread(target=self.listener.warm, daemon=True).start()

    def status(self) -> dict:
        """Which optional components are live (for /healthz)."""
        return {"mode": self.cfg.get("mode"), "device": self.recall.device, "entries": len(self.recall.entries),
                "asr_ready": self.listener.model is not None, "asr_error": self.listener.error,
                "compose_backend": self.composer.backend if self.composer.ready else None,
                "compose_error": self.composer.error, "vision_available": self.vision.available,
                "safety_categories": sorted(self.safety.triggers)}

    # ------------------------------------------------------------------ public API
    def ask(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text", log: bool = True) -> dict:
        """Blocking: first phase, then wait for the compose phase. Returns the complete result."""
        r = self.ask_first(text, audio, image, mode, log)
        pid = r.get("pending_id")
        return self.wait(pid, 30) if pid else r

    def ask_first(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text",
                  log: bool = True, t0: float = None) -> dict:
        """Phase 1. Answered questions come back with pending=True, pending_id and an empty explanation."""
        t0 = t0 if t0 is not None else time.perf_counter()
        with self.lock:
            return self._first(text or "", audio, image, mode, log, t0)

    def poll(self, pid: str):
        """The finished result for a pending_id, {"pending": True} while composing, None if unknown."""
        with self._plock:
            p = self._pending.get(pid)
        if p is None:
            return None
        return p["result"] if p["done"].is_set() else {"pending": True, "pending_id": pid}

    def wait(self, pid: str, timeout: float = 30.0) -> dict:
        with self._plock:
            p = self._pending.get(pid)
        if p:
            p["done"].wait(timeout)
            if p["result"]:
                return p["result"]
        return {"pending": True, "pending_id": pid}

    # ------------------------------------------------------------------ internals
    def _log(self, mode, r, lat, log):
        r["latency_ms"] = lat
        r["event_id"] = None
        if log:
            r["event_id"] = self.db.insert_event(mode=mode, **{k: r.get(k) for k in (
                "question", "object", "topic", "kb_id", "status", "first_sentence", "explanation", "ask_back",
                "bridge_used")}, sensitive_category=r.get("sensitive_category"), latency_ms=lat)

    def _done(self, mode, r, lat, t0, log=True):
        """Complete (non-pending) result: abstained / sensitive / not heard."""
        lat["total"] = lat["first_sentence"] = _ms(t0)
        r.update(first_sentence_ms=lat["total"], pending=False, pending_id=None, reaction="", emoji="")
        self._log(mode, r, lat, log)
        return r

    def _first(self, text, audio, image, mode, log, t0):
        lat = {"listen": 0, "vision": 0, "recall": 0, "compose": 0, "safety": 0}
        r = {"question": text, "object": None, "topic": None, "kb_id": None, "confidence": 0.0,
             "status": "abstained", "first_sentence": "", "explanation": "", "ask_back": "", "bridge_used": None, "reason": ""}

        # 1. listen
        if audio:
            t = time.perf_counter()
            try:
                text = self.listener.transcribe(audio)
            except Exception as e:
                text = ""
                self.listener.error = f"{type(e).__name__}: {str(e)[:200]}"
            lat["listen"] = _ms(t)
            r["question"] = text
            if not text.strip():
                r["first_sentence"], r["reason"] = NOT_HEARD, "not_heard"
                return self._done(mode, r, lat, t0, log)
        if not text.strip():
            if not image:
                r["first_sentence"], r["reason"] = NO_QUESTION, "no_question"
                return self._done(mode, r, lat, t0, False)
            text = "這是什麼"
            r["question"] = text

        # 2. safety
        t = time.perf_counter()
        hit = self.safety.check(text)
        lat["safety"] = _ms(t)
        if hit:
            r.update(status="sensitive", first_sentence=hit["deflection_zh"], sensitive_category=hit["category"],
                     urgent=hit["urgent"])
            return self._done(mode, r, lat, t0, log)

        # 3. vision (optional)
        obj = None
        if image:
            t = time.perf_counter()
            v = self.vision.label(image, self.recall.vision_labels())
            lat["vision"] = _ms(t)
            if v:
                obj, r["confidence"] = v

        # 4. recall
        t = time.perf_counter()
        entry, score = self.recall.search(text, obj)
        lat["recall"] = _ms(t)
        r["confidence"] = round(score, 3)
        if entry is None or score < float(self.cfg["recall"]["threshold"]):
            r["first_sentence"], r["reason"] = UNSURE, "unsure"
            return self._done(mode, r, lat, t0, log)

        # 5. phase 1 answer: the entry's first sentence (jargon-free), an occasional short reaction
        age = self.memory.child_age()
        bridges = self.memory.available_bridges()
        first = wording.plainify(entry["first_sentence"])
        self._answered += 1
        reaction = ""
        if self._answered % 3 == 1:  # at most one question in three
            reaction = wording.REACTIONS[1] if image else wording.REACTIONS[0]
        budget = wording.MAX_TOTAL_CHARS - wording.chars_of(first) - wording.chars_of(reaction)
        if budget < 20:
            reaction, budget = "", wording.MAX_TOTAL_CHARS - wording.chars_of(first)
        use_bridge = any(k in bridges for k in entry.get("bridges", {})) and not self._last_bridge
        self._last_bridge = use_bridge
        obj = obj or entry["labels"][0]
        r.update(status="answered", object=obj, topic=entry["topic"], kb_id=entry["id"], first_sentence=first,
                 reaction=reaction, emoji=emoji_for(obj, entry["topic"]), pending=True,
                 pending_id=uuid.uuid4().hex[:12])
        lat["first_sentence"] = lat["total"] = _ms(t0)
        r["first_sentence_ms"] = lat["first_sentence"]
        self._log(mode, r, dict(lat), log)
        if log:
            self.memory.note_asked(entry["topic"], obj)

        # 6. compose in the background
        slot = {"done": threading.Event(), "result": None, "ts": time.time()}
        with self._plock:
            for k in [k for k, v in self._pending.items() if time.time() - v["ts"] > PENDING_TTL_S]:
                del self._pending[k]
            self._pending[r["pending_id"]] = slot
        snapshot = dict(r)
        self._pool.submit(self._compose_phase, slot, snapshot, entry, age, bridges, use_bridge, budget, lat, t0, log)
        return r

    def _compose_phase(self, slot, r, entry, age, bridges, use_bridge, budget, lat, t0, log):
        t = time.perf_counter()
        try:
            c = self.composer.compose(entry, age, bridges, use_bridge, budget)
        except Exception:  # compose never raises, but a result must always be delivered
            from .compose import template
            c = template(entry, age, bridges, use_bridge, budget)
        lat["compose"] = _ms(t)
        lat["total"] = _ms(t0)
        r.update(explanation=c["explanation"], ask_back=c["ask_back"], bridge_used=c["bridge_used"],
                 compose_source=c["source"], pending=False, latency_ms=dict(lat))
        if log and r.get("event_id"):
            try:
                self.db.update_event(r["event_id"], explanation=c["explanation"], ask_back=c["ask_back"],
                                     bridge_used=c["bridge_used"], latency_ms=lat)
            except Exception:
                pass
        slot["result"] = r
        slot["done"].set()
