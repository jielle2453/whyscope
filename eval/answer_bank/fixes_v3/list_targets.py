"""List bank items needing fixes, using the hub's own checks (no reimplementation).
1. ask_back: non-sensitive (bank.sensitive_category(item) is None) and ask_back non-empty and not wording.askback_ok_en(ask_back)
   -- exactly the drop condition in hub/pipeline.py _bank_answer.
2. banned words: wording.has_banned_en(field) on a1 / a2 / ask_back (regex _BANNED_EN built from wording.PLAIN_EN),
   the same check compose/guard/check_text_en use. All items, sensitive included.
Writes work/askback_targets.jsonl and work/wording_targets.jsonl."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from hub import wording, bank as bankm

items = [json.loads(l) for l in (ROOT / "knowledge/answer_bank_en.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
out = Path(__file__).parent / "work"
ab, wd = [], []
for it in items:
    ask = (it.get("ask_back") or "").strip()
    if ask and not bankm.sensitive_category(it) and not wording.askback_ok_en(ask):
        ab.append({"id": it["id"], "topic": it.get("topic"), "q": it["q"], "a1": it["a1"], "a2": it.get("a2", ""),
                   "old": ask, "hit": wording.ASKBACK_BLOCK_EN.search(ask).group(0)})
    for f in ("a1", "a2", "ask_back"):
        t = it.get(f) or ""
        for m in wording._BANNED_EN.finditer(t):
            wd.append({"id": it["id"], "field": f, "word": m.group(0), "text": t, "q": it["q"], "a1": it["a1"],
                       "a2": it.get("a2", ""), "sensitive": bankm.sensitive_category(it)})
print("items", len(items), "sensitive", sum(1 for i in items if bankm.sensitive_category(i)))
print("askback targets", len(ab))
print("banned-word hits", len(wd), "items", len({w["id"] for w in wd}))
for name, rows in (("askback_targets.jsonl", ab), ("wording_targets.jsonl", wd)):
    (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
from collections import Counter
print(Counter(r["hit"].lower() for r in ab).most_common())
