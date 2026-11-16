"""Merge the three independent fact checks (A/B/C) of every new item.
Step 1 (default): integrity (ids/order per chunk), per-checker counts, agreement, and a misalignment test: every corrected a1
must be about the item (cosine of correction vs item q).  Writes parts_v2/check_{A,B,C}.jsonl (concatenated) and
parts_v2/check_merge.json (per-item decision), and parts_v2/reconcile_in.jsonl (items with a fix majority).
Rules: >=2 true/simplified -> keep as written (label true if >=2 true else simplified); >=2 fix -> fix (texts reconciled);
>=2 reject -> drop; anything else -> drop (no agreement). A variant is removed when >=2 checkers flag it."""
import json, collections, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
P = HERE / "parts_v2"
items = {}
order = []
for k in range(1, 9):
    for l in open(P / f"tocheck_{k}.jsonl", encoding="utf-8"):
        d = json.loads(l); items[d["id"]] = d; order.append(d["id"])
C = {}
ok_all = True
for L in "ABC":
    rows = []
    for k in range(1, 9):
        ids = [json.loads(l)["id"] for l in open(P / f"tocheck_{k}.jsonl", encoding="utf-8")]
        r = [json.loads(l) for l in open(P / f"check_{L}_{k}.jsonl", encoding="utf-8-sig") if l.strip()]
        if [x["id"] for x in r] != ids:
            ok_all = False; print("MISMATCH", L, k, len(r), len(ids))
        rows += r
    C[L] = {x["id"]: x for x in rows}
    with open(P / f"check_{L}.jsonl", "w", encoding="utf-8") as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(L, dict(collections.Counter(x["verdict"] for x in rows)))
print("integrity ok" if ok_all else "INTEGRITY FAIL")

# misalignment test: corrected a1 vs its own item's q, vs the best other item's q
if "--align" in sys.argv:
    sys.path.insert(0, str(HERE))
    from retrieve import model
    import numpy as np
    m = model()
    qs = [items[i]["q"] for i in order]
    Q = m.encode(qs, normalize_embeddings=True, show_progress_bar=False, batch_size=128)
    pos = {i: n for n, i in enumerate(order)}
    for L in "ABC":
        fx = [(i, x["a1"]) for i, x in C[L].items() if x.get("a1")]
        if not fx: continue
        E = m.encode([t for _, t in fx], normalize_embeddings=True, show_progress_bar=False)
        S = E @ Q.T
        bad = [(i, t, round(float(S[n, pos[i]]), 2), items[order[int(S[n].argmax())]]["q"]) for n, (i, t) in enumerate(fx)
               if S[n, pos[i]] < S[n].max() - 0.15 and S[n, pos[i]] < 0.4]
        print(L, "corrected a1:", len(fx), "suspect misaligned:", len(bad))
        for b in bad[:10]: print("   ", b[0], "|", items[b[0]]["q"], "|", b[1], "| best other:", b[3])

dec = {}
for i in order:
    vs = [C[L][i]["verdict"] for L in "ABC"]
    c = collections.Counter(vs)
    ok = c["true"] + c["simplified"]
    if ok >= 2:
        d = "keep"; label = "true" if c["true"] >= 2 else "simplified"
    elif c["fix"] >= 2:
        d = "fix"; label = "fix"
    elif c["reject"] >= 2:
        d = "drop"; label = "reject"
    else:
        d = "drop"; label = "no_agreement"
    bv = collections.Counter(v for L in "ABC" for v in set(C[L][i].get("bad_variants") or []))
    dec[i] = {"decision": d, "check": label, "verdicts": vs, "bad_variants": sorted(v for v, n in bv.items() if n >= 2),
              "minority_fix": d == "keep" and c["fix"] == 1}
cnt = collections.Counter(x["check"] for x in dec.values())
print("decisions", dict(cnt), "minority single fix (kept as written):", sum(x["minority_fix"] for x in dec.values()))
print("unanimous", sum(len(set(x["verdicts"])) == 1 for x in dec.values()),
      "all three ok", sum(all(v in ("true", "simplified") for v in x["verdicts"]) for x in dec.values()))
print("variants removed (>=2 flags)", sum(len(x["bad_variants"]) for x in dec.values()),
      "single-flagged", sum(1 for i in order for v in set(sum([C[L][i].get("bad_variants") or [] for L in "ABC"], [])) if v not in dec[i]["bad_variants"]))
json.dump(dec, open(P / "check_merge.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
with open(P / "reconcile_in.jsonl", "w", encoding="utf-8") as f:
    for i in order:
        if dec[i]["decision"] == "fix":
            fixes = {L: {k: C[L][i][k] for k in ("verdict", "why", "a1", "a2", "ask_back") if k in C[L][i]} for L in "ABC"}
            f.write(json.dumps({"item": items[i], "checks": fixes}, ensure_ascii=False) + "\n")
