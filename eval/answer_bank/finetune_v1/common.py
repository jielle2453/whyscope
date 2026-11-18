"""Shared helpers for the retriever fine-tune (train.py, evaluate.py): the bank, the hub's normalisation, the two models,
an index with the hub's scoring (max cosine over an item's q + variants), and the held-out evaluation questions."""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from hub.recall import normalize_en  # noqa: E402  (the hub's own English normalisation)

BANK_FILE = ROOT / "knowledge" / "answer_bank_en.jsonl"
BASE = "paraphrase-multilingual-MiniLM-L12-v2"
FT_DIR = ROOT / "models" / "recall" / "whyscope-minilm-en-v1"
WORK = HERE / "work"


def load_jsonl(fn):
    return [json.loads(l) for l in open(fn, encoding="utf-8") if l.strip()]


def bank():
    return [d for d in load_jsonl(BANK_FILE) if d.get("id") and d.get("q") and d.get("a1")]


def sensitive(d):
    return str(d.get("notes") or "").startswith("sensitive:")


def model(name="base", device=None):
    from sentence_transformers import SentenceTransformer
    import torch
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    if name == "base":
        return SentenceTransformer(BASE, device=dev, cache_folder=str(ROOT / "models" / "hf"), local_files_only=True)
    return SentenceTransformer(str(name if name != "ft" else FT_DIR), device=dev, local_files_only=True)


def embed(m, texts, bs=128):
    return m.encode([normalize_en(t) for t in texts], normalize_embeddings=True, show_progress_bar=False,
                    batch_size=bs, convert_to_numpy=True).astype(np.float32)


class Index:
    """Rows = q + variants of every item (as hub/bank.py); score(item) = max cosine over its rows."""

    def __init__(self, m, items, exclude_rows=None):
        self.items = items
        self.rows, owner = [], []
        for i, d in enumerate(items):
            for t in [d["q"]] + list(d.get("variants") or []):
                if normalize_en(t):
                    self.rows.append(t)
                    owner.append(i)
        self.owner = np.asarray(owner, dtype=np.int64)
        self.mat = embed(m, self.rows)
        self.m = m

    def scores(self, Q, drop_items=None, drop_rows=None):
        """Q: (n, d) query embeddings -> (n, n_items) item scores. drop_items: per query an item index to remove
        (leave-item-out); drop_rows: per query a row index to remove (the query's own row)."""
        S = Q @ self.mat.T
        if drop_rows is not None:
            for k, r in enumerate(drop_rows):
                if r is not None and r >= 0:
                    S[k, r] = -1.0
        out = np.full((Q.shape[0], len(self.items)), -1.0, dtype=np.float32)
        # rows are contiguous per item: reduceat over the start of each item's block
        starts = np.flatnonzero(np.r_[True, self.owner[1:] != self.owner[:-1]])
        out[:, self.owner[starts]] = np.maximum.reduceat(S, starts, axis=1)
        if drop_items is not None:
            for k, i in enumerate(drop_items):
                if i is not None and i >= 0:
                    out[k, i] = -1.0
        return out

    def top(self, texts, k=5, **kw):
        Q = embed(self.m, texts)
        sc = self.scores(Q, **kw)
        idx = np.argsort(-sc, axis=1)[:, :k]
        return [[(self.items[j]["id"], float(sc[n, j])) for j in row] for n, row in enumerate(idx)], sc


def heldout_questions():
    """Every existing evaluation question (never trained on): the 145 routing set (heldout_en_v3 + guess_fresh_en),
    heldout_en_v2, the abstention and chat sets, the v3 fresh probes, check_safety_en's lists, and fresh_v4 (clean,
    noisy grammar, ASR)."""
    ev = ROOT / "eval"
    out = []
    for f, tag in (("heldout_en_v3.jsonl", "v3"), ("guess_fresh_en.jsonl", "fresh"), ("heldout_en_v2.jsonl", "v2"),
                   ("abstention_set_en.jsonl", "abst"), ("chat_set_en.jsonl", "chat")):
        out += [(tag, d["q"]) for d in load_jsonl(ev / f)]
    out += [("probes", d["q"]) for d in load_jsonl(ev / "answer_bank" / "fixes_v3" / "gaps_v3_work" / "probes.jsonl")]
    sys.path.insert(0, str(ev))
    from check_safety_en import SENSITIVE, HARMLESS
    out += [("safety", q) for q in SENSITIVE + HARMLESS]
    fv = ev / "answer_bank" / "fresh_v4"
    for f in ("questions.jsonl", "noisy_grammar.jsonl"):
        if (fv / f).exists():
            out += [("fresh_v4", d["q"]) for d in load_jsonl(fv / f)]
    if (fv / "asr_test.jsonl").exists():
        out += [("fresh_v4", d["asr"]) for d in load_jsonl(fv / "asr_test.jsonl") if d.get("asr")]
    return out
