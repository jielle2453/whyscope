"""Time each pipeline stage over 10 text questions (in-process) and append a section to docs/benchmarks.md.

Usage: python eval/run_latency.py [--wav path.wav] [--mode cpu|gpu] [--no-write]
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


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1) + 0.4999)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--mode", choices=["cpu", "gpu"], help="override config.yaml mode for this run")
    a = ap.parse_args()

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
    rows, sources, statuses = [], [], []
    for q in QUESTIONS:
        r = p.ask(q, log=False)
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
    out = head + "\n" + "\n".join(lines) + "\n\n`first_sentence` = time until the verbatim KB sentence could be spoken " \
        "(listen + safety + vision + recall; it never waits for the LLM).\n"
    print(out)
    if not a.no_write:
        f = ROOT / "docs" / "benchmarks.md"
        f.parent.mkdir(exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write("\n" + out)
        print("appended to", f)


if __name__ == "__main__":
    main()
