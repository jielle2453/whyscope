"""Round-2 numbers from retrieval_top_v2.json + labels (round-1 judg.py labels for pairs judged in round 1, the round-2 judge's
labels for new pairs) + the selector picks. Prints all tables used in report_v2.md and writes eval_v2.json."""
import json, collections
import numpy as np
from pathlib import Path
HERE = Path(__file__).resolve().parent
P = HERE / "parts_v2"
qs = [q for q in json.load(open(HERE / "retrieval_top_v2.json", encoding="utf-8")) if q["set"] != "user"]
K = json.load(open(P / "judge_key.json", encoding="utf-8"))
known = {tuple(k.split("|")): v for k, v in K["known"].items()}
new = {}
cal = []
for l in open(P / "judge_labels.txt", encoding="utf-8"):
    n, lab = l.strip().split("|")
    a, b, kind = K["key"][n]
    if kind == "new": new[(a, b)] = lab
    else: cal.append((known[(a, b)], lab))
import sys
SINGLE = "--single" in sys.argv     # single-judge view: the round-2 judge's labels for every pair (incl. old-bank pairs)
if SINGLE:
    r2 = dict(new)
    for l in open(P / "judge_labels.txt", encoding="utf-8"):
        n, lb = l.strip().split("|"); a, b, kind = K["key"][n]; r2[(a, b)] = lb
    K2 = json.load(open(P / "judge_key2.json", encoding="utf-8"))
    for l in open(P / "judge_labels2.txt", encoding="utf-8"):
        n, lb = l.strip().split("|"); a, b = K2[n]; r2[(a, b)] = lb
    LAB = r2
    print("== SINGLE-JUDGE VIEW (round-2 judge labels for all pairs) ==")
else:
    LAB = {**new, **known}             # round-1 label wins where it exists
    print("== MIXED VIEW (round-1 labels where they exist, round-2 judge for new pairs) ==")
K3 = json.load(open(P / "judge_key3.json", encoding="utf-8"))
for l in open(P / "judge_labels3.txt", encoding="utf-8"):
    n, lb = l.strip().split("|"); a, b = K3[n]; LAB[(a, b)] = lb   # 1 pair, labelled by the evaluator (obvious W)
def lab(q, i): return LAB[(q, i)]
out = {}
# calibration
cm = collections.Counter(cal)
agree = sum(v for (a, b), v in cm.items() if a == b)
rp = sum(v for (a, b), v in cm.items() if (a in "RP") == (b in "RP"))
print(f"calibration on {len(cal)} round-1 pairs: exact agreement {agree}/{len(cal)}, R+P vs W agreement {rp}/{len(cal)}")
print("  (round1, round2) counts:", dict(cm))
out["calibration"] = {"n": len(cal), "exact": agree, "rp_vs_w": rp, "matrix": {f"{a}->{b}": v for (a, b), v in cm.items()}}
SETS = {"v3": [q for q in qs if q["set"] == "v3"], "fresh": [q for q in qs if q["set"] == "fresh"]}
SETS["all"] = SETS["v3"] + SETS["fresh"]


def stats(sel, bank, T):
    a = [lab(q["id"], q["top"][bank][0][0]) for q in sel if q["top"][bank][0][1] >= T]
    c = collections.Counter(a)
    return {"n": len(sel), "ans": len(a), "R": c["R"], "P": c["P"], "W": c["W"]}


def fmt(s):
    return f"{100*(s['R']+s['P'])/s['n']:.0f}%"


print("\nAlways-answer coverage (R+P share; R share in brackets)")
out["size"] = {}
for b in ("old1182", "grow2500", "v2_1182", "v2_2500", "v2full"):
    row = {k: stats(sel, b, 0.0) for k, sel in SETS.items()}
    out["size"][b] = row
    print(b, " | ".join(f"{k} {fmt(s)} (R {100*s['R']/s['n']:.0f}%) W {s['W']}" for k, s in row.items()))
