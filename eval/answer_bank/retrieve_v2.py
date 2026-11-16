"""Round-2 retrieval: same model, normalisation and scoring as retrieve.py (score = max cosine over q + variants).
Banks: "old1182" = frozen bank_en.jsonl (round 1); "v2_1182", "v2_2500" = topic-proportional random subsets of bank_en_v2
(retrieve.subsets, seed 1); "v2full" = all of bank_en_v2.jsonl. Top-5 per bank. Writes retrieval_top_v2.json.
Usage: python retrieve_v2.py   (HF_HUB_OFFLINE=1)"""
import json, time, sys
import numpy as np
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from retrieve import Bank, model, subsets, ROOT  # noqa: E402

if __name__ == "__main__":
    old = [json.loads(l) for l in open(HERE / "bank_en.jsonl", encoding="utf-8")]
    v2 = [json.loads(l) for l in open(HERE / "bank_en_v2.jsonl", encoding="utf-8")]
    m = model()
    qs = []
    for tag, f in {"v3": "heldout_en_v3.jsonl", "fresh": "guess_fresh_en.jsonl"}.items():
        for l in open(ROOT / "eval" / f, encoding="utf-8"):
            d = json.loads(l); qs.append({"id": d["id"], "set": tag, "q": d["q"]})
    qs += [{"id": "u-1", "set": "user", "q": "Why my hair is black? I want a blonded hair"},
           {"id": "u-2", "set": "user", "q": "why i need to go to bed at 10"}]
    t0 = time.perf_counter()
    banks = {"old1182": Bank(old, m)}
    sub = subsets(v2, sizes=(1182, 2500))
    banks["v2_1182"] = Bank([v2[i] for i in sub[1182]], m)
    banks["v2_2500"] = Bank([v2[i] for i in sub[2500]], m)
    t1 = time.perf_counter()
    banks["v2full"] = Bank(v2, m)
    build_full = time.perf_counter() - t1
    for _ in range(5): banks["v2full"].search("warm up", 5)
    lat = {"old1182": [], "v2full": []}
    for q in qs:
        q["top"] = {}
        for n, b in banks.items():
            t = time.perf_counter()
            top = b.search(q["q"], 5)
            dt = (time.perf_counter() - t) * 1000
            if n in lat: lat[n].append(dt)
            q["top"][n] = [(b.items[i]["id"], s) for i, s in top]
    json.dump(qs, open(HERE / "retrieval_top_v2.json", "w", encoding="utf-8"), ensure_ascii=False)
    rows = {n: int(b.mat.shape[0]) for n, b in banks.items()}
    res = {"n_queries": len(qs), "rows": rows, "build_full_s": round(build_full, 1),
           "latency_ms": {n: {"median": round(float(np.median(v)), 1), "p95": round(float(np.percentile(v, 95)), 1)} for n, v in lat.items()}}
    json.dump(res, open(HERE / "latency_v2.json", "w"), indent=1)
    print(res)
