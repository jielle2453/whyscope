"""Child-friendly wording rules (product pass 1, section A).

* BANNED / REPLACEMENTS: science jargon is rewritten into plain phrases (`plainify`) and then re-checked.
* common_chars.txt: a bundled list of everyday characters. A sentence may contain at most MAX_RARE characters
  that are not in the list (`rare_chars`). Build it with `python scripts/build_common_chars.py`.
* Hard limits for spoken text: <= 18 characters per sentence, <= 2 sentences, <= 60 characters in total
  (first sentence + reaction + explanation; the ask-back is a separate question limited to 30 characters).
"""
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
