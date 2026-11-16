"""Does the UGen300's CLIP image encoder match OpenAI or laion2b ViT-B/32?  Needs the worker's POST /clip_image on :8711.

    set HF_HUB_OFFLINE=1 & set PYTHONIOENCODING=utf-8
    C:\\whyscope-venv\\Scripts\\python eval\\ugen\\clip_match.py [openai laion2b_s34b_b79k ...]

Test set = snapshots + demo photos + crop/flip/resize variants + synthetic images. For each CPU model: cosine(UGen, CPU)
on the same image vs UGen-vs-UGen across different images; then zero-shot top-3 against models/clip/labels_<name>.npz.
"""
import glob
import io
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

BASE = Path(r"C:\Users\Jie\Desktop\whyscope\whyscope")
MODELS = BASE / "models" / "clip"
SHORT = {"openai": "openai", "laion2b_s34b_b79k": "laion2b"}
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ugen_embed(img):
    # the worker's Python has no Pillow: send the 224x224 uint8 crop (same preprocessing as vision_bench.clip_u8)
    w, h = img.size
    sc = 224 / min(w, h)
    im = img.resize((max(224, round(w * sc)), max(224, round(h * sc))), Image.BICUBIC)
    l, t = (im.size[0] - 224) // 2, (im.size[1] - 224) // 2
    raw = np.asarray(im.crop((l, t, l + 224, t + 224)), dtype=np.uint8).tobytes()
    r = OPEN.open(urllib.request.Request("http://127.0.0.1:8711/clip_image", data=raw,
                                         headers={"Content-Type": "application/x-raw-u8"}), timeout=30)
    e = np.array(json.loads(r.read())["embedding"], dtype=np.float32)
    return e / np.linalg.norm(e)


def test_images():
    out = []
    paths = sorted(glob.glob(str(BASE / "data" / "snapshots" / "*.jpg")) + glob.glob(str(BASE / "brand" / "demo-photos" / "*.jpg")))
    for p in paths:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        n = Path(p).name
        out += [(n, im), (n + " flip", im.transpose(Image.FLIP_LEFT_RIGHT)),
                (n + " crop", im.crop((w // 6, h // 6, w - w // 6, h - h // 6))),
                (n + " half", im.resize((max(64, w // 2), max(64, h // 2))))]
    for name, col in [("red", (220, 30, 30)), ("green", (30, 160, 60)), ("blue", (30, 60, 200)), ("yellow", (240, 220, 40))]:
        out.append(("synthetic " + name, Image.new("RGB", (320, 240), col)))
    im = Image.new("RGB", (320, 240), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((90, 50, 230, 190), fill=(240, 200, 0))
    out.append(("synthetic yellow circle", im))
    im = Image.new("RGB", (320, 240), (135, 206, 235))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 170, 320, 240), fill=(60, 160, 60))
    d.ellipse((240, 20, 290, 70), fill=(255, 220, 0))
    out.append(("synthetic sky sun grass", im))
    return out


def main():
    import torch
    import open_clip
    names = sys.argv[1:] or ["openai"]
    imgs = test_images()
    print(len(imgs), "test images")
    U = np.stack([ugen_embed(i) for _, i in imgs])
    base_sim = U @ U.T
    # baseline groups: image i vs image j from different source photos (names differ in prefix before first space)
    src = [n.split(" ")[0] if not n.startswith("synthetic") else n for n, _ in imgs]
    cross = [base_sim[i, j] for i in range(len(imgs)) for j in range(i + 1, len(imgs)) if src[i] != src[j]]
    print(f"UGen vs UGen, different images: mean {np.mean(cross):.3f} max {np.max(cross):.3f}")
    for pre in names:
        clip, _, tf = open_clip.create_model_and_transforms("ViT-B-32", pretrained=pre, cache_dir=str(MODELS), device="cpu")
        clip.eval()
        with torch.no_grad():
            C = torch.cat([clip.encode_image(tf(i).unsqueeze(0)) for _, i in imgs])
            C = (C / C.norm(dim=-1, keepdim=True)).numpy()
        same = (U * C).sum(1)
        cc = C @ U.T
        diff = [cc[i, j] for i in range(len(imgs)) for j in range(len(imgs)) if src[i] != src[j]]
        print(f"\n== {pre}: cosine(UGen, CPU) same image: mean {same.mean():.3f} min {same.min():.3f} max {same.max():.3f}; "
              f"across different images: mean {np.mean(diff):.3f} max {np.max(diff):.3f}")
        for (n, _), s in zip(imgs, same):
            print(f"   {n:40s} {s:.3f}")
        lp = MODELS / f"labels_{SHORT.get(pre, pre)}.npz"
        if lp.exists():
            z = np.load(lp)
            lab, lang, eid, T = z["labels"], z["lang"], z["entry_id"], z["emb"].astype(np.float32)
            en = lang == "en"
            for tag, E in (("UGen", U), ("CPU", C)):
                print(f"-- zero-shot top-3 ({tag} image emb, {pre} text, English labels)")
                for (n, _), e in zip(imgs, E):
                    if n.count(" ") and not n.startswith("synthetic"):
                        continue  # variants only for the base images
                    s = T[en] @ e
                    top, seen = [], set()
                    for k in np.argsort(-s):
                        l = lab[en][k]
                        if l not in seen:
                            seen.add(l)
                            top.append(f"{l} {s[k]:.3f}")
                        if len(top) == 3:
                            break
                    print(f"   {n:28s} " + " | ".join(top))
        else:
            print("   (no", lp.name, "- run scripts/build_clip_labels.py --pretrained", pre, ")")


if __name__ == "__main__":
    main()
