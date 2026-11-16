"""Dedup for bank v2: embed q + variants of every old and new item (retrieve.py's model and normalisation), and for each
new item find the most similar OTHER item (score = max cosine over all row pairs, i.e. any q/variant vs any q/variant).
Writes parts_v2/dedup_pairs.json: [{"id", "best", "score", "kind": old|new, "q", "best_q"}] for every new item, sorted by score.
Usage: python dedup_v2.py   (HF_HUB_OFFLINE=1)"""
import json, glob, sys
import numpy as np
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from retrieve import norm, model  # noqa: E402


def load_new():
    out = []
    for f in sorted(glob.glob(str(HERE / "parts_v2" / "w[0-9][0-9]_*.jsonl"))):
        out += [json.loads(l) for l in open(f, encoding="utf-8-sig") if l.strip()]
    return out


def main():
    old = [json.loads(l) for l in open(HERE / "bank_en.jsonl", encoding="utf-8")]
    new = load_new()
    items = old + new
    rows, owner = [], []
    for i, d in enumerate(items):
        for t in [d["q"]] + d["variants"]:
            rows.append(norm(t)); owner.append(i)
    owner = np.array(owner)
    m = model()
    E = m.encode(rows, normalize_embeddings=True, show_progress_bar=False, batch_size=128).astype(np.float32)
    starts = np.r_[0, np.flatnonzero(np.diff(owner)) + 1]          # first row of each item (rows are contiguous)
    n_old = len(old)
    new_rows = np.flatnonzero(owner >= n_old)
    best_item = np.full(len(items), -1.0, dtype=np.float32); best_idx = np.zeros(len(items), dtype=int)
    for s in range(0, len(new_rows), 1500):
        r = new_rows[s:s + 1500]
        S = E[r] @ E.T                                              # rows x all rows
        S = np.maximum.reduceat(S, starts, axis=1)                  # rows x items
        S[np.arange(len(r)), owner[r]] = -1.0                       # not itself
        j = S.argmax(1); v = S[np.arange(len(r)), j]
        for k, row in enumerate(r):
            o = owner[row]
            if v[k] > best_item[o]:
                best_item[o] = v[k]; best_idx[o] = j[k]
    out = []
    for i in range(n_old, len(items)):
        b = int(best_idx[i])
        out.append({"id": items[i]["id"], "best": items[b]["id"], "score": round(float(best_item[i]), 4),
                    "kind": "old" if b < n_old else "new", "q": items[i]["q"], "best_q": items[b]["q"]})
    out.sort(key=lambda x: -x["score"])
    json.dump(out, open(HERE / "parts_v2" / "dedup_pairs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    sc = np.array([x["score"] for x in out])
    print("new items", len(new), "rows", len(rows))
    for t in (0.95, 0.92, 0.90, 0.88, 0.85):
        sel = [x for x in out if x["score"] >= t]
        print(f">= {t}: {len(sel)} (vs old {sum(x['kind']=='old' for x in sel)}, vs new {sum(x['kind']=='new' for x in sel)})")


if __name__ == "__main__":
    main()
