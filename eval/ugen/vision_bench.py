"""Vision on the UGen300 vs the hub's CPU path: yolov8s.hef + CLIP ViT-B/32 image encoder.hef (compatibility + speed).

Two steps, because the HailoRT venv has no torch / PIL:
    1. C:\\whyscope-venv\\Scripts\\python eval\\ugen\\vision_bench.py cpu   --out <dir>   (preprocess, ultralytics yolov8n,
       open_clip laion2b image + text embeddings, CPU timings; saves arrays + cpu.json into <dir>)
    2. C:\\whyscope-hailo-venv\\Scripts\\python eval\\ugen\\vision_bench.py hailo --out <dir>   (runs the HEFs on the same
       arrays, compares with cpu.json, writes hailo.json)
"""
import argparse
import glob
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

BASE = Path(r"C:\Users\Jie\Desktop\whyscope\whyscope")
IMAGES = sorted(glob.glob(str(BASE / "data" / "snapshots" / "*.jpg")) + glob.glob(str(BASE / "brand" / "demo-photos" / "*.jpg")))
LABELS = ["cat", "dog", "bird", "flower", "tree", "car", "person", "book", "cup", "bottle", "apple", "banana", "chair",
          "laptop", "phone", "camera", "pizza", "bicycle", "clock", "bus", "fish", "horse", "cow", "butterfly", "moon",
          "sun", "cloud", "rainbow", "mountain", "river", "building", "bridge", "toy", "ball", "shoe", "hat", "plant",
          "leaf", "dinosaur", "rabbit"]
RUNS = 20


def letterbox(img, size=640):
    from PIL import Image
    w, h = img.size
    s = min(size / w, size / h)
    nw, nh = round(w * s), round(h * s)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    ox, oy = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (ox, oy))
    return np.asarray(canvas, dtype=np.uint8), s, ox, oy


def clip_u8(img):
    """Resize shorter side to 224 (bicubic) + centre crop, uint8 HWC: what open_clip does before normalisation."""
    from PIL import Image
    w, h = img.size
    s = 224 / min(w, h)
    im = img.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
    l, t = (im.size[0] - 224) // 2, (im.size[1] - 224) // 2
    return np.asarray(im.crop((l, t, l + 224, t + 224)), dtype=np.uint8)


def mean_ms(fn, runs=RUNS):
    fn()
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    return round(statistics.mean(ts), 1), round(statistics.pstdev(ts), 1)


def cpu(out: Path):
    import torch
    import open_clip
    from PIL import Image
    from ultralytics import YOLO
    models = BASE / "models"
    yolo = YOLO(str(models / "yolov8n.pt"))
    res = {"images": [], "labels": LABELS, "names": yolo.names, "clip_cpu": None}
    try:
        clip, _, pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k",
                                                             cache_dir=str(models / "clip"), device="cpu")
        clip.eval()
        tok = open_clip.get_tokenizer("ViT-B-32")
        with torch.no_grad():
            t = clip.encode_text(tok([f"a photo of a {n}" for n in LABELS]))
            np.save(out / "text_laion.npy", (t / t.norm(dim=-1, keepdim=True)).numpy())
        res["clip_cpu"] = True
    except Exception as e:  # the laion2b weights are not on disk (models/clip holds only refs/main): never download here
        clip = pre = None
        res["clip_cpu"] = f"unavailable: {str(e)[:150]}"
        print(res["clip_cpu"])
    embs = []
    for i, p in enumerate(IMAGES):
        img = Image.open(p).convert("RGB")
        lb, s, ox, oy = letterbox(img)
        np.save(out / f"yolo_in_{i}.npy", lb)
        np.save(out / f"clip_in_{i}.npy", clip_u8(img))
        r = yolo.predict(img, verbose=False, device="cpu")[0]
        dets = [{"cls": int(c), "name": yolo.names[int(c)], "conf": round(float(f), 3),
                 "xyxy": [round(v, 1) for v in b]} for c, f, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]
        if clip is not None:
            with torch.no_grad():
                f = clip.encode_image(pre(img).unsqueeze(0))
                f = f / f.norm(dim=-1, keepdim=True)
            embs.append(f[0].numpy())
        res["images"].append({"path": p, "size": img.size, "scale": s, "pad": [ox, oy], "dets": dets})
        print(Path(p).name, img.size, [(d["name"], d["conf"]) for d in dets], flush=True)
    img0 = Image.open(IMAGES[0]).convert("RGB")
    res["cpu_yolov8n_ms"] = mean_ms(lambda: yolo.predict(img0, verbose=False, device="cpu"))
    if clip is not None:
        np.save(out / "emb_laion.npy", np.stack(embs))
        x0 = pre(img0).unsqueeze(0)
        with torch.no_grad():
            res["cpu_clip_ms"] = mean_ms(lambda: clip.encode_image(x0))
            res["cpu_clip_with_preprocess_ms"] = mean_ms(lambda: clip.encode_image(pre(img0).unsqueeze(0)))
    (out / "cpu.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cpu timings", {k: v for k, v in res.items() if k.endswith("_ms")})


