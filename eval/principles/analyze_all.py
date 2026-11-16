import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from judgments_main import J, O

H = Path(__file__).resolve().parent
R = [json.loads(l) for l in open(H / "results" / "ugen_results.jsonl", encoding="utf-8")]
OR = {json.loads(l)["id"]: json.loads(l) for l in open(H / "results" / "oracle_answers.jsonl", encoding="utf-8")}
OUT = {}


def sub(st, lang="all"):
    return [r for r in R if r["set"] == st and (lang == "all" or r["lang"] == lang)]


def pct(a, b):
    return f"{a}/{b} ({100*a/b:.0f}%)" if b else f"{a}/0"


# ---------------- A: coverage by gold
print("=== A coverage by gold (failed set, 54)")
for lang in ("all", "zh", "en"):
    S = sub("failed", lang)
    print(lang, Counter(r["coverage"] for r in S))
cat = defaultdict(Counter)
for r in sub("failed"):
    cat[r["category"]][(r["lang"], r["coverage"])] += 1
for c, v in sorted(cat.items()):
    print(c, dict(Counter({k[1]: sum(x for kk, x in v.items() if kk[1] == k[1]) for k in v})))
print("heldout", Counter(r["coverage"] for r in sub("heldout")))

# ---------------- B: UGen choice
print("\n=== B UGen choice")
for st in ("failed", "heldout"):
    for lang in ("all", "zh", "en"):
        S = sub(st, lang)
        ans = [r for r in S if r["coverage"] != "none"]
        full = [r for r in S if r["coverage"] == "full"]
        none = [r for r in S if r["coverage"] == "none"]
        ok = sum(r["choice_id"] == r["principle"] for r in ans)
        okf = sum(r["choice_id"] == r["principle"] for r in full)
        embt1 = sum(r["top5"][0]["id"] == r["principle"] for r in ans)
        pred_none = [r for r in S if r["choice_id"] is None]
        tp = sum(r["coverage"] == "none" for r in pred_none)
        none_rec = sum(r["choice_id"] is None for r in none)
        # chose something when gold none
        halluc = sum(r["choice_id"] is not None for r in none)
        # in-candidates (gold in top5) ceiling
        inc = sum(r["principle"] in [c["id"] for c in r["top5"]] for r in ans)
        # LLM said none although gold answerable
        miss_none = sum(r["choice_id"] is None for r in ans)
        wrong_pick = sum(r["choice_id"] is not None and r["choice_id"] != r["principle"] for r in ans)
        print(f"{st}/{lang}: gold-answerable n={len(ans)} (full {len(full)}): LLM choice correct {pct(ok,len(ans))}, full-only {pct(okf,len(full))}; "
              f"emb top1 {pct(embt1,len(ans))}; gold in top5 {pct(inc,len(ans))}; LLM said none on answerable {miss_none}; picked wrong principle {wrong_pick}; "
              f"'none' precision {pct(tp,len(pred_none))}, recall {pct(none_rec,len(none))}; picked a principle on gold-none {halluc}/{len(none)}")

# ---------------- C: answers
print("\n=== C answer quality (UGen's own choice)")
for st in ("failed", "heldout", "both"):
    for lang in ("all", "zh", "en"):
        S = [r for r in R if (st == "both" or r["set"] == st) and (lang == "all" or r["lang"] == lang) and r["id"] in J]
        v = Counter(J[r["id"]][0] for r in S)
        fl = sum(J[r["id"]][1] for r in S)
        un = sum(J[r["id"]][2] for r in S)
        mapped = [r for r in S if r["choice_id"] == r["principle"] and r["coverage"] != "none"]
        vm = Counter(J[r["id"]][0] for r in mapped)
        fm = sum(J[r["id"]][1] for r in mapped)
        print(f"{st}/{lang}: answers n={len(S)} {dict(v)} false={fl} ungrounded-right={sum(1 for r in S if J[r['id']][2] and J[r['id']][0]=='right')} | correctly mapped n={len(mapped)} {dict(vm)} false={fm}")
# oracle
print("\n-- oracle mapping (gold principle forced) answers")
allgold = [r for r in R if r["coverage"] != "none"]
orac = []
for r in allgold:
    if r["choice_id"] == r["principle"]:
        orac.append((r["id"], r["lang"], r["set"], J[r["id"]][0], J[r["id"]][1], r["coverage"]))
    else:
        v = O[r["id"]]
        orac.append((r["id"], r["lang"], r["set"], v[0], v[1], r["coverage"]))
for st in ("failed", "heldout"):
    for lang in ("all", "zh", "en"):
        S = [o for o in orac if o[2] == st and (lang == "all" or o[1] == lang)]
        print(st, lang, "n", len(S), dict(Counter(o[3] for o in S)), "false", sum(o[4] for o in S),
              "| gold-full only:", dict(Counter(o[3] for o in S if o[5] == "full")), "false", sum(o[4] for o in S if o[5] == "full"))
