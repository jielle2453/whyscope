"""Assemble askback_fixes.jsonl and wording_fixes.jsonl from the reviewed work files and verify them with the hub's own functions."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from hub import wording, bank as bankm
import check_askbacks as ca

rd = lambda p: [json.loads(l) for l in (HERE / p).read_text(encoding="utf-8").splitlines() if l.strip()]
bank = ca.bank
targets = {r["id"]: r for r in rd("work/askback_targets.jsonl")}
ab = []
for n in range(1, 5):
    for r in rd(f"work/ab_final_{n}.jsonl"):
        ab.append({"id": r["id"], "old": targets[r["id"]]["old"], "new": r["new"].strip()})
assert sorted(r["id"] for r in ab) == sorted(targets), "id mismatch"
hard = 0
for r in ab:
    it = bank[r["id"]]
    assert it["ask_back"].strip() == r["old"] and not bankm.sensitive_category(it)
    assert wording.askback_ok_en(r["new"]), r
    h, _ = ca.check(it, r["new"]); hard += bool(h)
    if h: print("HARD", r["id"], h, r["new"])
wd = []
for r in rd("work/wording_review.jsonl"):
    it = bank[r["id"]]; old = it[r["field"]]
    word = next(t["word"] for t in rd("work/wording_targets.jsonl") if t["id"] == r["id"] and t["field"] == r["field"])
    new = r["final"].strip()
    assert not wording.has_banned_en(new), r
    if r["field"] == "a1":
        assert len(wording.words_en(new)) <= len(wording.words_en(old)) and len(new) <= len(old), r
    if r["field"] == "ask_back":
        assert wording.askback_ok_en(new), r
    wd.append({"id": r["id"], "field": r["field"], "old": old, "new": new, "word": word})
assert len({(r["id"], r["field"]) for r in wd}) == len(wd)
for name, rows in (("askback_fixes.jsonl", ab), ("wording_fixes.jsonl", wd)):
    (HERE / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
# after both fixes, no item may still contain a banned word or a dropped ask_back
fixed = {r["id"]: dict(bank[r["id"]]) for r in ab + wd}
for r in ab: fixed[r["id"]]["ask_back"] = r["new"]
for r in wd: fixed[r["id"]][r["field"]] = r["new"]
left_ban = [i for i, it in bank.items() if any(wording.has_banned_en((fixed.get(i) or it).get(f) or "") for f in ("a1", "a2", "ask_back"))]
left_ab = [i for i, it in bank.items() if (fixed.get(i) or it).get("ask_back") and not bankm.sensitive_category(it)
           and not wording.askback_ok_en((fixed.get(i) or it)["ask_back"])]
print(f"askback_fixes {len(ab)} (checker hard-fail {hard}); wording_fixes {len(wd)} rows / {len({r['id'] for r in wd})} items")
print("after merge: items with banned words", left_ban, "; non-sensitive ask_backs failing askback_ok_en", left_ab)
