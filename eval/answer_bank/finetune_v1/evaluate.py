"""Base vs fine-tuned retriever for the English answer bank.

  pool    top-5 of both models on fresh_v4 (clean, noisy grammar, ASR of clean, ASR of grammar) and on the older sets
          (145 = heldout_en_v3 + guess_fresh_en, heldout_en_v2, v3 probes); writes the blind judge sheets for every
          (question, item) pair without a label (fresh_v4: top-5 of every split; older sets: top-1), mixed with 40
          round-2-labelled calibration pairs. Noisy versions are judged through their clean question (same intent).
  calib   per model: answer threshold and sensitive threshold from bank-derived validation only (val items of
          train.py, leave-item-out): the fine-tuned thresholds accept the same share of "right item removed" queries
          as the base model does at 0.80 / 0.93 (equal false-accept budget). fresh_v4 is not read.
  report  R / P / W tables (needs the judge labels), -> work/metrics.json and report tables on stdout
  latency CPU latency per query and extra RAM of the second model
Usage (HF_HUB_OFFLINE=1): python evaluate.py pool|calib|report|latency
"""
import json
import random
import sys
from collections import Counter, defaultdict

import numpy as np

from common import FT_DIR, HERE, ROOT, WORK, Index, bank, embed, load_jsonl, model, normalize_en, sensitive

FV = HERE.parent / "fresh_v4"
JUDGE = WORK / "judge"
SPLITS = ("clean", "grammar", "asr_clean", "asr_grammar")


def fresh_queries():
    clean = {d["id"]: d for d in load_jsonl(FV / "questions.jsonl")}
    gram = {d["id"]: d for d in load_jsonl(FV / "noisy_grammar.jsonl")}
    asr = {d["key"]: d for d in load_jsonl(FV / "asr_test.jsonl")}
    out = []
    for i, d in clean.items():
        out.append({"qid": i, "split": "clean", "q": d["q"], "intent": d["q"], "topic": d["topic"]})
        out.append({"qid": i, "split": "grammar", "q": gram[i]["q"], "intent": d["q"], "topic": d["topic"],
                    "kind": gram[i]["kind"]})
        for tag, sp in (("clean", "asr_clean"), ("grammar", "asr_grammar")):
            a = asr[f"{i}_{tag}"]
            out.append({"qid": i, "split": sp, "q": a["asr"] or "", "intent": d["q"], "topic": d["topic"],
                        "voice": a["tts"]["voice"].split()[1]})
    return out


def older_queries():
    ev = ROOT / "eval"
    out = []
    for f, tag in (("heldout_en_v3.jsonl", "145"), ("guess_fresh_en.jsonl", "145"), ("heldout_en_v2.jsonl", "v2")):
        out += [{"qid": d["id"], "split": tag, "q": d["q"], "intent": d["q"]} for d in load_jsonl(ev / f)]
    for n, d in enumerate(load_jsonl(ev / "answer_bank" / "fixes_v3" / "gaps_v3_work" / "probes.jsonl")):
        out.append({"qid": f"p-{n:03d}", "split": "probes", "q": d["q"], "intent": d["q"]})
    return out


def old_labels():
    """(question id, item id) -> R/P/W from round 2 (parts_v2) and round 3 (gaps_v3_work); later rounds win."""
    P = HERE.parent / "parts_v2"
    lab = {}
    K = json.load(open(P / "judge_key.json", encoding="utf-8"))
    for l in open(P / "judge_labels.txt", encoding="utf-8"):
        n, lb = l.strip().split("|"); a, b, _ = K["key"][n]; lab[(a, b)] = lb
    for kf, lf in (("judge_key2.json", "judge_labels2.txt"), ("judge_key3.json", "judge_labels3.txt")):
        K = json.load(open(P / kf, encoding="utf-8"))
        for l in open(P / lf, encoding="utf-8"):
            n, lb = l.strip().split("|"); a, b = K[n]; lab[(a, b)] = lb
    G = HERE.parent / "fixes_v3" / "gaps_v3_work"
    K = json.load(open(G / "judge_key_v3.json", encoding="utf-8"))
    for l in open(G / "judge_labels_v3.txt", encoding="utf-8"):
        n, lb = l.strip().split("|")
        lab[tuple(K[n]["pair"])] = lb
    return lab


def retrieve(name, queries, items, k=5):
    m = model(name)
    ix = Index(m, items)
    top, _ = ix.top([q["q"] or "." for q in queries], k=k)
    return top