OUT["oracle"] = orac

# ---------------- rule breaks
print("\n=== rule breaks (hub wording.py rules; checked on the opencc-converted text)")
for lang in ("zh", "en"):
    S = [r for r in R if r["lang"] == lang and r.get("wording")]
    w = [r["wording"] for r in S]
    anyp = sum(bool(x["problems"]) for x in w)
    sl = sum(any(p.startswith("sentence too long") for p in x["problems"]) for x in w)
    rare = sum(any(p.startswith(("rare", "uncommon")) for p in x["problems"]) for x in w)
    other = sum(any(not p.startswith(("sentence too long", "rare", "uncommon")) for p in x["problems"]) for x in w)
    ban = sum(x["banned"] for x in w)
    feel = sum(x["feelings"] for x in w)
    ns = Counter(x["n_sent"] for x in w)
    # passes the hub rules AND judged right
    clean = [r for r in S if not r["wording"]["problems"]]
    cr = sum(J[r["id"]][0] == "right" for r in clean)
    rr = [r for r in S if J[r["id"]][0] == "right"]
    rr_clean = sum(not r["wording"]["problems"] for r in rr)
    print(f"{lang}: n={len(S)} any rule problem {pct(anyp,len(S))}; sentence-too-long {sl}; rare chars/words {rare}; other {other}; jargon-in-raw {ban}; device feelings {feel}; sentence-count dist {dict(ns)}; clean answers {len(clean)} of which right {cr}; right answers {len(rr)} of which fully clean {rr_clean}")
    others = [(r["id"], p) for r in S for p in r["wording"]["problems"] if not p.startswith(("sentence too long", "rare", "uncommon"))]
    print("  other problems:", others[:10])
# ---------------- latency
print("\n=== latency (s)")


def q(a):
    a = np.array(a)
    return f"p50 {np.percentile(a,50):.1f} p95 {np.percentile(a,95):.1f} n={len(a)} mean {a.mean():.1f}"


for lang in ("all", "zh", "en"):
    S = [r for r in R if lang == "all" or r["lang"] == lang]
    print(lang, "choice:", q([r["choice_s"] for r in S]), "| answer:", q([r["answer_s"] for r in S if "answer_s" in r]),
          "| end-to-end (embed+choice+answer):", q([r["total_s"] for r in S]),
          "| end-to-end for answered:", q([r["total_s"] for r in S if "answer_s" in r]), "| embed", q([r["embed_s"] for r in S]))

# ---------------- D: coverage
print("\n=== D coverage")
hubf = {"zh": 22, "en": 24}
for lang in ("all", "zh", "en"):
    S = sub("failed", lang)
    abst = [r for r in S if r["hub_verdict"] in ("abstained", "sensitive")]
    hubwrong = [r for r in S if r["hub_verdict"] in ("wrong", "partly")]

    def cnt(L, grounded_only):
        right = [r for r in L if r["id"] in J and J[r["id"]][0] == "right" and (not grounded_only or not J[r["id"]][2])]
        return len(right)
    print(lang, "failed", len(S), "abstained/sensitive", len(abst), "hub wrong/partly", len(hubwrong),
          "| lib right on abstained: grounded", cnt(abst, True), "any", cnt(abst, False), "| partly", sum(1 for r in abst if r["id"] in J and J[r["id"]][0] == "partly"),
          "| lib right on all failed grounded", cnt(S, True), "any", cnt(S, False))
# gates
print("\n-- gates on all 94")
for name, f in (("LLM choice only", lambda r: r["choice_id"] is not None),
                ("LLM choice == emb top1", lambda r: r["choice_id"] is not None and r["choice_id"] == r["top5"][0]["id"]),
                ("LLM choice == emb top1 and score>=0.55", lambda r: r["choice_id"] is not None and r["choice_id"] == r["top5"][0]["id"] and r["top5"][0]["score"] >= 0.55),
                ("LLM choice == emb top1 and score>=0.60", lambda r: r["choice_id"] is not None and r["choice_id"] == r["top5"][0]["id"] and r["top5"][0]["score"] >= 0.60)):
    for st in ("failed", "heldout"):
        S = [r for r in R if r["set"] == st and f(r)]
        v = Counter(J[r["id"]][0] for r in S)
        fl = sum(J[r["id"]][1] for r in S)
        gr = sum(1 for r in S if J[r["id"]][0] == "right" and not J[r["id"]][2])
        print(f"{name} / {st}: delivered {len(S)} of {len(sub(st))}: {dict(v)} false={fl} grounded-right={gr}")
# save
json.dump({"judged": {r["id"]: {"verdict": J[r["id"]][0], "false": J[r["id"]][1], "ungrounded": J[r["id"]][2]} for r in R if r["id"] in J}},
          open(H / "results" / "judgments_applied.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
