"""Write review_sample.md: 100 random new items (seed 2026) with the final text and the three fact-check verdicts."""
import json, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
P = HERE / "parts_v2"
new = [json.loads(l) for l in open(P / "new_final.jsonl", encoding="utf-8")]
C = {L: {d["id"]: d for d in map(json.loads, open(P / f"check_{L}.jsonl", encoding="utf-8"))} for L in "ABC"}
s = random.Random(2026).sample(new, 100)
esc = lambda t: (t or "").replace("|", "/").replace("\n", " ")
L = ["# Human review sample: 100 random new items (bank_en_v2)", "",
     "Random sample (seed 2026) of the 3,908 new items, in the final text that is in `bank_en_v2.jsonl`.",
     "Verdicts = the three independent AI checkers A / B / C (T = true, S = simplified acceptable, F = needs fix); "
     "\"final\" = the merged label (fix = the majority fix was applied and the text below is the corrected one).",
     "Please fill the last column: OK / wrong (say what) / not for kids / bad match of question and answer.", "",
     "| # | id | question | a1 | a2 | A / B / C | final | team verdict |", "|---|---|---|---|---|---|---|---|"]
ab = {"true": "T", "simplified": "S", "fix": "F", "reject": "X"}
for n, d in enumerate(s, 1):
    v = " / ".join(ab[C[x][d["id"]]["verdict"]] for x in "ABC")
    L.append(f"| {n} | {d['id']} | {esc(d['q'])} | {esc(d['a1'])} | {esc(d['a2'])} | {v} | {d['check']} |  |")
L += ["", "Checker notes on the sampled items that were not unanimous \"true\":", ""]
for d in s:
    w = [f"{x}: {C[x][d['id']].get('why')}" for x in "ABC" if C[x][d["id"]]["verdict"] != "true" and C[x][d["id"]].get("why")]
    if w: L.append(f"- {d['id']} ({esc(d['q'])}): " + "; ".join(esc(t) for t in w))
(HERE / "review_sample.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("written", len(s))