def cmd_pool():
    items = bank()
    byid = {d["id"]: d for d in items}
    fq, oq = fresh_queries(), older_queries()
    res = {}
    for name in ("base", "ft"):
        res[name] = {"fresh": retrieve(name, fq, items), "older": retrieve(name, oq, items)}
    json.dump({"fresh_queries": fq, "older_queries": oq, "top": res}, open(WORK / "retrieval.json", "w", encoding="utf-8"))
    lab = old_labels()
    need = []
    for n, q in enumerate(fq):
        for name in res:
            for iid, _ in res[name]["fresh"][n]:
                need.append((q["qid"], iid))
    for n, q in enumerate(oq):
        for name in res:
            iid = res[name]["older"][n][0][0]
            if (q["qid"], iid) not in lab:
                need.append((q["qid"], iid))
    need = list(dict.fromkeys(need))
    intent = {q["qid"]: q["intent"] for q in fq + oq}
    # calibration: 40 round-2 labelled pairs of the 145 set (R/P/W mixed)
    rng = random.Random(4)
    known = [(k, v) for k, v in lab.items() if k[0] in intent and k[1] in byid]
    cal = []
    for want in "RPW":
        pool = [k for k, v in known if v == want and k not in need]
        cal += rng.sample(pool, min({"R": 15, "P": 15, "W": 10}[want], len(pool)))
    allp = [(a, b, "new") for a, b in need] + [(a, b, "cal") for a, b in cal]
    rng.shuffle(allp)
    JUDGE.mkdir(parents=True, exist_ok=True)
    nj = max(1, -(-len(allp) // 360))
    key = {}
    for j in range(nj):
        part = allp[j::nj]
        with open(JUDGE / f"sheet_{j + 1}.txt", "w", encoding="utf-8") as f:
            for a, b, kind in part:
                num = f"{j + 1}-{len(key) + 1}"
                key[num] = [a, b, kind]
                f.write(f"{num}|{intent[a]}|{byid[b]['q']}\n")
    # 10% overlap: a second judge labels a sample of other sheets' pairs (agreement)
    ov = rng.sample([k for k, v in key.items() if v[2] == "new"], min(250, len(key) // 10))
    with open(JUDGE / "sheet_overlap.txt", "w", encoding="utf-8") as f:
        for num in ov:
            a, b, _ = key[num]
            f.write(f"o{num}|{intent[a]}|{byid[b]['q']}\n")
    json.dump(key, open(JUDGE / "key.json", "w", encoding="utf-8"))
    print(f"pairs to judge: {len(need)} new + {len(cal)} calibration -> {nj} sheets; overlap {len(ov)}")


def read_labels():
    key = json.load(open(JUDGE / "key.json", encoding="utf-8"))
    new, cal, ov = {}, [], []
    for f in sorted(JUDGE.glob("labels_*.txt")):
        for l in open(f, encoding="utf-8"):
            l = l.strip()
            if not l or "|" not in l:
                continue
            n, lb = l.split("|")[0].strip(), l.split("|")[-1].strip().upper()[:1]
            if n.startswith("o"):
                ov.append((key[n[1:]], lb))
                continue
            a, b, kind = key[n]
            if kind == "cal":
                cal.append(((a, b), lb))
            else:
                new[(a, b)] = lb
    return new, cal, ov


def leave_item_out(name, items, val):
    """Top-1 score of every validation query with its own item removed from the index ("no right item" scores), and
    of the validation variants with only their own row removed ("right item present")."""
    m = model(name)
    ix = Index(m, items)
    pos = {d["id"]: i for i, d in enumerate(items)}
    qs, own = [], []
    for d in items:
        if d["id"] in val:
            for t in [d["q"]] + list(d.get("variants") or []):
                qs.append(t)
                own.append(pos[d["id"]])
    aug = []
    for k in range(1, 7):
        for d in load_jsonl(WORK / "child_aug" / f"out_{k}.jsonl"):
            if d["id"] in val:
                aug += [(r, pos[d["id"]]) for r in d["rw"]]
    for d in load_jsonl(WORK / "asr_train.jsonl"):
        if d["id"] in val and d.get("asr"):
            aug.append((d["asr"], pos[d["id"]]))
    allq = qs + [t for t, _ in aug]
    allo = own + [o for _, o in aug]
    Q = embed(m, allq)
    S_out = ix.scores(Q, drop_items=allo)
    s_out = S_out.max(axis=1)
    # right item present (variants: own row removed; aug: all rows present)
    row_of = {(int(o), normalize_en(t)): r for r, (t, o) in enumerate(zip(ix.rows, ix.owner))}
    dr = [row_of.get((o, normalize_en(t)), -1) for t, o in zip(qs, own)] + [-1] * len(aug)
    S_in = ix.scores(Q, drop_rows=dr)
    top_in = S_in.argmax(axis=1)
    s_in = S_in.max(axis=1)
    # sensitive: the same with only sensitive items as candidates (queries of NON-sensitive val items):
    # how often does a non-sensitive question score >= T against some sensitive item
    sens = np.array([sensitive(d) for d in items])
    nonsens_q = np.array([not sens[o] for o in allo])
    s_sens = np.where(sens[None, :], S_out, -1).max(axis=1)[nonsens_q]
    return {"s_out": s_out, "s_in": s_in, "ok_in": top_in == np.array(allo), "s_sens_false": s_sens,
            "n": len(allq), "kind": ["bank"] * len(qs) + ["aug"] * len(aug)}


def cmd_calib():
    items = bank()
    val = set(json.load(open(WORK / "split.json", encoding="utf-8"))["val_items"])
    r = {name: leave_item_out(name, items, val) for name in ("base", "ft")}
    b, f = r["base"], r["ft"]

    def match(base_scores, ft_scores, t):
        rate = float(np.mean(base_scores >= t))
        # the ft threshold with the same acceptance rate (quantile of the ft scores)
        tf = float(np.quantile(ft_scores, 1 - rate)) if rate > 0 else float(ft_scores.max() + 1e-3)
        return rate, tf
    rate, t_ft = match(b["s_out"], f["s_out"], 0.80)
    # sensitive threshold: the same equal-false-accept rule at the base model's 0.93 over all items. (Restricted to
    # sensitive items the validation sample is too small: no non-sensitive validation query reaches 0.93 against a
    # sensitive item with either model, so that rule has no information; its maxima are recorded below.)
    srate, ts_ft = match(b["s_out"], f["s_out"], 0.93)
    out = {"n_val_queries": b["n"], "answer": {"base": 0.80, "ft": round(t_ft, 3), "false_accept_rate": round(rate, 4)},
           "sensitive": {"base": 0.93, "ft": round(ts_ft, 3), "false_accept_rate": round(srate, 4),
                         "max_nonsensitive_query_vs_sensitive_item": {"base": round(float(b["s_sens_false"].max()), 3),
                                                                      "ft": round(float(f["s_sens_false"].max()), 3)}}}
    sweep = []
    for t in np.arange(0.70, 0.99, 0.02):
        row = {"t": round(float(t), 2)}
        for name, x in r.items():
            row[name] = {"accept_no_right_item": round(float(np.mean(x["s_out"] >= t)), 4),
                         "right_top1_and_accepted": round(float(np.mean(x["ok_in"] & (x["s_in"] >= t))), 4)}
        sweep.append(row)
    out["sweep"] = sweep
    for name, x, t in (("base", b, 0.80), ("ft", f, t_ft)):
        out[name] = {"right_top1": round(float(np.mean(x["ok_in"])), 4),
                     "right_top1_and_accepted": round(float(np.mean(x["ok_in"] & (x["s_in"] >= t))), 4),
                     "accept_no_right_item": round(float(np.mean(x["s_out"] >= t)), 4)}
    json.dump(out, open(WORK / "calib.json", "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "sweep"}, indent=1))


def metrics(top, queries, lab, thr, sens_thr, byid, splits):
    """R/P/W at the threshold with the hub's sensitive-item rule, plus top-1 / top-5 accuracy."""
    out = {}
    for sp in splits:
        idx = [n for n, q in enumerate(queries) if q["split"] == sp]
        c = Counter()
        for n in idx:
            q = queries[n]
            t5 = top[n]
            iid, s = t5[0]
            l1 = lab.get((q["qid"], iid), "?")
            c["n"] += 1
            c["top1_R"] += l1 == "R"
            c["top5_R"] += any(lab.get((q["qid"], i)) == "R" for i, _ in t5)
            if sensitive(byid[iid]):
                if s >= sens_thr:
                    c["handover"] += 1
                continue
            if s >= thr:
                c["answered"] += 1
                c[l1] += 1
        a = c["answered"]
        out[sp] = {"n": c["n"], "answered": a, "R": c["R"], "P": c["P"], "W": c["W"], "unlabelled": c["?"],
                   "answer_rate": round(a / max(1, c["n"]), 3), "off_question": round(c["W"] / max(1, a), 3),
                   "R_of_all": round(c["R"] / max(1, c["n"]), 3), "R_of_answered": round(c["R"] / max(1, a), 3),
                   "top1_acc": round(c["top1_R"] / max(1, c["n"]), 3), "top5_acc": round(c["top5_R"] / max(1, c["n"]), 3),
                   "handover": c["handover"]}
    return out


def cmd_report():
    items = bank()
    byid = {d["id"]: d for d in items}
    R = json.load(open(WORK / "retrieval.json", encoding="utf-8"))
    cal = json.load(open(WORK / "calib.json", encoding="utf-8"))
    new, calp, ov = read_labels()
    lab = {**old_labels(), **new}
    olab = old_labels()
    agree = sum(olab[k] == v for k, v in calp)
    ovk = {}
    for (a, b, _), lb in ov:
        ovk[(a, b)] = lb
    ov_agree = sum(new.get(k) == v for k, v in ovk.items() if k in new)
    rp = sum((new.get(k) in "RP") == (v in "RP") for k, v in ovk.items() if k in new and new.get(k))
    out = {"judge": {"calibration": f"{agree}/{len(calp)}",
                     "calibration_R": f"{sum(olab[k] == v for k, v in calp if olab[k] == 'R')}/{sum(olab[k] == 'R' for k, _ in calp)}",
                     "overlap_exact": f"{ov_agree}/{len(ovk)}", "overlap_RP_vs_W": f"{rp}/{len(ovk)}",
                     "new_pairs": len(new), "labels": dict(Counter(new.values()))}}
    thr = {"base": (0.80, 0.93), "ft": (cal["answer"]["ft"], cal["sensitive"]["ft"])}
    for name in ("base", "ft"):
        for tag, (t, st) in (("own", thr[name]), ("at_0.80", (0.80, 0.93))):
            if name == "base" and tag == "at_0.80":
                continue
            out[f"{name}_{tag}"] = {
                "threshold": t, "sensitive_threshold": st,
                "fresh": metrics(R["top"][name]["fresh"], R["fresh_queries"], lab, t, st, byid, SPLITS),
                "older": metrics(R["top"][name]["older"], R["older_queries"], lab, t, st, byid, ("145", "v2", "probes"))}
        # always answer (threshold off) for top-1 accuracy comparisons
    # per noisy kind / voice breakdown at own thresholds
    br = {}
    for name in ("base", "ft"):
        t, st = thr[name]
        fq = R["fresh_queries"]
        top = R["top"][name]["fresh"]
        for keyf in ("kind", "voice"):
            groups = defaultdict(list)
            for n, q in enumerate(fq):
                if q.get(keyf):
                    groups[(q["split"], q[keyf])].append(n)
            for g, idx in groups.items():
                qs = [dict(fq[n], split="g") for n in idx]
                br.setdefault(f"{g[0]}:{g[1]}", {})[name] = metrics([top[n] for n in idx], qs, lab, t, st, byid, ("g",))["g"]
        # top-1 changes on clean fresh_v4
    out["breakdown"] = br
    # pairs where the models disagree at top-1 on clean fresh_v4 (for the report's examples)
    ex = []
    for n, q in enumerate(R["fresh_queries"]):
        b1, f1 = R["top"]["base"]["fresh"][n][0], R["top"]["ft"]["fresh"][n][0]
        if b1[0] != f1[0]:
            ex.append({"split": q["split"], "q": q["q"], "intent": q["intent"], "base": [b1[0], round(b1[1], 3), lab.get((q["qid"], b1[0]), "?"), byid[b1[0]]["q"]],
                       "ft": [f1[0], round(f1[1], 3), lab.get((q["qid"], f1[0]), "?"), byid[f1[0]]["q"]]})
    out["changed_top1"] = ex
    json.dump(out, open(WORK / "metrics.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("changed_top1", "breakdown")}, indent=1))


def cmd_latency():
    import os
    import time
    import psutil
    import torch
    torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
    proc = psutil.Process()
    qs = [d["q"] for d in load_jsonl(FV / "questions.jsonl")][:100]
    out = {}
    for name in ("base", "ft"):
        m = model(name, "cpu")
        for q in qs[:5]:
            embed(m, [q])
        t = []
        for q in qs:
            s = time.perf_counter(); embed(m, [q]); t.append((time.perf_counter() - s) * 1000)
        t.sort()
        out[name] = {"median_ms": round(t[len(t) // 2], 1), "p90_ms": round(t[int(len(t) * 0.9)], 1)}
    rss0 = proc.memory_info().rss
    m2 = model("ft", "cpu")
    embed(m2, qs[:3])
    out["extra_rss_mb_second_model"] = round((proc.memory_info().rss - rss0) / 2**20, 1)
    out["model_files_mb"] = round(sum(p.stat().st_size for p in FT_DIR.rglob("*") if p.is_file()) / 2**20, 1)
    out["threads"] = torch.get_num_threads()
    print(json.dumps(out, indent=1))
    json.dump(out, open(WORK / "latency.json", "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    {"pool": cmd_pool, "calib": cmd_calib, "report": cmd_report, "latency": cmd_latency}[sys.argv[1]]()
