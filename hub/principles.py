"""Principle library: about 70 child-level science principles (buoyancy, gravity, germs, ...) with pre-written answers.

Why retrieval and not generation: the small on-device LLM must not write explanations for children (it reverses facts
and invents, see eval/principles/report.md). So a question is matched to a principle by embedding, with a score floor
and a margin over the runner-up, and the answer is one of the principle's own pre-written sentences. Nothing is
rewritten. Below the floor, or with a close runner-up, the hub does not answer (the question goes to the parent).

Index per language: for every principle one row for its name, one per question example, and one row for the list of
things it applies to. Score = max cosine over the principle's rows (the "applies to" row counts 0.9).
Precision gates (English, see config.yaml `principles`): the best principle is answered only if the question contains
one of its `keywords_en` (the mechanism it explains) and most of the question's content words are known to the principle
(its question examples, applies_to and keywords). The gates only veto; they never pick a different principle.
`{object}` in an answer is filled only when the asked thing (named in the question, or the label the camera saw) is in
the principle's `applies_to` list; otherwise a slotless answer is used.

knowledge/principles/principles.json is an AI draft (`reviewed_by` empty): every answer from it is marked `draft`.
"""
import json

import numpy as np

from .config import resolve
from .recall import _bigrams, content, content_en, normalize, normalize_en, stem_en

APPLIES_WEIGHT = 0.9
OBJECT_BONUS = 0.05   # the asked thing (in the question or seen by the camera) is on the principle's applies_to list
_EXTRA_STOP = {"cant", "dont", "wont", "doesnt", "isnt", "didnt", "couldnt", "wouldnt", "arent", "wasnt", "im", "ive"}


