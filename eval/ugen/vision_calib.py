"""Camera calibration without new photos: YOLO + CLIP on the UGen300 over a small fixed image set.

    set PYTHONIOENCODING=utf-8 & set HF_HUB_OFFLINE=1 & set WHYSCOPE_CONFIG=config.hailo.yaml
    C:\\whyscope-venv\\Scripts\\python eval\\ugen\\vision_calib.py [--json out.json] [--vlm]

--vlm: also compare CLIP-only with the VLM (Qwen3-VL-2B on the UGen300, worker /describe) on the same images.

Images: the 3 demo photos on disk (balloon, snail, cat eye), the two avatar renders of a child holding a magnifying glass
(stand-ins for "a child in front of the camera"), composites (a demo photo pasted into the avatar's hands, i.e. a child
holding a thing up), simple renders (yellow circle, sky + sun + grass, plain colours, grey wall). Nothing is downloaded.

For each image and each crop strategy (YOLO best box incl. person, YOLO best non-person box, centre crop, full frame) it
prints the best KB entries (max cosine over each entry's English label rows) and the gap to the runner-up, so the hub's
floor / margin (config vision.min_confidence / clip_margin) and the person rule can be set from data.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BASE = ROOT.parent / "whyscope"

from hub import hailo_vision as hv  # noqa: E402
from hub.config import load_config  # noqa: E402
from hub.hailo import HailoVisionRemote  # noqa: E402
from hub.recall import Recall  # noqa: E402
from hub.vision import Vision  # noqa: E402


def renders():
    out = []
    im = Image.new("RGB", (480, 360), (255, 255, 255))
    ImageDraw.Draw(im).ellipse((150, 90, 330, 270), fill=(240, 200, 0))
    out.append(("render yellow circle", im, {"sky_weather-sun-hot", "sky_weather-star-twinkle"}))
    im = Image.new("RGB", (480, 360), (135, 206, 235))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 260, 480, 360), fill=(60, 160, 60))
    d.ellipse((360, 30, 430, 100), fill=(255, 220, 0))
    out.append(("render sky sun grass", im, {"sky_weather-blue-sky", "sky_weather-sun-hot", "sky_weather-cloud"}))
    im = Image.new("RGB", (480, 360), (250, 250, 250))
    d = ImageDraw.Draw(im)
    d.ellipse((160, 110, 320, 270), fill=(200, 20, 30))
    d.rectangle((236, 80, 244, 115), fill=(90, 60, 20))
    d.ellipse((244, 80, 290, 105), fill=(40, 150, 40))
    out.append(("render red apple", im, {"food-apple-turns-brown"}))
    im = Image.new("RGB", (480, 360), (250, 250, 250))
    ImageDraw.Draw(im).arc((90, 40, 390, 340), 20, 160, fill=(245, 215, 40), width=50)
    out.append(("render banana arc", im, {"food-banana-black"}))
    for name, col in [("plain red", (220, 30, 30)), ("plain blue", (30, 60, 200)), ("grey wall", (128, 128, 128))]:
        out.append(("render " + name, Image.new("RGB", (480, 360), col), set()))
    rng = np.random.default_rng(0)
    out.append(("render noise", Image.fromarray(rng.integers(0, 255, (360, 480, 3), dtype=np.uint8)), set()))
    return out


def images():
    out = []
    photos = {"12-film.jpg": {"machines-balloon"}, "13-film.jpg": {"animals-snail-shell"},
              "14-film.jpg": {"animals-cat", "animals-owl", "animals-cat-purr"}}
    for n, want in photos.items():
        p = BASE / "brand" / "demo-photos" / n
        if p.exists():
            im = Image.open(p).convert("RGB")
            out.append(("photo " + n, im, want))
            w, h = im.size
            out.append(("photo " + n + " small-in-frame", _in_room(im, 0.35), want))
    for av in ("avatar-girl.png", "avatar-boy.png"):
        p = ROOT / "hub" / "static" / av
        if p.exists():
            a = Image.open(p).convert("RGB")
            out.append(("child " + av, a, set()))     # nothing the child asks about: must stay unlabelled
            for n, want in photos.items():
                q = BASE / "brand" / "demo-photos" / n
                if q.exists():
                    out.append((f"child {av} holding {n}", _held(a, Image.open(q).convert("RGB")), want))
    return out + renders()


def _in_room(obj, frac):
    """The object small in a plain room-like frame (beige wall, brown floor)."""
    W, H = 640, 480
    bg = Image.new("RGB", (W, H), (214, 200, 180))
    ImageDraw.Draw(bg).rectangle((0, int(H * 0.72), W, H), fill=(120, 90, 60))
    w = int(W * frac)
    o = obj.resize((w, int(obj.size[1] * w / obj.size[0])))
    bg.paste(o, ((W - o.size[0]) // 2, (H - o.size[1]) // 2))
    return bg


def _held(child, obj):
    """A child image with the object held up in front, lower centre (what a webcam sees when a child shows a thing)."""
    c = child.resize((640, 640))
    w = 300
    o = obj.resize((w, int(obj.size[1] * w / obj.size[0])))
    c.paste(o, ((640 - w) // 2, 640 - o.size[1] - 20))
    return c


def per_entry(cos, tab, ids):
    best = {}
    for c, eid in zip(cos.tolist(), tab[1]):
        if eid in ids and c > best.get(eid, -1):
            best[eid] = c
    return sorted(best.items(), key=lambda kv: -kv[1])


def main():
    cfg = load_config()
    rc = Recall(cfg)
    vis = Vision(cfg)
    tab = vis._label_table()
    ids = {e["id"] for e in rc.entries}
    hw = HailoVisionRemote(cfg)
    rows = []
    for name, im, want in images():
        lb, s, ox, oy = hv.letterbox(im)
        dets = hw.detect(lb, s, (ox, oy), 0.25)
        crops = {"full": im}
        w, h = im.size
        crops["centre"] = im.crop((int(w * .2), int(h * .2), int(w * .8), int(h * .8)))
        if dets:
            x1, y1, x2, y2 = [int(v) for v in dets[0]["box"]]
            crops["yolo_top"] = im.crop((max(x1, 0), max(y1, 0), x2, y2))
        np_d = [d for d in dets if d["label"] != "person"]
        if np_d:
            x1, y1, x2, y2 = [int(v) for v in np_d[0]["box"]]
            crops["yolo_nonperson"] = im.crop((max(x1, 0), max(y1, 0), x2, y2))
        rec = {"image": name, "want": sorted(want), "dets": [(d["label"], d["score"]) for d in dets[:4]], "crops": {}}
        for cn, cr in crops.items():
            if cr.size[0] < 16 or cr.size[1] < 16:
                continue
            emb = np.asarray(hw.clip_image(hv.clip_u8(cr)), dtype=np.float32)
            top = per_entry(tab[0] @ emb, tab, ids)[:3]
            rec["crops"][cn] = {"top": [(e, round(c, 3)) for e, c in top], "margin": round(top[0][1] - top[1][1], 3),
                                "hit": top[0][0] in want}
        rows.append(rec)
        print(f"\n{name}  want={sorted(want) or '-'}  yolo={rec['dets']}")
        for cn, r in rec["crops"].items():
            print(f"   {cn:15s} {'OK ' if r['hit'] else ('-- ' if not want else 'XX ')} margin {r['margin']:.3f}  {r['top']}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    # sweep: what a floor / margin pair would accept, per crop strategy
    print("\nsweep (strategy: the hub's order; accepted right / accepted wrong / accepted on a no-object image)")
    for floor in (0.25, 0.26, 0.27, 0.28, 0.29, 0.30):
        for margin in (0.005, 0.01, 0.015, 0.02, 0.03):
            ok = bad = none = 0
            for r in rows:
                for cn in ("yolo_nonperson", "centre", "full"):
                    c = r["crops"].get(cn)
                    if c and c["top"][0][1] >= floor and c["margin"] >= margin:
                        if not r["want"]:
                            none += 1
                        elif c["hit"]:
                            ok += 1
                        else:
                            bad += 1
                        break
            print(f"  floor {floor:.2f} margin {margin:.3f}: right {ok}, wrong {bad}, on no-object {none}")
    # the hub's own decision (hub/vision.py with the config's floor / margin), end to end on the same images
    import io
    print(f"\nhub decision (vision.min_confidence {vis.vc.get('min_confidence')}, clip_margin {vis.vc.get('clip_margin')}):")
    tally = {"right": 0, "wrong": 0, "none_ok": 0, "missed": 0, "false_on_empty": 0}
    for name, im, want in images():
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        r = vis.label(buf.getvalue(), rc.vision_labels(), rc.entries, "en")
        eid = vis.last.get("entry_id")
        k = ("right" if eid in want else "wrong") if r and want else ("false_on_empty" if r else ("missed" if want else "none_ok"))
        tally[k] += 1
        print(f"  {k:14s} {name:45s} -> {r and r[0]!s:18s} {vis.last.get('crop', '')}")
    print("  " + ", ".join(f"{k} {v}" for k, v in tally.items()))
    if "--vlm" in sys.argv:
        compare_vlm(vis, rc)


def compare_vlm(vis, rc):
    """CLIP-only (the hub's YOLO + CLIP decision) vs the VLM (Qwen3-VL-2B on the UGen300, worker /describe) on the same
    images: the VLM phrase, the KB label it maps to (Vision.match_phrase), right / wrong per image, latency per call.
    "chain" = the hub's order: CLIP first, the VLM only when CLIP is not sure. Needs a worker with hailo.vlm_hef."""
    import io
    import time
    vis.vc = {**vis.vc, "vlm": {**(vis.vc.get("vlm") or {}), "enabled": True}}
    if not vis.vlm_on():
        print("\nVLM: the worker has no VLM loaded (hailo.vlm_hef)")
        return
    rows = []
    print("\nCLIP-only vs VLM (right = names a wanted KB entry; on an image with no wanted entry a KB label is a false label)")
    for name, im, want in images():
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        jpg = buf.getvalue()
        t = time.perf_counter()
        r = vis.label(jpg, rc.vision_labels(), rc.entries, "en")
        clip_ms = (time.perf_counter() - t) * 1000
        clip_id = vis.last.get("entry_id") if r else None
        t = time.perf_counter()
        phrase = vis.describe(jpg, "what is this", "en")
        vlm_ms = (time.perf_counter() - t) * 1000
        m = vis.match_phrase(phrase, rc.entries, "en") if phrase else None
        vlm_id = m[1] if m else None

        def verdict(eid, named):
            if want:
                return "right" if eid in want else ("wrong" if eid or named else "missed")
            return "false_on_empty" if eid else "none_ok"
        row = {"image": name, "want": sorted(want), "clip": clip_id, "clip_ms": round(clip_ms), "clip_v": verdict(clip_id, bool(r)),
               "vlm_raw": vis.last_vlm.get("raw"), "vlm_phrase": phrase, "vlm_kb": vlm_id or (m[0] if m else None),
               "vlm_ms": round(vlm_ms), "vlm_v": verdict(vlm_id, bool(m))}
        chain_id, chain_named = (clip_id, bool(r)) if r else (vlm_id, bool(m))
        row["chain_v"] = verdict(chain_id, chain_named)
        rows.append(row)
        print(f"  {name:45s} clip {row['clip_v']:14s} {str(clip_id):26s} {row['clip_ms']:5d} ms | vlm {row['vlm_v']:14s} "
              f"{str(phrase)!r:28s} -> {str(row['vlm_kb']):26s} {row['vlm_ms']:5d} ms | chain {row['chain_v']}")
    for k in ("clip_v", "vlm_v", "chain_v"):
        tally = {}
        for r in rows:
            tally[r[k]] = tally.get(r[k], 0) + 1
        print(f"  {k[:-2]:6s}: " + ", ".join(f"{a} {b}" for a, b in sorted(tally.items())))
    import statistics as st
    for k in ("clip_ms", "vlm_ms"):
        v = sorted(r[k] for r in rows)
        print(f"  {k}: median {st.median(v):.0f}, p90 {v[int(0.9 * (len(v) - 1))]:.0f}, max {v[-1]:.0f}")
    if "--json" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--json") + 1])
        p.with_name(p.stem + "_vlm.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
