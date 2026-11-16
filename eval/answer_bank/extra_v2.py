"""Extra round-2 numbers: (1) near-verbatim overlap between test questions and bank rows (old vs new items),
(2) camera-label coverage before/after, (3) wording flags old vs new."""
import json, re, sys
import numpy as np
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from retrieve import norm  # noqa: E402
import voice_v2  # noqa: E402
qs = [q for q in json.load(open(HERE / "retrieval_top_v2.json", encoding="utf-8")) if q["set"] != "user"]
bank = [json.loads(l) for l in open(HERE / "bank_en_v2.jsonl", encoding="utf-8")]
isnew = {d["id"]: i >= 1182 for i, d in enumerate(bank)}
rows = {}
for d in bank:
    for t in [d["q"]] + d["variants"]:
        rows.setdefault(norm(t), set()).add(d["id"])
ex_old = ex_new = 0
for q in qs:
    hit = rows.get(norm(q["q"]), set())
    ex_old += any(not isnew[i] for i in hit); ex_new += any(isnew[i] for i in hit)
print(f"test questions identical (after normalising) to a bank q/variant: old items {ex_old}, new items {ex_new} of {len(qs)}")
for T in (0.95, 0.90):
    n_new = sum(1 for q in qs if q["top"]["v2full"][0][1] >= T and isnew[q["top"]["v2full"][0][0]])
    n_old = sum(1 for q in qs if q["top"]["old1182"][0][1] >= T)
    print(f"top-1 cosine >= {T}: old bank {n_old}; v2 with a NEW item at top-1 {n_new}")
# camera labels
labs = [l.strip() for l in open(HERE / "parts_v2" / "camera_labels_en.txt", encoding="utf-8") if l.strip()]
plan = json.load(open(HERE / "parts_v2" / "plan.json", encoding="utf-8"))
kept = {x["label"] for w in plan["writers"].values() for x in w["labels"]}
def texts(items): return [(" ".join([d["q"]] + d["variants"])).lower() for d in items]
To, Tn = texts(bank[:1182]), texts(bank)
def stem(w): return w[:-1] if w.endswith("s") and len(w) > 3 else w
def cnt(l, T):
    ws = [stem(w) for w in re.findall("[a-z]+", l)]
    rx = re.compile(r"\b" + r"\w*\s+".join(re.escape(w) for w in ws) + r"\w*\b")
    return sum(1 for t in T if rx.search(t))
co = [cnt(l, To) for l in sorted(kept)]; cn = [cnt(l, Tn) for l in sorted(kept)]
print(f"camera labels (kept after merges): {len(kept)}; with 0 items: old {sum(c==0 for c in co)} -> v2 {sum(c==0 for c in cn)}; "
      f"with >=2 items: old {sum(c>=2 for c in co)} -> v2 {sum(c>=2 for c in cn)}")
print("still 0:", [l for l, c in zip(sorted(kept), cn) if c == 0][:40])
for name, items in (("old", bank[:1182]), ("new", bank[1182:])):
    n, bad, c = voice_v2.run(items)
    print(f"wording flags {name}: {bad}/{n}", dict(c.most_common()))
