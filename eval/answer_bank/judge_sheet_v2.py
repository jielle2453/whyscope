"""Build the round-2 judging inputs.
- Checks that the old1182 top-1 reproduces round 1 (retrieval_top.json).
- Pairs already judged in round 1 (top-1 of the round-1 banks) keep their judg.py label.
- New pairs to judge (R/P/W, judge sees only the test question and the candidate item's question, as in round 1):
  top-1 of every bank and top-5 of v2full, minus known pairs. 60 known round-1 pairs are mixed in blind as a calibration.
  -> parts_v2/judge_sheet.txt  ("n|question|candidate question"), parts_v2/judge_key.json (n -> (qid, item id)).
- Selector input: question + the 5 v2full candidate questions -> parts_v2/selector_sheet.txt, parts_v2/selector_key.json."""
import json, random, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from judg import judge  # noqa: E402
P = HERE / "parts_v2"
qs = json.load(open(HERE / "retrieval_top_v2.json", encoding="utf-8"))
r1 = {q["id"]: q for q in json.load(open(HERE / "retrieval_top.json", encoding="utf-8"))}
same = sum(q["top"]["old1182"][0][0] == r1[q["id"]]["top"]["1182"][0][0] for q in qs)
print("old1182 top-1 reproduces round 1:", same, "/", len(qs))
known = {}
for q in r1.values():
    for n in ("1182", "500", "250"):
        known[(q["id"], q["top"][n][0][0])] = judge(q["id"], q["top"][n][0][0])
bank = {d["id"]: d for d in map(json.loads, open(HERE / "bank_en_v2.jsonl", encoding="utf-8"))}
need = []
for q in qs:
    cands = [q["top"][b][0][0] for b in ("old1182", "v2_1182", "v2_2500")] + [i for i, _ in q["top"]["v2full"]]
    for i in cands:
        if (q["id"], i) not in known and (q["id"], i) not in need:
            need.append((q["id"], i))
rng = random.Random(7)
calib = rng.sample(sorted(k for k in known if k[0] in {q["id"] for q in qs}), 60)
rows = [(a, b, "new") for a, b in need] + [(a, b, "calib") for a, b in calib]
rng.shuffle(rows)
qtext = {q["id"]: q["q"] for q in qs}
key = {}
with open(P / "judge_sheet.txt", "w", encoding="utf-8") as f:
    for n, (a, b, kind) in enumerate(rows, 1):
        key[n] = [a, b, kind]
        f.write(f"{n}|{qtext[a]}|{bank[b]['q']}\n")
json.dump({"key": key, "known": {f"{a}|{b}": v for (a, b), v in known.items()}}, open(P / "judge_key.json", "w", encoding="utf-8"))
print("pairs to judge", len(need), "+ calibration", len(calib))
skey = {}
with open(P / "selector_sheet.txt", "w", encoding="utf-8") as f:
    order = [q for q in qs if q["set"] != "user"]
    rng.shuffle(order)
    for n, q in enumerate(order, 1):
        c = [i for i, _ in q["top"]["v2full"]]
        perm = c[:]; rng.shuffle(perm)       # candidate order shuffled so the selector cannot use the retrieval rank
        skey[n] = {"qid": q["id"], "cands": perm}
        f.write(f"Q{n}: {q['q']}\n" + "".join(f"  {k+1}. {bank[i]['q']}\n" for k, i in enumerate(perm)) + "\n")
json.dump(skey, open(P / "selector_key.json", "w", encoding="utf-8"))
print("selector questions", len(skey))
