"""Fine-tune the answer bank's English retriever (paraphrase-multilingual-MiniLM-L12-v2) on the bank itself.

Training data (bank only, nothing from any evaluation set):
  - positives: q <-> variant and variant <-> variant of the same item;
  - child speech: subagent rewrites of 2,400 bank questions (work/child_aug/out_*.jsonl: broken grammar, Taiwanese
    learner English, overregularisation, baby words, disfluencies, fragments) -> paired with a clean row of the item;
  - real ASR noise: 1,900 bank rows / rewrites spoken by SAPI TTS (Zira), made child-like, transcribed by faster-whisper
    small (asr_noise.py --profile train, work/asr_train.jsonl) -> paired with a clean row of the item;
  - hard negatives: per item, the 10 items the BASE model ranks closest (max cosine row to row); likely false negatives
    (near-duplicate items answering the same question) are dropped: q-score >= 0.97, or q-score >= 0.92 with a1 cosine
    >= 0.80. Those near-duplicates are also kept out of each other's batches (no in-batch false negatives);
  - 43 hand-written word-sense contrast triplets (contrast_pairs.jsonl: a cold / cold weather, laugh / laugh at me ...).
Loss: MultipleNegativesRankingLoss with the mined hard negative (in-batch negatives + 1 hard negative per anchor, scale
20), batches with one example per item cluster. AdamW 2e-5, 10% warm-up, 3 epochs, best epoch by validation top-1.
Validation: 8% of the items (seed 13) are never trained on (not as positives, not as negatives); their variants
(own row removed from the index), child rewrites and ASR transcripts are the validation queries.
Decontamination: every training text with base cosine >= 0.95 to any evaluation question (common.heldout_questions:
the 145 set, heldout_v2, abstention, chat, v3 probes, check_safety_en, fresh_v4 clean/noisy/ASR) is dropped.

Output: models/recall/whyscope-minilm-en-v1/ (refuses to overwrite), work/train_log.json, work/split.json.
Usage (HF_HUB_OFFLINE=1): C:\\whyscope-venv\\Scripts\\python.exe eval\\answer_bank\\finetune_v1\\train.py
"""
import json
import math
import random
import shutil
import sys
import time
from collections import defaultdict

import numpy as np
import torch
import torch.nn.functional as F

from common import FT_DIR, WORK, HERE, Index, bank, embed, heldout_questions, load_jsonl, model, normalize_en

SEED = 13
VAL_SHARE = 0.08
EPOCHS = 3
BATCH = 64
LR = 2e-5
SCALE = 20.0
PAIRS_PER_ITEM = 4
DECON = 0.95


