"""Retrieval over the frozen answer bank (same embedding model as hub/recall.py). Usage: python retrieve.py"""
import json, re, time, random, sys, collections
import numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
_P = re.compile(r"[^a-z0-9 ]+")
def norm(q):
    q = (q or "").lower().replace("’", "'").replace("'s ", " ").replace("'", "")
    return " ".join(_P.sub(" ", q).split())
def load_bank():
    return [json.loads(l) for l in open(ROOT/"eval/answer_bank/bank_en.jsonl", encoding="utf-8")]
def model():
    from sentence_transformers import SentenceTransformer
    cache = str(ROOT/"models"/"hf")
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device="cpu", cache_folder=cache, local_files_only=True)
class Bank:
    def __init__(s, items, m):
        s.items, s.m = items, m
        rows, owner = [], []
        for i, d in enumerate(items):
            for t in [d["q"]] + d["variants"]:
                rows.append(norm(t)); owner.append(i)
        s.owner = np.array(owner)
        s.mat = m.encode(rows, normalize_embeddings=True, show_progress_bar=False, batch_size=64).astype(np.float32)
    def search(s, text, k=3):
        v = s.m.encode([norm(text)], normalize_embeddings=True, show_progress_bar=False)[0]
        sims = s.mat @ v
        best = np.full(len(s.items), -1.0, dtype=np.float32)
        np.maximum.at(best, s.owner, sims)
        idx = np.argsort(-best)[:k]
        return [(int(i), float(best[i])) for i in idx]
def subsets(items, sizes=(250, 500), seed=1):
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for i, d in enumerate(items): by[d["id"][:3]].append(i)
    for v in by.values(): rng.shuffle(v)
    order = []   # round-robin by topic group proportional: shuffle within group, interleave by rank fraction
    keyed = []
    for g, v in by.items():
        for r, i in enumerate(v): keyed.append(((r + 0.5) / len(v) + rng.random() * 1e-3, i))
    keyed.sort()
    order = [i for _, i in keyed]
    return {n: sorted(order[:n]) for n in sizes}
if __name__ == "__main__":
    items = load_bank(); m = model()
    sets = {"v3": "heldout_en_v3.jsonl", "fresh": "guess_fresh_en.jsonl"}
    qs = []
    for tag, f in sets.items():
        for l in open(ROOT/"eval"/f, encoding="utf-8"):
            d = json.loads(l); qs.append({"id": d["id"], "set": tag, "q": d["q"]})
    qs += [{"id": "u-1", "set": "user", "q": "Why my hair is black? I want a blonded hair"}, {"id": "u-2", "set": "user", "q": "why i need to go to bed at 10"}]
    res = {}
    full = Bank(items, m)
    sub = subsets(items)
    banks = {"1182": (full, None)}
    for n, ix in sub.items():
        banks[str(n)] = (Bank([items[i] for i in ix], m), ix)
    ts = []
    for q in qs:
        r = {}
        for n, (b, ix) in banks.items():
            t = time.perf_counter()
            top = b.search(q["q"], 3)
            ts.append((time.perf_counter() - t) * 1000 if n == "1182" else 0)
            ids = [(b.items[i]["id"], s) for i, s in top]
            r[n] = ids
        q["top"] = r
    json.dump(qs, open(ROOT/"eval/answer_bank/retrieval_top.json", "w", encoding="utf-8"), ensure_ascii=False)
    ts = [t for t in ts if t]
    print("n", len(qs), "retrieval ms median", np.median(ts), "p95", np.percentile(ts, 95))