print("\nThreshold sweep")
out["sweep"] = {}
for b in ("old1182", "v2full"):
    for T in (0.6, 0.7, 0.75, 0.8, 0.85, 0.9):
        s = {k: stats(sel, b, T) for k, sel in SETS.items()}
        out["sweep"][f"{b}@{T}"] = s
        a = s["all"]
        print(f"{b} T={T}: ans {a['ans']} R {a['R']} P {a['P']} W {a['W']} off {100*a['W']/max(a['ans'],1):.1f}% cov {fmt(a)} v3 {fmt(s['v3'])} fresh {fmt(s['fresh'])}"
              f" | v3 R{s['v3']['R']} P{s['v3']['P']} W{s['v3']['W']} | fresh R{s['fresh']['R']} P{s['fresh']['P']} W{s['fresh']['W']}")
# top-5 ceiling
print("\nTop-5 ceiling (v2full): any R in top 5:",
      {k: sum(any(lab(q["id"], i) == "R" for i, _ in q["top"]["v2full"]) for q in sel) for k, sel in SETS.items()},
      "any R/P:", {k: sum(any(lab(q["id"], i) in "RP" for i, _ in q["top"]["v2full"]) for q in sel) for k, sel in SETS.items()})
# selector
S = json.load(open(P / "selector_key.json", encoding="utf-8"))
pick = {}
for l in open(P / "selector_picks.txt", encoding="utf-8"):
    n, k = l.strip().split("|")
    e = S[n]
    pick[e["qid"]] = None if k == "none" else e["cands"][int(k) - 1]
print("\nSelector (top-5 -> pick one or none) on v2full")
out["selector"] = {}
for T in (0.0, 0.7, 0.8, 0.85):
    res = {}
    for k, sel in SETS.items():
        base = collections.Counter(); sl = collections.Counter(); trans = collections.Counter()
        for q in sel:
            top = q["top"]["v2full"]; sc = dict(top)
            b = lab(q["id"], top[0][0]) if top[0][1] >= T else "-"
            p = pick[q["id"]]
            s_ = lab(q["id"], p) if (p is not None and sc[p] >= T) else "-"
            base[b] += 1; sl[s_] += 1; trans[(b, s_)] += 1
        res[k] = {"base": dict(base), "sel": dict(sl), "trans": {f"{a}>{b}": v for (a, b), v in trans.items()}}
        n = len(sel)
        if k == "all" or True:
            Wb, Ws = base["W"], sl["W"]
            removedW = sum(v for (a, b), v in trans.items() if a == "W" and b != "W")
            lostRP = sum(v for (a, b), v in trans.items() if a in "RP" and b not in ("R", "P"))
            lostR = sum(v for (a, b), v in trans.items() if a == "R" and b != "R")
            gained = sum(v for (a, b), v in trans.items() if a not in ("R", "P") and b in "RP")
            print(f"T>={T} {k}: base ans {n-base['-']} R{base['R']} P{base['P']} W{base['W']} cov {100*(base['R']+base['P'])/n:.0f}% -> "
                  f"sel ans {n-sl['-']} R{sl['R']} P{sl['P']} W{sl['W']} cov {100*(sl['R']+sl['P'])/n:.0f}% | W removed {removedW}/{Wb}, "
                  f"R/P lost {lostRP} (R lost {lostR}), gained R/P {gained}, off-share {100*Wb/max(n-base['-'],1):.0f}% -> {100*Ws/max(n-sl['-'],1):.0f}%")
    out["selector"][str(T)] = res
json.dump(out, open(HERE / ("eval_v2_single.json" if SINGLE else "eval_v2.json"), "w"), indent=1)
# questions with no R anywhere in the v2 top-5 (what is still missing)
miss = [(q["id"], q["q"], round(q["top"]["v2full"][0][1], 2), q["top"]["v2full"][0][0]) for q in qs
        if not any(lab(q["id"], i) == "R" for i, _ in q["top"]["v2full"])]
print(f"\nno R in v2 top-5: {len(miss)}")
for m in miss: print("  ", m)
print("\nW at top-1 (v2full):")
for q in qs:
    i, s = q["top"]["v2full"][0]
    if lab(q["id"], i) == "W": print("  ", q["id"], q["q"], "->", i, round(s, 2))

