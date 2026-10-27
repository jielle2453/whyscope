"""Optional vision: YOLO finds the main object, CLIP zero-shot picks the best KB label.

No-op (label() returns None) if ultralytics / open_clip are not installed, the model cannot be
loaded, or no label clears the confidence floor. Image bytes live only in memory.
"""
import io

from .config import resolve, torch_device


class Vision:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.vc = cfg.get("vision", {})
        self.enabled = bool(self.vc.get("enabled", True))
        self.ready = False
        self.error = None
        self.device = torch_device(cfg)
        self._text_cache = {}

    @property
    def available(self) -> bool:
        try:
            import ultralytics  # noqa: F401
            import open_clip  # noqa: F401
            return self.enabled
        except Exception:
            return False

    def _load(self):
        if self.ready:
            return
        import open_clip
        from ultralytics import YOLO
        models = resolve(self.cfg, "models")
        self.yolo = YOLO(str(models / self.vc.get("yolo_model", "yolov8n.pt")))
        self.clip, _, self.pre = open_clip.create_model_and_transforms(
            self.vc.get("clip_model", "ViT-B-32"), pretrained=self.vc.get("clip_pretrained", "laion2b_s34b_b79k"),
            cache_dir=str(models / "clip"), device=self.device)
        self.clip.eval()
        self.tok = open_clip.get_tokenizer(self.vc.get("clip_model", "ViT-B-32"))
        self.ready = True

    def label(self, image_bytes: bytes, kb_labels):
        """kb_labels: [(label_zh, [ascii labels])]. Returns (label_zh, confidence) or None."""
        if not (image_bytes and kb_labels and self.available):
            return None
        try:
            import torch
            from PIL import Image
            self._load()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            res = self.yolo.predict(img, verbose=False, device=self.device if self.device == "cuda" else "cpu")[0]
            crop = img
            if len(res.boxes):
                i = int(res.boxes.conf.argmax())
                x1, y1, x2, y2 = [int(v) for v in res.boxes.xyxy[i].tolist()]
                if x2 - x1 > 16 and y2 - y1 > 16:
                    crop = img.crop((x1, y1, x2, y2))
            names = [(zh, en[0]) for zh, en in kb_labels]
            key = tuple(n for _, n in names)
            if key not in self._text_cache:
                with torch.no_grad():
                    t = self.clip.encode_text(self.tok([f"a photo of a {n}" for _, n in names]).to(self.device))
                    self._text_cache = {key: t / t.norm(dim=-1, keepdim=True)}
            with torch.no_grad():
                f = self.clip.encode_image(self.pre(crop).unsqueeze(0).to(self.device))
                f = f / f.norm(dim=-1, keepdim=True)
                probs = (100.0 * f @ self._text_cache[key].T).softmax(dim=-1)[0]
            j = int(probs.argmax())
            conf = float(probs[j])
            if conf < float(self.vc.get("min_confidence", 0.25)):
                return None
            return names[j][0], conf
        except Exception as e:
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
            return None
