"""Check knowledge/quiz.json against the entries and the wording rules. No server needed.

    python eval/check_quiz.py          # prints problems; exit code 1 if there are any

Checks per entry and language: a key exists, indices are valid, the reveal (fact or sentence) follows the child-voice
rules, both options are mentioned in the question back when it is an "A or B" question, and the voice matcher maps
each option's own text (and "I don't know") back to the right choice.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hub import quiz, wording  # noqa: E402

problems, n = [], 0
for p in sorted((ROOT / "knowledge" / "entries").glob("*/*.json")):
    e = json.loads(p.read_text(encoding="utf-8"))
    for lang in ("zh", "en"):
        n += 1
        k = quiz.key(e["id"], lang)
        where = f"{e['id']} [{lang}]"
        if not k:
            problems.append(f"{where}: no key")
            continue
        opts, ans, fact = k["options"], k.get("answer"), k.get("fact")
        facts = (e["en"]["facts"] if lang == "en" else e["facts"])
        ask = e["en"]["ask_back"] if lang == "en" else e["ask_back"]
        if len(opts) != 2 or not all(o.strip() for o in opts):
            problems.append(f"{where}: needs two options")
        if not (ans is None or ans == "both" or ans in (0, 1)):
            problems.append(f"{where}: bad answer {ans!r}")
        if fact is not None and not 0 <= fact < len(facts):
            problems.append(f"{where}: bad fact index {fact}")
        if fact is None and not k.get("reveal"):
            problems.append(f"{where}: neither fact nor reveal")
        r = quiz.judge(e, lang, choice=-1)
        reveal = quiz._reveal(e, k, lang)
        probs = (wording.check_text_en(reveal, 2, wording.entry_allow_en(e)) if lang == "en"
                 else wording.check_text(reveal, 2, wording.entry_allow_zh(e)))   # the entry's own label words are not "uncommon"
        if probs:
            problems.append(f"{where}: reveal breaks a wording rule {probs}: {reveal}")
        if lang == "zh" and "還是" in ask:
            for o in opts:
                if o.replace("比較", "").replace("的", "")[:1] not in ask:
                    problems.append(f"{where}: option '{o}' is not in the question '{ask}' (check it)")
        if lang == "en" and ", or " in ask and not ask.rstrip("?").endswith("or not"):
            for o in opts:
                w = [x for x in re.findall(r"[a-z]+", o.lower()) if x not in ("a", "an", "the", "in", "on", "at")]
                if not any(x in ask.lower() for x in w):
                    problems.append(f"{where}: option '{o}' is not in the question '{ask}' (check it)")
        for i, o in enumerate(opts):
            got = quiz.match(o, opts, lang)
            if got != i:
                problems.append(f"{where}: saying '{o}' matched {got}, expected {i}")
        if quiz.match(quiz.IDK[lang], opts, lang) != -1:
            problems.append(f"{where}: 'I don't know' not recognised")
        if not r or not r["say"]:
            problems.append(f"{where}: empty reply")

extra = [("animals-spider", "zh", "八隻腳", 1), ("animals-spider", "zh", "8隻", 1), ("animals-spider", "zh", "8 支", 1), ("animals-spider", "zh", "應該是六隻吧", 0),
         ("machines-balloon", "zh", "不會", 1), ("machines-balloon", "zh", "會啊", 0), ("machines-balloon", "zh", "可以", 0),
         ("machines-remote", "zh", "看不到", 1), ("animals-whale", "en", "no it can't", 1),
         ("food-onion-tears", "en", "under the ground", 1), ("food-onion-tears", "zh", "我不知道", -1),
         ("sky_weather-thunder-lightning", "en", "before", 0)]
for eid, lang, said, want in extra:
    k = quiz.key(eid, lang)
    got = quiz.match(said, k["options"], lang)
    if got != want:
        problems.append(f"{eid} [{lang}]: '{said}' matched {got}, expected {want}")

print(f"{n} keys checked, {len(extra)} spoken replies checked, {len(problems)} problems")
for x in problems:
    print(" -", x)
sys.exit(1 if problems else 0)
