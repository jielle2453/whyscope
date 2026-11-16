"""Build bank_en_v2.jsonl = the 1,182 frozen round-1 items (unchanged) + the new items after dedup and the 3-checker merge.
New items keep the round-1 fields (id, topic, q, variants, a1, a2, ask_back, confidence, notes, check).
Also writes parts_v2/new_final.jsonl, parts_v2/minority_fixes.jsonl (one checker said fix, two said ok: kept as written,
listed for human review) and FROZEN_v2."""
import json, datetime
from pathlib import Path
HERE = Path(__file__).resolve().parent
P = HERE / "parts_v2"
old = [json.loads(l) for l in open(HERE / "bank_en.jsonl", encoding="utf-8")]
new = [json.loads(l) for l in open(P / "new_dedup.jsonl", encoding="utf-8")]
dec = json.load(open(P / "check_merge.json", encoding="utf-8"))
rec = {d["id"]: d for d in map(json.loads, open(P / "reconcile_out.jsonl", encoding="utf-8"))}
C = {L: {d["id"]: d for d in map(json.loads, open(P / f"check_{L}.jsonl", encoding="utf-8"))} for L in "ABC"}
FIELDS = ["id", "topic", "q", "variants", "a1", "a2", "ask_back", "confidence", "notes", "check"]
out, dropped, minority = [], [], []
for d in new:
    x = dec[d["id"]]
    if x["decision"] == "drop" or (x["decision"] == "fix" and rec[d["id"]].get("drop")):
        dropped.append(d["id"]); continue
    d = dict(d)
    if x["decision"] == "fix":
        r = rec[d["id"]]
        for k in ("a1", "a2", "ask_back"): d[k] = r[k]
    d["variants"] = [v for v in d["variants"] if v not in x["bad_variants"]]
    d["check"] = x["check"]
    out.append({k: d.get(k, "") for k in FIELDS})
    if x["minority_fix"]:
        L = next(L for L in "ABC" if C[L][d["id"]]["verdict"] == "fix")
        minority.append({"id": d["id"], "q": d["q"], "a1": d["a1"], "a2": d["a2"], "ask_back": d["ask_back"],
                         "checker": L, "why": C[L][d["id"]].get("why", ""),
                         "suggested": {k: C[L][d["id"]][k] for k in ("a1", "a2", "ask_back") if k in C[L][d["id"]]}})
with open(P / "new_final.jsonl", "w", encoding="utf-8") as f:
    for d in out: f.write(json.dumps(d, ensure_ascii=False) + "\n")
with open(P / "minority_fixes.jsonl", "w", encoding="utf-8") as f:
    for d in minority: f.write(json.dumps(d, ensure_ascii=False) + "\n")
with open(HERE / "bank_en_v2.jsonl", "w", encoding="utf-8") as f:
    for d in old + out: f.write(json.dumps(d, ensure_ascii=False) + "\n")
n = len(old) + len(out)
(HERE / "FROZEN_v2").write_text(f"FROZEN {datetime.datetime.now().isoformat()} items={n} (old 1182 + new {len(out)})\n", encoding="utf-8")
ids = [d["id"] for d in old + out]
assert len(ids) == len(set(ids))
print("new kept", len(out), "dropped", len(dropped), "bank_en_v2", n, "minority fixes listed", len(minority),
      "variants <3:", sum(len(d["variants"]) < 3 for d in out))
