import json
from pathlib import Path
import numpy as np

H = Path(__file__).resolve().parent
rows = [json.loads(l) for l in open(H / "results" / "retrieval.jsonl", encoding="utf-8")]


def auc(pos, neg):
    if not pos or not neg:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


res = {}
for st in ("failed", "heldout"):
    for lang in ("all", "zh", "en"):
        R = [r for r in rows if r["set"] == st and (lang == "all" or r["lang"] == lang)]
        out = {"n": len(R)}
        for lab, cov in (("full", {"full"}), ("full+partly", {"full", "partly"})):
            S = [r for r in R if r["coverage"] in cov]
            t1 = sum(r["top5"][0]["id"] == r["principle"] for r in S)
            t3 = sum(r["principle"] in [c["id"] for c in r["top5"][:3]] for r in S)
            t5 = sum(r["principle"] in [c["id"] for c in r["top5"]] for r in S)
            out[lab] = {"n": len(S), "top1": t1, "top3": t3, "top5": t5}
        # none separation: top-1 score; "has a (full) principle" = positive
        pos = [r["top5"][0]["score"] for r in R if r["coverage"] == "full"]
        neg = [r["top5"][0]["score"] for r in R if r["coverage"] == "none"]
        out["auc_full_vs_none"] = auc(pos, neg)
        out["mean_top1_score"] = {"full": float(np.mean(pos)) if pos else None, "none": float(np.mean(neg)) if neg else None}
        res[f"{st}/{lang}"] = out
# threshold sweep on all 94: reject (say "none") when top1 score < t; positives = coverage full (answerable)
print(json.dumps(res, indent=1))
for st in ("failed", "heldout", "both"):
    R = [r for r in rows if st == "both" or r["set"] == st]
    print("\nthreshold sweep", st, "(predict answerable if top1>=t; truth answerable = gold full or partly)")
    for t in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
        tp = sum(r["top5"][0]["score"] >= t and r["coverage"] != "none" for r in R)
        fp = sum(r["top5"][0]["score"] >= t and r["coverage"] == "none" for r in R)
        fn = sum(r["top5"][0]["score"] < t and r["coverage"] != "none" for r in R)
        tn = sum(r["top5"][0]["score"] < t and r["coverage"] == "none" for r in R)
        cor = sum(r["top5"][0]["score"] >= t and r["top5"][0]["id"] == r["principle"] for r in R)
        print(f"t={t}: accepted={tp+fp} accepted_with_gold_principle={tp} none-correctly-rejected={tn}/{tn+fp} answerable-lost={fn} top1_correct_among_accepted={cor}")
json.dump(res, open(H / "results" / "retrieval_summary.json", "w"), indent=1)
