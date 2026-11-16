"""Second judge sheet for the single-judge view: every pair used in the tables that the round-2 judge has not labelled yet
(mostly round-1-labelled pairs). Same judge, same format, numbering continues at 661.
-> parts_v2/judge_sheet2.txt, parts_v2/judge_key2.json"""
import json, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
P = HERE / "parts_v2"
qs = [q for q in json.load(open(HERE / "retrieval_top_v2.json", encoding="utf-8")) if q["set"] != "user"]
K = json.load(open(P / "judge_key.json", encoding="utf-8"))
judged = {(a, b) for a, b, _ in K["key"].values()}
bank = {d["id"]: d for d in map(json.loads, open(HERE / "bank_en_v2.jsonl", encoding="utf-8"))}
need = []
for q in qs:
    c = [q["top"][b][0][0] for b in ("old1182", "v2_1182", "v2_2500")] + [i for i, _ in q["top"]["v2full"]]
    for i in c:
        if (q["id"], i) not in judged and (q["id"], i) not in need:
            need.append((q["id"], i))
random.Random(11).shuffle(need)
qt = {q["id"]: q["q"] for q in qs}
key = {}
with open(P / "judge_sheet2.txt", "w", encoding="utf-8") as f:
    for n, (a, b) in enumerate(need, 661):
        key[n] = [a, b]
        f.write(f"{n}|{qt[a]}|{bank[b]['q']}\n")
json.dump(key, open(P / "judge_key2.json", "w", encoding="utf-8"))
print(len(need))
