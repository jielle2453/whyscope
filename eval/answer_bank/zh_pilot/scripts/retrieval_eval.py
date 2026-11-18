"""Retrieval sanity check for the zh pilot (same model and scoring as eval/answer_bank/retrieve.py: score of an item =
max cosine over its rows, paraphrase-multilingual-MiniLM-L12-v2, normalized embeddings).

Queries: ../retrieval/heldout_zh.jsonl (60 child questions, Chinese or mixed, written by a subagent that never saw the
pilot zh text; gold = the item id). Indexes:
  zh          pilot 300 items, q_zh + variants_zh
  zh_q        pilot 300 items, q_zh only (value of the variants)
  en          pilot 300 items, English q + variants (cross-lingual: Chinese question vs English text)
  zh+en       pilot 300 items, both
  en_full     all 5,139 bank items, English q + variants (what the hub could do today with no zh layer)
  zh+en_full  all 5,139 items, English rows + zh rows of the 300 pilot items
Metrics: top-1, top-3, MRR; "ans@0.80" = top-1 correct AND score >= answer_bank.threshold (0.80);
"wrong@0.80" = top-1 wrong but score >= 0.80 (a wrong answer would be spoken).
Usage: HF_HUB_OFFLINE=1 python retrieval_eval.py [pilot.jsonl]   -> ../retrieval/results.json + printed table"""
import json, re, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = HERE.parents[3]
THRESH = 0.80
_EN = re.compile(r"[^a-z0-9 ]+")
_ANY = re.compile(r"[^\w一-鿿 ]+")


def norm_en(q):  # as eval/answer_bank/retrieve.py
    q = (q or "").lower().replace("’", "'").replace("'s ", " ").replace("'", "")
    return " ".join(_EN.sub(" ", q).split())


def norm_any(q):
    return " ".join(_ANY.sub(" ", (q or "").lower()).split())


def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device="cpu",
                               cache_folder=str(ROOT / "models" / "hf"), local_files_only=True)


class Index:
    def __init__(self, rows, m):  # rows: [(item_id, text)]
        self.ids = sorted({i for i, _ in rows})
        pos = {i: k for k, i in enumerate(self.ids)}
        self.owner = np.array([pos[i] for i, _ in rows])
        self.mat = m.encode([t for _, t in rows], normalize_embeddings=True, show_progress_bar=False,
                            batch_size=64).astype(np.float32)

    def rank(self, v):
        best = np.full(len(self.ids), -1.0, dtype=np.float32)
        np.maximum.at(best, self.owner, self.mat @ v)
        order = np.argsort(-best)
        return [(self.ids[i], float(best[i])) for i in order[:10]], best, order


def main():
    pilot_f = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "pilot_zh.jsonl"
    pilot = [json.loads(l) for l in open(pilot_f, encoding="utf-8-sig") if l.strip()]
    bank = [json.loads(l) for l in open(ROOT / "knowledge" / "answer_bank_en.jsonl", encoding="utf-8")]
    bmap = {d["id"]: d for d in bank}
    qs = [json.loads(l) for l in open(OUT / "retrieval" / "heldout_zh.jsonl", encoding="utf-8-sig") if l.strip()]
    pids = {p["id"] for p in pilot}
    assert all(q["id"] in pids for q in qs)
    m = model()
    zh = [(p["id"], norm_any(t)) for p in pilot for t in [p["q_zh"]] + p["variants_zh"]]
    zhq = [(p["id"], norm_any(p["q_zh"])) for p in pilot]
    en = [(p["id"], norm_en(t)) for p in pilot for t in [bmap[p["id"]]["q"]] + bmap[p["id"]]["variants"]]
    en_full = [(d["id"], norm_en(t)) for d in bank for t in [d["q"]] + d["variants"]]
    idx = {"zh": Index(zh, m), "zh_q": Index(zhq, m), "en": Index(en, m), "zh+en": Index(zh + en, m),
           "en_full": Index(en_full, m), "zh+en_full": Index(en_full + zh, m)}
    qv = m.encode([norm_any(q["q"]) for q in qs], normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
    res, per_q = {}, []
    for q in qs:
        per_q.append({"id": q["id"], "q": q["q"], "kind": q["kind"], "top": {}})
    for name, ix in idx.items():
        stats = {k: {"n": 0, "top1": 0, "top3": 0, "mrr": 0.0, "ans": 0, "wrong_ans": 0, "gold_score": []}
                 for k in ("all", "zh", "mixed")}
        for qi, q in enumerate(qs):
            top, best, order = ix.rank(qv[qi])
            rank = [ix.ids[i] for i in order].index(q["id"]) + 1
            gold = float(best[ix.ids.index(q["id"])])
            per_q[qi]["top"][name] = {"rank": rank, "top1": top[0], "gold_score": round(gold, 3)}
            for k in ("all", q["kind"]):
                s = stats[k]
                s["n"] += 1; s["top1"] += rank == 1; s["top3"] += rank <= 3; s["mrr"] += 1 / rank
                s["ans"] += rank == 1 and top[0][1] >= THRESH
                s["wrong_ans"] += rank != 1 and top[0][1] >= THRESH
                s["gold_score"].append(gold)
        for k, s in stats.items():
            n = s["n"] or 1
            stats[k] = {"n": s["n"], "top1": round(s["top1"] / n, 3), "top3": round(s["top3"] / n, 3),
                        "mrr": round(s["mrr"] / n, 3), "ans@0.80": round(s["ans"] / n, 3),
                        "wrong@0.80": round(s["wrong_ans"] / n, 3),
                        "gold_score_median": round(float(np.median(s["gold_score"])), 3) if s["gold_score"] else None}
        res[name] = {"items": len(ix.ids), "rows": int(ix.mat.shape[0]), **stats}
    json.dump({"results": res, "queries": per_q}, open(OUT / "retrieval" / "results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{'index':12} {'items':>5} {'rows':>6} | {'top1':>5} {'top3':>5} {'mrr':>5} {'ans@.8':>6} {'wrong@.8':>8} "
          f"{'gold~':>5} | zh top1  mixed top1")
    for name, r in res.items():
        a = r["all"]
        print(f"{name:12} {r['items']:5} {r['rows']:6} | {a['top1']:5} {a['top3']:5} {a['mrr']:5} {a['ans@0.80']:6} "
              f"{a['wrong@0.80']:8} {a['gold_score_median']:5} | {r['zh']['top1']:7}  {r['mixed']['top1']}")


if __name__ == "__main__":
    main()