def main():
    if FT_DIR.exists() and any(FT_DIR.iterdir()):
        sys.exit(f"{FT_DIR} exists: versioned output, not overwriting")
    rng = random.Random(SEED)
    torch.manual_seed(SEED)
    items = bank()
    ids = [d["id"] for d in items]
    pos = {d["id"]: i for i, d in enumerate(items)}
    clean = {d["id"]: [t for t in [d["q"]] + list(d.get("variants") or []) if normalize_en(t)] for d in items}
    multi = [i for i in ids if len(clean[i]) >= 2]
    val = set(rng.sample(multi, int(VAL_SHARE * len(items))))

    # augmentation texts per item
    aug = defaultdict(list)
    for k in range(1, 7):
        for d in load_jsonl(WORK / "child_aug" / f"out_{k}.jsonl"):
            for r, st in zip(d["rw"], d.get("st", [""] * 2)):
                aug[d["id"]].append(("child:" + st, r))
    for d in load_jsonl(WORK / "asr_train.jsonl"):
        a = d.get("asr") or ""
        # keep transcripts that still share a content word with the source (drops "Thank you." style hallucinations)
        src = set(normalize_en(d["text"]).split())
        if a and (set(normalize_en(a).split()) & src) - {"why", "do", "does", "the", "a", "is", "how", "what", "my", "i"}:
            aug[d["id"]].append(("asr", a))

    base = model("base")
    # ---- decontamination against every evaluation question ----
    hq = [q for _, q in heldout_questions()]
    H = embed(base, hq)
    cand = sorted({t for i in ids for t in clean[i]} | {t for i in aug for _, t in aug[i]})
    C = embed(base, cand)
    mx = np.zeros(len(cand), dtype=np.float32)
    for s in range(0, len(cand), 4096):
        mx[s:s + 4096] = (C[s:s + 4096] @ H.T).max(axis=1)
    banned = {t for t, v in zip(cand, mx) if v >= DECON}
    print(f"decontamination: {len(banned)} of {len(cand)} texts have cosine >= {DECON} to an evaluation question; dropped")

    # ---- hard negatives with the base model ----
    ix = Index(base, items)
    Q = ix.mat
    sc = np.full((len(items), len(items)), -1.0, dtype=np.float32)
    starts = np.flatnonzero(np.r_[True, ix.owner[1:] != ix.owner[:-1]])
    for s in range(0, len(Q), 2048):
        part = ix.scores(Q[s:s + 2048])   # (rows, items)
        np.maximum.at(sc, ix.owner[s:s + 2048], part)
    np.fill_diagonal(sc, -1.0)
    A1 = embed(base, [d["a1"] for d in items])
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    negs, dropped, kept_examples, dropped_examples = {}, 0, [], []
    for i, d in enumerate(items):
        order = np.argsort(-sc[i])[:10]
        keep = []
        for j in order:
            a1c = float(A1[i] @ A1[j])
            if sc[i, j] >= 0.97 or (sc[i, j] >= 0.92 and a1c >= 0.80):
                dropped += 1
                parent[find(i)] = find(int(j))
                if len(dropped_examples) < 400:
                    dropped_examples.append((d["q"], items[j]["q"], round(float(sc[i, j]), 3), round(a1c, 3)))
                continue
            if items[j]["id"] in val:
                continue
            keep.append(int(j))
            if len(kept_examples) < 400 and len(keep) == 1:
                kept_examples.append((d["q"], items[j]["q"], round(float(sc[i, j]), 3), round(a1c, 3)))
        negs[i] = keep
    cluster = [find(i) for i in range(len(items))]
    print(f"hard negatives: {sum(map(len, negs.values()))} kept, {dropped} dropped as likely same question; "
          f"{len(set(cluster))} clusters for {len(items)} items")
    rs = random.Random(1)
    json.dump({"dropped_sample": rs.sample(dropped_examples, min(40, len(dropped_examples))),
               "kept_top1_sample": rs.sample(kept_examples, min(40, len(kept_examples)))},
              open(WORK / "hardneg_sanity.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    del base
    torch.cuda.empty_cache()

    contrast = load_jsonl(HERE / "contrast_pairs.jsonl")

    def epoch_examples():
        ex = []
        for i, d in enumerate(items):
            if d["id"] in val:
                continue
            rows = [t for t in clean[d["id"]] if t not in banned]
            pairs = []
            if len(rows) >= 2:
                for _ in range(PAIRS_PER_ITEM):
                    a, p = rng.sample(rows, 2)
                    pairs.append((a, p))
            if rows:
                for _, t in aug.get(d["id"], []):
                    if t not in banned:
                        pairs.append((t, rng.choice(rows)))
            for a, p in pairs:
                n_item = rng.choice(negs[i]) if negs[i] else None
                n_txt = rng.choice(clean[items[n_item]["id"]]) if n_item is not None else None
                ex.append({"a": a, "p": p, "n": n_txt, "c": cluster[i], "nc": cluster[n_item] if n_item is not None else -1})
        for k, c in enumerate(contrast * 4):
            ex.append({"a": c["a"], "p": c["p"], "n": c["n"], "c": -10 - (k % len(contrast)), "nc": -1000 - (k % len(contrast))})
        rng.shuffle(ex)
        # batches with one example per cluster (anchor cluster and hard-negative cluster both unique in the batch)
        batches, pending = [], ex
        while pending:
            b, used, rest = [], set(), []
            for e in pending:
                if len(b) < BATCH and e["c"] not in used and e["nc"] not in used:
                    b.append(e)
                    used.add(e["c"])
                    if e["nc"] != -1:
                        used.add(e["nc"])
                else:
                    rest.append(e)
            batches.append(b)
            pending = rest
        return batches

    # ---- validation queries ----
    vq = []   # (text, item index, own row index or -1, kind)
    vix_rows = {}
    for i, d in enumerate(items):
        if d["id"] not in val:
            continue
        for t in clean[d["id"]][1:]:
            vq.append((t, i, "variant"))
        for kind, t in aug.get(d["id"], []):
            vq.append((t, i, kind.split(":")[0]))
    json.dump({"val_items": sorted(val), "seed": SEED, "banned": sorted(banned)},
              open(WORK / "split.json", "w", encoding="utf-8"))

    def validate(m):
        m.eval()
        vix = Index(m, items)
        row_of = {}
        for r, (t, o) in enumerate(zip(vix.rows, vix.owner)):
            row_of[(int(o), normalize_en(t))] = r
        dr = [row_of.get((i, normalize_en(t)), -1) if k == "variant" else -1 for t, i, k in vq]
        S = vix.scores(embed(m, [t for t, _, _ in vq]), drop_rows=dr)
        top1 = S.argmax(axis=1)
        out = {}
        for kind in ("variant", "child", "asr", "all"):
            sel = [n for n, (_, _, k) in enumerate(vq) if kind == "all" or k == kind]
            out[kind] = {"n": len(sel), "top1": round(float(np.mean([top1[n] == vq[n][1] for n in sel])), 4)}
        return out

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = model("base", dev)
    log = {"val_base": validate(m), "epochs": []}
    print("validation, base:", log["val_base"])
    first = epoch_examples()
    steps = EPOCHS * len(first)
    opt = torch.optim.AdamW(m.parameters(), lr=LR, weight_decay=0.01)
    warm = int(0.1 * steps)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / max(1, warm) if s < warm else max(0.0, (steps - s) / max(1, steps - warm)))

    def enc(texts):
        f = m.tokenize([normalize_en(t) for t in texts])
        f = {k: (v.to(dev) if hasattr(v, "to") else v) for k, v in f.items()}
        return F.normalize(m(f)["sentence_embedding"], dim=-1)

    best, step = -1.0, 0
    tmp_dir = WORK / "best_tmp"
    for ep in range(EPOCHS):
        batches = first if ep == 0 else epoch_examples()
        m.train()
        t0, tot = time.time(), 0.0
        for b in batches:
            a = enc([e["a"] for e in b])
            hn = [e for e in b if e["n"]]
            cands = enc([e["p"] for e in b] + [e["n"] for e in hn])
            cc = torch.tensor([e["c"] for e in b] + [e["nc"] for e in hn], device=dev)
            ac = torch.tensor([e["c"] for e in b], device=dev)
            logits = a @ cands.T * SCALE
            mask = (ac[:, None] == cc[None, :])
            eye = torch.zeros_like(mask)
            eye[torch.arange(len(b)), torch.arange(len(b))] = True
            logits = logits.masked_fill(mask & ~eye, -1e4)
            loss = F.cross_entropy(logits, torch.arange(len(b), device=dev))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += float(loss)
            step += 1
        v = validate(m)
        log["epochs"].append({"epoch": ep + 1, "batches": len(batches), "examples": sum(map(len, batches)),
                              "loss": round(tot / len(batches), 4), "val": v, "s": round(time.time() - t0, 1)})
        print(log["epochs"][-1], flush=True)
        if v["all"]["top1"] > best:
            best = v["all"]["top1"]
            m.save(str(tmp_dir))
            log["best_epoch"] = ep + 1
    FT_DIR.parent.mkdir(parents=True, exist_ok=True)
    if FT_DIR.exists():
        FT_DIR.rmdir()   # empty (checked at the start)
    shutil.move(str(tmp_dir), str(FT_DIR))
    json.dump(log, open(WORK / "train_log.json", "w", encoding="utf-8"), indent=1)
    print("saved", FT_DIR, "best epoch", log["best_epoch"])


if __name__ == "__main__":
    main()
