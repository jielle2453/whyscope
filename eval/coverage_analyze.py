"""Tables for eval/coverage_report.md from the raw results and eval/coverage_judgments.json.
Usage: python eval/coverage_analyze.py <hub_results.jsonl> <proto_results.jsonl>
Judgments were made by an AI, not a human."""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

hub = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
proto = {json.loads(l)["id"]: json.loads(l) for l in open(sys.argv[2], encoding="utf-8")}
J = json.load(open(Path(__file__).with_name("coverage_judgments.json"), encoding="utf-8"))


def pct(a, n):
    return f"{a}/{n} ({100 * a / n:.0f}%)" if n else "-"


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else float("nan")


for lang in ("zh", "en"):
    H = [h for h in hub if h["lang"] == lang]
    n = len(H)
    ans = [h for h in H if h["resp"].get("status") == "answered"]
    sens = [h for h in H if h["resp"].get("status") == "sensitive"]
    right = [h for h in ans if h["id"] not in J["hub_wrong"] and h["id"] not in J["hub_partial"]]
    part = [h for h in ans if h["id"] in J["hub_partial"]]
    llm = [h for h in ans if str(h["resp"].get("compose_source")) == "llm"]
    lat = [h["resp"]["latency_ms"]["total"] / 1000 for h in ans]
    print(f"\n=== {lang} (n={n}) HUB: answered {pct(len(ans), n)}, right {pct(len(right), n)} of all "
          f"({pct(len(right), len(ans))} of answered), partial {len(part)}, wrong {len(ans) - len(right) - len(part)}, "
          f"sensitive-flagged {len(sens)}, abstained {n - len(ans) - len(sens)}, composed by LLM {len(llm)}/{len(ans)}")
    print(f"    hub answer latency (complete answer) p50 {q(lat, .5):.1f}s p95 {q(lat, .95):.1f}s")
    P = [proto[h["id"]] for h in H]
    nopass = [r for r in P if not r.get("passage")]
    rel = [r for r in P if r["id"] in J["passage_relevant"]]
    idk = [r for r in P if r["id"] in J["I"]]
    gen = [r for r in P if r.get("chk")]
    relaxed = [r for r in gen if r["chk"]["pass_relaxed"]]
    strict = [r for r in gen if r["chk"]["pass_strict"]]
    verdict = lambda r: "R" if r["id"] in J["R"] else "P" if r["id"] in J["P"] else "I" if r["id"] in J["I"] else "N" if r["id"] in J["N"] else "W"  # noqa: E731
    R = [r for r in P if verdict(r) == "R"]
    Pp = [r for r in P if verdict(r) == "P"]
    W = [r for r in P if verdict(r) == "W"]
    fe = [r for r in P if r["id"] in J["factual_error"]]
    print(f"PROTO: relevant passage {pct(len(rel), n)}; no passage at all {len(nopass)}; model said IDK {len(idk)}")
    print(f"    verdict R {pct(len(R), n)}  P {len(Pp)}  W {len(W)}  I {len(idk)}  N {len(nopass)}; factual-error answers {len(fe)}")
    print(f"    pass relaxed {pct(len(relaxed), n)} (right among them {sum(verdict(r) == 'R' for r in relaxed)}, "
          f"partly {sum(verdict(r) == 'P' for r in relaxed)}, wrong {sum(verdict(r) == 'W' for r in relaxed)})")
    print(f"    pass strict  {pct(len(strict), n)} (right among them {sum(verdict(r) == 'R' for r in strict)})")
    print(f"    R rejected by relaxed checks: {[r['id'] for r in R if not r['chk']['pass_relaxed']]}")
    chkfail = defaultdict(int)
    for r in gen:
        for k in ("language_ok", "sentence_count_ok", "sentence_len_ok", "total_len_ok", "rare_ok", "jargon_ok", "voice_ok", "grounded_ok"):
            if not r["chk"][k]:
                chkfail[k] += 1
    print("    check failures:", dict(chkfail))
    g = [r["gen_s"] for r in gen]
    a = [r["gen_s"] + r["select_s"] for r in gen]
    t = [r["total_s"] for r in gen]
    print(f"    latency gen-only p50 {q(g, .5):.1f}s p95 {q(g, .95):.1f}s | with passage select p50 {q(a, .5):.1f} p95 {q(a, .95):.1f} | "
          f"incl. 2 wiki requests p50 {q(t, .5):.1f} p95 {q(t, .95):.1f}  (wiki fetch alone p50 {q([r['fetch_s'] for r in gen], .5):.1f}s)")
    # best possible: relevant passage AND right/partial AND relaxed checks
    print(f"    relevant-passage subset: right {sum(verdict(r) == 'R' for r in rel)}/{len(rel)}, "
          f"partly {sum(verdict(r) == 'P' for r in rel)}, rel & relaxed-pass {sum(1 for r in rel if r['chk']['pass_relaxed'])}")
    cats = defaultdict(lambda: defaultdict(int))
    for h in H:
        c, r = h["category"], proto[h["id"]]
        s = cats[c]
        s["n"] += 1
        s["hub_ans"] += h["resp"].get("status") == "answered"
        s["hub_right"] += h in right
        s["rel"] += r["id"] in J["passage_relevant"]
        s["R"] += verdict(r) == "R"
        s["P"] += verdict(r) == "P"
        s["relaxed"] += bool(r.get("chk") and r["chk"]["pass_relaxed"])
    print("    category | n | hub answered | hub right | passage ok | proto right | proto partly | passed checks")
    for c, s in cats.items():
        print(f"    {c} | {s['n']} | {s['hub_ans']} | {s['hub_right']} | {s['rel']} | {s['R']} | {s['P']} | {s['relaxed']}")


