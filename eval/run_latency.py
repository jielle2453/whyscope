"""Time each pipeline stage over 10 text questions (in-process) and append a section to docs/benchmarks.md.

Usage: python eval/run_latency.py [--wav path.wav] [--mode cpu|gpu] [--no-write] [--url http://127.0.0.1:8000]
With --url the questions go through a RUNNING server over HTTP (POST /api/ask, then GET /api/ask/{id}) and the
wall-clock time to the first response is reported as `http_first_ms`; without it the pipeline runs in-process.
`first_sentence_ms` = time from request start to the first-phase response (the verbatim sentence can be spoken).
A temporary DB is used so your real events are untouched. Audio/images are never stored.
"""
import argparse
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hub.config import load_config  # noqa: E402
from hub.pipeline import Pipeline  # noqa: E402

QUESTIONS = ["為什麼蝸牛有殼", "蝸牛的殼是什麼", "為什麼會有彩虹", "彩虹是怎麼來的", "吸塵器為什麼會吸東西",
             "吸塵器是怎麼吸灰塵的", "為什麼人會死", "為什麼股票會跌", "為什麼蝸牛背著房子", "下雨後為什麼有彩虹"]
STAGES = ["safety", "recall", "compose", "first_sentence", "total"]


def http_run(url, qs):
    """(rows, statuses, sources, http_first_ms list) for questions asked through a running server."""
    import json
    import urllib.request

    def call(path, body=None):
        req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())

    rows, statuses, sources, first = [], [], [], []
    for q in qs:
        t = time.perf_counter()
        _, r = call("/api/ask", {"text": q, "mode": "text"})
        first.append((time.perf_counter() - t) * 1000)
        while r.get("pending"):
            time.sleep(0.1)
            code, r2 = call("/api/ask/" + r["pending_id"])
            if code == 200 and not r2.get("pending"):
                r = r2
        rows.append(r["latency_ms"])
        statuses.append(r["status"])
        sources.append(r.get("compose_source", r["status"]))
    return rows, statuses, sources, first


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1) + 0.4999)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--url", help="measure through a running server over HTTP instead of in-process")
    ap.add_argument("--mode", choices=["cpu", "gpu"], help="override config.yaml mode for this run")
    a = ap.parse_args()

    if a.url:
        call_first = []
        http_rows, statuses, sources, call_first = http_run(a.url.rstrip("/"), ["為什麼蝸牛有殼"] + QUESTIONS)
        rows, statuses, sources, call_first = http_rows[1:], statuses[1:], sources[1:], call_first[1:]
        ans = [r for r, st in zip(rows, statuses) if st == "answered"]
        lines = [f"| stage (answered questions, n={len(ans)}) | mean ms | p95 ms |", "|---|---|---|"]
        for s in STAGES:
            xs = [r.get(s, 0) for r in ans] or [0]
            lines.append(f"| {s} | {statistics.mean(xs):.0f} | {p95(xs):.0f} |")
        lines.append(f"| http_first_ms (POST /api/ask round trip, incl. HTTP) | {statistics.mean(call_first):.0f} | {p95(call_first):.0f} |")
        n_llm = sum(1 for s in sources if s == "llm")
        n_tpl = sum(1 for s in sources if str(s).startswith("template"))
        out = (f"### Latency run via HTTP {time.strftime('%Y-%m-%d %H:%M')} ({a.url})\n\n"
               f"- 10 text questions through the running server; statuses "
               f"{dict((k, statuses.count(k)) for k in sorted(set(statuses)))}; LLM output accepted: {n_llm}, template: {n_tpl}\n\n"
               + "\n".join(lines) + "\n")
        print(out)
        if not a.no_write:
            with open(ROOT / "docs" / "benchmarks.md", "a", encoding="utf-8") as fh:
                fh.write("\n" + out)
        return

    cfg = load_config()
    if a.mode:
        cfg["mode"] = a.mode
    tmp = tempfile.mkdtemp()
    cfg["paths"]["db"] = str(Path(tmp) / "bench.db")
    t0 = time.perf_counter()
    p = Pipeline(cfg, preload_models=False)
    for _ in range(100):                      # wait (<=120 s) for the LLM to finish loading
        if p.composer.ready or p.composer.error or not cfg["compose"].get("enabled", True):
            break
        time.sleep(1.2)
    startup = time.perf_counter() - t0
    p.ask("為什麼蝸牛有殼", log=False)           # warm-up, discarded
    for _ in range(3):                          # a few more warm-ups so the CUDA kernels / caches are hot
        p.ask_first("為什麼會有彩虹", log=False)
    rows, sources, statuses = [], [], []
    for q in QUESTIONS:
        r1 = p.ask_first(q, log=False)            # phase 1: first sentence
        r = p.wait(r1["pending_id"]) if r1.get("pending_id") else r1   # phase 2: explanation + ask-back
        rows.append(r["latency_ms"])
        statuses.append(r["status"])
        sources.append(r.get("compose_source", r["status"]))
    ans = [r for r, st in zip(rows, statuses) if st == "answered"]  # stage stats over answered questions only
    asr = []
    if a.wav:
        data = Path(a.wav).read_bytes()
        p.listener.warm()
        p.ask(audio=data, log=False)
        for _ in range(3):
            r = p.ask(audio=data, mode="voice", log=False)
            asr.append(r["latency_ms"]["listen"])

    lines = [f"| stage (answered questions, n={len(ans)}) | mean ms | p95 ms |", "|---|---|---|"]
    for s in STAGES:
        xs = [r.get(s, 0) for r in ans] or [0]
        lines.append(f"| {s} | {statistics.mean(xs):.0f} | {p95(xs):.0f} |")
    if asr:
        lines.append(f"| listen (ASR on a {Path(a.wav).stat().st_size // 1000} kB wav, n=3) | {statistics.mean(asr):.0f} | {max(asr):.0f} |")
    n_llm = sum(1 for s in sources if s == "llm")
    n_tpl = sum(1 for s in sources if str(s).startswith("template"))
    st = p.status()
    head = (f"### Latency run {time.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"- machine: {platform.processor() or platform.machine()}, {platform.platform()}, Python {platform.python_version()}\n"
            f"- config mode: `{cfg['mode']}`; device used: `{st['device']}`; compose backend: `{st['compose_backend']}`"
            f" (error: {st['compose_error']}); model startup: {startup:.1f} s\n"
            f"- 10 text questions, warm models, in-process (no HTTP). statuses: "
            f"{dict((k, statuses.count(k)) for k in sorted(set(statuses)))}; LLM output accepted: {n_llm}, "
            f"template fallback: {n_tpl}\n")
    out = head + "\n" + "\n".join(lines) + "\n\n`first_sentence` = `first_sentence_ms` = time from request start to the first-phase response " \
        "(listen + safety + vision + recall; it never waits for the LLM). `total` = until explanation and ask-back are ready.\n"
    print(out)
    if not a.no_write:
        f = ROOT / "docs" / "benchmarks.md"
        f.parent.mkdir(exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write("\n" + out)
        print("appended to", f)


if __name__ == "__main__":
    main()
