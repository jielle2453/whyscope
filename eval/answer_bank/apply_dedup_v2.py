"""Apply the same/different verdicts: drop new items that duplicate an old item, drop the non-kept item of a same new-new
pair (never both), remove the listed colliding variants. Writes parts_v2/new_dedup.jsonl and parts_v2/dedup_log.json."""
import json, glob
from pathlib import Path
HERE = Path(__file__).resolve().parent
new, order = {}, []
for f in sorted(glob.glob(str(HERE / "parts_v2" / "w[0-9][0-9]_*.jsonl"))):
    for l in open(f, encoding="utf-8-sig"):
        if l.strip():
            d = json.loads(l); new[d["id"]] = d; order.append(d["id"])
V = []
for n in (1, 2, 3):
    V += [json.loads(l) for l in open(HERE / "parts_v2" / f"dedup_verdict_{n}.jsonl", encoding="utf-8") if l.strip()]
drop_old, drop_new, keep_new = {}, {}, set()
badv = {}
for v in V:
    a, b = v["A"], v["B"]
    if v["verdict"] == "same":
        if b not in new:
            drop_old[a] = b
        else:
            k, x = (a, b) if v["keep"] == "A" else (b, a)
            drop_new[x] = k; keep_new.add(k)
    else:
        for side, iid in (("bad_variants_A", a), ("bad_variants_B", b)):
            if iid in new and v.get(side):
                badv.setdefault(iid, set()).update(v[side])
# never drop both sides of a same new-new pair: if the kept item is itself dropped as a new-new duplicate, keep chains resolve
# to the first item that survives; if the kept item duplicates an OLD item, the old item answers both, so dropping is fine.
changed = True
while changed:
    changed = False
    for x, k in list(drop_new.items()):
        if k in drop_new and drop_new[k] == x:      # mutual: keep x
            del drop_new[x]; changed = True
dropped = set(drop_old) | set(drop_new)
short = []
out = []
for iid in order:
    if iid in dropped: continue
    d = dict(new[iid])
    if iid in badv:
        vs = [x for x in d["variants"] if x not in badv[iid]]
        d["variants"] = vs
        if len(vs) < 3: short.append(iid)
    out.append(d)
with open(HERE / "parts_v2" / "new_dedup.jsonl", "w", encoding="utf-8") as f:
    for d in out: f.write(json.dumps(d, ensure_ascii=False) + "\n")
json.dump({"dropped_dup_of_old": drop_old, "dropped_dup_of_new": drop_new, "variants_removed": {k: sorted(v) for k, v in badv.items()},
           "items_left_with_lt3_variants": short}, open(HERE / "parts_v2" / "dedup_log.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("new", len(new), "kept", len(out), "dropped vs old", len(drop_old), "dropped vs new", len(drop_new),
      "items with variants removed", len(badv), "variants removed", sum(len(v) for v in badv.values()), "left <3 variants", len(short))