# ---- looser tier: the hub's own grounding rule (every sentence shares >= 1 content word with the passage), no length caps
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub import compose  # noqa: E402

print("\n=== looser tier (not IDK, language, no jargon/flattery, hub grounded(): each sentence shares a content word with the passage; NO length caps)")
for lang in ("zh", "en"):
    P = [r for r in proto.values() if r["lang"] == lang and r.get("chk")]
    ok = []
    for r in P:
        c = r["chk"]
        txt = c["clean_text"]
        gr = (compose.grounded_en if lang == "en" else compose.grounded)(txt, [r["passage"]])
        if (not c["idk"]) and c["language_ok"] and c["jargon_ok"] and c["voice_ok"] and gr:
            ok.append(r)
    v = lambda r: "R" if r["id"] in J["R"] else "P" if r["id"] in J["P"] else "W"  # noqa: E731
    print(f"{lang}: passes {len(ok)}/50; right {sum(v(r) == 'R' for r in ok)}, partly {sum(v(r) == 'P' for r in ok)}, wrong {sum(v(r) == 'W' for r in ok)}; "
          f"also sentence_len_ok: {sum(1 for r in ok if r['chk']['sentence_len_ok'])}")
    Rr = [r for r in P if r["id"] in J["R"]]
    print(f"   among the {len(Rr)} right answers: sentence_len_ok {sum(r['chk']['sentence_len_ok'] for r in Rr)}, total_len_ok "
          f"{sum(r['chk']['total_len_ok'] for r in Rr)}, rare_ok {sum(r['chk']['rare_ok'] for r in Rr)}, grounded_ok {sum(r['chk']['grounded_ok'] for r in Rr)}, "
          f"idk {sum(r['chk']['idk'] for r in P)} (IDK flagged overall)")
    # right answers whose passage did NOT contain the answer (model used its own knowledge)
    print(f"   right but passage lacked the answer (ungrounded knowledge): {[r['id'] for r in Rr if r['id'] not in J['passage_relevant']]}")
