"""Write ../review_sample.md: 30 pilot items side by side (English | Chinese | mix + key_en | empty verdict column).
Seeded pick: 8 items with a1_zh_mix, 4 with a tw_note, 18 others. Usage: python make_review_sample.py"""
import json, random
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = HERE.parents[3]
bank = {json.loads(l)["id"]: json.loads(l) for l in open(ROOT / "knowledge" / "answer_bank_en.jsonl", encoding="utf-8")}
P = [json.loads(l) for l in open(OUT / "pilot_zh.jsonl", encoding="utf-8")]
rng = random.Random(30)
mix = [p for p in P if p["a1_zh_mix"] and not p["tw_note"]]
tw = [p for p in P if p["tw_note"]]
rest = [p for p in P if not p["a1_zh_mix"] and not p["tw_note"]]
pick = rng.sample(mix, 8) + rng.sample(tw, 4) + rng.sample(rest, 18)
pick.sort(key=lambda p: (bank[p["id"]]["topic"], p["id"]))


def esc(s):
    return (s or "").replace("|", "\\|")


lines = ["# zh pilot: review sample (30 items)", "",
         "Seeded sample (seed 30) from `pilot_zh.jsonl`: 8 items with a mix sentence, 4 with a tw_note, 18 others. "
         "English = the fact-checked bank item. Fill in **Verdict** (ok / fix: … / drop) and anything you would change.",
         "", "| # | id · topic | English q / a1 | 中文 q / a1 / a2（為什麼？）/ ask-back | mix · key_en · tw_note | Verdict |",
         "|---|---|---|---|---|---|"]
for i, p in enumerate(pick, 1):
    b = bank[p["id"]]
    en = f"**Q** {esc(b['q'])}<br>**A1** {esc(b['a1'])}"
    zh = (f"**Q** {esc(p['q_zh'])}<br>**A1** {esc(p['a1_zh'])}<br>**A2** {esc(p['a2_zh'])}"
          f"<br>**問** {esc(p['ask_back_zh'])}")
    ke = ", ".join(f"{k['en']} {k['zh']}" for k in p["key_en"]) or "(none)"
    side = f"**mix** {esc(p['a1_zh_mix']) if p['a1_zh_mix'] else '—'}<br>**key_en** {esc(ke)}"
    if p["tw_note"]:
        side += f"<br>**tw** {esc(p['tw_note'])}"
    lines.append(f"| {i} | `{p['id']}` · {b['topic']} | {en} | {zh} | {side} |  |")
lines += ["", "Variants (child phrasings used for retrieval) are in `pilot_zh.jsonl`, field `variants_zh`."]
(OUT / "review_sample.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(len(pick), "items")
