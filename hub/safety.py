"""Sensitive-topic rules: keyword -> category -> deflection + parent cheat-sheet event.

Loads knowledge/sensitive_rules.json and the triggers of knowledge/cheats/*.json once at startup.
Accepted rules shapes: {"categories": {cat: {"triggers": [...], "category_zh": ...}}},
{cat: [words]} or [{"id"|"category": cat, "keywords"|"triggers": [...]}].
"""
import json
import re
from pathlib import Path

from .config import ROOT, to_trad

DEFAULT_DEFLECTION_EN = "That is a big question. Let's ask a grown-up together."
_CJK = re.compile(r"[\u4e00-\u9fff]")
DEFAULT_DEFLECTION = "這個問題很重要，我們一起去問爸爸媽媽好嗎？"
# Safety floor that is always on, even if the rules file is missing or thin (err on the side of the parent).
BASELINE = {"death": ["死"], "self_harm": ["自殺", "想死", "不想活"]}
PRIORITY = ["self_harm", "death", "violence_war", "birth_sex"]  # tie-break only
_STRIP = re.compile(r"[\s，。！？、,.!?~～「」『』（）()]+")

# An ask-back may never probe the child's day, feelings, family or friends (product pass 1, A.1).
ASKBACK_BLOCK = re.compile(r"今天|開心|難過|傷心|生氣|害怕|爸爸媽媽有沒有|朋友|同學|學校|老師|你的家人|你家人|你喜歡|你愛")


def askback_ok(q: str) -> bool:
    """False if an ask-back question touches blocked personal topics."""
    return not ASKBACK_BLOCK.search(q or "")


def _norm_en(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\u2019", "'").lower()).strip()


def _word_rx(w: str) -> str:
    """One trigger word, tolerant of plain inflections: 'fighting' also matches 'fight', 'fights', 'fighting'
    (generic stemming, so a trigger written in one form still catches the child's form)."""
    from .recall import stem_en
    base = stem_en(w)
    if base == w and w.endswith("ing") and len(w) > 5:
        base = w[:-3]
    return "(?:" + re.escape(w) + "|" + re.escape(base) + r"(?:s|es|ed|d|ing)?)"


def _en_regex(phrase: str):
    """Case-insensitive, word-boundary regex built generically from one English trigger phrase."""
    words = [_word_rx(w) for w in _norm_en(phrase).split(" ") if w]
    if not words:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(words) + r"(?![a-z0-9])", re.I)


def _norm(s: str) -> str:
    return _STRIP.sub("", to_trad(s or "")).lower()


class Safety:
    def __init__(self, cfg: dict):
        s = cfg.get("safety", {})
        self.rules_file = self._p(s.get("rules_file", "knowledge/sensitive_rules.json"))
        self.cheats_dir = self._p(s.get("cheats_dir", "knowledge/cheats"))
        self.reload()

    @staticmethod
    def _p(x):
        p = Path(x)
        return p if p.is_absolute() else ROOT / p

    def reload(self):
        self.triggers = {}   # category -> set(normalised words)
        self.triggers_en = {}  # category -> set(normalised English phrases)
        self.zh = {}         # category -> category_zh
        self.cheats = {}     # category -> cheat dict
        self.urgent = set()  # categories flagged urgent in the rules file
        for cat, words in BASELINE.items():
            self._add(cat, words)
        self._load_rules()
        self._load_cheats()
        flat = [(len(w), w, c) for c, ws in self.triggers.items() for w in ws if w]
        self._flat = sorted(flat, key=lambda t: -t[0])
        en = sorted(((len(w), _en_regex(w), c) for c, ws in self.triggers_en.items() for w in ws if w),
                    key=lambda t: -t[0])
        self._flat_en = [t for t in en if t[1]]

    def _add(self, cat, words, zh=None):
        self.triggers.setdefault(cat, set()).update(_norm(w) for w in words if w)
        if zh:
            self.zh[cat] = zh

    def _add_en(self, cat, words):
        self.triggers_en.setdefault(cat, set()).update(_norm_en(w) for w in words if w)

    def _load_rules(self):
        try:
            data = json.loads(self.rules_file.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, dict) and isinstance(data.get("categories"), (dict, list)):
            data = data["categories"]
        if isinstance(data, dict):
            for cat, v in data.items():
                if cat.startswith("_"):
                    continue
                if isinstance(v, list):
                    self._add(cat, v)
                elif isinstance(v, dict):
                    self._add(cat, v.get("triggers") or v.get("keywords") or [], v.get("category_zh"))
                    self._add_en(cat, v.get("triggers_en") or [])
        elif isinstance(data, list):
            for v in data:
                cat = v.get("category") or v.get("id")
                if cat:
                    self._add(cat, v.get("triggers") or v.get("keywords") or [], v.get("category_zh"))
                    self._add_en(cat, v.get("triggers_en") or [])
                    if v.get("urgent"):
                        self.urgent.add(cat)

    def _load_cheats(self):
        if not self.cheats_dir.is_dir():
            return
        for f in sorted(self.cheats_dir.glob("*.json")):
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            cat = c.get("category") or c.get("id")
            if not cat:
                continue
            self.cheats[cat] = c
            self._add(cat, c.get("triggers", []), c.get("category_zh"))
            self._add_en(cat, (c.get("en") or {}).get("triggers", []))

    def check(self, text: str, lang: str = "zh"):
        """Return the sensitive category hit (with deflection text in `lang`) or None.
        zh: Chinese triggers. en: English triggers (case-insensitive, word boundary); Chinese triggers are also
        tried when an English-mode text contains Chinese characters."""
        hits = {}
        if lang == "en":
            t = _norm_en(text)
            if not t:
                return None
            for n, rx, cat in self._flat_en:
                if rx.search(t):
                    hits[cat] = max(hits.get(cat, 0), n)
        if lang != "en" or _CJK.search(text or ""):
            t = _norm(text)
            if not t and not hits:
                return None
            for _, w, cat in self._flat:
                if w and w in t:
                    hits[cat] = max(hits.get(cat, 0), len(w))
        if not hits:
            return None
        best = max(hits, key=lambda c: (hits[c], -PRIORITY.index(c) if c in PRIORITY else -99))
        cheat = self.cheats.get(best, {})
        en = cheat.get("en") or {}
        zh_text = cheat.get("deflection_zh") or DEFAULT_DEFLECTION
        en_text = en.get("deflection") or DEFAULT_DEFLECTION_EN
        return {"category": best,
                "category_zh": cheat.get("category_zh") or self.zh.get(best, best),
                "deflection_zh": zh_text, "deflection_en": en_text,
                "deflection": en_text if lang == "en" else zh_text,
                "urgent": bool(cheat.get("urgent", best in self.urgent or best == "self_harm"))}

    def cheat(self, category):
        return self.cheats.get(category)
