"""On-device selector over the English answer bank: can Qwen2.5-1.5B on the UGen300 (Hailo-10H), through the running
worker (hub/hailo_worker.py, POST /complete), pick the top-k bank item that answers a child's question, or "none"?

Each call: one fixed system prefix (instructions + 3 invented few-shot turns; the worker saves it once as a device context
and loads it per call), a turn with the question and k numbered candidate questions (optionally + a1 truncated), and ONE
generated token: the digit (0 = none). Every call is sent at priority "low" (as the parent-assistant drafts), so a child
request preempts it; a preempted call is retried later and counted. Calls are sequential. Nothing is started, stopped or
loaded on the device.

Stages (results are appended to a cache, so a rerun skips calls already made):
  dev    prompt variants A/B/C on a dev slice (eval/heldout_en_v2.jsonl questions, hand-labelled here; none of them is in the
         145 test questions) + synthetic "none" cases (top-5 minus the right item). Choose one variant here.
  test   the frozen variant on the 145 labelled questions (heldout_en_v3 + guess_fresh_en, = the run_bank_order.py set),
         k = 5 and k = 3, candidates from retrieval_top_v2.json (v2full, retrieval order).
  report tables -> selector_ondevice.json (and the numbers used in selector_ondevice.md).

Usage (HF_HUB_OFFLINE=1): python eval/answer_bank/selector_ondevice.py dev | test [--variant A] | report [--variant A]
"""
import argparse
import collections
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKER = "http://127.0.0.1:8711"
CACHE = HERE / "selector_ondevice_calls.jsonl"     # raw calls (one JSON per line)
OUT = HERE / "selector_ondevice.json"
_open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open


def chatml(msgs):   # hub.hailo.chatml (Qwen2.5 ChatML), copied so this script needs no hub import
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in msgs)


