"""Offline principle-matching harness: loads the recall index + principle library (no hub, no worker) and reports, per
question set, which questions the principle library would answer when recall does not (recall score < threshold).
Usage: python eval/principles/offline_match.py [set.jsonl ...]   (overrides: PRINC_FLOOR / PRINC_MARGIN env vars)"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hub.config import load_config  # noqa: E402
from hub.principles import Principles  # noqa: E402
from hub.recall import Recall  # noqa: E402


def load(cfg_over=None):
    cfg = load_config()
    cfg.setdefault("principles", {}).update(cfg_over or {})
    rc = Recall(cfg)
    return cfg, rc, Principles(cfg, rc)


def run(rc, pr, path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    out = []
    for r in rows:
        if r.get("lang", "en") != "en":
            continue
        q = r.get("q") or r.get("question")
        entry, score = rc.search(q, "en", None)
        via_entry = entry is not None and score >= rc.threshold
        m = None if via_entry else pr.search(q, "en", None)
        out.append({"id": r.get("id"), "q": q, "entry": entry["id"] if via_entry else None, "pid": m["id"] if m else None,
                    "answer": m["answer"] if m else None, "score": round(m["score"], 3) if m else None, "last": pr.last})
    return out


if __name__ == "__main__":
    cfg, rc, pr = load()
    for p in sys.argv[1:] or ["eval/heldout_en_v2.jsonl"]:
        res = run(rc, pr, ROOT / p)
        n = sum(1 for r in res if r["pid"])
        print(f"{p}: {len(res)} q, entry {sum(1 for r in res if r['entry'])}, principle {n}")
        for r in res:
            if r["pid"]:
                print(f"  {r['id']} {r['pid']:22s} {r['score']} | {r['q']} -> {r['answer']}")
