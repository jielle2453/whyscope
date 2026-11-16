"""The reply turn: the child answers the question back, Whyscope answers once more.

knowledge/quiz.json holds, per entry and language, two options the child can tap or say, the right one (an index,
"both", or null when there is no single right answer) and what reveals it: an entry fact (`fact`, which is then left out
of the explanation so the explanation does not give the answer away) or a short `reveal` sentence.

Everything here is deterministic: no LLM, so the reply is instant on any host and cannot invent knowledge.
Voice replies are matched to an option by text; anything unclear is treated like "I don't know" (the answer is told,
never "wrong").
"""
import json
import re

from . import wording
from .config import ROOT

IDK = {"zh": "我不知道", "en": "I don't know"}
IDK_WORDS = {"zh": ("不知道", "不曉得", "不清楚", "猜不到", "不會猜"),
             "en": ("don't know", "dont know", "do not know", "no idea", "not sure", "dunno")}
_KEYS = None


def keys() -> dict:
    global _KEYS
    if _KEYS is None:
        p = ROOT / "knowledge" / "quiz.json"
        try:
            _KEYS = {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if isinstance(v, dict)}
        except FileNotFoundError:
            _KEYS = {}
    return _KEYS


def key(entry_id: str, lang: str):
    """The answer key of an entry in a language, or None."""
    return (keys().get(entry_id) or {}).get("en" if lang == "en" else "zh")


def without_fact(entry: dict, lang: str, idx: int) -> dict:
    """Copy of the entry with fact `idx` (in `lang`) removed, as long as at least one fact remains."""
    if lang == "en":
        ev = dict(entry.get("en") or {})
        facts = list(ev.get("facts") or [])
        if 0 <= idx < len(facts) and len(facts) > 1:
            ev["facts"] = facts[:idx] + facts[idx + 1:]
        return {**entry, "en": ev}
    facts = list(entry.get("facts") or [])
    if 0 <= idx < len(facts) and len(facts) > 1:
        facts = facts[:idx] + facts[idx + 1:]
    return {**entry, "facts": facts}


def public(k: dict, lang: str):
    """What the kid page needs to show the choices (never the answer)."""
    if not k:
        return None
    return {"options": list(k["options"]), "idk": IDK["en" if lang == "en" else "zh"]}


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", " ", (s or "").lower()).strip()


_ZH_NUM = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九", "兩": "二",
           # measure words that Whisper writes for the spoken "zhī" (八隻 is often transcribed as "8 支")
           "支": "隻", "只": "隻", "枝": "隻"}
# a spoken reply that is really a new question: the kid page asks it as one
_QUESTION = re.compile(r"為什麼|為啥|怎麼|是什麼|什麼是|\b(why|what|how|where|who)\b", re.I)


def match(text: str, options: list, lang: str):
    """Index of the option the child said, -1 for "I don't know", None if it is unclear."""
    t = _norm(text)
    if not t:
        return None
    if lang != "en":
        t = "".join(_ZH_NUM.get(c, c) for c in t)
    if any(_norm(w) in t for w in IDK_WORDS["en" if lang == "en" else "zh"]):
        return -1
    hits = []
    for i, o in enumerate(options):
        o_n = _norm(o)
        if lang != "en":
            o_n = "".join(_ZH_NUM.get(c, c) for c in o_n)
            core = o_n.replace("的", "").replace(" ", "")
            if o_n.replace(" ", "") in t.replace(" ", "") or (len(core) >= 1 and core in t.replace(" ", "")):
                hits.append((len(core), i))
        else:
            words = [w for w in o_n.split() if w not in ("a", "an", "the", "in", "on", "at", "it", "to", "of")]
            if words and all(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words):
                hits.append((len(o_n), i))
            elif o_n in ("yes", "no") and re.search(r"\b" + o_n + r"\b", t):
                hits.append((1, i))
    if not hits:
        if lang != "en":   # yes/no style options said differently: 會 / 不會, 能 / 不能, 有 / 沒有
            neg = re.search(r"不|沒", t)
            for i, o in enumerate(options):
                if o in ("不會", "不能", "沒有", "看不到") and neg:
                    return i
            for i, o in enumerate(options):
                if o in ("會", "能", "有", "看得到") and not neg and re.search(r"會|能|有|可以|看得到|對|是", t):
                    return i
        return None
    hits.sort(reverse=True)   # longest option found wins ("不會" over "會", "In the sun" over "sun")
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return None
    return hits[0][1]


def _reveal(entry: dict, k: dict, lang: str) -> str:
    if k.get("fact") is not None:
        facts = (entry.get("en") or {}).get("facts", []) if lang == "en" else entry.get("facts", [])
        if 0 <= k["fact"] < len(facts):
            f = facts[k["fact"]].strip()
            if lang == "en":
                f = wording.plainify_en(f)
                return f if f.endswith((".", "!", "?")) else f + "."
            f = wording.plainify(f)
            return f if f.endswith(("。", "！", "？")) else f + "。"
    return (k.get("reveal") or "").strip()


def judge(entry: dict, lang: str, choice=None, text: str = "") -> dict:
    """The reply to the child's answer.

    choice: option index, or -1 for "I don't know"; text: what the child said or typed (used when choice is None).
    Returns {"result": right|wrong|both|open|idk|unknown|question, "choice": int|None, "say": str} or None without a
    key. "question": the child said a new question instead of an answer ("為什麼…", "why…"); say is empty and the
    client asks it as a new question."""
    en = lang == "en"
    k = key(entry["id"], lang)
    if not k:
        return None
    opts = k["options"]
    if choice is None:
        choice = match(text, opts, lang)
    if choice is not None and not (choice == -1 or 0 <= int(choice) < len(opts)):
        choice = None
    if choice is None and _QUESTION.search(text or ""):
        return {"result": "question", "choice": None, "say": ""}
    reveal = _reveal(entry, k, lang)
    ans = k.get("answer")
    if choice is None or choice == -1:
        result = "idk" if choice == -1 else "unknown"
        if isinstance(ans, int):
            lead = f'The answer is "{opts[ans]}".' if en else f"答案是「{opts[ans]}」。"
        elif ans == "both":
            lead = "Both are right!" if en else "兩個都對喔！"
        else:
            lead = ""
    elif ans == "both":
        result, lead = "both", ("Both are right!" if en else "兩個都對喔！")
    elif ans is None:
        result, lead = "open", ("There is more than one answer." if en else "這題的答案不只一個。")
    elif int(choice) == ans:
        result, lead = "right", ("Yes!" if en else "對！")
    else:
        result = "wrong"
        lead = f'Not quite. The answer is "{opts[ans]}".' if en else f"其實是「{opts[ans]}」喔。"
    say = " ".join(s for s in (lead, reveal) if s) if en else lead + reveal
    return {"result": result, "choice": None if choice is None else int(choice), "say": say}
