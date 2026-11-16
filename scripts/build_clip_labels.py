"""Precompute CLIP text embeddings for every object label, so the hub never needs the CLIP text encoder at run time.

    set PYTHONIOENCODING=utf-8
    C:\\whyscope-venv\\Scripts\\python scripts\\build_clip_labels.py [--pretrained openai|laion2b_s34b_b79k] [--cache-dir DIR] [--out FILE]

Sources: knowledge/entries/*/*.json (labels = zh + ascii names, en.labels = English names) and, if present,
knowledge/principles/principles.json (every `applies_to_en` list).
Output: models/clip/labels_<name>.npz with arrays labels (str), lang (zh|en), entry_id, emb (float16, L2-normalised).
Rerunnable: always rebuilds from the current knowledge base. Needs the weights already on disk (HF_HUB_OFFLINE=1 is fine).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SHORT = {"openai": "openai", "laion2b_s34b_b79k": "laion2b"}


def _principle_labels(path: Path):
    """Yield (label, principle_id) from every applies_to_en list, wherever it sits in the JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))

    def walk(node, pid):
        if isinstance(node, dict):
            pid = str(node.get("id") or node.get("name") or pid)
            for k, v in node.items():
                if k == "applies_to_en" and isinstance(v, list):
                    for s in v:
                        if isinstance(s, str) and s.strip():
                            yield s.strip(), "principle:" + pid
                else:
                    yield from walk(v, pid)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v, pid)

    yield from walk(data, "")


def collect(root: Path):
    """[(label, lang, entry_id)], de-duplicated on (label.lower(), entry_id)."""
    rows, seen = [], set()

    def add(label, lang, eid):
        label = str(label).strip()
        k = (label.lower(), eid)
        if label and k not in seen:
            seen.add(k)
            rows.append((label, lang, eid))

    for p in sorted((root / "knowledge" / "entries").glob("*/*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        eid = e.get("id") or p.stem
        for l in e.get("labels", []):
            add(l, "en" if l.isascii() else "zh", eid)
        for l in (e.get("en") or {}).get("labels", []):
            add(l, "en", eid)
    pp = root / "knowledge" / "principles" / "principles.json"
    if pp.exists():
        for l, pid in _principle_labels(pp):
            add(l, "en", pid)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pretrained", default="openai")
    ap.add_argument("--model", default="ViT-B-32-quickgelu")  # the OpenAI weights were trained with QuickGELU
    ap.add_argument("--cache-dir", default=None, help="default: <whyscope data dir>/models/clip, else repo models/clip")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    import torch
    import open_clip

    cache = Path(a.cache_dir) if a.cache_dir else None
    if cache is None:
        for c in (ROOT / "models" / "clip", ROOT.parent / "whyscope" / "models" / "clip"):
            if c.exists():
                cache = c
                break
        cache = cache or ROOT / "models" / "clip"
    out = Path(a.out) if a.out else cache / f"labels_{SHORT.get(a.pretrained, a.pretrained)}.npz"
    rows = collect(ROOT)
    if not rows:
        sys.exit("no labels found")
    clip, _, _ = open_clip.create_model_and_transforms(a.model, pretrained=a.pretrained, cache_dir=str(cache), device="cpu")
    clip.eval()
    tok = open_clip.get_tokenizer(a.model)
    embs = []
    with torch.no_grad():
        for i in range(0, len(rows), 128):
            t = clip.encode_text(tok([f"a photo of a {r[0]}" for r in rows[i:i + 128]]))
            embs.append((t / t.norm(dim=-1, keepdim=True)).numpy())
    emb = np.concatenate(embs).astype(np.float16)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, labels=np.array([r[0] for r in rows]), lang=np.array([r[1] for r in rows]),
             entry_id=np.array([r[2] for r in rows]), emb=emb)
    print(f"{len(rows)} labels ({sum(r[1] == 'zh' for r in rows)} zh) -> {out}")


if __name__ == "__main__":
    main()