class Principles:
    def __init__(self, cfg: dict, recall):
        pc = cfg.get("principles") or {}
        self.recall = recall
        self.enabled = bool(pc.get("enabled", True))
        self.floor = float(pc.get("floor", 0.60))
        self.margin = float(pc.get("margin", 0.05))
        # Precision gates (English), applied to the best-matching principle only (they can veto an answer, never pick another
        # principle). require_keyword: the question must contain one of its `keywords_en` (the mechanism it explains:
        # "float"/"sink" for buoyancy), else the hub does not answer.
        # coverage_weight: the score is multiplied by 1 - w * (1 - coverage), coverage = share of the question's content
        # words that the principle knows (its question examples, applies_to and keywords): a question about a
        # detail the principle never mentions ("whiskers", "sticky") scores lower.
        self.require_keyword = bool(pc.get("require_keyword", True))
        self.coverage_weight = float(pc.get("coverage_weight", 0.5))
        self.min_coverage = float(pc.get("min_coverage", 0.6))   # hard floor on coverage (0 = off)
        self.kw, self.vocab = [], []   # per principle (English): keyword phrases as stem tuples, known content stems
        self.items, self.draft, self.error = [], True, None
        self.idx = {}      # lang -> {"rows": [principle_index], "matrix": ndarray, "weight": ndarray}
        self.known = set()  # content stems of every English principle text (so gibberish checks know these words)
        if self.enabled:
            try:
                self._load(resolve(cfg, "knowledge") / "principles" / "principles.json")
            except Exception as e:  # a broken file must not stop the hub
                self.error = f"{type(e).__name__}: {str(e)[:160]}"
                self.enabled, self.items = False, []

    # ---------------------------------------------------------------- loading
    def _load(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.draft = not str(data.get("reviewed_by") or "").strip()
        self.items = [p for p in data.get("principles", []) if p.get("id") and p.get("answers_en")]
        for p in self.items:
            kws = [tuple(stem_en(w) for w in normalize_en(k).split()) for k in p.get("keywords_en") or []]
            self.kw.append([k for k in kws if k])
            v = set()
            for t in (list(p.get("question_examples_en") or []) + list(p.get("applies_to_en") or [])
                      + list(p.get("keywords_en") or [])):
                v |= set(content_en(t))
            self.vocab.append(v)
        for lang in ("en", "zh"):
            norm = normalize_en if lang == "en" else normalize
            texts, rows, weight = [], [], []
            for i, p in enumerate(self.items):
                if not p.get(f"answers_{lang}"):
                    continue
                name = p.get(f"name_{lang}") or ""
                ex = list(p.get(f"question_examples_{lang}") or [])
                ap = list(p.get(f"applies_to_{lang}") or [])
                for t in ([name] if name else []) + ex:
                    texts.append(norm(t)), rows.append(i), weight.append(1.0)
                if ap:
                    sep = ", " if lang == "en" else "、"
                    texts.append(norm(("about " if lang == "en" else "") + sep.join(ap))), rows.append(i), weight.append(APPLIES_WEIGHT)
                if lang == "en":
                    for t in [name] + ex + ap + list(p.get("facts_en") or []):
                        self.known |= set(content_en(t))
            self.idx[lang] = {"rows": np.array(rows), "weight": np.array(weight, dtype=np.float32),
                              "matrix": self.recall._embed(texts) if texts else None}

    # ---------------------------------------------------------------- retrieval
    def scores(self, text: str, lang: str) -> np.ndarray:
        """Per-principle best weighted cosine (-1 where the principle has no text in this language)."""
        out = np.full(len(self.items), -1.0, dtype=np.float32)
        ix = self.idx.get(lang)
        if not ix or ix["matrix"] is None or not text.strip():
            return out
        q = self.recall._embed([(normalize_en if lang == "en" else normalize)(text)])[0]
        sims = (ix["matrix"] @ q) * ix["weight"]
        for i, s in zip(ix["rows"], sims):
            if s > out[i]:
                out[i] = s
        return out

    def gates(self, text: str):
        """(keyword hit per principle (True where it has no keywords), coverage per principle) for an English question."""
        toks = [stem_en(w) for w in normalize_en(text).split()]
        joined = [tuple(toks[i:i + n]) for n in range(1, 4) for i in range(len(toks) - n + 1)]
        have = set(joined)
        hit = np.array([(not k) or any(x in have for x in k) for k in self.kw], dtype=bool)
        qc = {w for w in content_en(text) if w not in _EXTRA_STOP}
        cov = np.array([len(qc & v) / len(qc) if qc else 1.0 for v in self.vocab], dtype=np.float32)
        return hit, cov

    def plausible(self, text: str, lang: str) -> bool:
        from .recall import plausible, plausible_en
        if lang == "en":
            return plausible_en(text, self.recall.idx["en"]["known"] | self.known)
        return plausible(text)

    def top(self, text: str, lang: str, k: int = 3) -> list:
        """[(principle, score)] best first (no floor), for retrieval of context."""
        sc = self.scores(text, lang)
        return [(self.items[i], float(sc[i])) for i in np.argsort(-sc)[:k] if sc[i] > -1]

    def find_object(self, p: dict, text: str, lang: str, obj=None):
        """The thing asked about, if it is in the principle's applies_to list: named in the question (longest phrase
        wins), else the vision label. Returns the applies_to phrase, or None."""
        applies = list(p.get(f"applies_to_{lang}") or [])
        if lang == "en":
            qs = [stem_en(w) for w in normalize_en(text).split()]
            best = None
            for a in applies:
                ws = [stem_en(w) for w in normalize_en(a).split()]
                if ws and any(qs[i:i + len(ws)] == ws for i in range(len(qs) - len(ws) + 1)):
                    if best is None or len(ws) > len(best[1]):
                        best = (a, ws)
            if best:
                return best[0]
            if obj:
                ow = [stem_en(w) for w in normalize_en(obj).split()]
                for a in applies:
                    if [stem_en(w) for w in normalize_en(a).split()] == ow:
                        return a
            return None
        q = normalize(text)
        hits = [a for a in applies if normalize(a) and normalize(a) in q]
        if hits:
            return max(hits, key=len)
        return next((a for a in applies if obj and normalize(a) == normalize(obj)), None)

    @staticmethod
    def _stems(text: str, lang: str) -> set:
        return set(content_en(text)) if lang == "en" else _bigrams(content(text))

    def choose_answer(self, p: dict, text: str, lang: str, obj) -> tuple:
        """(answer text, slot filled?). With a known object every answer may be used (slots filled), else only the
        slotless ones. The first usable answer is the default; a later one wins only when it contains a word of the
        question that the other answers do not (weighted by how few answers have it: 'sink' picks "... A heavy one
        sinks", not "... it floats"). The object's own words do not count."""
        answers = list(p.get(f"answers_{lang}") or [])
        cands, own = [], []
        for a in answers:
            if "{object}" in a:
                if obj:
                    cands.append((a.replace("{object}", obj), True))
                    own.append(a.replace("{object}", ""))
            else:
                cands.append((a, False))
                own.append(a)
        if not cands:   # every answer has a slot and the object is unknown: nothing safe to say
            return "", False
        if len(cands) == 1:
            return cands[0]
        qs = self._stems(text, lang) - (self._stems(obj, lang) if obj else set())
        ast = [self._stems(a.replace("{object}", ""), lang) for a in answers]
        df = {w: sum(w in st for st in ast) for w in qs}
        score = [sum(1.0 / df[w] for w in qs if df[w] and w in self._stems(o, lang)) for o in own]
        best = max(range(len(cands)), key=lambda i: (score[i], -i))
        return cands[best] if score[best] > score[0] else cands[0]

    def search(self, text: str, lang: str = "en", obj=None):
        """The best principle for the question, or None. Returns a dict {principle, id, score, margin, runner_up,
        object, answer, slot, partial, draft}; `self.last` always says what the best two were (for logs and tuning)."""
        self.last = None
        if not self.enabled or lang not in self.idx or not (text or "").strip():
            return None
        if not obj and not self.plausible(text, lang):
            return None
        sc = self.scores(text, lang)
        for i in np.argsort(-sc)[:5]:   # the asked thing is one this principle is about: a little evidence for it
            if sc[i] > -1 and self.find_object(self.items[int(i)], text, lang, obj):
                sc[i] += OBJECT_BONUS
        o = np.argsort(-sc)[:2]
        if len(o) < 2 or sc[o[0]] <= -1:
            return None
        raw, second = float(sc[o[0]]), float(sc[o[1]])
        p = self.items[int(o[0])]
        top, veto, cov = raw, False, None
        if lang == "en":   # the semantic winner must also be asked about by its mechanism and well covered; it is never replaced
            hit, covs = self.gates(text)
            cov = float(covs[o[0]])
            veto = (self.require_keyword and not hit[o[0]]) or cov < self.min_coverage - 1e-6
            top = raw * (1.0 - self.coverage_weight * (1.0 - cov))
        self.last = {"id": p["id"], "score": round(top, 3), "margin": round(raw - second, 3),
                     "runner_up": self.items[int(o[1])]["id"], **({"coverage": round(cov, 2), "veto": veto} if cov is not None else {})}
        if veto or top < self.floor or raw - second < self.margin:
            return None
        thing = self.find_object(p, text, lang, obj)
        ans, slot = self.choose_answer(p, text, lang, thing)
        if not ans:
            return None
        return {"principle": p, "id": p["id"], "score": top, "margin": raw - second, "runner_up": self.items[int(o[1])]["id"],
                "object": thing, "answer": ans, "slot": slot, "partial": bool(p.get("partial")), "draft": self.draft}
