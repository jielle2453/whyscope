"""Pipeline (spec section 8): listen -> safety -> vision -> recall -> compose -> log.

Two phases (product pass 1, B): `ask_first` returns as soon as recall/safety is done (the first sentence is spoken
at once), the compose step runs in a background thread and is collected with `poll` / `wait`.
`ask` keeps the old blocking behaviour (both phases) for scripts and tests.
Audio and image bytes are used in memory only and never persisted, except for opt-in snapshots (setting `snapshots`,
default off): the child's photo is then saved locally as data/snapshots/<event_id>.jpg and never leaves the device.
"""
import io
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from . import db as dbm
from . import intent as intents
from . import quiz, wording
from .assistant import ParentAssistant
from .chat import GUESS_FAIL_EN, GUESS_FAIL_ZH, Chat
from .compose import Composer, en_view, repeats_en
from .config import load_config, resolve
from .emoji import emoji_for
from .family import Family
from .listen import Listener
from .memory import Memory
from .principles import Principles
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


def _asked_ts(asked_at):
    """The local ISO time (seconds) a wand's curiosity-jar question was asked, or None: unparsable, in the future
    (more than a minute) or older than 7 days all mean "now"."""
    if not asked_at:
        return None
    try:
        d = datetime.fromisoformat(str(asked_at).strip().replace("Z", "+00:00"))
        if d.tzinfo is not None:
            d = d.astimezone().replace(tzinfo=None)
    except ValueError:
        return None
    n = datetime.now()
    if d > n + timedelta(minutes=1) or d < n - timedelta(days=7):
        return None
    return min(d, n).isoformat(timespec="seconds")


