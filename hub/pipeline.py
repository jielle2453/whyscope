"""Pipeline (spec section 8): listen -> safety -> vision -> recall -> compose -> log.

Two phases (product pass 1, B): `ask_first` returns as soon as recall/safety is done (the first sentence is spoken
at once), the compose step runs in a background thread and is collected with `poll` / `wait`.
`ask` keeps the old blocking behaviour (both phases) for scripts and tests.
Audio and image bytes are used in memory only and never persisted, except for opt-in snapshots (setting `snapshots`,
default off): the child's photo is then saved locally as data/snapshots/<event_id>.jpg and never leaves the device.
"""
import io
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import db as dbm
from . import wording
from .compose import Composer, en_view
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
UNSURE_EN = "I'm not sure. Let's ask a grown-up together."
NOT_HEARD_EN = "I did not hear that. Can you say it again?"
NO_QUESTION_EN = "What do you want to ask me?"
LANGS = ("en", "zh")
PENDING_TTL_S = 300
SNAP_MAX_PX, SNAP_QUALITY = 1024, 82


def _ms(t0) -> int:
    return int((time.perf_counter() - t0) * 1000)


class Pipeline:
    def __init__(self, cfg: dict = None, preload_models: bool = True):
        self.cfg = cfg or load_config()
        self.db = dbm.DB(resolve(self.cfg, "db"))
        self.db.purge(int(self.db.setting_get("retention_days", self.cfg.get("retention_days", 30))))
        self.memory = Memory(self.db)
        self.snap_dir = Path(self.db.path).parent / "snapshots"
        self.sweep_snapshots()
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
        wording.common_words_en()     # the English common-words set is built from the entries at startup
        if preload_models:
            threading.Thread(target=self.listener.warm, daemon=True).start()

    def default_lang(self) -> str:
        """The `language` setting (default "en")."""
        v = self.db.setting_get("language", "en")
        return v if v in LANGS else "en"

    # ---- opt-in snapshots (local files; never in reports or exports) ----
    def snapshots_on(self) -> bool:
        return bool(self.db.setting_get("snapshots", False))

    def snap_path(self, event_id) -> Path:
        return self.snap_dir / f"{int(event_id)}.jpg"

    def save_snapshot(self, event_id, data: bytes) -> bool:
        """Re-encode to JPEG (max 1024 px long side, quality 82, EXIF dropped) and flag the event."""
        try:
            from PIL import Image, ImageOps
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            im.thumbnail((SNAP_MAX_PX, SNAP_MAX_PX))
            self.snap_dir.mkdir(parents=True, exist_ok=True)
            im.save(self.snap_path(event_id), "JPEG", quality=SNAP_QUALITY, optimize=True)
            self.db.set_snapshot(event_id, True)
            return True
        except Exception:
            return False

    def delete_snapshot(self, event_id) -> bool:
        p = self.snap_path(event_id)
        had = p.exists()
        if had:
            p.unlink()
        self.db.set_snapshot(event_id, False)
        return had

    def delete_all_snapshots(self) -> int:
        n = 0
        for p in list(self.snap_dir.glob("*.jpg")):
            p.unlink(missing_ok=True)
            n += 1
        self.db.clear_snapshot_flags()
        return n

    def snapshot_count(self) -> int:
        return sum(1 for _ in self.snap_dir.glob("*.jpg")) if self.snap_dir.exists() else 0

    def sweep_snapshots(self) -> int:
        """Delete photos older than `snapshots_retention_days` (default 30) and photos whose event is gone."""
        if not self.snap_dir.exists():
            return 0
        days = int(self.db.setting_get("snapshots_retention_days", 30))
        cutoff, n = time.time() - days * 86400, 0
        for p in list(self.snap_dir.glob("*.jpg")):
            eid = int(p.stem) if p.stem.isdigit() else None
            if eid is None or p.stat().st_mtime < cutoff or not self.db.get_event(eid):
                p.unlink(missing_ok=True)
                n += 1
                if eid is not None:
                    self.db.set_snapshot(eid, False)
        return n

    def norm_lang(self, lang=None) -> str:
        return lang if lang in LANGS else self.default_lang()

    def entry_map(self) -> dict:
        return {e["id"]: e for e in self.recall.entries}

    def emoji_of(self, obj, topic=None) -> str:
        """Emoji for an object name in any language (English labels resolve through the entry's Chinese label)."""
        if not hasattr(self, "_label_emoji"):
            m = {}
            for e in self.recall.entries:
                zh = e["labels"][0]
                for lab in list(e.get("labels", [])) + list((e.get("en") or {}).get("labels", [])):
                    m[lab.lower()] = (zh, e["topic"])
            self._label_emoji = m
        hit = self._label_emoji.get((obj or "").lower())
        return emoji_for(hit[0], hit[1]) if hit else emoji_for(obj, topic)

    def status(self) -> dict:
        """Which optional components are live (for /healthz)."""
        return {"mode": self.cfg.get("mode"), "device": self.recall.device, "entries": len(self.recall.entries),
                "asr_ready": self.listener.model is not None, "asr_error": self.listener.error,
                "compose_backend": self.composer.backend if self.composer.ready else None,
                "compose_error": self.composer.error, "vision_available": self.vision.available,
                "safety_categories": sorted(self.safety.triggers), "language": self.default_lang()}

    # ------------------------------------------------------------------ public API
    def ask(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text", log: bool = True,
            lang: str = None) -> dict:
        """Blocking: first phase, then wait for the compose phase. Returns the complete result."""
        r = self.ask_first(text, audio, image, mode, log, lang=lang)
        pid = r.get("pending_id")
        return self.wait(pid, 30) if pid else r

    def ask_first(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text",
                  log: bool = True, t0: float = None, lang: str = None) -> dict:
        """Phase 1. Answered questions come back with pending=True, pending_id and an empty explanation.
        `lang` ("en"|"zh") defaults to the `language` setting (default "en")."""
        t0 = t0 if t0 is not None else time.perf_counter()
        lang = self.norm_lang(lang)
        with self.lock:
            r = self._first(text or "", audio, image, mode, log, t0, lang)
        if image and log and r.get("event_id") and self.snapshots_on():  # opt-in; otherwise the bytes are discarded
            threading.Thread(target=self.save_snapshot, args=(r["event_id"], image), daemon=True).start()
        return r

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
                "bridge_used")}, sensitive_category=r.get("sensitive_category"), latency_ms=lat, lang=r.get("lang"))

    def _done(self, mode, r, lat, t0, log=True):
        """Complete (non-pending) result: abstained / sensitive / not heard."""
        lat["total"] = lat["first_sentence"] = _ms(t0)
        r.update(first_sentence_ms=lat["total"], pending=False, pending_id=None, reaction="", emoji="")
        self._log(mode, r, lat, log)
        return r

    def _first(self, text, audio, image, mode, log, t0, lang="zh"):
        en = lang == "en"
        lat = {"listen": 0, "vision": 0, "recall": 0, "compose": 0, "safety": 0}
        r = {"lang": lang, "question": text, "object": None, "topic": None, "kb_id": None, "confidence": 0.0,
             "status": "abstained", "first_sentence": "", "explanation": "", "ask_back": "", "bridge_used": None, "reason": ""}

        # 1. listen
        if audio:
            t = time.perf_counter()
            try:
                text = self.listener.transcribe(audio, lang)
            except Exception as e:
                text = ""
                self.listener.error = f"{type(e).__name__}: {str(e)[:200]}"
            lat["listen"] = _ms(t)
            r["question"] = text
            if not text.strip():
                r["first_sentence"], r["reason"] = (NOT_HEARD_EN if en else NOT_HEARD), "not_heard"
                return self._done(mode, r, lat, t0, log)
        if not text.strip():
            if not image:
                r["first_sentence"], r["reason"] = (NO_QUESTION_EN if en else NO_QUESTION), "no_question"
                return self._done(mode, r, lat, t0, False)
            text = "what is this" if en else "這是什麼"
            r["question"] = text

        # 2. safety
        t = time.perf_counter()
        hit = self.safety.check(text, lang)
        lat["safety"] = _ms(t)
        if hit:
            r.update(status="sensitive", first_sentence=hit["deflection"], sensitive_category=hit["category"],
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
        entry, score = self.recall.search(text, lang, obj)
        lat["recall"] = _ms(t)
        r["confidence"] = round(score, 3)
        if entry is None or score < float(self.cfg["recall"]["threshold"]):
            r["first_sentence"], r["reason"] = (UNSURE_EN if en else UNSURE), "unsure"
            return self._done(mode, r, lat, t0, log)

        # 5. phase 1 answer: the entry's first sentence (jargon-free), an occasional short reaction
        age = self.memory.child_age()
        bridges = self.memory.available_bridges()
        ev = en_view(entry) if en else entry
        first = wording.plainify_en(ev["first_sentence"]) if en else wording.plainify(entry["first_sentence"])
        self._answered += 1
        reaction = ""
        if self._answered % 3 == 1:  # at most one question in three
            reaction = (wording.REACTIONS_EN if en else wording.REACTIONS)[1 if image else 0]
        if en:
            budget = wording.MAX_TOTAL_WORDS - wording.spoken_words(first) - wording.spoken_words(reaction)
            if budget < 12:
                reaction, budget = "", wording.MAX_TOTAL_WORDS - wording.spoken_words(first)
        else:
            budget = wording.MAX_TOTAL_CHARS - wording.chars_of(first) - wording.chars_of(reaction)
            if budget < 20:
                reaction, budget = "", wording.MAX_TOTAL_CHARS - wording.chars_of(first)
        use_bridge = any(k in bridges for k in ev.get("bridges", {})) and not self._last_bridge
        self._last_bridge = use_bridge
        zh_label = entry["labels"][0]
        obj = obj or ev["labels"][0]
        r.update(status="answered", object=obj, topic=entry["topic"], kb_id=entry["id"], first_sentence=first,
                 reaction=reaction, emoji=emoji_for(zh_label, entry["topic"]), pending=True,
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
        self._pool.submit(self._compose_phase, slot, snapshot, entry, age, bridges, use_bridge, budget, lat, t0, log, lang)
        return r

    def _compose_phase(self, slot, r, entry, age, bridges, use_bridge, budget, lat, t0, log, lang="zh"):
        t = time.perf_counter()
        try:
            c = self.composer.compose(entry, age, bridges, use_bridge, budget, lang)
        except Exception:  # compose never raises, but a result must always be delivered
            from .compose import template, template_en
            c = (template_en if lang == "en" else template)(entry, age, bridges, use_bridge, budget)
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
