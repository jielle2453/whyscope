"""Embedding retrieval over knowledge/entries/*/*.json with threshold abstention.

One index per language (zh from the top-level entry fields, en from entry["en"]): embeddings of
(labels + question_patterns) for every entry, built at startup.
Query score = max cosine similarity over an entry's index rows, multiplied by a coverage factor
(share of the question's content tokens found in the entry's own text), so "same topic, unknown detail" abstains.
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


# ---------------------------------------------------------------- English helpers
_EN_PUNCT = re.compile(r"[^a-z0-9 ]+")
_EN_STOP = set("""why what how when where who which does do did is are was were am be been a an the this that these those
it its of to in on at by for with from up out as and or but so if then than too very can could would should will
you your we our us they them their he she him her his i me my there here have has had get gets make makes made
go goes going come comes just all some any each also not no yes into over about like one thing things
say said tell please look see""".split())
_COMMON_EN = None


def normalize_en(q: str) -> str:
    """Lower case, no punctuation (apostrophes dropped), single spaces."""
    q = (q or "").lower().replace("’", "'").replace("'s ", " ").replace("'", "")
    return " ".join(_EN_PUNCT.sub(" ", q).split())


def stem_en(w: str) -> str:
    """Tiny plural / -ing stemmer, good enough to match 'ants' with 'ant' and 'glowing' with 'glow'."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "shes", "ches", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    return w


def content_en(q: str) -> list:
    """Stemmed content words (question and function words removed)."""
    return [stem_en(w) for w in normalize_en(q).split() if w not in _EN_STOP]


def common_en() -> frozenset:
    global _COMMON_EN
    if _COMMON_EN is None:
        f = Path(__file__).resolve().parent / "data" / "common_words_en.txt"
        try:
            _COMMON_EN = frozenset(stem_en(w) for w in f.read_text(encoding="utf-8").split())
        except OSError:
            _COMMON_EN = frozenset()
    return _COMMON_EN


def plausible_en(q: str, known=frozenset()) -> bool:
    """English gibberish pre-check: too short, one repeated syllable/word, or no content word we know at all."""
    n = normalize_en(q)
    toks = n.split()
    if len(n) < 3 or len(set(n.replace(" ", ""))) <= 2 or not re.search(r"[a-z]{2}", n):
        return False
    if len(toks) < 2 or len(set(toks)) == 1:   # a single word (or one word repeated) is not a question
        return False
    cw = content_en(q)
    if cw and known and not any(w in known or w in common_en() for w in cw):
        return False
    return True


class Recall:
    LANGS = ("zh", "en")

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.threshold = float(cfg["recall"]["threshold"])
        self.cov_weight = float(cfg["recall"].get("coverage_weight", 0.4))
        self.cov_weight_en = float(cfg["recall"].get("coverage_weight_en", self.cov_weight))
        self.entries = []     # entry dicts (id, topic, zh fields at top level, English fields in e["en"])
        self.idx = {}         # lang -> {"rows": [(entry_index, text)], "matrix": ndarray, "vocab": [set], "known": set}
        self.model = None
        self.device = "cpu"
        self.load_error = None
        self._load_model()
        self.build_index()

    # kept for older callers: the zh index
    @property
    def rows(self):
        return self.idx["zh"]["rows"]

    @property
    def matrix(self):
        return self.idx["zh"]["matrix"]

    @property
    def vocab(self):
        return self.idx["zh"]["vocab"]

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

    @staticmethod
    def fields(e: dict, lang: str) -> dict:
        """The entry's text fields in `lang` (zh = top-level fields, en = e["en"])."""
        return e if lang == "zh" else (e.get("en") or {})

    def build_index(self):
        """(Re)load all entries and embed labels + question_patterns, once per language."""
        root = resolve(self.cfg, "knowledge") / "entries"
        self.entries = []
        for f in sorted(root.glob("*/*.json")):
            try:
                e = json.loads(f.read_text(encoding="utf-8"))
                if not (e.get("id") and e.get("first_sentence") and e.get("facts")):
                    continue
            except Exception:
                continue
            self.entries.append(e)
        self.idx = {}
        for lang in self.LANGS:
            norm = normalize if lang == "zh" else normalize_en
            rows, vocab, known = [], [], set()
            for i, e in enumerate(self.entries):
                fl = self.fields(e, lang)
                if not (fl.get("first_sentence") and fl.get("facts")):
                    vocab.append(set())
                    continue
                for t in list(fl.get("labels", [])) + list(fl.get("question_patterns", [])):
                    rows.append((i, norm(t)))
                text = " ".join(list(fl.get("labels", [])) + list(fl.get("question_patterns", [])) +
                                list(fl["facts"]) + [fl["first_sentence"], fl.get("ask_back", "")])
                if lang == "zh":
                    vocab.append(_bigrams(content(text)))
                else:
                    v = set(content_en(text))
                    vocab.append(v)
                    known |= v
            self.idx[lang] = {"rows": rows, "vocab": vocab, "known": known,
                              "matrix": self._embed([t for _, t in rows]) if rows else None}

    def coverage(self, text: str, lang: str = "zh") -> np.ndarray:
        """Per-entry fraction of the question's content tokens (zh bigrams / en stems) that the entry has."""
        qb = _bigrams(content(text)) if lang == "zh" else set(content_en(text))
        if not qb:
            return np.zeros(len(self.entries), dtype=np.float32)
        return np.array([len(qb & v) / len(qb) for v in self.idx[lang]["vocab"]], dtype=np.float32)

    def raw_scores(self, text: str, lang: str = "zh") -> np.ndarray:
        """Per-entry best cosine score for the query."""
        out = np.full(len(self.entries), -1.0, dtype=np.float32)
        ix = self.idx[lang]
        if ix["matrix"] is None or not text.strip():
            return out
        sims = ix["matrix"] @ self._embed([(normalize if lang == "zh" else normalize_en)(text)])[0]
        for (i, _), s in zip(ix["rows"], sims):
            if s > out[i]:
                out[i] = s
        return out

    def scores(self, text: str, lang: str = "zh") -> np.ndarray:
        """Final per-entry score = cosine * (1 - w * (1 - coverage)): off-topic details lower the score."""
        sc = self.raw_scores(text, lang)
        w = self.cov_weight if lang == "zh" else self.cov_weight_en
        return sc * (1.0 - w * (1.0 - self.coverage(text, lang)))

    def search(self, text: str, lang: str = "zh", obj=None):
        """Return (entry|None, score). `obj` is an optional vision label (matches entry labels in any language)."""
        if lang not in self.idx:
            lang = "zh"
        ok = plausible(text) if lang == "zh" else plausible_en(text, self.idx["en"]["known"])
        if not self.entries or (not obj and not ok):
            return None, 0.0
        sc = self.scores(text, lang)
        if obj:
            o = obj.lower()
            for i, e in enumerate(self.entries):
                labs = list(e.get("labels", [])) + list((e.get("en") or {}).get("labels", []))
                if o in [l.lower() for l in labs]:
                    sc[i] = max(sc[i], 0.75)  # the camera saw it: strong evidence for this entry
        i = int(np.argmax(sc))
        return self.entries[i], float(sc[i])

    def vision_labels(self):
        """[(label_zh, [ascii labels])] for open-vocabulary vision matching."""
        out = []
        for e in self.entries:
            labs = e.get("labels", [])
            en = [l for l in labs if l.isascii()] + list((e.get("en") or {}).get("labels", []))
            if labs and en:
                out.append((labs[0], list(dict.fromkeys(en))))
        return out
