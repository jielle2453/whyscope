"""Pre- and post-processing for the vision HEFs on the UGen300 (yolov8s detection, CLIP ViT-B/32 image encoder).

Same steps as eval/ugen/vision_bench.py, which was checked against the CPU models in step 0. numpy only at import time;
Pillow is imported inside the functions that need it, because the HailoRT venv may not have it (then the hub does the
image work and sends the worker ready-made uint8 arrays, see hub/hailo_worker.py).
"""
import numpy as np

YOLO_SIZE, CLIP_SIZE = 640, 224

COCO = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
        "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant",
        "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
        "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
        "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
        "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
        "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
        "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]


def letterbox(img, size=YOLO_SIZE):
    """PIL RGB image -> (uint8 size x size x 3 with grey padding, scale, pad_x, pad_y)."""
    from PIL import Image
    w, h = img.size
    s = min(size / w, size / h)
    nw, nh = round(w * s), round(h * s)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    ox, oy = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (ox, oy))
    return np.asarray(canvas, dtype=np.uint8), s, ox, oy


def clip_u8(img):
    """PIL RGB image -> uint8 224 x 224 x 3: shorter side to 224 (bicubic) + centre crop, as open_clip does before
    normalisation (the HEF normalises on the device)."""
    from PIL import Image
    w, h = img.size
    s = CLIP_SIZE / min(w, h)
    im = img.resize((max(CLIP_SIZE, round(w * s)), max(CLIP_SIZE, round(h * s))), Image.BICUBIC)
    left, top = (im.size[0] - CLIP_SIZE) // 2, (im.size[1] - CLIP_SIZE) // 2
    return np.asarray(im.crop((left, top, left + CLIP_SIZE, top + CLIP_SIZE)), dtype=np.uint8)


def decode_nms(per_class, scale, pad, thr=0.25, size=YOLO_SIZE):
    """HAILO_NMS_BY_CLASS output (one array of [y1, x1, y2, x2, score] per COCO class, normalised to the letterboxed
    image) -> [{"label", "score", "box": [x1, y1, x2, y2]}] in original-image pixels, best first."""
    out = []
    for c, arr in enumerate(per_class):
        for y1, x1, y2, x2, sc in np.asarray(arr).reshape(-1, 5):
            if sc >= thr:
                out.append({"label": COCO[c] if c < len(COCO) else str(c), "score": round(float(sc), 3),
                            "box": [round(float((x1 * size - pad[0]) / scale), 1),
                                    round(float((y1 * size - pad[1]) / scale), 1),
                                    round(float((x2 * size - pad[0]) / scale), 1),
                                    round(float((y2 * size - pad[1]) / scale), 1)]})
    return sorted(out, key=lambda d: -d["score"])


def l2(v):
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / max(float(np.linalg.norm(v)), 1e-12)
