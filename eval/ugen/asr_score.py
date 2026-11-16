"""Score asr_bench.py outputs: Chinese character error rate and English word error rate, plus latency.

    C:\\whyscope-hailo-venv\\Scripts\\python eval\\ugen\\asr_score.py <results1.jsonl> [<results2.jsonl> ...]

Chinese hypotheses are converted to Traditional (OpenCC s2twp) before scoring, because Whisper often writes
Simplified; punctuation and spaces are ignored. English is lower-cased and stripped of punctuation.
"""
import json
import re
import statistics
import sys

try:
    import opencc
    _CC = opencc.OpenCC("s2twp")
except Exception:  # pragma: no cover
    _CC = None


def edits(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def norm_zh(s: str) -> list:
    if _CC:
        s = _CC.convert(s)
    s = s.replace("妳", "你").replace("牠", "它").replace("祂", "他")
    return [c for c in re.sub(r"[\W_]+", "", s)]


def norm_en(s: str) -> list:
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower()).split()


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def main(paths):
    print(f"{'backend':32s} {'lang':4s} {'n':>3s} {'err%':>6s} {'exact':>6s} {'p50 s':>6s} {'p95 s':>6s} {'load s':>6s}")
    for p in paths:
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        for lang in ("zh", "en"):
            rs = [r for r in rows if r["lang"] == lang]
            if not rs:
                continue
            n_err = n_ref = exact = 0
            for r in rs:
                f = norm_zh if lang == "zh" else norm_en
                ref, hyp = f(r["ref"]), f(r["hyp"])
                e = edits(ref, hyp)
                n_err += e
                n_ref += len(ref)
                exact += e == 0
            secs = [r["sec"] for r in rs]
            print(f"{rs[0]['backend']:32s} {lang:4s} {len(rs):3d} {100 * n_err / max(1, n_ref):6.1f} {exact:6d} "
                  f"{statistics.median(secs):6.2f} {pct(secs, 0.95):6.2f} {rs[0].get('load_sec', 0):6.1f}")


if __name__ == "__main__":
    main(sys.argv[1:])