class Pipeline:
    def __init__(self, cfg: dict = None, preload_models: bool = True):
        self.cfg = cfg or load_config()
        self.db = dbm.DB(resolve(self.cfg, "db"))
        for hh in self.db.household_ids():   # retention is a household setting
            self.db.purge(int(self.db.setting_get("retention_days", self.cfg.get("retention_days", 30), hh)), hh)
        self.memory = Memory(self.db)
        self.snap_dir = Path(self.db.path).parent / "snapshots"
        self.sweep_snapshots()
        self.safety = Safety(self.cfg)
        self.recall = Recall(self.cfg)
        self.principles = Principles(self.cfg, self.recall)   # pre-written principle answers (draft, AI-written)
        self.family = Family(self.cfg, self.db, self.recall)  # answers a parent approved
        self.listener = Listener(self.cfg)
        self.vision = Vision(self.cfg)
        self.composer = Composer(self.cfg)
        self.lock = threading.Lock()  # one UGen300: serialise recall / safety / ASR across all children
        self._pool = ThreadPoolExecutor(max_workers=3)
        self._pending = {}            # pending_id -> {"done": Event, "result": dict|None, "ts": float}
        self._plock = threading.Lock()
        self._answered = {}           # child id -> answered questions so far (for the reaction cadence)
        self._last_bridge = {}        # child id -> did the previous answer use a bridge? (<= 1 in 2)
        wording.common_words_en()     # the English common-words set is built from the entries at startup
        self.last_compose = None      # compose_source of the last finished answer ("llm" | "template(...)")
        self.assistant = ParentAssistant(self)   # drafts answers for the parent while no child is asking
        self.chat = Chat(self)                   # chat replies and AI guesses on the UGen LLM, with guardrails and memory
        if preload_models:
            threading.Thread(target=self.listener.warm, daemon=True).start()
            threading.Thread(target=self.vision.probe, daemon=True).start()

    def default_lang(self, hh=None) -> str:
        """The household's `language` setting (default "en")."""
        v = self.db.setting_get("language", "en", hh)
        return v if v in LANGS else "en"

    # ---- opt-in snapshots (local files; never in reports or exports) ----
    def snapshots_on(self, hh=None) -> bool:
        return bool(self.db.setting_get("snapshots", False, hh))

    def snap_path(self, event_id) -> Path:
        return self.snap_dir / f"{int(event_id)}.jpg"

    def save_snapshot(self, event_id, data: bytes) -> bool:
        """Re-encode with the nostalgic old-phone look (hub.film: 640 px, soft, grainy, warm, JPEG q45),
        EXIF dropped, and flag the event."""
        try:
            from PIL import Image, ImageOps
            from . import film
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            self.snap_dir.mkdir(parents=True, exist_ok=True)
            film.save(im, str(self.snap_path(event_id)))
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

    def delete_all_snapshots(self, hh=None) -> int:
        """Delete the photos of one household (None = every household)."""
        n = 0
        if hh is None:
            files = list(self.snap_dir.glob("*.jpg")) if self.snap_dir.exists() else []
        else:
            files = [self.snap_path(e["id"]) for e in self.db.snapshot_events(household_id=hh)]
        for p in files:
            if p.exists():
                p.unlink(missing_ok=True)
                n += 1
        self.db.clear_snapshot_flags(hh)
        return n

    def snapshot_count(self, hh=None) -> int:
        if not self.snap_dir.exists():
            return 0
        if hh is None:
            return sum(1 for _ in self.snap_dir.glob("*.jpg"))
        return sum(1 for e in self.db.snapshot_events(household_id=hh) if self.snap_path(e["id"]).exists())

    def sweep_snapshots(self) -> int:
        """Delete photos older than the household's `snapshots_retention_days` (default 30) and photos whose event is gone."""
        if not self.snap_dir.exists():
            return 0
        n = 0
        for p in list(self.snap_dir.glob("*.jpg")):
            eid = int(p.stem) if p.stem.isdigit() else None
            ev = self.db.get_event(eid) if eid is not None else None
            days = int(self.db.setting_get("snapshots_retention_days", 30, self.db.child_household(ev["child_id"]) if ev else None))
            if ev is None or p.stat().st_mtime < time.time() - days * 86400:
                p.unlink(missing_ok=True)
                n += 1
                if eid is not None:
                    self.db.set_snapshot(eid, False)
        return n

    def norm_lang(self, lang=None, hh=None) -> str:
        return lang if lang in LANGS else self.default_lang(hh)

    def ai_guess_on(self, hh=None) -> bool:
        """Household setting `ai_guess` (default on): uncovered questions get a hedged AI guess (draft, checked by the parent
        afterwards); off = the old "I'm not sure, let's ask a grown-up" path."""
        return bool(self.db.setting_get("ai_guess", True, hh))

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
        v = self.vision.status()
        return {"mode": self.cfg.get("mode"), "device": self.recall.device, "entries": len(self.recall.entries),
                "asr_ready": self.listener.model is not None, "asr_error": self.listener.error,
                "compose_backend": self.composer.backend if self.composer.ready else None,
                "compose_error": self.composer.error,
                "vision_available": v["yolo"]["can_run"] or v["clip_image"]["can_run"],   # something can really run
                "vision": v, "ugen": self.ugen_status(),
                "principles": {"enabled": self.principles.enabled, "count": len(self.principles.items),
                               "draft": self.principles.draft, "error": self.principles.error},
                "family_answers": self.family.count(),
                "assistant": self.assistant.status(), "chat": self.chat.status(),
                "safety_categories": sorted(self.safety.triggers), "language": self.default_lang()}

    def ugen_status(self) -> dict:
        """The UGen300 as the hub sees it: is the worker reachable, which models are loaded, and which backend each
        stage uses (what is configured, and what actually answered last)."""
        h = self.cfg.get("hailo") or {}
        out = {"worker": h.get("worker") or None, "worker_reachable": None, "models": {}, "worker_error": None}
        if h.get("worker"):
            try:
                out["models"] = self.vision._hailo().client.info(2).get("models") or {}
                out["worker_reachable"] = True
            except Exception as e:
                out["worker_reachable"], out["worker_error"] = False, f"{type(e).__name__}: {str(e)[:120]}"
        li = self.listener
        out["asr"] = {lang: {"configured": li.backend_for(lang), "uses_ugen": li._wants_hailo(lang), "last": li.last.get(lang)}
                      for lang in LANGS}
        out["asr_hailo_error"] = li.hailo_error
        out["vision"] = {"backend": self.vision.backend, "last": self.vision.last or None}
        out["compose"] = {"backend": self.composer.backend if self.composer.ready else None, "last_source": self.last_compose}
        return out

    # ------------------------------------------------------------------ public API
    def ask(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text", log: bool = True,
            lang: str = None, child_id: int = None, asked_at: str = None) -> dict:
        """Blocking: first phase, then wait for the compose phase. Returns the complete result."""
        r = self.ask_first(text, audio, image, mode, log, lang=lang, child_id=child_id, asked_at=asked_at)
        pid = r.get("pending_id")
        return self.wait(pid, 30) if pid else r

    def ask_first(self, text: str = "", audio: bytes = None, image: bytes = None, mode: str = "text",
                  log: bool = True, t0: float = None, lang: str = None, child_id: int = None, asked_at: str = None) -> dict:
        """Phase 1. Answered questions come back with pending=True, pending_id and an empty explanation.
        `lang` ("en"|"zh") defaults to the household's `language` setting (default "en"). `child_id` is who asks (None =
        the first child of the first household: scripts with no account). `asked_at` is the original time of a question
        a wand kept in its curiosity jar while it was offline (ISO 8601; the event is logged with that time)."""
        t0 = t0 if t0 is not None else time.perf_counter()
        child_id = child_id or self.db.default_child_id()
        hh = self.db.child_household(child_id)
        lang = self.norm_lang(lang, hh)
        ts = _asked_ts(asked_at)
        self.assistant.child_begin()   # a child request has priority on the UGen: the parent assistant waits
        r = {}
        try:
            with self.lock:
                r = self._first(text or "", audio, image, mode, log, t0, lang, child_id, ts)
        finally:
            if not r.get("pending"):   # a pending answer keeps the child "busy" until its compose phase is done
                self.assistant.child_end()
        if image and log and r.get("event_id") and self.snapshots_on(hh):  # opt-in; otherwise the bytes are discarded
            threading.Thread(target=self.save_snapshot, args=(r["event_id"], image), daemon=True).start()
        return r

    def poll(self, pid: str, child_id: int = None):
        """The finished result for a pending_id, {"pending": True} while composing, None if unknown (or not this child's)."""
        with self._plock:
            p = self._pending.get(pid)
        if p is None or (child_id is not None and p.get("child_id") != child_id):
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

    def reply(self, event_id: int, choice=None, text: str = "", audio: bytes = None, lang: str = None, child_id: int = None) -> dict:
        """The child's answer to the question back (tap: `choice`, -1 = "I don't know"; or typed `text`; or `audio`).
        Deterministic (hub/quiz.py), logged on the event for the parent page."""
        ev = self.db.get_event(int(event_id)) if event_id is not None else None
        if not ev or ev["status"] != "answered" or not ev.get("kb_id") or (child_id is not None and ev["child_id"] != child_id):
            raise KeyError("no answered event")
        self.assistant.child_begin()
        try:
            return self._reply(ev, choice, text, audio, lang)
        finally:
            self.assistant.child_end()

    def _reply(self, ev, choice, text, audio, lang):
        entry = self.entry_map().get(ev["kb_id"])
        lang = lang if lang in LANGS else (ev.get("lang") or self.default_lang(self.db.child_household(ev["child_id"])))
        if entry is None or not quiz.key(entry["id"], lang):
            raise KeyError("no answer key")
        heard = text or ""
        if audio and choice is None:
            with self.lock:
                try:
                    heard = self.listener.transcribe(audio, lang)
                except Exception:
                    heard = ""
        res = quiz.judge(entry, lang, choice=choice, text=heard)
        k = quiz.key(entry["id"], lang)
        said = heard or (k["options"][res["choice"]] if res["choice"] not in (None, -1) else quiz.IDK[lang])
        self.db.set_reply(ev["id"], said, res["result"])
        return {**res, "heard": heard, "event_id": ev["id"], "lang": lang}

    # ------------------------------------------------------------------ internals
    def _log(self, mode, r, lat, log):
        r["latency_ms"] = lat
        r["event_id"] = None
        if log:
            r["event_id"] = self.db.insert_event(child_id=r.get("child_id"), ts=r.get("asked_ts"), mode=mode, **{k: r.get(k) for k in (
                "question", "object", "topic", "kb_id", "status", "first_sentence", "explanation", "ask_back",
                "bridge_used", "source", "draft", "partial", "intent", "llm")}, sensitive_category=r.get("sensitive_category"),
                latency_ms=lat, lang=r.get("lang"))

    def _done(self, mode, r, lat, t0, log=True):
        """Complete (non-pending) result: abstained / sensitive / not heard."""
        lat["total"] = lat["first_sentence"] = _ms(t0)
        r.update(first_sentence_ms=lat["total"], pending=False, pending_id=None, reaction="", emoji="")
        self._log(mode, r, lat, log)
        return r

    def _first(self, text, audio, image, mode, log, t0, lang="zh", child_id=None, asked_ts=None):
        en = lang == "en"
        hh = self.db.child_household(child_id)
        lat = {"listen": 0, "vision": 0, "recall": 0, "compose": 0, "safety": 0}
        r = {"lang": lang, "child_id": child_id, "asked_ts": asked_ts, "question": text, "object": None, "topic": None, "kb_id": None, "confidence": 0.0,
             "status": "abstained", "asr_backend": None, "first_sentence": "", "explanation": "", "ask_back": "", "bridge_used": None, "reason": ""}

        # 1. listen
        if audio:
            t = time.perf_counter()
            try:
                text, r["asr_backend"] = self.listener.transcribe_ex(audio, lang)
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

        # 2. safety (always first: a sensitive text never reaches recall, chat or an AI guess)
        t = time.perf_counter()
        hit = self.safety.check(text, lang)
        history = self.chat.memory.recent(child_id)
        it = intents.classify(text, lang, bool(image), bool(history))
        if not hit and it.kind == "followup" and history and history[-1]["source"] == "sensitive":
            hit = self.safety.check(history[-1]["q"], lang)   # "why?" after a sensitive question: still the parent's topic
        lat["safety"] = _ms(t)
        r["intent"] = it.kind + (":" + it.sub if it.sub else "")
        if hit:
            if it.kind == "chat" and hit["category"] in ("death", "illness", "divorce_family"):
                # "My grandpa died." is news, not a question: comfort first, then the same hand-over to a grown-up
                hit = {**hit, "deflection": ("I'm sorry, that sounds really hard. A grown-up can give you a hug and talk with you, okay?"
                                             if en else "聽起來好難過。去找爸爸媽媽抱一抱，跟他們說說好嗎？")}
            r.update(status="sensitive", first_sentence=hit["deflection"], sensitive_category=hit["category"],
                     urgent=hit["urgent"], source="sensitive", kind="sensitive")
            res = self._done(mode, r, lat, t0, log)
            self.chat.memory.add(child_id, text, res["first_sentence"], "sensitive", lang=lang)
            return res

        # 2b. follow-up ("why?", "tell me more") to the last turn
        if it.kind == "followup":
            res = self._followup(text, lang, history, r, lat, mode, t0, log, child_id)
            if res is not None:
                return res
            if history[-1]["source"] != "chat":   # no new facts from the model after curated text or a guess
                return self._canned_now("followup", r, lang, child_id, lat, t0, log, mode)
            return self._llm_pending("chat", r, text, lang, "followup", child_id, history, "", lat, t0, log, mode)
        # 2c. chit-chat: no knowledge-base lookup, a chat reply (pure "what is it?" without a camera: a canned line)
        if it.kind == "chat":
            return self._llm_pending("chat", r, text, lang, it.sub, child_id, history, "", lat, t0, log, mode)

        # 3. vision (optional)
        obj = None
        if image:
            t = time.perf_counter()
            v = self.vision.label(image, self.recall.vision_labels(), self.recall.entries, lang)
            lat["vision"] = _ms(t)
            r["vision_backend"] = self.vision.last.get("backend")
            r["vision"] = {k: self.vision.last.get(k) for k in ("how", "label", "score", "crop") if self.vision.last.get(k) is not None}
            if v:
                obj, r["confidence"] = v
        # 3b. YOLO + CLIP not sure and the child asks about "this": the VLM names the thing (Qwen3-VL-2B on the UGen300,
        # about 2-3 s). A phrase that names a KB label is used like a CLIP label; any other phrase is only a note.
        desc = None
        if image and not obj and (it.kind == "deictic" or it.deictic) and self.vision.vlm_on():
            t = time.perf_counter()
            desc = self.vision.describe(image, text, lang)
            lat["vlm"] = _ms(t)
            r["vlm"] = {k: v for k, v in self.vision.last_vlm.items() if k in ("raw", "phrase", "error")}
            m = self.vision.match_phrase(desc, self.recall.entries, lang) if desc else None
            if m:
                obj, r["confidence"] = m[0], 0.0
                r["vision"] = {**(r.get("vision") or {}), "how": "vlm", "label": m[0]}
                r["vlm"]["kb"] = m[1]
                desc = None
            if not en:
                desc = None   # the phrase is English: in Chinese it only helps through a KB label
        if it.kind == "deictic" and not obj:
            # nothing confident on camera: say so and ask for its name; with a VLM phrase, name what it looks like
            note = (f"it looks like {desc}" if en else f"看起來像{desc}") if desc else (
                ("I can't tell what it is." if en else "看不出來是什麼。") if image else "")
            if it.pure_deictic and desc and en:   # instant, no LLM: the phrase only names the thing
                return self._looks_like_now(desc, r, lang, child_id, lat, t0, log, mode)
            if it.pure_deictic and not (desc and en):
                r["camera"] = bool(image)
                return self._canned_now("camera" if image else "camera_none", r, lang, child_id, lat, t0, log, mode)
            return self._llm_pending("chat", r, text, lang, it.sub or "camera", child_id, history, note, lat, t0, log, mode)

        # 4. recall (the camera's object counts only when the child refers to "this / it")
        t = time.perf_counter()
        qtext = it.question if lang == "en" and it.question and it.question != text else text
        use_obj = obj if (it.deictic or it.kind == "deictic") else None
        entry, score = self.recall.search(qtext, lang, use_obj)
        if qtext != text and (entry is None or score < float(self.cfg["recall"]["threshold"])):
            entry, score = self.recall.search(text, lang, use_obj)
        lat["recall"] = _ms(t)
        r["confidence"] = round(score, 3)
        if entry is None or score < float(self.cfg["recall"]["threshold"]):
            # 2. an answer the parent approved, 3. the principle library
            extra = self._family_or_principle(text, lang, use_obj, r, lat, mode, t0, log, hh, child_id)
            if extra is not None:
                self.chat.memory.add(child_id, text, extra["first_sentence"] + " " + extra.get("explanation", ""),
                                     extra.get("source", ""), lang=lang)
                return extra
            if it.kind == "deictic":   # the camera saw a principle phrase or an object with no entry: talk about it
                note = (f"it looks like {obj}" if en else f"看起來像{obj}") if obj else ""
                return self._llm_pending("chat", r, text, lang, "camera", child_id, history, note, lat, t0, log, mode)
            if it.kind == "rule":      # a home rule with no entry: point to the grown-ups' reasons, never contradict them
                return self._llm_pending("chat", r, text, lang, "rule", child_id, history, "", lat, t0, log, mode)
            # 4. an AI guess (hedged, draft, on the parent's list), or 5. abstain and ask the parent
            if self.ai_guess_on(hh) and self.chat.llm_ready() and self.assistant_worth(text, lang):
                return self._llm_pending("guess", r, qtext, lang, "", child_id, history, "", lat, t0, log, mode)
            return self._abstain(r, text, lang, lat, t0, log, mode, child_id)

        # 5. phase 1 answer: the entry's first sentence (jargon-free), an occasional short reaction
        age = self.memory.child_age(child_id)
        bridges = self.memory.available_bridges(child_id)
        ev = en_view(entry) if en else entry
        first = wording.plainify_en(ev["first_sentence"]) if en else wording.plainify(entry["first_sentence"])
        self._answered[child_id] = self._answered.get(child_id, 0) + 1
        reaction = ""
        if self._answered[child_id] % 3 == 1:  # at most one question in three
            reaction = (wording.REACTIONS_EN if en else wording.REACTIONS)[1 if image else 0]
        if use_obj and it.kind == "deictic":   # "What is this?" + a confident camera label: name it first
            fs = (en_view(entry)["first_sentence"] if en else entry["first_sentence"]).lower()
            named = str(use_obj).lower() in fs
            reaction = ("Ooh, I see it!" if named else f"That looks like a {use_obj}!") if en else ("我看到了！" if named else f"這看起來像{use_obj}！")
        if en:
            budget = wording.MAX_TOTAL_WORDS - wording.spoken_words(first) - wording.spoken_words(reaction)
            if budget < 12:
                reaction, budget = "", wording.MAX_TOTAL_WORDS - wording.spoken_words(first)
        else:
            budget = wording.MAX_TOTAL_CHARS - wording.chars_of(first) - wording.chars_of(reaction)
            if budget < 20:
                reaction, budget = "", wording.MAX_TOTAL_CHARS - wording.chars_of(first)
        use_bridge = any(k in bridges for k in ev.get("bridges", {})) and not self._last_bridge.get(child_id)
        self._last_bridge[child_id] = use_bridge
        zh_label = entry["labels"][0]
        obj = obj or ev["labels"][0]
        r.update(status="answered", object=obj, topic=entry["topic"], kb_id=entry["id"], source="entry:" + entry["id"], kind="kb",
                 draft=bool(entry.get("draft")), first_sentence=first,
                 reaction=reaction, emoji=emoji_for(zh_label, entry["topic"]), pending=True,
                 pending_id=uuid.uuid4().hex[:12])
        lat["first_sentence"] = lat["total"] = _ms(t0)
        r["first_sentence_ms"] = lat["first_sentence"]
        self._log(mode, r, dict(lat), log)
        if log:
            self.memory.note_asked(entry["topic"], obj, child_id)
        self.chat.memory.add(child_id, text, first, "entry:" + entry["id"], entry["id"], obj, [first], lang)

        # 6. compose in the background
        slot = {"done": threading.Event(), "result": None, "ts": time.time(), "child_id": child_id}
        with self._plock:
            for k in [k for k, v in self._pending.items() if time.time() - v["ts"] > PENDING_TTL_S]:
                del self._pending[k]
            self._pending[r["pending_id"]] = slot
        snapshot = dict(r)
        self._pool.submit(self._compose_phase, slot, snapshot, entry, age, bridges, use_bridge, budget, lat, t0, log, lang)
        return r

    # ------------------------------------------------------------------ chat turn (2026-11-15)
    def assistant_worth(self, text, lang) -> bool:
        from .assistant import worth_asking
        return worth_asking(text, lang)

    def _abstain(self, r, text, lang, lat, t0, log, mode, child_id, first=None, reason="unsure"):
        """The old path: "I'm not sure, let's ask a grown-up", and a to-answer item for the parent."""
        r["first_sentence"], r["reason"], r["source"], r["kind"] = first or (UNSURE_EN if lang == "en" else UNSURE), reason, "abstain", "abstain"
        r["status"] = "abstained"
        res = self._done(mode, r, lat, t0, log)
        if log and res.get("event_id"):   # a to-answer item for the parent (deduplicated per question)
            try:
                self.assistant.note_question(res["event_id"], text, lang)   # (the item takes the child from the event)
            except Exception:
                pass
        self.chat.memory.add(child_id, text, res["first_sentence"], "abstain", lang=lang)
        return res

    def _canned_now(self, key, r, lang, child_id, lat, t0, log, mode):
        """An instant chat line (no model): "What is this?" with nothing confident on camera, and the like."""
        line = self.chat.canned(key, lang, child_id)
        r.update(status="chat", source="chat", kind="chat", first_sentence=line, emoji="\U0001F440" if key == "camera" else "\U0001F4AC",
                 llm={"mode": "chat", "sub": key, "source": "canned", "why": "pure deictic"})
        lat["total"] = lat["first_sentence"] = _ms(t0)
        r.update(first_sentence_ms=lat["total"], pending=False, pending_id=None, reaction="")
        self._log(mode, r, lat, log)
        self.chat.memory.add(child_id, r["question"], line, "chat", lang=lang)
        return r

    LOOKS_ASK_EN = ["What is it called?", "Where did you find it?", "What do you want to know about it?",
                    "What do you like about it?"]

    def _looks_like_now(self, desc, r, lang, child_id, lat, t0, log, mode):
        """ "What is this?" + a VLM phrase with no KB label: "That looks like a green toy dinosaur!" and a question back.
        No LLM: the phrase only names the thing. It passes hub/guard.py like any model text, else the canned camera line."""
        from . import guard
        import random
        art = "" if re.match(r"^(?:an?|the|some|two|three)\b", desc) else ("an " if desc[:1] in "aeiou" else "a ")
        line = f"Ooh, that looks like {art}{desc}! {random.choice(self.LOOKS_ASK_EN)}"
        allow = frozenset(w.lower() for w in re.findall(r"[a-z']+", desc, re.I))
        out, probs = guard.check(line, lang, "chat", self.safety, allow, max_sent=2, max_words=14, max_total=24, max_rare=4)
        if not out:
            r["vlm"] = {**(r.get("vlm") or {}), "guard": probs}
            r["camera"] = True
            return self._canned_now("camera", r, lang, child_id, lat, t0, log, mode)
        r.update(status="chat", source="chat", kind="chat", first_sentence=out, emoji="\U0001F440",
                 llm={"mode": "chat", "sub": "camera", "source": "vlm", "why": "vlm phrase, no KB label"})
        lat["total"] = lat["first_sentence"] = _ms(t0)
        r.update(first_sentence_ms=lat["total"], pending=False, pending_id=None, reaction="")
        self._log(mode, r, lat, log)
        self.chat.memory.add(child_id, r["question"], out, "chat", lang=lang)
        return r

    def _followup(self, text, lang, history, r, lat, mode, t0, log, child_id):
        """"Tell me more" / "why?" right after a knowledge-base answer: the entry's next fact nobody has said yet
        (deterministic, curated text). None when there is nothing left (a chat reply follows instead)."""
        last = history[-1]
        if not (last.get("kb_id") and str(last.get("source", "")).startswith("entry:")):
            return None
        entry = self.entry_map().get(last["kb_id"])
        if not entry:
            return None
        en = lang == "en"
        ev = en_view(entry) if en else entry
        said = " ".join(last.get("said") or [])
        allow = wording.entry_allow_en(entry) if en else wording.entry_allow_zh(entry)
        for f in ev.get("facts") or []:
            f = wording.plainify_en(f.strip()) if en else wording.plainify(f.strip())
            if (repeats_en(f, said) if en else f[:6] in said):
                continue
            if (wording.check_text_en(f, 1, allow) if en else wording.check_text(f, 1, allow)):
                continue
            ask = "Do you want to know more?" if en else "你還想知道更多嗎？"
            r.update(status="answered", object=last.get("obj"), topic=entry["topic"], kb_id=entry["id"], source="entry:" + entry["id"],
                     kind="kb", draft=bool(entry.get("draft")), first_sentence=f, explanation="", ask_back=ask,
                     emoji=emoji_for(entry["labels"][0], entry["topic"]))
            res = self._answered_now(mode, r, lat, t0, log)
            self.chat.memory.update_last(child_id, said=(last.get("said") or []) + [f], ts=time.time())
            return res
        return None

    def _llm_pending(self, job, r, text, lang, sub, child_id, history, camera_note, lat, t0, log, mode):
        """Phase 1 of a chat reply / AI guess: log the event and return at once (pending); the UGen writes the text in the
        background (`_chat_job` / `_guess_job`), the kid page polls GET /api/ask/{pending_id}."""
        en = lang == "en"
        if job == "chat" and sub in ("unclear",):
            return self._canned_now("unclear", r, lang, child_id, lat, t0, log, mode)
        guess = job == "guess"
        r.update(status="answered" if guess else "chat", source="ai_guess" if guess else "chat", kind="ai_guess" if guess else "chat",
                 draft=guess, first_sentence="", explanation="", ask_back="", reaction="", thinking=guess,
                 filler=self.chat.filler(lang) if guess else "", emoji="\U0001F4AD" if guess else "\U0001F4AC",
                 pending=True, pending_id=uuid.uuid4().hex[:12])
        lat["first_sentence"] = lat["total"] = _ms(t0)   # (replaced by the time the reply is ready)
        r["first_sentence_ms"] = None
        self._log(mode, r, dict(lat), log)
        slot = {"done": threading.Event(), "result": None, "ts": time.time(), "child_id": child_id}
        with self._plock:
            for k in [k for k, v in self._pending.items() if time.time() - v["ts"] > PENDING_TTL_S]:
                del self._pending[k]
            self._pending[r["pending_id"]] = slot
        fn = self._guess_job if guess else self._chat_job
        self._pool.submit(fn, slot, dict(r), text, lang, sub, child_id, history, camera_note, lat, t0, log)
        return r

    def _finish_llm(self, slot, r, lat, t0, log, upd):
        lat["first_sentence"] = lat["total"] = _ms(t0)
        r.update(pending=False, latency_ms=dict(lat), first_sentence_ms=lat["first_sentence"])
        if log and r.get("event_id"):
            try:
                self.db.update_event(r["event_id"], latency_ms=lat, **upd)
            except Exception:
                pass
        slot["result"] = r
        slot["done"].set()

    def _chat_job(self, slot, r, text, lang, sub, child_id, history, camera_note, lat, t0, log):
        try:
            t = time.perf_counter()
            try:
                c = self.chat.chat_reply(text, lang, sub, child_id, history, camera_note)
            except Exception as e:   # never leave the child without a reply
                c = {"text": self.chat.canned("statement", lang, child_id), "source": "canned", "info": {"why": f"error {type(e).__name__}"}}
            lat["llm"] = _ms(t)
            info = {**c["info"], "source": c["source"]}
            r.update(first_sentence=c["text"], llm=info, chat_source=c["source"])
            self.chat.memory.add(child_id, text, c["text"], "chat", lang=lang)
            self._finish_llm(slot, r, lat, t0, log, {"first_sentence": c["text"], "llm": info})
        finally:
            self.assistant.child_end()

    def _guess_job(self, slot, r, text, lang, sub, child_id, history, camera_note, lat, t0, log):
        en = lang == "en"
        try:
            t = time.perf_counter()
            try:
                g = self.chat.ai_guess(text, lang, child_id, history)
            except Exception as e:
                g = {"text": None, "ask_back": "", "context": [], "info": {"why": f"error {type(e).__name__}"}}
            lat["llm"] = _ms(t)
            info = {**g["info"], "context": [{k: c[k] for k in ("kind", "id", "score", "used")} for c in g.get("context") or []]}
            if not g["text"]:   # no usable guess: the old path (ask a grown-up; the parent assistant drafts later)
                first = GUESS_FAIL_EN if en else GUESS_FAIL_ZH
                r.update(status="abstained", source="abstain", kind="abstain", draft=False, thinking=False, first_sentence=first,
                         reason="unsure", llm={**info, "fallback": "abstain"})
                self._finish_llm(slot, r, lat, t0, log, {"status": "abstained", "source": "abstain", "draft": 0,
                                                         "first_sentence": first, "llm": r["llm"]})
                if log and r.get("event_id"):
                    try:
                        self.assistant.note_question(r["event_id"], text, lang)
                    except Exception:
                        pass
                self.chat.memory.add(child_id, text, first, "abstain", lang=lang)
                return
            r.update(first_sentence=g["text"], ask_back=g["ask_back"], llm=info)
            self._finish_llm(slot, r, lat, t0, log, {"first_sentence": g["text"], "ask_back": g["ask_back"], "llm": info})
            self.chat.memory.add(child_id, text, g["text"] + " " + g["ask_back"], "ai_guess", lang=lang)
            if log and r.get("event_id"):   # straight onto the parent's To-answer list, the guess as the ready draft
                try:
                    import json as _json
                    from .recall import normalize, normalize_en
                    w = {"ok": True, "problems": [], "not_in_facts": [], "ai_guess": True}   # it passed hub/guard.py
                    self.db.todo_add_guess(r["event_id"], text, normalize_en(text) if en else normalize(text), lang, child_id, g["text"],
                                           _json.dumps(g.get("context") or [], ensure_ascii=False), _json.dumps(w, ensure_ascii=False))
                except Exception:
                    pass
        finally:
            self.assistant.child_end()

    def _family_or_principle(self, text, lang, obj, r, lat, mode, t0, log, hh=1, child_id=None):
        """Order step 2 and 3: an approved family answer (near-duplicate question), else the principle library.
        Returns the finished result (status "answered", nothing left to compose), or None."""
        en = lang == "en"
        t = time.perf_counter()
        row, fscore = self.family.match(text, lang, hh or 1)
        if row:
            sents = wording.sentences_en(row["answer"]) if en else wording.sentences(row["answer"])
            sep = " " if en else ""
            r.update(status="answered", object=None, source=f"family:{row['id']}", family_id=row["id"],
                     first_sentence=(sents[0] if sents else row["answer"]), explanation=sep.join(sents[1:]), emoji="\U0001F48C",
                     confidence=round(fscore, 3), draft=False, partial=False)
            lat["family"] = _ms(t)
            return self._answered_now(mode, r, lat, t0, log)
        lat["family"] = _ms(t)
        t = time.perf_counter()
        m = self.principles.search(text, lang, obj)
        lat["principle"] = _ms(t)
        if m is None:
            if self.principles.last:
                r["principle_best"] = self.principles.last   # what was closest and why it was not used
            return None
        r.update(status="answered", object=m["object"] or obj, source="principle:" + m["id"], first_sentence=m["answer"],
                 explanation="", ask_back="", confidence=round(m["score"], 3), draft=m["draft"], partial=m["partial"],
                 principle={"id": m["id"], "name": m["principle"].get("name_en" if en else "name_zh"), "score": round(m["score"], 3),
                            "margin": round(m["margin"], 3), "slot": m["slot"]},
                 emoji=self.emoji_of(m["object"]) if m["object"] else "\U0001F4A1")
        res = self._answered_now(mode, r, lat, t0, log)
        if log and res.get("object"):
            self.memory.note_asked(None, res["object"], child_id)
        return res

    def _answered_now(self, mode, r, lat, t0, log):
        """An answer that needs no compose phase (family / principle): complete at once, logged as answered."""
        lat["total"] = lat["first_sentence"] = _ms(t0)
        r.update(first_sentence_ms=lat["total"], pending=False, pending_id=None, reaction="")
        self._log(mode, r, lat, log)
        return r

    def _compose_phase(self, slot, r, entry, age, bridges, use_bridge, budget, lat, t0, log, lang="zh"):
        try:
            self._compose_phase_inner(slot, r, entry, age, bridges, use_bridge, budget, lat, t0, log, lang)
        finally:
            self.assistant.child_end()

    def _compose_phase_inner(self, slot, r, entry, age, bridges, use_bridge, budget, lat, t0, log, lang="zh"):
        t = time.perf_counter()
        try:
            c = self.composer.compose(entry, age, bridges, use_bridge, budget, lang)
        except Exception:  # compose never raises, but a result must always be delivered
            from .compose import template, template_en
            c = (template_en if lang == "en" else template)(entry, age, bridges, use_bridge, budget)
        lat["compose"] = _ms(t)
        lat["total"] = _ms(t0)
        r.update(explanation=c["explanation"], ask_back=c["ask_back"], bridge_used=c["bridge_used"],
                 compose_source=c["source"], quiz=c.get("quiz"), pending=False, latency_ms=dict(lat))
        hist = self.chat.memory.recent(r.get("child_id"))
        if hist and hist[-1].get("kb_id") == entry["id"]:
            self.chat.memory.update_last(r.get("child_id"), a=(r["first_sentence"] + " " + c["explanation"] + " " + c["ask_back"]).strip(),
                                         said=hist[-1]["said"] + [c["explanation"]])
        if log and r.get("event_id"):
            try:
                self.db.update_event(r["event_id"], explanation=c["explanation"], ask_back=c["ask_back"],
                                     bridge_used=c["bridge_used"], latency_ms=lat)
            except Exception:
                pass
        self.last_compose = c["source"]
        slot["result"] = r
        slot["done"].set()
