"""Product-pass check: ask in_kb questions through a running hub (/api/ask + polling) and assert the child-voice rules.

Usage: python eval/check_answers.py [--lang en|zh] [--url http://127.0.0.1:8000] [-n 10] [--age 6] [--bridges has_dog]
Asserts for every answer. zh: each sentence <= 18 chars, first sentence + reaction + explanation <= 60 chars,
no banned science term, ask-back matches 嗎/還是/猜/你覺得 and passes the safety block list.
en: each sentence <= 12 words, explanation <= 2 sentences (1 for age <= 6), spoken total <= 45 words, at most 2 uncommon
words per sentence (long ones count double), no banned science term, ask-back has "?" and one of
"do you think / or / guess / can you / is it / does" and passes the English block list, no flattery / "I think".
It sets child_age (and the bridge keys given) in memory for the run and restores/deletes them afterwards.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hub import wording  # noqa: E402
from hub.safety import askback_ok  # noqa: E402


def call(url, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--age", type=int, default=6)
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--bridges", default="", help="comma list of memory bridge keys to set to true")
    a = ap.parse_args()
    fname = "abstention_set.jsonl" if a.lang == "zh" else f"abstention_set_{a.lang}.jsonl"
    qs = [json.loads(l) for l in (ROOT / "eval" / fname).read_text(encoding="utf-8").splitlines() if l.strip()]
    qs = [q["q"] for q in qs if q["kind"] == "in_kb"]
    step = max(1, len(qs) // a.n)
    qs = qs[::step] + [q for i, q in enumerate(qs) if i % step]   # evenly spread first, then the rest as spares
    old = call(a.url + "/api/memory")[1].get("memory", {})
    bridges = [b for b in a.bridges.split(",") if b]
    call(a.url + "/api/memory", "POST", {"key": "child_age", "value": a.age})
    for b in bridges:
        call(a.url + "/api/memory", "POST", {"key": b, "value": True})
    fails, firsts, totals, skipped, done = [], [], [], [], 0
    try:
        for q in qs:
            if done >= a.n:
                break
            t0 = time.perf_counter()
            _, r = call(a.url + "/api/ask", "POST", {"text": q, "mode": "text", "lang": a.lang})
            t_first = (time.perf_counter() - t0) * 1000
            if r["status"] != "answered":
                skipped.append(q)   # recall abstained on this paraphrase (see run_abstention.py); try the next one
                continue
            done += 1
            for _ in range(60):   # poll every 300 ms up to 18 s
                code, full = call(a.url + "/api/ask/" + r["pending_id"])
                if code == 200 and not full.get("pending"):
                    break
                time.sleep(0.3)
            else:
                fails.append((q, "timeout"))
                continue
            firsts.append(r["first_sentence_ms"])
            totals.append(full["latency_ms"]["total"])
            spoken = [full.get("reaction", ""), full["first_sentence"], full["explanation"]]
            allt = " ".join(spoken + [full["ask_back"]])
            problems = []
            if a.lang == "en":
                parts = [s for t in spoken for s in wording.sentences_en(t)]
                if any(len(wording.words_en(s)) > wording.MAX_SENT_WORDS for s in parts):
                    problems.append("sentence>12 words")
                if len(wording.sentences_en(full["explanation"])) > (1 if a.age <= 6 else 2):
                    problems.append("explanation sentences")
                if wording.spoken_words(*spoken) > wording.MAX_TOTAL_WORDS:
                    problems.append("total>45 words")
                if any(wording.rare_score_en(s) > wording.MAX_RARE_EN for s in wording.sentences_en(full["explanation"])):
                    problems.append("uncommon words")
                if wording.has_banned_en(allt):
                    problems.append("banned term")
                if not wording.ask_ok_pattern_en(full["ask_back"]) or not wording.askback_ok_en(full["ask_back"]):
                    problems.append("ask-back pattern/blocklist")
                if wording.NOT_ALLOWED_EN.search(allt):
                    problems.append("feelings/flattery")
            else:
                parts = [s for t in spoken for s in wording.sentences(t)]
                if any(wording.chars_of(s) > 18 for s in parts):
                    problems.append("sentence>18")
                if sum(wording.chars_of(t) for t in spoken) > 60:
                    problems.append("total>60")
                if wording.has_banned(allt):
                    problems.append("banned term")
                if not wording.ask_ok_pattern(full["ask_back"]) or not askback_ok(full["ask_back"]):
                    problems.append("ask-back pattern/blocklist")
                if wording.NOT_ALLOWED.search(allt):
                    problems.append("feelings/flattery")
            tag = "OK  " if not problems else "FAIL"
            print(f"{tag} [{full['compose_source']}] {q}\n     {full.get('reaction','')} {full['first_sentence']} {full['explanation']}"
                  f"\n     ? {full['ask_back']}  (bridge={full['bridge_used']}, first={r['first_sentence_ms']} ms,"
                  f" request->response {t_first:.0f} ms)")
            if problems:
                fails.append((q, ",".join(problems)))
    finally:
        for k in ["child_age", *bridges]:
            if k in old:
                call(a.url + "/api/memory", "POST", {"key": k, "value": old[k]["value"]})
            else:
                call(a.url + "/api/memory?key=" + k, "DELETE")
    print(f"\n{done - len(fails)}/{done} passed ({len(skipped)} abstained, replaced); first_sentence_ms max {max(firsts or [0])}, "
          f"full answer ms mean {sum(totals) / max(1, len(totals)):.0f}")
    for q, why in fails:
        print("  fail:", q, why)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
