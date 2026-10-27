"""Abstention evaluation: recall + safety only (no ASR, no LLM) against eval/abstention_set.jsonl.

Prints overall accuracy, a 4-row confusion table by kind, and a threshold sweep; appends to docs/benchmarks.md.
Safety hits count as "abstain" (the device does not answer). Usage: python eval/run_abstention.py [--no-write]
"""
import json
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KINDS = ["in_kb", "near_kb", "out_kb", "nonsense"]


def main():
    f = ROOT / "eval" / "abstention_set.jsonl"
    if not f.exists():
        print("eval/abstention_set.jsonl not found - nothing to evaluate yet (spec section 4 describes the format).")
        return
    from hub.config import load_config
    from hub.recall import Recall
    from hub.safety import Safety

    cfg = load_config()
    thr = float(cfg["recall"]["threshold"])
    rc, sf = Recall(cfg), Safety(cfg)
    items = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    res = []
    for it in items:
        hit = sf.check(it["q"])
        entry, score = (None, 0.0) if hit else rc.search(it["q"])
        res.append({**it, "safety": bool(hit), "score": score, "kb_pred": entry["id"] if entry else None})

    def pred(r, t):
        return "abstain" if (r["safety"] or r["score"] < t) else "answer"

    ok = sum(pred(r, thr) == r["expect"] for r in res)
    conf = defaultdict(Counter)
    for r in res:
        conf[r["kind"]][pred(r, thr)] += 1
    right_kb = [r for r in res if r["kind"] == "in_kb" and pred(r, thr) == "answer"]
    kb_ok = sum(r["kb_pred"] == r.get("kb_id") for r in right_kb)

    out = [f"### Abstention run {time.strftime('%Y-%m-%d %H:%M')}",
           f"\n- {len(res)} questions, threshold {thr}, entries in index: {len(rc.entries)}, embedding device: {rc.device}",
           f"- accuracy: {ok}/{len(res)} = {100 * ok / max(1, len(res)):.1f}%",
           f"- in_kb answered with the correct kb_id: {kb_ok}/{len(right_kb)}\n",
           "| kind | n | predicted answer | predicted abstain | correct |", "|---|---|---|---|---|"]
    for k in KINDS:
        c = conf.get(k, Counter())
        n = sum(c.values())
        want = "answer" if k == "in_kb" else "abstain"
        out.append(f"| {k} | {n} | {c['answer']} | {c['abstain']} | {c[want]}/{n} |")
    out += ["", "Threshold sweep (accuracy / false answers on non-in_kb / false abstains on in_kb):", "",
            "| threshold | accuracy | false answers | false abstains |", "|---|---|---|---|"]
    for t in [0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75]:
        acc = sum(pred(r, t) == r["expect"] for r in res)
        fa = sum(1 for r in res if r["expect"] == "abstain" and pred(r, t) == "answer")
        fb = sum(1 for r in res if r["expect"] == "answer" and pred(r, t) == "abstain")
        out.append(f"| {t} | {100 * acc / max(1, len(res)):.1f}% | {fa} | {fb} |")
    text = "\n".join(out) + "\n"
    print(text)
    if "--no-write" not in sys.argv:
        with open(ROOT / "docs" / "benchmarks.md", "a", encoding="utf-8") as fh:
            fh.write("\n" + text)
        print("appended to docs/benchmarks.md")


if __name__ == "__main__":
    main()