def post(path, body, timeout=180):
    req = urllib.request.Request(WORKER + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with _open(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------- prompts
SYS = ("You help a question app for young children. You get a child's question and a numbered list of questions that "
       "already have answers. Reply with the number of the list question that asks the same thing, so that its answer "
       "answers the child. A question about the same thing but asking something else does not count. If no list question "
       "asks the same thing, reply 0. Reply with one digit only.")
SYS_C = ("Pick the list question that means the same as the child's question. Reply with its number. "
         "If none means the same (only the same topic is not enough), reply 0. One digit only.")
# invented examples (checked: not in the dev or test questions)
SHOTS = [
    ("Why does my dog wag his tail?",
     ["Why do dogs bark?", "Why do cats purr?", "Why do dogs wag their tails?", "Why do dogs have wet noses?",
      "Why do dogs sniff everything?"],
     ["Dogs bark to talk to us and to other dogs.", "Cats purr when they feel calm and happy.",
      "A wagging tail shows how a dog feels.", "A wet nose helps a dog smell better.", "Dogs learn about the world by smell."],
     "3"),
    ("Why is the sea salty?",
     ["Why is the sea blue?", "Why can't I drink sea water?", "Why are there waves?", "Why do fish live in the sea?",
      "Why is the sea so big?"],
     ["The sea looks blue because water holds red light and gives back blue.", "Too much salt makes you thirstier.",
      "Wind pushes the water into waves.", "Sea fish need salty water to live.", "The sea covers most of the Earth."],
     "0"),
    ("why do the leaves fall off trees",
     ["Why are leaves green?", "Why do trees lose their leaves in autumn?", "Why do trees grow tall?",
      "Why do leaves crunch?", "Why do some trees stay green?"],
     ["Leaves have green stuff that catches sunlight.", "Trees drop leaves to save water in the cold.",
      "Trees reach up to get more sunlight.", "Dry leaves break into tiny bits.", "Pine needles have a waxy coat."],
     "2"),
]


def short(a, n=9):
    w = (a or "").split()
    return " ".join(w[:n]) + ("..." if len(w) > n else "")


def user_msg(variant, q, cands, a1s):
    if variant == "B":
        lines = [f"{i}. {c} (Answer: {short(a)})" for i, (c, a) in enumerate(zip(cands, a1s), 1)]
    else:
        lines = [f"{i}. {c}" for i, c in enumerate(cands, 1)]
    return f"Child: {q}\nList:\n" + "\n".join(lines)


def prefix(variant):
    msgs = [{"role": "system", "content": SYS_C if variant == "C" else SYS}]
    for q, cs, aa, ans in SHOTS:
        msgs += [{"role": "user", "content": user_msg(variant, q, cs, aa)}, {"role": "assistant", "content": ans}]
    return chatml(msgs)


def turn(variant, q, cands, a1s):
    return chatml([{"role": "user", "content": user_msg(variant, q, cands, a1s)}]) + "<|im_start|>assistant\n"


# ---------------------------------------------------------------- data
def bank():
    """The v2 bank (5,090 items; byte-identical to knowledge/answer_bank_en.jsonl until 2026-11-18). The labels, the
    prototype and retrieval_top_v2.json all refer to it, so the selector sees the same candidates (the hub's bank is now v3)."""
    return {d["id"]: d for d in (json.loads(l) for l in open(HERE / "bank_en_v2.jsonl", encoding="utf-8"))}


SOAK = HERE / "selector_ondevice_soak.jsonl"   # 503s (worker recovering/degraded) and health snapshots


def soak_log(rec):
    rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}
    with open(SOAK, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("soak:", rec, flush=True)


def health():
    try:
        return post("/info", {}, 10).get("health") or {}
    except Exception as e:
        return {"state": "unreachable", "error": str(e)}


def wait_ok(stats, max_s=600):
    """Poll /info until health is ok; stop on degraded (or nothing after max_s)."""
    t0 = time.time()
    while time.time() - t0 < max_s:
        h = health()
        st = h.get("state")
        if st == "ok":
            soak_log({"event": "health_ok_again", "waited_s": round(time.time() - t0, 1), "recoveries": h.get("recoveries")})
            return
        if st == "degraded":
            soak_log({"event": "degraded", "health": h})
            raise SystemExit(f"worker degraded; stopping. Results so far are in {CACHE}")
        time.sleep(5)
    raise SystemExit("worker not ok after 10 minutes; stopping")


def labels():
    """Single-judge labels of report_v2.md (same as run_bank_order.labels): (question id, item id) -> R / P / W."""
    P = HERE / "parts_v2"
    lab = {}
    K = json.load(open(P / "judge_key.json", encoding="utf-8"))
    for l in open(P / "judge_labels.txt", encoding="utf-8"):
        n, lb = l.strip().split("|"); a, b, _ = K["key"][n]; lab[(a, b)] = lb
    for kf, lf in (("judge_key2.json", "judge_labels2.txt"), ("judge_key3.json", "judge_labels3.txt")):
        K = json.load(open(P / kf, encoding="utf-8"))
        for l in open(P / lf, encoding="utf-8"):
            n, lb = l.strip().split("|"); a, b = K[n]; lab[(a, b)] = lb
    return lab


def test_questions():
    return [q for q in json.load(open(HERE / "retrieval_top_v2.json", encoding="utf-8")) if q["set"] != "user"]


# Dev slice: eval/heldout_en_v2.jsonl (not in the test sets), top-5 from the same bank and scoring (retrieve.Bank, v2 bank),
# labelled by the evaluator before any device call: the 1-based ranks that answer the question (empty = none).
DEV_LABELS = {
    "v2-005": [], "v2-013": [1], "v2-014": [1, 2], "v2-016": [1], "v2-018": [1], "v2-020": [1], "v2-022": [3],
    "v2-028": [], "v2-031": [1], "v2-032": [1, 2], "v2-033": [1], "v2-035": [1], "v2-036": [1], "v2-042": [1, 5],
    "v2-046": [1], "v2-047": [1], "v2-048": [1], "v2-049": [1], "v2-050": [1], "v2-053": [1], "v2-054": [1],
    "v2-056": [], "v2-058": [1, 2, 3], "v2-059": [1], "v2-060": [2, 3], "v2-063": [], "v2-068": [2], "v2-069": [1],
    "v2-070": [2, 3], "v2-071": [1], "v2-075": [], "v2-080": [2],
}
# synthetic "none": easy questions (top-1 = 1.0 and right) with the right item removed -> 4 candidates, expected 0
# (ranks 2-5 checked by hand: none of them asks the same thing)
DEV_NONE = ["v2-002", "v2-008", "v2-019", "v2-026", "v2-030", "v2-037", "v2-039", "v2-043", "v2-062", "v2-065"]
DEV_FILE = HERE / "selector_ondevice_dev.json"   # dev_retrieve() output, saved once


def dev_cases():
    if DEV_FILE.exists():
        top = json.load(open(DEV_FILE, encoding="utf-8"))
    else:
        top = dev_retrieve()
        json.dump(top, open(DEV_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    cases = []
    for qid, ok in DEV_LABELS.items():
        o = top[qid]
        cases.append({"qid": qid, "q": o["q"], "cands": [t[0] for t in o["top"]], "ok": ok})
    for qid in DEV_NONE:
        o = top[qid]
        cases.append({"qid": qid + "-none", "q": o["q"], "cands": [t[0] for t in o["top"][1:]], "ok": []})
    return cases


def dev_retrieve():
    sys.path.insert(0, str(HERE))
    from retrieve import Bank, model
    v2 = [json.loads(l) for l in open(HERE / "bank_en_v2.jsonl", encoding="utf-8")]
    b = Bank(v2, model())
    out = {}
    for l in open(ROOT / "eval" / "heldout_en_v2.jsonl", encoding="utf-8"):
        d = json.loads(l)
        out[d["id"]] = {"q": d["q"], "top": [(v2[i]["id"], s) for i, s in b.search(d["q"], 5)]}
    return out


# ---------------------------------------------------------------- calls
def load_cache():
    c = {}
    if CACHE.exists():
        for l in open(CACHE, encoding="utf-8"):
            r = json.loads(l); c[r["key"]] = r
    return c


def call(B, cache, key, variant, q, cands, stats):
    if key in cache:
        return cache[key]
    pre = prefix(variant)
    t_ = turn(variant, q, [B[c]["q"] for c in cands], [B[c]["a1"] for c in cands])
    tries = 0
    while True:
        tries += 1
        t0 = time.perf_counter()
        try:
            r = post("/complete", {"prefix": pre, "turn": t_, "max_new": 1, "stop": None, "priority": "low"})
        except urllib.error.HTTPError as e:
            body = e.read()[:400]
            if e.code == 503:   # self-recovery in progress: wait for health ok, retry this call, count it
                try:
                    j = json.loads(body)
                except Exception:
                    j = {"raw": body.decode("utf-8", "replace")}
                stats["503"] += 1
                soak_log({"event": "503", "key": key, "body": j})
                if j.get("state") == "degraded":
                    raise SystemExit(f"worker degraded; stopping. Results so far are in {CACHE}")
                wait_ok(stats)
                tries -= 1
                continue
            soak_log({"event": f"http_{e.code}", "key": key, "body": body.decode("utf-8", "replace")})
            raise SystemExit(f"worker error HTTP {e.code}: {e.read()[:300]!r}; stopping. Results so far are in {CACHE}")
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise SystemExit(f"worker unreachable ({e}); stopping. Results so far are in {CACHE}")
        wall = (time.perf_counter() - t0) * 1000
        if r.get("error"):
            raise SystemExit(f"worker error: {r['error']}")
        if r.get("preempted"):
            stats["preempted"] += 1
            if tries >= 30:
                raise SystemExit("preempted 30 times in a row; stopping")
            time.sleep(min(2 * tries, 10))   # a child request is using the device: wait and retry
            continue
        break
    txt = r.get("text", "")
    m = re.search(r"\d", txt)
    pick = int(m.group()) if m else -1
    rec = {"key": key, "variant": variant, "k": len(cands), "q": q, "cands": cands, "text": txt,
           "pick": pick if 0 <= pick <= len(cands) else -1, "ms_worker": r.get("ms"), "ms_wall": round(wall),
           "tries": tries, "turn_chars": len(t_), "prefix_chars": len(pre), "t": time.strftime("%H:%M:%S")}
    with open(CACHE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    cache[key] = rec
    return rec


def run_dev(variants):
    B, cache = bank(), load_cache()
    stats = collections.Counter()
    cases = dev_cases()
    for v in variants:
        for c in cases:
            call(B, cache, f"dev|{v}|{c['qid']}", v, c["q"], c["cands"], stats)
        res = dev_score(cache, v, cases)
        print(f"variant {v}: {res}", flush=True)
    print("preempted (retried):", stats["preempted"])


def dev_score(cache, v, cases):
    s = collections.Counter()
    for c in cases:
        p = cache[f"dev|{v}|{c['qid']}"]["pick"]
        if p == -1: s["invalid"] += 1
        if c["ok"]:
            s["right_pick" if p in c["ok"] else ("missed(none)" if p == 0 else "wrong_pick")] += 1
        else:
            s["right_none" if p == 0 else "wrong_pick_on_none"] += 1
    ms = sorted(cache[f"dev|{v}|{c['qid']}"]["ms_wall"] for c in cases)
    s["ms_median"] = ms[len(ms) // 2]
    return dict(s)


def run_test(variant, ks=(5, 3)):
    B, cache, stats = bank(), load_cache(), collections.Counter()
    qs = test_questions()
    n0 = len(cache)
    soak_log({"event": "start", "health": health(), "cached_calls": n0})
    try:
        for k in ks:
            for i, q in enumerate(qs):
                cands = [c for c, _ in q["top"]["v2full"][:k]]
                call(B, cache, f"test|{variant}|k{k}|{q['id']}", variant, q["q"], cands, stats)
                if i % 20 == 0:
                    print(f"k={k} {i}/{len(qs)}", flush=True)
    finally:
        soak_log({"event": "end", "health": health(), "new_calls": len(cache) - n0, "preempted": stats["preempted"],
                  "http_503": stats["503"]})
    print("preempted (retried):", stats["preempted"], "503:", stats["503"])


# ---------------------------------------------------------------- scoring
def pct(a, b):
    return round(100 * a / b, 1) if b else 0.0


def policy_rows(qs, lab, pickf, name):
    """pickf(q) -> (answered item id or None, used_selector bool). Returns the row for one policy."""
    c = collections.Counter()
    sel_calls = 0
    for q in qs:
        it, used = pickf(q)
        sel_calls += used
        c[lab[(q["id"], it)] if it else "-"] += 1
    n, ans = len(qs), len(qs) - c["-"]
    return {"policy": name, "n": n, "answered": ans, "R": c["R"], "P": c["P"], "W": c["W"],
            "answer_rate": pct(ans, n), "R_rate": pct(c["R"], n), "RP_rate": pct(c["R"] + c["P"], n),
            "off_share_W": pct(c["W"], ans), "off_share_PW": pct(c["P"] + c["W"], ans), "selector_calls": sel_calls}


def report(variant):
    lab, qs, cache = labels(), test_questions(), load_cache()
    out = {"variant": variant, "prefix": prefix(variant), "example_turn": None}
    try:
        info = post("/info", {}, 10)
        out["worker_info"] = {"name": info.get("name"), "models": {k: {kk: vv for kk, vv in v.items()} for k, v in
                                                                    (info.get("models") or {}).items()}}
    except Exception as e:
        out["worker_info"] = {"error": str(e)}
    # prototype (big-AI) picks
    S = json.load(open(HERE / "parts_v2" / "selector_key.json", encoding="utf-8"))
    proto = {}
    for l in open(HERE / "parts_v2" / "selector_picks.txt", encoding="utf-8"):
        n, k = l.strip().split("|"); e = S[n]
        proto[e["qid"]] = None if k == "none" else e["cands"][int(k) - 1]

    def dev_pick(k):
        def f(q):
            r = cache[f"test|{variant}|k{k}|{q['id']}"]
            p = r["pick"]
            return (r["cands"][p - 1] if p >= 1 else None)
        return f

    sel = {k: dev_pick(k) for k in (5, 3) if all(f"test|{variant}|k{k}|{q['id']}" in cache for q in qs)}
    top1 = lambda q: q["top"]["v2full"][0]   # noqa: E731
    pols = []
    for T in (0.80, 0.85):
        pols.append(policy_rows(qs, lab, lambda q, T=T: (top1(q)[0] if top1(q)[1] >= T else None, 0), f"(a) threshold top-1 >= {T}"))
    pols.append(policy_rows(qs, lab, lambda q: (top1(q)[0], 0), "always top-1"))
    for k, f in sel.items():
        pols.append(policy_rows(qs, lab, lambda q, f=f: (f(q), 1), f"selector k={k}, every question"))
        pols.append(policy_rows(qs, lab, lambda q, f=f: (f(q) if top1(q)[1] >= 0.80 else None, int(top1(q)[1] >= 0.80)),
                                f"selector k={k} when top-1 >= 0.80"))
        for lo, hi in ((0.70, 0.88), (0.75, 0.88), (0.70, 0.92)):
            def g(q, f=f, lo=lo, hi=hi):
                s = top1(q)[1]
                if s >= hi: return top1(q)[0], 0
                if s >= lo: return f(q), 1
                return None, 0
            pols.append(policy_rows(qs, lab, g, f"(b) gray zone k={k}: >= {hi} top-1, {lo}-{hi} selector"))
    pols.append(policy_rows(qs, lab, lambda q: (proto[q["id"]], 1), "(c) big-AI prototype, every question"))
    pols.append(policy_rows(qs, lab, lambda q: (proto[q["id"]] if top1(q)[1] >= 0.80 else None, 1), "(c) big-AI prototype when top-1 >= 0.80"))

    def gp(q):
        s = top1(q)[1]
        if s >= 0.88: return top1(q)[0], 0
        if s >= 0.70: return proto[q["id"]], 1
        return None, 0
    pols.append(policy_rows(qs, lab, gp, "(c) big-AI prototype, gray zone 0.70-0.88"))
    out["policies"] = pols

    # selector confusion (all 145 questions, no threshold)
    conf = {}
    for k, f in sel.items():
        c = collections.Counter()
        for q in qs:
            cands = [i for i, _ in q["top"]["v2full"][:k]]
            hasR = any(lab[(q["id"], i)] == "R" for i in cands)
            r = cache[f"test|{variant}|k{k}|{q['id']}"]
            p = f(q)
            if r["pick"] == -1: c["invalid_output"] += 1
            if p is None:
                c["none_but_R_in_topk (missed)" if hasR else "none_correct (no R in top-k)"] += 1
            else:
                c[f"picked {lab[(q['id'], p)]}" + ("" if hasR else " (no R in top-k)")] += 1
            c["pick_rank_" + str(r["pick"])] += 1
        c["R_in_topk"] = sum(any(lab[(q["id"], i)] == "R" for i, _ in q["top"]["v2full"][:k]) for q in qs)
        conf[f"k{k}"] = dict(sorted(c.items()))
    c = collections.Counter()
    for q in qs:
        hasR = any(lab[(q["id"], i)] == "R" for i, _ in q["top"]["v2full"])
        p = proto[q["id"]]
        c["none_but_R_in_topk (missed)" if (p is None and hasR) else "none_correct (no R in top-k)" if p is None
          else f"picked {lab[(q['id'], p)]}" + ("" if hasR else " (no R in top-k)")] += 1
    conf["prototype_k5"] = dict(sorted(c.items()))
    out["confusion"] = conf
    # agreement with the prototype on k=5
    if 5 in sel:
        out["agree_with_prototype_k5"] = sum(sel[5](q) == proto[q["id"]] for q in qs)

    # latency
    lat = {}
    for k in sel:
        ms = sorted(cache[f"test|{variant}|k{k}|{q['id']}"]["ms_worker"] for q in qs)
        wl = sorted(cache[f"test|{variant}|k{k}|{q['id']}"]["ms_wall"] for q in qs)
        tc = [cache[f"test|{variant}|k{k}|{q['id']}"]["turn_chars"] for q in qs]
        tries = sum(cache[f"test|{variant}|k{k}|{q['id']}"]["tries"] - 1 for q in qs)
        q_ = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]   # noqa: E731
        lat[f"k{k}"] = {"n": len(ms), "worker_ms_mean": round(sum(ms) / len(ms)), "worker_ms_median": q_(ms, 0.5),
                        "worker_ms_p90": q_(ms, 0.9), "worker_ms_max": ms[-1], "wall_ms_mean": round(sum(wl) / len(wl)),
                        "wall_ms_p90": q_(wl, 0.9), "turn_chars_mean": round(sum(tc) / len(tc)), "preempted_retries": tries}
    for v in ("A", "B", "C"):
        d = [r for r in cache.values() if r["key"].startswith(f"dev|{v}|")]
        if d:
            ms = sorted(r["ms_worker"] for r in d)
            lat[f"dev_{v}"] = {"n": len(ms), "worker_ms_median": ms[len(ms) // 2], "worker_ms_p90": ms[int(0.9 * len(ms))],
                               "turn_chars_mean": round(sum(r["turn_chars"] for r in d) / len(d))}
    out["latency"] = lat
    cases = dev_cases()
    out["dev"] = {v: dev_score(cache, v, cases) for v in ("A", "B", "C")
                  if all(f"dev|{v}|{c['qid']}" in cache for c in cases)}
    out["dev_n"] = {"questions": len(DEV_LABELS), "with_answer": sum(bool(v) for v in DEV_LABELS.values()),
                    "real_none": sum(not v for v in DEV_LABELS.values()), "synthetic_none": len(DEV_NONE)}
    q0 = qs[0]
    B = bank()
    out["example_turn"] = turn(variant, q0["q"], [B[i]["q"] for i, _ in q0["top"]["v2full"][:5]],
                               [B[i]["a1"] for i, _ in q0["top"]["v2full"][:5]])
    # per-question rows
    out["per_question"] = [{"id": q["id"], "q": q["q"], "top1": [q["top"]["v2full"][0][0], round(q["top"]["v2full"][0][1], 3)],
                            "labels_top5": [lab[(q["id"], i)] for i, _ in q["top"]["v2full"]],
                            **{f"pick_k{k}": cache[f"test|{variant}|k{k}|{q['id']}"]["pick"] for k in sel},
                            "proto": (None if proto[q["id"]] is None else [i for i, _ in q["top"]["v2full"]].index(proto[q["id"]]) + 1)}
                           for q in qs]
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for p in pols:
        print(f"{p['policy']:58} ans {p['answered']:3} ({p['answer_rate']:5.1f}%) R {p['R']:3} P {p['P']:2} W {p['W']} "
              f"R% {p['R_rate']:5.1f} off(W) {p['off_share_W']:4.1f}% off(P+W) {p['off_share_PW']:4.1f}% calls {p['selector_calls']}")
    print(json.dumps(conf, indent=1))
    print(json.dumps(lat, indent=1))
    print("dev:", json.dumps(out["dev"]))
    print("agree with prototype (k5):", out.get("agree_with_prototype_k5"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["dev", "test", "report"])
    ap.add_argument("--variant", default="A")
    ap.add_argument("--variants", default="A,B,C")
    a = ap.parse_args()
    if a.stage == "dev":
        run_dev(a.variants.split(","))
    elif a.stage == "test":
        run_test(a.variant)
    else:
        report(a.variant)
