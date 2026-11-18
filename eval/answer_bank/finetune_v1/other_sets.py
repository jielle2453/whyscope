"""Chat set and abstention set through the base and fine-tuned pipelines (work/config_*.yaml) -> work/other_sets.json."""
import json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, WORK, load_jsonl
sys.path.insert(0, str(ROOT / "eval"))
from hub.config import load_config
from run_bank_order import make, route
out = {}
for tag in ("base", "ft"):
    p = make(load_config(str(WORK / f"config_{tag}.yaml")), True)
    rows = []
    for f, kf in (("chat_set_en.jsonl", "cat"), ("abstention_set_en.jsonl", "kind")):
        for d in load_jsonl(ROOT / "eval" / f):
            p.chat.memory.clear()
            r = p.ask(text=d["q"], mode="text", lang="en")
            rows.append({"set": f.split("_")[0], "kind": d[kf], "expect": d["expect"], "q": d["q"], "route": route(r) if r.get("status") != "sensitive" else "sensitive",
                         "bank": (r.get("bank") or {}).get("id") if route(r) == "bank" else None, "bq": (r.get("bank") or {}).get("q")})
    out[tag] = rows
    c = Counter((x["set"], x["kind"], x["route"]) for x in rows)
    print(tag, sorted(c.items()))
json.dump(out, open(WORK / "other_sets.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for a, b in zip(out["base"], out["ft"]):
    if a["route"] != b["route"] or a["bank"] != b["bank"]:
        print(" ", a["set"], a["kind"], a["q"], "|", a["route"], a["bq"], "->", b["route"], b["bq"])
