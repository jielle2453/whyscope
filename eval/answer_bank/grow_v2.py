"""Nested growth curve: old bank (1,182) -> old + 1,318 random new items (2,500, topic-proportional, seed 1) -> full v2.
Adds q["top"]["grow2500"] (top-5) to retrieval_top_v2.json and writes the not-yet-judged top-1 pairs to
parts_v2/judge_sheet3.txt / judge_key3.json (numbering from 804) for the same round-2 judge."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from retrieve import Bank, model, subsets  # noqa: E402
P = HERE / "parts_v2"
v2 = [json.loads(l) for l in open(HERE / "bank_en_v2.jsonl", encoding="utf-8")]
old, new = v2[:1182], v2[1182:]
pick = subsets(new, sizes=(1318,))[1318]
b = Bank(old + [new[i] for i in pick], model())
qs = json.load(open(HERE / "retrieval_top_v2.json", encoding="utf-8"))
for q in qs:
    q["top"]["grow2500"] = [(b.items[i]["id"], s) for i, s in b.search(q["q"], 5)]
json.dump(qs, open(HERE / "retrieval_top_v2.json", "w", encoding="utf-8"), ensure_ascii=False)
judged = {(a, c) for a, c, _ in json.load(open(P / "judge_key.json", encoding="utf-8"))["key"].values()}
judged |= {tuple(v) for v in json.load(open(P / "judge_key2.json", encoding="utf-8")).values()}
bank = {d["id"]: d for d in v2}
need = [(q["id"], q["top"]["grow2500"][0][0]) for q in qs if q["set"] != "user" and (q["id"], q["top"]["grow2500"][0][0]) not in judged]
key = {}
with open(P / "judge_sheet3.txt", "w", encoding="utf-8") as f:
    for n, (a, c) in enumerate(need, 804):
        key[n] = [a, c]
        f.write(f"{n}|{next(q['q'] for q in qs if q['id'] == a)}|{bank[c]['q']}\n")
json.dump(key, open(P / "judge_key3.json", "w", encoding="utf-8"))
print("grow2500 items", len(b.items), "new pairs to judge", len(need))
