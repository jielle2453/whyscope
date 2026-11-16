"""Validate knowledge/principles/principles.json (the human-reviewed principle library).

Checks (every failure is a "problem", the exit code is 1 if there is at least one):
  * schema: required fields, types, list sizes, unique ids, no duplicate items
  * every answers_en / answers_zh entry passes hub/wording.py (check_text_en / check_text) as it will be spoken:
    sentence length, sentence count, uncommon words/characters, banned science terms, feelings/flattery
  * the {object} slot: every answer that has one is rendered with EVERY applies_to item of its language and must
    still pass the same checks (so long or uncommon item names cannot break the voice rules)
  * at least one answer without a slot per language (the fallback when the child's object is not in applies_to)
Warnings (do not fail): fact sentences that are long, or that contain terms the voice rules would rewrite.

Usage:  python scripts/check_principles.py [path/to/principles.json]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hub import wording as W  # noqa: E402

DEFAULT = ROOT / "knowledge" / "principles" / "principles.json"
SLOT = "{object}"
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# field -> (type, min, max) for list fields (None = no limit)
LISTS = {
    "applies_to_en": (8, 20), "applies_to_zh": (8, 20),
    "question_examples_en": (5, 8), "question_examples_zh": (3, 5),
    "facts_en": (2, 4), "facts_zh": (2, 4),
    "answers_en": (2, 3), "answers_zh": (1, 2),
}


def render(answer: str, item: str, lang: str) -> str:
    return answer.replace(SLOT, item)


def check_answer(answer: str, lang: str):
    """Problems for one fully rendered answer."""
    probs = []
    if lang == "en":
        probs += W.check_text_en(answer)
        n = W.spoken_words(answer)
        if n > W.MAX_TOTAL_WORDS:
            probs.append(f"{n} words (max {W.MAX_TOTAL_WORDS})")
    else:
        probs += W.check_text(answer)
        if W.chars_of(answer) > W.MAX_TOTAL_CHARS:
            probs.append("too many characters")
    return probs


def main(path: Path) -> int:
    problems, warnings = [], []

    def bad(pid, msg):
        problems.append(f"[{pid}] {msg}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"cannot read {path}: {e}")
        return 1

    if not isinstance(data, dict) or not isinstance(data.get("principles"), list):
        print("top level must be an object with a 'principles' list")
        return 1
    for k in ("reviewed_by", "note"):
        if not isinstance(data.get(k), str):
            problems.append(f"[top] '{k}' must be a string")

    seen = set()
    n_ren = 0
    for p in data["principles"]:
        pid = p.get("id", "?") if isinstance(p, dict) else "?"
        if not isinstance(p, dict):
            bad(pid, "principle is not an object")
            continue
        if not isinstance(pid, str) or not ID_RE.match(pid):
            bad(pid, "id must be lower_snake_case")
        if pid in seen:
            bad(pid, "duplicate id")
        seen.add(pid)
        for k in ("name_en", "name_zh"):
            if not isinstance(p.get(k), str) or not p[k].strip():
                bad(pid, f"{k} missing")
        if not isinstance(p.get("partial"), bool):
            bad(pid, "partial must be true or false")
        for k, (lo, hi) in LISTS.items():
            v = p.get(k)
            if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                bad(pid, f"{k} must be a list of non-empty strings")
                continue
            if not lo <= len(v) <= hi:
                bad(pid, f"{k} has {len(v)} entries (need {lo}-{hi})")
            if len({x.strip().lower() for x in v}) != len(v):
                bad(pid, f"{k} has duplicates")
        kw = p.get("keywords_en")   # optional matching field (hub/principles.py): words a question about this principle contains
        if kw is not None and (not isinstance(kw, list) or not kw or not all(isinstance(x, str) and x.strip() for x in kw)):
            bad(pid, "keywords_en must be a non-empty list of non-empty strings")
        extra = set(p) - {"id", "name_en", "name_zh", "partial", "keywords_en"} - set(LISTS)
        if extra:
            bad(pid, f"unknown fields {sorted(extra)}")

        # ---- answers, with and without the slot ----
        for lang in ("en", "zh"):
            answers = p.get(f"answers_{lang}")
            items = p.get(f"applies_to_{lang}")
            if not isinstance(answers, list) or not isinstance(items, list):
                continue
            if not any(SLOT not in a for a in answers):
                bad(pid, f"answers_{lang}: need at least one answer without {SLOT}")
            for i, a in enumerate(answers):
                if a.count(SLOT) > 1:
                    bad(pid, f"answers_{lang}[{i}]: more than one {SLOT}")
                if "{" in a.replace(SLOT, "") or "}" in a.replace(SLOT, ""):
                    bad(pid, f"answers_{lang}[{i}]: stray brace")
                if lang == "en" and re.search(r"\b(?:a|an)\s+\{object\}", a, re.I):
                    bad(pid, f"answers_{lang}[{i}]: do not put a/an before {SLOT} (items have no article): {a}")
                if lang == "en" and re.search(r"(?:^|[.!?]\s+)\{object\}", a):
                    bad(pid, f"answers_{lang}[{i}]: {SLOT} at the start of a sentence (use 'The {{object}}'): {a}")
                if SLOT not in a:
                    n_ren += 1
                    for m in check_answer(a, lang):
                        bad(pid, f"answers_{lang}[{i}] {m}: {a}")
                else:
                    for it in items:
                        n_ren += 1
                        r = render(a, it, lang)
                        for m in check_answer(r, lang):
                            bad(pid, f"answers_{lang}[{i}] with '{it}': {m}")
            for it in items:
                if SLOT in it or "{" in it:
                    bad(pid, f"applies_to_{lang} item has a brace: {it}")

        # ---- facts: warnings only ----
        for f in p.get("facts_en") or []:
            for s in W.sentences_en(f):
                if len(W.words_en(s)) > 18:
                    warnings.append(f"[{pid}] long fact sentence ({len(W.words_en(s))} words): {s}")
            if W.has_banned_en(f):
                warnings.append(f"[{pid}] fact uses a term the voice rules rewrite: {f}")
        for f in p.get("facts_zh") or []:
            if W.has_banned(f):
                warnings.append(f"[{pid}] zh fact uses a term the voice rules rewrite: {f}")

    print(f"{len(data['principles'])} principles, {n_ren} rendered answers checked, {len(warnings)} warnings")
    for w in warnings:
        print("warning:", w)
    for pr in problems:
        print("PROBLEM:", pr)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT))