def decode_nms(per_class, scale, pad, thr=0.25, size=640):
    """HAILO_NMS_BY_CLASS list -> detections in original-image pixels (boxes are normalised to the 640 letterbox)."""
    out = []
    for c, arr in enumerate(per_class):
        for y1, x1, y2, x2, sc in np.asarray(arr).reshape(-1, 5):
            if sc >= thr:
                out.append({"cls": c, "conf": round(float(sc), 3),
                            "xyxy": [round(float((x1 * size - pad[0]) / scale), 1), round(float((y1 * size - pad[1]) / scale), 1),
                                     round(float((x2 * size - pad[0]) / scale), 1), round(float((y2 * size - pad[1]) / scale), 1)]})
    return sorted(out, key=lambda d: -d["conf"])


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0


def hailo(out: Path):
    sys.path.insert(0, str(Path(__file__).parent))
    from hailo_models import MODELS, Infer, make_vdevice
    cpu_res = json.loads((out / "cpu.json").read_text(encoding="utf-8"))
    names = cpu_res["names"]
    vd = make_vdevice()
    y = Infer(vd, MODELS + r"\yolov8s.hef")
    c = Infer(vd, MODELS + r"\clip_vit_b_32_image_encoder.hef")
    print("yolo", y.info(), f"load {y.load_sec:.2f}s")
    print("clip", c.info(), f"load {c.load_sec:.2f}s")
    have_clip = cpu_res.get("clip_cpu") is True
    text = np.load(out / "text_laion.npy") if have_clip else None
    emb_cpu = np.load(out / "emb_laion.npy") if have_clip else None
    embs_h = []
    res = {"yolo_load_s": round(y.load_sec, 2), "clip_load_s": round(c.load_sec, 2), "images": []}
    for i, im in enumerate(cpu_res["images"]):
        lb = np.load(out / f"yolo_in_{i}.npy")
        ci = np.load(out / f"clip_in_{i}.npy")
        r = y.run(lb)
        dets = decode_nms(list(r.values())[0], im["scale"], im["pad"])
        for d in dets:
            d["name"] = names[str(d["cls"])] if str(d["cls"]) in names else names[d["cls"]]
        e = np.asarray(list(c.run(ci).values())[0], dtype=np.float32).reshape(-1)
        en = e / np.linalg.norm(e)
        embs_h.append(en)
        top = lambda v: [cpu_res["labels"][j] for j in np.argsort(-(v @ text.T))[:3]]
        # detection agreement: yolov8s vs yolov8n, same class with IoU >= 0.5
        cd = im["dets"]
        match = sum(any(d["name"] == k["name"] and iou(d["xyxy"], k["xyxy"]) >= 0.5 for k in cd) for d in dets)
        row = {"image": Path(im["path"]).name, "hailo_dets": [(d["name"], d["conf"]) for d in dets],
               "cpu_dets": [(d["name"], d["conf"]) for d in cd], "dets_matched": match,
               "emb_norm": round(float(np.linalg.norm(e)), 3), "emb_first4": [round(float(v), 3) for v in e[:4]]}
        if have_clip:
            row.update(clip_cos_vs_laion=round(float(en @ emb_cpu[i]), 4), zs_hailo_img_top3=top(en), zs_laion_img_top3=top(emb_cpu[i]))
        res["images"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    # self-consistency of the hailo CLIP embedding between images (random-ish baseline for cosine)
    img0, ci0 = np.load(out / "yolo_in_0.npy"), np.load(out / "clip_in_0.npy")
    res["hailo_yolov8s_ms"] = mean_ms(lambda: y.run(img0))
    res["hailo_clip_ms"] = mean_ms(lambda: c.run(ci0))
    res["cpu_yolov8n_ms"], res["cpu_clip_ms"] = cpu_res["cpu_yolov8n_ms"], cpu_res.get("cpu_clip_ms")
    E = np.stack(embs_h)
    res["hailo_clip_pairwise_cos"] = np.round(E @ E.T, 3).tolist()
    (out / "hailo.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: v for k, v in res.items() if k != "images"})
    y.close()
    c.close()
    del vd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["cpu", "hailo"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    o = Path(a.out)
    o.mkdir(parents=True, exist_ok=True)
    (cpu if a.step == "cpu" else hailo)(o)
