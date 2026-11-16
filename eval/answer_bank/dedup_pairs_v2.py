"""Build the list of flagged pairs (best cosine >= 0.90) for the same/different judgment.
Writes parts_v2/dedup_review_N.jsonl chunks: {"pair", "score", "A": new item, "B": other item (old or new)}."""
import json, glob, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
T = 0.90
old = {d["id"]: d for d in map(json.loads, open(HERE / "bank_en.jsonl", encoding="utf-8"))}
new = {}
for f in sorted(glob.glob(str(HERE / "parts_v2" / "w[0-9][0-9]_*.jsonl"))):
    for l in open(f, encoding="utf-8-sig"):
        if l.strip():
            d = json.loads(l); new[d["id"]] = d
pairs = json.load(open(HERE / "parts_v2" / "dedup_pairs.json", encoding="utf-8"))
seen, out = set(), []
for p in pairs:
    if p["score"] < T: continue
    k = tuple(sorted((p["id"], p["best"])))
    if k in seen: continue
    seen.add(k)
    B = old.get(p["best"]) or new[p["best"]]
    sl = lambda d: {x: d[x] for x in ("id", "q", "variants", "a1")}
    out.append({"pair": len(out) + 1, "score": p["score"], "B_is_old": p["best"] in old, "A": sl(new[p["id"]]), "B": sl(B)})
print("pairs", len(out), "vs old", sum(o["B_is_old"] for o in out))
n = (len(out) + 2) // 3
for c in range(3):
    with open(HERE / "parts_v2" / f"dedup_review_{c+1}.jsonl", "w", encoding="utf-8") as f:
        for o in out[c * n:(c + 1) * n]:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
