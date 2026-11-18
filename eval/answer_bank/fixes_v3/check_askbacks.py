"""Check proposed ask_backs with the hub's own functions.
usage: python check_askbacks.py FILE.jsonl   (rows with "id" and "new")
HARD (must pass): wording.askback_ok_en; not wording.has_banned_en; exactly one sentence ending in a single "?";
  <= 14 words (wording.words_en); not wording.NOT_ALLOWED_EN; not guard.BLOCK_EN; not compose.BAD_ASKBACK_EN ("your");
  not compose.repeats_en(new, a1); rare_score_en(new, allow=words of q/a1/a2) <= wording.MAX_RARE_EN.
WARN: likely yes/no-only opening (Do/Does/Is/Are/Did/Have/Has/Will/Would/Was/Were with no " or ").
Prints problems per id and a summary; exit code 1 if any HARD failure."""
import json, re, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from hub import wording, guard, compose

bank = {}
for l in (ROOT / "knowledge/answer_bank_en.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        it = json.loads(l); bank[it["id"]] = it
YESNO = re.compile(r"^(?:do|does|is|are|did|have|has|will|would|was|were)\b", re.I)

def allow_of(it):
    s = set()
    for t in wording.words_en(" ".join([it["q"], it["a1"], it.get("a2", "")])):
        b = wording._base(t); s.add(b); s.add(wording._stem(b))
    return frozenset(s)

def check(it, new):
    hard, warn = [], []
    if not wording.askback_ok_en(new): hard.append("askback_ok_en: " + wording.ASKBACK_BLOCK_EN.search(new).group(0))
    if wording.has_banned_en(new): hard.append("banned term")
    if not new.endswith("?") or new.count("?") != 1 or len(wording.sentences_en(new)) != 1: hard.append("not one question")
    n = len(wording.words_en(new))
    if n > 14: hard.append(f"{n} words")
    if wording.NOT_ALLOWED_EN.search(new): hard.append("feelings/flattery")
    m = guard.BLOCK_EN.search(new)
    if m: hard.append("guard block: " + m.group(0))
    if compose.BAD_ASKBACK_EN.search(new): hard.append("'your'")
    if compose.repeats_en(new, it["a1"]): hard.append("repeats a1")
    rs = wording.rare_words_en(new, allow_of(it))
    if wording.rare_score_en(new, allow_of(it)) > wording.MAX_RARE_EN: hard.append(f"uncommon words {rs}")
    elif rs: warn.append(f"uncommon {rs}")
    if YESNO.search(new) and " or " not in new: warn.append("yes/no?")
    return hard, warn

if __name__ == "__main__":
    rows = [json.loads(l) for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = 0; opens = Counter()
    for r in rows:
        new = r["new"].strip(); opens[" ".join(new.split()[:2])] += 1
        h, w = check(bank[r["id"]], new)
        bad += bool(h)
        if h or w: print(r["id"], "HARD" if h else "warn", h + w, "|", new)
    print(f"rows {len(rows)} hard-fail {bad}")
    print("openings:", opens.most_common(12))
    sys.exit(1 if bad else 0)
