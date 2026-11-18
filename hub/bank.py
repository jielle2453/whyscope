"""English answer bank (knowledge/answer_bank_en.jsonl): fact-checked short answers for questions the knowledge base does
not cover, retrieved by the knowledge base's own embedding model.

Each item: id, topic, q, variants (child-style phrasings), a1 (the direct answer), a2 (one level deeper), ask_back,
confidence, notes ("sensitive:<category>" for gentle items), check. Retrieval is the method measured in
eval/answer_bank/report_v2.md: q and every variant are embedded (normalize_en, as hub/recall.py), an item's score is the
max cosine over its rows, top-1 is used at or above `answer_bank.threshold` (0.80: on the 145 held-out questions the top-1
answered the exact question for 73% with an off-question share of about 2%). No label / asks / coverage guard: they
were built for the knowledge base's labels and were not part of that measurement.

English only: the bank is never searched for a Chinese question.

Start-up: embedding 25,000 rows takes about 23 s on a CPU, so the matrix is cached next to the database
(data/answer_bank_en.npz, gitignored) and reused while the bank file's sha256 and the model name are unchanged.

Own model (optional `answer_bank.model`, e.g. models/recall/whyscope-minilm-en-v1, fine-tuned on the bank's own q/variants:
eval/answer_bank/finetune_v1/report.md): the bank then embeds with that SentenceTransformer (device as hub/config.py
torch_device decides, so CPU in hailo mode) for search, the sensitive check and its cache key, and the knowledge base
(Chinese and English) keeps the shared recall model untouched. The cache file is then named after the model
(data/answer_bank_en.<model folder>.npz), so switching models back and forth does not rebuild. Unset: exactly as before.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from .config import ROOT, resolve
from .recall import normalize_en

CACHE_VERSION = "1"   # bump when the row text or the normalisation changes
FIELDS = ("id", "q", "a1")

# bank topic -> one of the hub's nine report topics (hub/emoji.py TOPIC_EN), so the parent's weekly topics stay meaningful
TOPIC = {}
for _hub, _bank in {
    "animals": "birds bugs cats dinosaurs dogs farm fish frogs hamsters insects pets rabbits reptiles snails spiders worms zoo",
    "plants": "plants forest fungi",
    "food": "food baking cooking dairy drinks eggs fruit meals sweets vegetables",
    "body": "belly blood body bones brain ears eyes growth hair health heart laughing lungs mouth muscles nails nose senses "
            "skin sleep stomach taste teeth tongue voice",
    "sky_weather": "sky weather moon sun space air",
    "earth": "earth",
    "physics": "physics forces float heat light mirrors sound sounds bubbles fire water",
    "machines": "machines vehicles tools home toys made clothes",
    "people": "people family feelings friends fairness manners money rules school society town language holidays "
              "big_questions play sports time general art music",
}.items():
    for _t in _bank.split():
        TOPIC[_t] = _hub

# finer emoji than the nine report topics (the kid page shows it next to the answer)
EMOJI = {
    "birds": "\U0001F426", "bugs": "\U0001F41E", "insects": "\U0001F41C", "cats": "\U0001F431", "dogs": "\U0001F436",
    "dinosaurs": "\U0001F995", "farm": "\U0001F404", "fish": "\U0001F41F", "frogs": "\U0001F438", "hamsters": "\U0001F439",
    "pets": "\U0001F43E", "rabbits": "\U0001F430", "reptiles": "\U0001F98E", "snails": "\U0001F40C", "spiders": "\U0001F577",
    "worms": "\U0001FAB1", "zoo": "\U0001F992", "ocean": "\U0001F30A", "plants": "\U0001F331", "forest": "\U0001F332",
    "fungi": "\U0001F344", "food": "\U0001F37D", "baking": "\U0001F35E", "cooking": "\U0001F373", "dairy": "\U0001F95B",
    "drinks": "\U0001F964", "eggs": "\U0001F95A", "fruit": "\U0001F34E", "meals": "\U0001F35D", "sweets": "\U0001F36C",
    "vegetables": "\U0001F955", "teeth": "\U0001F9B7", "eyes": "\U0001F440", "ears": "\U0001F442", "nose": "\U0001F443",
    "mouth": "\U0001F444", "tongue": "\U0001F445", "taste": "\U0001F445", "brain": "\U0001F9E0", "bones": "\U0001F9B4",
    "heart": "❤️", "blood": "\U0001FA78", "lungs": "\U0001FAC1", "muscles": "\U0001F4AA", "hair": "\U0001F487",
    "health": "\U0001FA7A", "sleep": "\U0001F634", "laughing": "\U0001F602", "skin": "✋", "nails": "\U0001F485",
    "sky": "☁️", "weather": "\U0001F326️", "moon": "\U0001F319", "sun": "☀️", "space": "\U0001F680",
    "air": "\U0001F4A8", "earth": "\U0001F30D", "water": "\U0001F4A7", "fire": "\U0001F525", "light": "\U0001F4A1",
    "sound": "\U0001F50A", "sounds": "\U0001F50A", "music": "\U0001F3B5", "bubbles": "\U0001FAE7", "mirrors": "\U0001FA9E",
    "heat": "\U0001F321️", "float": "⛵", "forces": "\U0001F9F2", "machines": "⚙️",
    "vehicles": "\U0001F697", "tools": "\U0001F527", "home": "\U0001F3E0", "toys": "\U0001F9F8", "clothes": "\U0001F455",
    "made": "\U0001F3ED", "art": "\U0001F3A8", "sports": "⚽", "play": "\U0001F3B2", "time": "⏰",
    "school": "\U0001F3EB", "money": "\U0001FA99", "holidays": "\U0001F389", "language": "\U0001F524",
    "feelings": "\U0001F60A", "friends": "\U0001F91D", "family": "\U0001F46A", "town": "\U0001F3D8️",
}
SENSITIVE_EMOJI = "\U0001F499"   # a blue heart, as the kid page's soft card


def hub_topic(item: dict) -> str:
    t = item.get("topic") or ""
    if t == "ocean":   # sea animals (ani-) vs the sea itself (sky-)
        return "animals" if item["id"].startswith("ani") else "earth"
    return TOPIC.get(t, "people")


def sensitive_category(item: dict):
    n = str(item.get("notes") or "")
    if not n.startswith("sensitive:"):
        return None
    return n.split(":", 1)[1].strip() or "other"


def emoji(item: dict) -> str:
    if sensitive_category(item):
        return SENSITIVE_EMOJI
    from .emoji import TOPIC_EMOJI
    return EMOJI.get(item.get("topic"), TOPIC_EMOJI.get(hub_topic(item), "\U0001F50D"))


class AnswerBank:
    def __init__(self, cfg: dict, recall):
        c = cfg.get("answer_bank") or {}
        self.cfg = cfg
        self.recall = recall
        self.enabled = bool(c.get("enabled", True))
        self.threshold = float(c.get("threshold", 0.80))
        p = Path(c.get("path") or "knowledge/answer_bank_en.jsonl")
        self.path = p if p.is_absolute() else ROOT / p
        own = str(c.get("model") or "").strip()   # optional: the bank's own embedding model (see the module docstring)
        self.own_model = bool(own)
        self.model_path = (str(Path(own) if Path(own).is_absolute() else ROOT / own)) if own else ""
        cp = c.get("cache")   # default: next to the database (data/answer_bank_en.npz, gitignored)
        stem = self.path.stem + ("." + Path(own).name if own else "")
        self.cache_path = (Path(cp) if Path(cp).is_absolute() else ROOT / cp) if cp else resolve(cfg, "db").parent / (stem + ".npz")
        self.model_name = own or str(cfg["recall"]["model"])
        self.encoder = None      # SentenceTransformer of `answer_bank.model` (None: the recall model is used)
        self._kb_rows = {}       # KB entry id -> its en example rows embedded with the bank's model (kb_cosine)
        self._qvec = {}          # normalised text -> embedding, last few queries (search + kb_cosine share them)
        self.items, self.by_id = [], {}
        self.owner = np.zeros(0, dtype=np.int32)
        self.matrix = None
        self.error = None
        self.cache = None        # "hit" | "built" | "unsaved" (start-up)
        self.load_s = 0.0
        self.last = None         # {"id", "score"} of the last search (also below the threshold)
        if self.enabled:
            self.load()

    @property
    def ready(self) -> bool:
        return self.enabled and self.matrix is not None and len(self.items) > 0

    def status(self) -> dict:
        return {"enabled": self.enabled, "items": len(self.items), "threshold": self.threshold, "cache": self.cache,
                "load_s": round(self.load_s, 1), "error": self.error,
                "model": Path(self.model_name).name if self.own_model else "recall"}

    # ---- embedding ----
    def _load_encoder(self):
        from sentence_transformers import SentenceTransformer
        from .config import torch_device
        self.encoder = SentenceTransformer(self.model_path, device=torch_device(self.cfg), local_files_only=True)

    def _embed(self, texts):
        if not self.own_model:
            return self.recall._embed(texts)
        v = self.encoder.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False, batch_size=64)
        return v.astype(np.float32)

    def _query(self, n: str):
        v = self._qvec.get(n)
        if v is None:
            if len(self._qvec) > 8:
                self._qvec.clear()
            v = self._qvec[n] = self._embed([n])[0]
        return v

    def kb_cosine(self, entry: dict, texts) -> float:
        """Own model only: the KB entry's plain cosine (max over its English labels + question patterns, as
        Recall.raw_scores) measured with the BANK's model, so hub/pipeline.py's kb_margin compares like with like."""
        rows = self._kb_rows.get(entry["id"])
        if rows is None:
            fl = entry.get("en") or {}
            ts = [normalize_en(t) for t in list(fl.get("labels", [])) + list(fl.get("question_patterns", []))]
            ts = [t for t in ts if t]
            rows = self._kb_rows[entry["id"]] = self._embed(ts) if ts else np.zeros((0, 1), dtype=np.float32)
        best = 0.0
        for t in texts:
            n = normalize_en(t)
            if n and len(rows):
                best = max(best, float(np.max(rows @ self._query(n))))
        return best

    # ---- loading ----
    def load(self):
        t = time.perf_counter()
        try:
            raw = self.path.read_bytes()
            items = []
            for line in raw.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                if all(d.get(k) for k in FIELDS):
                    items.append(d)
            rows, owner = [], []
            for i, d in enumerate(items):
                for s in [d["q"]] + list(d.get("variants") or []):
                    n = normalize_en(s)
                    if n:
                        rows.append(n)
                        owner.append(i)
            if self.own_model and self.encoder is None:
                self._load_encoder()
            key = hashlib.sha256(raw + f"|{self.model_name}|{CACHE_VERSION}".encode()).hexdigest()
            mat = self._cached(key, len(rows))
            if mat is None:
                mat = self._embed(rows)
                self.cache = self._save(key, mat)
            self.items, self.by_id = items, {d["id"]: d for d in items}
            self.owner, self.matrix = np.asarray(owner, dtype=np.int32), mat
            self.error = None
        except Exception as e:   # no bank file, bad JSON ...: the hub runs without the bank
            self.items, self.by_id, self.matrix = [], {}, None
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
        self.load_s = time.perf_counter() - t

    def _cached(self, key: str, n_rows: int):
        try:
            with np.load(self.cache_path, allow_pickle=False) as z:
                if str(z["key"]) == key and z["matrix"].shape[0] == n_rows:
                    self.cache = "hit"
                    return z["matrix"].astype(np.float32)
        except Exception:
            pass
        return None

    def _save(self, key: str, mat) -> str:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp.npz")
            np.savez(tmp, key=np.array(key), matrix=mat)
            tmp.replace(self.cache_path)
            return "built"
        except Exception:
            return "unsaved"

    # ---- search ----
    def search(self, text: str, lang: str = "en"):
        """(item | None, score): the best item at or above the threshold. English only."""
        self.last = None
        if lang != "en" or not self.ready:
            return None, 0.0
        n = normalize_en(text)
        if not n:
            return None, 0.0
        sims = self.matrix @ self._query(n)
        best = np.full(len(self.items), -1.0, dtype=np.float32)
        np.maximum.at(best, self.owner, sims)
        i = int(np.argmax(best))
        s = float(best[i])
        self.last = {"id": self.items[i]["id"], "score": round(s, 3)}
        return (self.items[i], s) if s >= self.threshold else (None, s)
