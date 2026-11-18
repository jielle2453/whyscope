"""Pick the zh pilot items: ~300 non-sensitive items from knowledge/answer_bank_en.jsonl, stratified by topic.
Every topic gets 1 item; the rest are allocated proportionally to topic size (largest remainder). Fixed seed.
Writes ../pilot_ids.json and ../batches/src_XX.jsonl (writer input: id, topic, q, variants, a1, a2, ask_back).
Usage: python select_pilot.py"""
import json, random, collections
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = HERE.parents[3]
SEED = 20261118
N = 300
BATCH = 50

bank = [json.loads(l) for l in open(ROOT / "knowledge" / "answer_bank_en.jsonl", encoding="utf-8")]
pool = [d for d in bank if not (d.get("notes") or "").startswith("sensitive")]
by = collections.defaultdict(list)
for d in pool:
    by[d["topic"]].append(d)
topics = sorted(by)
alloc = {t: 1 for t in topics}
rest = N - len(topics)
quota = {t: rest * len(by[t]) / len(pool) for t in topics}
for t in topics:
    alloc[t] += int(quota[t])
left = N - sum(alloc.values())
for t in sorted(topics, key=lambda t: -(quota[t] - int(quota[t])))[:left]:
    alloc[t] += 1
rng = random.Random(SEED)
picked = []
for t in topics:
    items = sorted(by[t], key=lambda d: d["id"])
    picked += rng.sample(items, min(alloc[t], len(items)))
rng.shuffle(picked)
ids = [d["id"] for d in picked]
json.dump({"seed": SEED, "n": len(ids), "pool": len(pool), "alloc": alloc, "ids": ids},
          open(OUT / "pilot_ids.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
(OUT / "batches").mkdir(exist_ok=True)
keys = ["id", "topic", "q", "variants", "a1", "a2", "ask_back"]
for b in range(0, len(picked), BATCH):
    with open(OUT / "batches" / f"src_{b // BATCH + 1:02d}.jsonl", "w", encoding="utf-8") as f:
        for d in picked[b:b + BATCH]:
            f.write(json.dumps({k: d[k] for k in keys}, ensure_ascii=False) + "\n")
print(len(ids), "items from", len(pool), "non-sensitive;", len(topics), "topics")
