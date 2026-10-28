"""Child-friendly wording rules (product pass 1, section A).

* BANNED / REPLACEMENTS: science jargon is rewritten into plain phrases (`plainify`) and then re-checked.
* common_chars.txt: a bundled list of everyday characters. A sentence may contain at most MAX_RARE characters
  that are not in the list (`rare_chars`). Build it with `python scripts/build_common_chars.py`.
* Hard limits for spoken text: <= 18 characters per sentence, <= 2 sentences, <= 60 characters in total
  (first sentence + reaction + explanation; the ask-back is a separate question limited to 30 characters).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "common_chars.txt"

MAX_SENT_CHARS = 18
MAX_SENTENCES = 2
MAX_TOTAL_CHARS = 60
MAX_RARE = 2
ASKBACK_MAX = 30

# Order matters: longer / more specific phrases first.
REPLACEMENTS = [
    ("變成能量，讓我們有力氣", "變成力氣"),
    ("二氧化碳氣體", "會冒泡的氣"), ("二氧化碳", "會冒泡的氣"), ("是反射太陽的光", "是把太陽的光彈回來"), ("反射回去", "彈回去"),
    ("反射出來", "彈出來"), ("反射光線", "把光彈開"), ("反射", "彈回來"), ("折射", "拐彎"),
    ("光譜", "彩色的光"), ("蛋白質", "一種營養"), ("氧化", "變質"), ("細胞", "小小的小格子"),
    ("水分子", "水"), ("分子", "很小的小東西"), ("原子", "很小的小東西"), ("電磁", "磁鐵的力量"), ("磁場", "磁鐵的力量"),
    ("密度", "有多擠"), ("氣壓", "空氣的力量"), ("壓力", "擠的力氣"), ("蒸發", "變成水氣飛走"),
    ("凝結", "聚在一起"), ("波長", "長短"), ("能量", "力氣"), ("小病毒", "很小很小的小蟲蟲"),
    ("病毒", "很小很小的小蟲蟲"), ("細菌", "很小很小的小蟲蟲"), ("神經", "感覺的線"),
    ("器官", "身體的小幫手"), ("酸鹼", "酸酸的和滑滑的"),
]
BANNED = [a for a, _ in REPLACEMENTS if a not in ("二氧化碳氣體", "二氧化碳", "是反射太陽的光", "反射回去", "反射出來", "反射光線", "小病毒", "變成能量，讓我們有力氣")]

_SPLIT = re.compile(r"[^。！？!?；;\n]+")
_PUNCT = re.compile(r"[\s，。！？、；：,.!?;:「」『』（）()…~～\-—0-9A-Za-z]+")
# Things the voice must never say: device feelings, flattery of the child.
NOT_ALLOWED = re.compile(r"我覺得|我喜歡|我愛|我好開心|我很開心|我也想|你好聰明|你真聰明|你很聰明|你好棒|你真棒|你好厲害|你真厲害")
REACTIONS = ["好問題！", "哇，你有注意到耶！"]


def plainify(text: str) -> str:
    for a, b in REPLACEMENTS:
        text = text.replace(a, b)
    return text


def sentences(text: str) -> list:
    return [s.strip() for s in _SPLIT.findall(text or "") if s.strip()]


def chars_of(s: str) -> int:
    """Characters that are spoken (punctuation and spaces do not count)."""
    return len(_PUNCT.sub("", s))


@lru_cache(maxsize=1)
def common_chars() -> frozenset:
    try:
        return frozenset(DATA.read_text(encoding="utf-8").replace("\n", "").replace(" ", ""))
    except OSError:
        return frozenset()


def rare_chars(sentence: str) -> list:
    cc = common_chars()
    if not cc:
        return []
    return [c for c in _PUNCT.sub("", sentence) if c not in cc]


def has_banned(text: str) -> bool:
    return any(b in text for b in BANNED)


def check_text(text: str, max_sentences: int = MAX_SENTENCES) -> list:
    """Return a list of problems (empty = fine) for a spoken explanation."""
    probs = []
    ss = sentences(text)
    if not ss:
        return ["empty"]
    if len(ss) > max_sentences:
        probs.append("too many sentences")
    for s in ss:
        if chars_of(s) > MAX_SENT_CHARS:
            probs.append(f"sentence too long: {s}")
        if len(rare_chars(s)) > MAX_RARE:
            probs.append(f"rare characters: {s}")
    if has_banned(text):
        probs.append("banned term")
    if NOT_ALLOWED.search(text):
        probs.append("feelings/flattery")
    return probs


def ask_ok_pattern(q: str) -> bool:
    """An ask-back must be guessable: yes/no, either-or, or an explicit invitation to guess."""
    return bool(re.search(r"嗎|還是|猜|你覺得", q))


def guessable(q: str) -> str:
    """Make a question guessable by pattern (prefix an invitation to guess if needed)."""
    return q if ask_ok_pattern(q) else "猜猜看，" + q


# =====================================================================================================
# English rule set (english-mode.md section 2)
#
# * every spoken sentence <= 12 words, explanation <= 2 sentences (1 for age <= 6), spoken total <= 45 words
#   (first sentence + reaction + explanation; the ask-back is a separate question of <= 16 words)
# * PLAIN_EN: about 15 science terms -> child phrases (`plainify_en`); the terms are banned after rewriting
# * "common words" are NOT listed by hand: the set is built at startup from every word in the `en` fields of
#   knowledge/entries/**/*.json plus the words of the plain phrases. At most MAX_RARE_EN points of uncommon words
#   are allowed per sentence, and an uncommon word longer than LONG_WORD letters counts double.
# =====================================================================================================
KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge" / "entries"

MAX_SENT_WORDS = 12
MAX_SENTENCES_EN = 2
MAX_TOTAL_WORDS = 45
ASKBACK_MAX_WORDS = 16
MAX_RARE_EN = 2
LONG_WORD = 9
REACTIONS_EN = ["Good question!", "Oh, you noticed!"]

_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)*")
_SPLIT_EN = re.compile(r"(?<=[.!?])\s+|\n+")


def _stem(w: str) -> str:
    from .recall import stem_en
    return stem_en(w)


def _base(tok: str) -> str:
    t = tok.lower().replace("’", "'")
    return t[:-2] if t.endswith("'s") else t


def words_en(s: str) -> list:
    """Spoken words of an English text (numbers count, punctuation does not)."""
    return _WORD.findall(s or "")


def sentences_en(text: str) -> list:
    return [s.strip() for s in _SPLIT_EN.split(text or "") if s.strip() and words_en(s)]


# (term stem, plain phrase, kind). kind "v": the phrase starts with a verb that is inflected like the term;
# "n": fixed phrase for the noun; "c": countable noun phrase (plural gets an -s).
PLAIN_EN = [
    ("reflect", "bounce back", "v"), ("evaporat", "turn into water in the air", "v"),
    ("condens", "turn into little drops", "v"), ("vibrat", "wiggle very fast", "v"),
    ("absorb", "soak up", "v"), ("reflection", "bounce back", "n"), ("vibration", "very fast wiggle", "c"),
    ("bacteria", "tiny tiny bugs", "n"), ("bacterium", "tiny tiny bug", "n"), ("molecule", "tiny bit", "c"),
    ("atom", "tiny bit", "c"), ("gravity", "the pull of the Earth", "n"), ("oxygen", "the air we breathe", "n"),
    ("reflex", "something that happens by itself", "n"), ("nutrient", "good stuff in food", "n"),
    ("carbon dioxide", "the gas that makes bubbles", "n"), ("photosynthesis", "how plants make food from sunlight", "n"),
    ("organism", "living thing", "c"), ("predator", "hunter animal", "c"),
]


def _inflect(first: str, suffix: str) -> str:
    if suffix in ("s", "es"):
        return first + ("es" if first.endswith(("ch", "sh", "ss", "x")) else "s")
    if suffix in ("ed", "d"):
        return first + ("d" if first.endswith("e") else "ed")
    if suffix == "ing":
        return (first[:-1] if first.endswith("e") else first) + "ing"
    return first


def _case(m, text: str) -> str:
    return text[:1].upper() + text[1:] if m.group(0)[:1].isupper() else text


def _build_plain():
    rules = []
    for stem, phrase, kind in sorted(PLAIN_EN, key=lambda r: -len(r[0])):
        if kind == "v":
            rx = re.compile(r"\b" + stem + r"(e|es|ed|d|ing|s)?\b", re.I)
            first, _, rest = phrase.partition(" ")

            def sub(m, first=first, rest=rest):
                suf = m.group(1) or ""
                base = first if suf in ("", "e") else _inflect(first, suf)
                return _case(m, base + (" " + rest if rest else ""))
        else:
            rx = re.compile(r"\b" + stem + r"(s|es)?\b", re.I)

            def sub(m, phrase=phrase, kind=kind):
                return _case(m, phrase + ("s" if kind == "c" and m.group(1) else ""))
        rules.append((rx, sub))
    return rules


_PLAIN_RULES = _build_plain()
_BANNED_EN = re.compile(r"\b(?:" + "|".join(
    s + (r"(?:e|es|ed|d|ing|s)?" if k == "v" else r"(?:s|es)?") for s, _, k in PLAIN_EN) + r")\b", re.I)


def plainify_en(text: str) -> str:
    for rx, sub in _PLAIN_RULES:
        text = rx.sub(sub, text)
    return text


def has_banned_en(text: str) -> bool:
    return bool(_BANNED_EN.search(text or ""))


@lru_cache(maxsize=1)
def common_words_en() -> frozenset:
    """Programmatic 'common words': all words of the `en` fields of every entry + the plain phrases (stemmed)."""
    out = set()

    def add(s):
        for t in words_en(s):
            b = _base(t)
            out.add(b)
            out.add(_stem(b))

    def walk(o):
        if isinstance(o, str):
            add(o)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for x in o.values():
                walk(x)

    for f in KNOWLEDGE.glob("**/*.json"):
        try:
            walk(json.loads(f.read_text(encoding="utf-8")).get("en") or {})
        except Exception:
            continue
    for _, phrase, _ in PLAIN_EN:
        add(phrase)
    for r in REACTIONS_EN:
        add(r)
    return frozenset(out)


def rare_words_en(sentence: str) -> list:
    cw = common_words_en()
    if not cw:
        return []
    return [t for t in words_en(sentence) if not t.isdigit() and _base(t) not in cw and _stem(_base(t)) not in cw]


def rare_score_en(sentence: str) -> int:
    """Uncommon words in the sentence; one longer than LONG_WORD letters counts double."""
    return sum(2 if len(_base(t)) > LONG_WORD else 1 for t in rare_words_en(sentence))


NOT_ALLOWED_EN = re.compile(
    r"\bI (?:think|feel|like|love|am so|am very|am happy)\b|\bI'm (?:so |very )?(?:happy|glad|excited)\b|"
    r"\byou(?:'re| are) (?:so |very |really )?(?:smart|clever|great|good|amazing|brilliant)\b|"
    r"\b(?:good|great|nice) job\b|\bwell done\b", re.I)
ASKBACK_BLOCK_EN = re.compile(
    r"\b(?:today|yesterday|mom|mum|mommy|dad|daddy|parents?|friends?|school|teacher|classmates?)\b|"
    r"\byou(?: ever)? feel\b|\bare you (?:happy|sad|angry|scared|afraid)\b|\byour family\b|\bdo you (?:like|love)\b", re.I)
ASK_PATTERN_EN = re.compile(r"\b(?:do you think|or|guess|can you|is it|does)\b", re.I)


def askback_ok_en(q: str) -> bool:
    """False if an ask-back touches the child's day, feelings, family or friends."""
    return not ASKBACK_BLOCK_EN.search(q or "")


