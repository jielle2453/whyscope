"""Pipeline (spec section 8): listen -> safety -> vision -> recall -> compose -> log.

Audio and image bytes are used in memory only and never persisted.
"""
import threading
import time

from . import db as dbm
from .compose import Composer
from .config import load_config, resolve
from .listen import Listener
from .memory import Memory
from .recall import Recall
from .safety import Safety
from .vision import Vision

UNSURE = "我不確定，我們一起去問爸爸媽媽好嗎？"
NOT_HEARD = "我沒聽清楚，再說一次好嗎？"
NO_QUESTION = "你想問我什麼呢？"


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
        self.lock = threading.Lock()  # one child, one device: serialise model use
        if preload_models:
            threading.Thread(target=self.listener.warm, daemon=True).start()

    def status(self) -> dict:
        """Which optional components are live (for /healthz)."""
        return {"mode": self.cfg.get("mode"), "device": self.recall.device, "entries": len(self.recall.entries),
                "asr_ready": self.listener.model is not None, "asr_error": self.listener.error,
                "compose_backend": self.composer.backend if self.composer.ready else None,
                "compose_error": self.composer.error, "vision_available": self.vision.available,
                "safety_categories": sorted(self.safety.triggers)}

    def _finish(self, mode, r, lat, t0, log=True):
        lat["total"] = _ms(t0)
        r["latency_ms"] = lat
        if log:
            self.db.insert_event(mode=mode, **{k: r.get(k) for k in (
                "question", "object", "topic", "kb_id", "status", "first_sentence", "explanation", "ask_back",
                "bridge_used")}, sensitive_category=r.get("sensitive_category"), latency_ms=lat)
        return r

    def ask(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text", log: bool = True) -> dict:
        with self.lock:
            return self._ask(text or "", audio, image, mode, log)

    def _ask(self, text, audio, image, mode, log):
        t0 = time.perf_counter()
        lat = {"listen": 0, "vision": 0, "recall": 0, "compose": 0}
        r = {"question": text, "object": None, "topic": None, "kb_id": None, "confidence": 0.0,
             "status": "abstained", "first_sentence": "", "explanation": "", "ask_back": "", "bridge_used": None}

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
                r["first_sentence"] = NOT_HEARD
                return self._finish(mode, r, lat, t0, log)
        if not text.strip():
            if not image:
                r["first_sentence"] = NO_QUESTION
                return self._finish(mode, r, lat, t0, False)
            text = "這是什麼"
            r["question"] = text

        # 2. safety
        t = time.perf_counter()
        hit = self.safety.check(text)
        lat["safety"] = _ms(t)
        if hit:
            r.update(status="sensitive", first_sentence=hit["deflection_zh"], sensitive_category=hit["category"],
                     urgent=hit["urgent"])
            return self._finish(mode, r, lat, t0, log)

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
            r["first_sentence"] = UNSURE
            lat["first_sentence"] = lat["listen"] + lat["safety"] + lat["vision"] + lat["recall"]
            return self._finish(mode, r, lat, t0, log)
        lat["first_sentence"] = lat["listen"] + lat["safety"] + lat["vision"] + lat["recall"]

        # 5. compose (first_sentence is always the entry's, verbatim)
        t = time.perf_counter()
        c = self.composer.compose(entry, self.memory.child_age(), self.memory.available_bridges())
        lat["compose"] = _ms(t)
        r.update(status="answered", object=obj or entry["labels"][0], topic=entry["topic"], kb_id=entry["id"],
                 first_sentence=entry["first_sentence"], explanation=c["explanation"], ask_back=c["ask_back"],
                 bridge_used=c["bridge_used"], compose_source=c["source"])
        if log:
            self.memory.note_asked(entry["topic"], r["object"])
        return self._finish(mode, r, lat, t0, log)
