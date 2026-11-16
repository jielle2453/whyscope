"""Whyscope compose on the UGen300 (Windows or Linux). Run with the Python that has the HailoRT wheel installed.

    python scripts/check_ugen.py --hef <path to the Qwen2.5-1.5B-Instruct HEF> [--runs 3] [--entry animals-snail-shell]

Loads the LLM on the Hailo-10H through hub/hailo.py, then answers the same knowledge entry several times through the
real Composer (prompt, grounding check, wording rules, template fallback) and prints the time and result of each run.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hub.config import load_config  # noqa: E402


def find_entry(entry_id: str) -> dict:
    for p in (ROOT / "knowledge" / "entries").glob("*/*.json"):
        if p.stem == entry_id:
            return json.loads(p.read_text(encoding="utf-8"))
    sys.exit(f"knowledge entry not found: {entry_id}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hef", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--entry", default="animals-snail-shell")
    ap.add_argument("--age", type=int, default=6)
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    a = ap.parse_args()

    cfg = load_config()
    cfg["mode"] = "hailo"
    cfg.setdefault("hailo", {})["llm_hef"] = str(Path(a.hef).resolve())
    cfg["compose"]["timeout_s_hailo"] = 60.0   # measure the real time instead of falling back

    from hub.compose import Composer
    from hub.hailo import HailoLLM

    t = time.perf_counter()
    c = Composer.__new__(Composer)       # set up by hand so loading is timed here, not in a thread
    Composer.__init__(c, {**cfg, "compose": {**cfg["compose"], "enabled": False}})
    c.cfg = cfg["compose"]
    c.llm, c.backend, c.ready = HailoLLM(cfg), "hailo", True
    print(f"model loaded on the UGen300 in {time.perf_counter() - t:.1f} s ({c.llm.name})")

    entry = find_entry(a.entry)
    print(f"entry: {a.entry} | first sentence: {entry['first_sentence']}")
    for i in range(a.runs):
        t = time.perf_counter()
        raw = c._run(entry, a.age, a.lang)
        gen = time.perf_counter() - t
        res = c.compose(entry, a.age, [], lang=a.lang)
        total = time.perf_counter() - t
        print(f"\nrun {i + 1}: generate {gen:.2f} s (compose incl. a second generation {total:.2f} s)")
        print(f"  raw: {raw.strip()[:200]}")
        print(f"  result ({res['source']}): {res['explanation']} | ask back: {res['ask_back']}")
        if res["source"] != "llm":
            print(f"  rejected because: {c.last_reject}")


if __name__ == "__main__":
    main()
