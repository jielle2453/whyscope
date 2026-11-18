"""Abstention evaluation: recall + safety only (no ASR, no LLM) against eval/abstention_set.jsonl.

Prints overall accuracy, a 4-row confusion table by kind, and a threshold sweep; appends to docs/benchmarks.md.
Safety hits count as "abstain" (the device does not answer).
A second table shows where the full answer order now sends each question (hub/intent.py + recall + principles +
assistant.worth_asking): sensitive / kb / principle / chat / ai_guess / abstain. Questions the KB abstains on but that now
get an AI guess are reported apart: a hedged, parent-reviewed guess, not a knowledge-base answer.
Usage: python eval/run_abstention.py [--lang zh|en] [--no-write]
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
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else "zh"
    f = ROOT / "eval" / ("abstention_set.jsonl" if lang == "zh" else f"abstention_set_{lang}.jsonl")
    if not f.exists():
        print(f"{f.name} not found - nothing to evaluate yet (spec section 4 describes the format).")
        return
    from hub.config import load_config
    from hub.recall import Recall
    from hub.safety import Safety

    cfg = load_config()
    thr = float(cfg["recall"]["threshold"])
    rc, sf = Recall(cfg), Safety(cfg)
    from hub import intent as intents
    from hub.assistant import worth_asking
    from hub.principles import Principles
    pr = Principles(cfg, rc)
    from hub.bank import AnswerBank
    bk = AnswerBank(cfg, rc) if lang == "en" else None
    ab = cfg.get("answer_bank") or {}
    kb_strong, kb_margin = float(ab.get("kb_strong", 0.85)), float(ab.get("kb_margin", 0.05))

    def bank_route(q, q2, ik):
        """hub/pipeline.py _bank_first: does the English answer bank answer before a weak KB match / principle / guess?"""
        if not (bk and bk.ready and ik.kind in ("question", "rule")):
            return False
        e, s = rc.search(q2, lang)
        raw = rc.last_raw
        if e is not None and s >= thr and (s >= kb_strong or raw >= rc.verbatim):
            return False
        item, bs = bk.search(q2)
        if item is None and q2 != q:
            item, bs = bk.search(q)
        return item is not None and not (e is not None and s >= thr and bs < raw + kb_margin)
    items = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    res = []
    for it in items:
        hit = sf.check(it["q"], lang)
        entry, score = (None, 0.0) if hit else rc.search(it["q"], lang)
        route = "sensitive" if hit else None
        if not route:
            ik = intents.classify(it["q"], lang)
            q2 = ik.question if lang == "en" and ik.question else it["q"]
            s2 = rc.search(q2, lang)[1] if q2 != it["q"] else score
            if ik.kind == "chat":
                route = "chat"
            elif bank_route(it["q"], q2, ik):
                route = "bank"
            elif max(score, s2) >= thr:
                route = "kb"
            elif pr.search(it["q"], lang, None):
                route = "principle"
            elif ik.kind in ("rule", "deictic"):
                route = "chat"
            elif worth_asking(it["q"], lang):
                route = "ai_guess"
            else:
                route = "abstain"
        res.append({**it, "safety": bool(hit), "score": score, "kb_pred": entry["id"] if entry else None, "route": route})

    def pred(r, t):
        return "abstain" if (r["safety"] or r["score"] < t) else "answer"

    ok = sum(pred(r, thr) == r["expect"] for r in res)
    conf = defaultdict(Counter)
    for r in res:
        conf[r["kind"]][pred(r, thr)] += 1
    right_kb = [r for r in res if r["kind"] == "in_kb" and pred(r, thr) == "answer"]
    kb_ok = sum(r["kb_pred"] == r.get("kb_id") for r in right_kb)

    out = [f"### Abstention run ({lang}) {time.strftime('%Y-%m-%d %H:%M')}",
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
    routes = ["sensitive", "kb", "bank", "principle", "chat", "ai_guess", "abstain"]
    out += ["", "Full answer order (where each question goes now, AI guess on):", "",
            "| kind | n | " + " | ".join(routes) + " |", "|---|---|" + "---|" * len(routes)]
    for k in KINDS:
        rr = [r for r in res if r["kind"] == k]
        c = Counter(r["route"] for r in rr)
        out.append(f"| {k} | {len(rr)} | " + " | ".join(str(c[x]) for x in routes) + " |")
    nk = [r for r in res if r["kind"] != "in_kb"]
    fa_kb = sum(1 for r in nk if r["route"] == "kb")
    fa_pr = sum(1 for r in nk if r["route"] == "principle")
    g = [r for r in nk if r["route"] == "ai_guess"]
    bb = [r for r in nk if r["route"] == "bank"]
    if bb:
        out.append(f"- non-in_kb questions answered from the answer bank (fact-checked, English): {len(bb)}/{len(nk)}"
                   f" (out_kb {sum(r['kind'] == 'out_kb' for r in bb)}, near_kb {sum(r['kind'] == 'near_kb' for r in bb)},"
                   f" nonsense {sum(r['kind'] == 'nonsense' for r in bb)}); in_kb questions sent to the bank:"
                   f" {sum(1 for r in res if r['kind'] == 'in_kb' and r['route'] == 'bank')}")
    out += ["", f"- false answers from the KB on non-in_kb questions: {fa_kb}/{len(nk)} = {100 * fa_kb / max(1, len(nk)):.1f}%"
            f" (plus {fa_pr} answered from the principle library, a general answer that may only partly fit)",
            f"- non-in_kb questions now given a hedged AI guess (draft, on the parent's list), counted apart: {len(g)}/{len(nk)}"
            f" (out_kb {sum(r['kind'] == 'out_kb' for r in g)}, near_kb {sum(r['kind'] == 'near_kb' for r in g)},"
            f" nonsense {sum(r['kind'] == 'nonsense' for r in g)})"]
    if "--show" in sys.argv:
        for r in res:
            if r["kind"] != "in_kb" and r["route"] not in ("abstain", "sensitive"):
                out.append(f"  - [{r['kind']} -> {r['route']}] {r['q']}")
    text = "\n".join(out) + "\n"
    print(text)
    if "--no-write" not in sys.argv:
        with open(ROOT / "docs" / "benchmarks.md", "a", encoding="utf-8") as fh:
            fh.write("\n" + text)
        print("appended to docs/benchmarks.md")


if __name__ == "__main__":
    main()
