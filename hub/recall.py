"""Embedding retrieval over knowledge/entries/*/*.json with threshold abstention.

Index = embeddings of (labels + question_patterns) for every entry, built at startup.
Query score = max cosine similarity over an entry's index rows, multiplied by a coverage factor
(share of the question's content bigrams found in the entry's own text), so "same topic, unknown detail" abstains.
"""
import json
import re
from pathlib import Path

import numpy as np

from .config import resolve, to_trad, torch_device

_PUNCT = re.compile(r"[\s，。！？、,.!?~～「」『』（）()]+")
_TAIL = re.compile(r"[嗎呢啊吧喔哦啦呀]+$")


_GENERIC = ["為什麼", "為甚麼", "為何", "什麼", "怎麼", "怎樣", "如何", "是誰", "哪裡", "哪個", "可以", "一個", "有沒有", "是不是",
            "會不會", "這是", "那是", "這個", "那個", "我們", "你們", "它們", "他們", "自己", "一直", "可是", "因為", "所以", "然後"]
_GENERIC_CH = set("的了是在有會和也都就很把被讓跟著這那嗎呢吧啊喔哦呀啦我你他她它牠們個為什麼怎樣要能對給不沒到從與及或但而又還更之以於用得地")
_CJK = re.compile(r"[一-鿿]")


def content(q: str) -> str:
    """Question words and function characters removed: what the question is actually about."""
    q = normalize(q)
    for g in _GENERIC:
        q = q.replace(g, "")
    return "".join(ch for ch in q if ch not in _GENERIC_CH and not ch.isspace())


def _bigrams(s: str) -> set:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())


def plausible(q: str) -> bool:
    """Reject gibberish and non-questions before embedding: too short, repeated syllables, or no Chinese at all."""
    n = normalize(q)
    return len(n) >= 3 and len(set(n)) > 2 and bool(_CJK.search(n))


def normalize(q: str) -> str:
    """Light normalisation: Traditional script, no punctuation, no sentence-final particles."""
    return _TAIL.sub("", _PUNCT.sub("", to_trad(q or "")))


class Recall:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.threshold = float(cfg["recall"]["threshold"])
        self.cov_weight = float(cfg["recall"].get("coverage_weight", 0.4))
        self.entries = []     # list of entry dicts
        self.rows = []        # list of (entry_index, text)
        self.matrix = None
        self.model = None
        self.device = "cpu"
        self.load_error = None
        self._load_model()
        self.build_index()

    def _load_model(self):
        from sentence_transformers import SentenceTransformer
        name = self.cfg["recall"]["model"]
        cache = str(resolve(self.cfg, "models") / "hf")
        self.device = torch_device(self.cfg)
        try:
            self.model = SentenceTransformer(name, device=self.device, cache_folder=cache,
                                             local_files_only=True)
        except Exception:
            self.model = SentenceTransformer(name, device=self.device, cache_folder=cache)

    def _embed(self, texts):
        v = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True,
                              show_progress_bar=False, batch_size=64)
        return v.astype(np.float32)

    def build_index(self):
        """(Re)load all entries and embed labels + question_patterns."""
        root = resolve(self.cfg, "knowledge") / "entries"
        self.entries, self.rows = [], []
        for f in sorted(root.glob("*/*.json")):
            try:
                e = json.loads(f.read_text(encoding="utf-8"))
                if not (e.get("id") and e.get("first_sentence") and e.get("facts")):
                    continue
            except Exception:
                continue
            idx = len(self.entries)
            self.entries.append(e)
            for t in list(e.get("labels", [])) + list(e.get("question_patterns", [])):
                self.rows.append((idx, normalize(t)))
        self.matrix = self._embed([t for _, t in self.rows]) if self.rows else None
        # Vocabulary of each entry (content bigrams) for the coverage check.
        self.vocab = [_bigrams(content(" ".join(list(e.get("labels", [])) + list(e.get("question_patterns", [])) +
                                                list(e["facts"]) + [e["first_sentence"], e.get("ask_back", "")])))
                      for e in self.entries]

    def coverage(self, text: str) -> np.ndarray:
        """Per-entry fraction of the question's content bigrams that the entry's vocabulary contains."""
        qb = _bigrams(content(text))
        if not qb:
            return np.zeros(len(self.entries), dtype=np.float32)
        return np.array([len(qb & v) / len(qb) for v in self.vocab], dtype=np.float32)

    def raw_scores(self, text: str) -> np.ndarray:
        """Per-entry best cosine score for the query."""
        out = np.full(len(self.entries), -1.0, dtype=np.float32)
        if self.matrix is None or not text.strip():
            return out
        sims = self.matrix @ self._embed([normalize(text)])[0]
        for (i, _), s in zip(self.rows, sims):
            if s > out[i]:
                out[i] = s
        return out

    def scores(self, text: str) -> np.ndarray:
        """Final per-entry score = cosine * (1 - w * (1 - coverage)): off-topic details lower the score."""
        sc = self.raw_scores(text)
        return sc * (1.0 - self.cov_weight * (1.0 - self.coverage(text)))

    def search(self, text: str, obj=None):
        """Return (entry|None, score). `obj` is an optional vision label (matches entry labels)."""
        if not self.entries or (not obj and not plausible(text)):
            return None, 0.0
        sc = self.scores(text)
        if obj:
            o = obj.lower()
            for i, e in enumerate(self.entries):
                if o in [l.lower() for l in e.get("labels", [])]:
                    sc[i] = max(sc[i], 0.75)  # the camera saw it: strong evidence for this entry
        i = int(np.argmax(sc))
        return self.entries[i], float(sc[i])

    def vision_labels(self):
        """[(label_zh, [ascii labels])] for open-vocabulary vision matching."""
        out = []
        for e in self.entries:
            labs = e.get("labels", [])
            en = [l for l in labs if l.isascii()]
            if labs and en:
                out.append((labs[0], en))
        return out