def ask_ok_pattern_en(q: str) -> bool:
    """A guessable ask-back: a question with 'do you think', 'or', 'guess', 'can you', 'is it' or 'does'."""
    return "?" in (q or "") and bool(ASK_PATTERN_EN.search(q))


def guessable_en(q: str) -> str:
    """Make a question guessable by pattern (yes/no bridge questions get a short lead-in)."""
    q = q.strip()
    return q if ask_ok_pattern_en(q) else "Can you tell me, " + q[:1].lower() + q[1:]


def check_text_en(text: str, max_sentences: int = MAX_SENTENCES_EN) -> list:
    """Problems (empty = fine) for a spoken English explanation."""
    probs = []
    ss = sentences_en(text)
    if not ss:
        return ["empty"]
    if len(ss) > max_sentences:
        probs.append("too many sentences")
    for s in ss:
        if len(words_en(s)) > MAX_SENT_WORDS:
            probs.append(f"sentence too long: {s}")
        if rare_score_en(s) > MAX_RARE_EN:
            probs.append(f"uncommon words: {s}")
    if has_banned_en(text):
        probs.append("banned term")
    if NOT_ALLOWED_EN.search(text):
        probs.append("feelings/flattery")
    return probs


def spoken_words(*texts) -> int:
    return sum(len(words_en(t)) for t in texts)
