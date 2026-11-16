"""Family answers: answers a parent approved for a question the device could not answer.

Stored in SQLite (table family_answers: household, question, answer, embedding, source event, approved_at). A new question is
matched against them by the same sentence-embedding model as the knowledge base, with a HIGH threshold (near-duplicate
wording only) plus a content-word check, so "Why do zebras have stripes?" finds the approved answer but "Why do zebras
have spots?" does not. Checked after the knowledge-base entries and before the principle library.

Family answers belong to a household and are shared by its children; another household never sees them.
"""
import numpy as np

from .recall import _bigrams, content, content_en, normalize, normalize_en


class Family:
    def __init__(self, cfg: dict, db, recall):
        fc = cfg.get("family") or {}
        self.db, self.recall = db, recall
        self.threshold = float(fc.get("threshold", 0.88))
        self.min_overlap = float(fc.get("min_overlap", 0.6))   # share of content words the two questions must share
        self.rows = {}   # household id -> {lang -> [(row dict, vector, content set)]}
        self.reload()

    @staticmethod
    def _content(text: str, lang: str) -> set:
        return set(content_en(text)) if lang == "en" else _bigrams(content(text))

    @staticmethod
    def _norm(text: str, lang: str) -> str:
        return normalize_en(text) if lang == "en" else normalize(text)

    def reload(self):
        self.rows = {}
        for r in self.db.family_all():
            lang = r["lang"] if r["lang"] in ("en", "zh") else "zh"
            vec = np.frombuffer(r["embedding"], dtype=np.float32) if r.get("embedding") else None
            if vec is None or not len(vec):
                vec = self.recall._embed([self._norm(r["question"], lang)])[0]
            hh = r.get("household_id") or 1
            self.rows.setdefault(hh, {"en": [], "zh": []})[lang].append(
                ({k: v for k, v in r.items() if k != "embedding"}, vec, self._content(r["question"], lang)))

    def count(self) -> int:
        return sum(len(v) for per in self.rows.values() for v in per.values())

    def embed(self, text: str, lang: str) -> np.ndarray:
        return self.recall._embed([self._norm(text, lang)])[0]

    def match(self, text: str, lang: str, household_id: int = 1):
        """(row, score) of the best approved answer of this household for a near-duplicate question, else (None, best score)."""
        rows = (self.rows.get(household_id) or {}).get(lang) or []
        if not rows or not (text or "").strip():
            return None, 0.0
        q = self.embed(text, lang)
        qc = self._content(text, lang)
        best, bs = None, 0.0
        for row, vec, cs in rows:
            s = float(vec @ q)
            if s <= bs:
                continue
            union = qc | cs
            if union and len(qc & cs) / len(union) < self.min_overlap:
                continue
            best, bs = row, s
        return (best, bs) if bs >= self.threshold else (None, bs)

    def add(self, question: str, lang: str, answer: str, source_event, todo_id, household_id: int = 1) -> int:
        vec = self.embed(question, lang).astype(np.float32)
        fid = self.db.family_add(question, lang, answer, vec.tobytes(), source_event, todo_id, household_id)
        self.reload()
        return fid

    def delete(self, fid: int):
        self.db.family_delete(fid)
        self.reload()
