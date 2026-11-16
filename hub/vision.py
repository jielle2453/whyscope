"""Optional vision: find the main object, then pick the best KB label.

Backends (vision.backend): `cpu` = ultralytics YOLO + open_clip on the hub's own CPU/GPU; `hailo` = yolov8s and the CLIP
image encoder on the UGen300 (through the worker, or in-process when hailo.worker is empty). The UGen's CLIP image
encoder is OpenAI ViT-B/32; the text side is PRECOMPUTED (vision.clip_labels, an .npz built by
scripts/build_clip_labels.py), so no CLIP text encoder runs at run time: image embedding . label embeddings, best label
per KB entry, raw-cosine floor plus a margin over the runner-up (see eval/ugen/clip_match.md). Without that file, or
when CLIP is not sure, the object comes from the YOLO (COCO) label mapped to a KB label, or from the question text alone.
`status()` says what can really run, for /healthz.

No-op (label() returns None) if nothing can run or no label clears the floor. Image bytes live only in memory.
"""
import io
import re
import threading
import time

from .config import resolve, torch_device


def clean_phrase(s: str) -> str:
    """'A red balloon.' / "'a cat'" -> 'a red balloon' / 'a cat': one line, no quotes or end punctuation, at most 6 words,
    ASCII only (anything else is dropped)."""
    s = (s or "").strip().splitlines()[0] if (s or "").strip() else ""
    s = re.sub(r"^(?:answer|it is|it's|this is|that is|i see)\s*:?\s*", "", s.strip(" \t\"'`*"), flags=re.I)
    s = re.sub(r"\s*[,;]\s*", " ", s.strip(" \t\"'`*.!,;:")).lower()   # "a blue, fuzzy creature" -> "a blue fuzzy creature"
    if not s.isascii() or len(s.split()) > 6:
        return ""
    return s


# words a VLM phrase may add to a KB label and still name the same thing
_MODIFIERS = frozenset("""red orange yellow green blue purple pink brown black white grey gray gold golden silver
colorful colourful dark light bright big small little tiny large huge long short round tall fat thin old new shiny
plastic wooden toy fluffy furry soft cute baby striped spotted""".split())


def _letterbox_rgb(img, w: int, h: int):
    """PIL RGB image -> uint8 array (h, w, 3), aspect kept, padded with grey (the VLM's input frame)."""
    import numpy as np
    from PIL import Image
    s = min(w / img.size[0], h / img.size[1])
    nw, nh = max(1, round(img.size[0] * s)), max(1, round(img.size[1] * s))
    canvas = Image.new("RGB", (w, h), (114, 114, 114))
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), ((w - nw) // 2, (h - nh) // 2))
    return np.asarray(canvas, dtype=np.uint8)

# COCO label -> other words a KB entry may use for it
COCO_ALIAS = {"tv": ["television"], "cell phone": ["phone", "mobile phone"], "potted plant": ["plant"],
              "dining table": ["table"], "sports ball": ["ball"], "couch": ["sofa"], "motorcycle": ["motorbike"],
              "wine glass": ["glass"], "hair drier": ["hair dryer"], "airplane": ["plane", "aeroplane"],
              "bicycle": ["bike"], "person": ["people", "man", "woman", "child", "boy", "girl"]}


class Vision:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.vc = cfg.get("vision", {})
        self.enabled = bool(self.vc.get("enabled", True))
        self.backend = self.vc.get("backend", "cpu")
        self.ready = False
        self.error = None
        self.device = torch_device(cfg)
        self.last = {}               # what the last label() call used: {"backend", "how", "ms"}
        self._clip = None            # (open_clip model, preprocess): cpu image side only
        self.clip_error = None       # why open_clip cannot run (weights missing ...); None until tried
        self._clip_tried = False
        self._labels = None          # (English label embeddings float32 [n, 512], entry_id per row, label text per row)
        self.labels_error = None
        self._hw = None              # HailoVision (in-process) or HailoVisionRemote
        self._hw_lock = threading.Lock()
        self._info = (0.0, None)     # (time, worker /info) cache for status()
        self.last_vlm = {}           # the last describe() call: {"raw", "phrase", "ms"} or {"error"}

    # ---- availability ----
    @property
    def available(self) -> bool:
        """Imports exist (cpu backend). See status() for what can actually run."""
        try:
            import ultralytics  # noqa: F401
            import open_clip  # noqa: F401
            return self.enabled
        except Exception:
            return False

    def _hailo(self):
        """The UGen vision client, or None when neither a worker nor a HEF is configured."""
        h = self.cfg.get("hailo") or {}
        with self._hw_lock:
            if self._hw is None:
                if h.get("worker"):
                    from .hailo import HailoVisionRemote
                    self._hw = HailoVisionRemote(self.cfg)
                elif h.get("yolo_hef") or h.get("clip_image_hef"):
                    from .hailo import HailoVision
                    self._hw = HailoVision(self.cfg)
            return self._hw

    def _hailo_loaded(self) -> dict:
        """{"yolo": bool, "clip_image": bool, "reachable": bool, "error": str|None} for the UGen vision models."""
        hw = self._hailo()
        if hw is None:
            return {"yolo": False, "clip_image": False, "reachable": False, "error": "hailo.worker / *_hef not set"}
        if hasattr(hw, "models"):   # in-process
            return {"yolo": "yolo" in hw.models, "clip_image": "clip_image" in hw.models, "reachable": True,
                    "error": "; ".join(hw.errors.values()) or None}
        now = time.time()
        if now - self._info[0] > 3:   # healthz may be polled: do not hit the worker more than every 3 s
            try:
                self._info = (now, hw.client.info(2))
            except Exception as e:
                self._info = (now, {"_error": f"{type(e).__name__}: {str(e)[:120]}"})
        info = self._info[1]
        if "_error" in info:
            return {"yolo": False, "clip_image": False, "reachable": False, "error": info["_error"]}
        m = info.get("models") or {}
        return {"yolo": bool((m.get("yolo") or {}).get("loaded")), "clip_image": bool((m.get("clip_image") or {}).get("loaded")),
                "reachable": True,
                "error": "; ".join(v["error"] for k, v in m.items() if k in ("yolo", "clip_image") and v.get("error")) or None}

    def _clip_model(self):
        """open_clip image encoder for the cpu backend, loaded once; None if its weights are not available."""
        if self._clip is None and not self._clip_tried:
            self._clip_tried = True
            try:
                import open_clip
                m, _, pre = open_clip.create_model_and_transforms(
                    self.vc.get("clip_model", "ViT-B-32-quickgelu"), pretrained=self.vc.get("clip_pretrained", "openai"),
                    cache_dir=str(resolve(self.cfg, "models") / "clip"), device=self.device)
                m.eval()
                self._clip = (m, pre)
            except Exception as e:
                self.clip_error = f"{type(e).__name__}: {str(e)[:160]}"
        return self._clip

    def _label_table(self):
        """Precomputed CLIP text embeddings of the English labels: (emb [n, 512] float32, entry_id per row) or None."""
        if self._labels is None and self.labels_error is None:
            try:
                import numpy as np
                rel = str(self.vc.get("clip_labels") or "clip/labels_openai.npz").replace("\\", "/")
                path = resolve(self.cfg, "models") / (rel[7:] if rel.startswith("models/") else rel)   # relative to the models folder
                z = np.load(path, allow_pickle=False)
                en = z["lang"] == "en"
                self._labels = (z["emb"][en].astype(np.float32), [str(x) for x in z["entry_id"][en]],
                                [str(x) for x in z["labels"][en]])
            except Exception as e:
                self.labels_error = f"{type(e).__name__}: {str(e)[:160]}"
        return self._labels

    def probe(self):
        """Find out now (start-up, background) what can run, so /healthz is honest from the start."""
        if self.enabled:
            self._label_table()
            if self.backend != "hailo":
                self._clip_model()

    def status(self) -> dict:
        """What can actually run, per piece and backend (for /healthz)."""
        tab = self._labels is not None
        out = {"enabled": self.enabled, "backend": self.backend,
               "clip_labels": {"can_run": tab, "rows": len(self._labels[1]) if tab else 0,
                               "error": None if tab else (self.labels_error or "not tried yet")}}
        if self.backend == "hailo":
            h = self._hailo_loaded()
            out["worker_reachable"] = h["reachable"]
            out["yolo"] = {"can_run": self.enabled and h["yolo"], "backend": "hailo" if h["yolo"] else None}
            out["clip_image"] = {"can_run": self.enabled and h["clip_image"], "backend": "hailo" if h["clip_image"] else None}
            if h["error"]:
                out["error"] = h["error"]
            if (self.vc.get("vlm") or {}).get("enabled"):
                out["vlm"] = {"can_run": self.vlm_on(), "backend": "hailo", **({"last": self.last_vlm} if self.last_vlm else {})}
        else:
            try:
                import ultralytics  # noqa: F401
                yolo = (resolve(self.cfg, "models") / self.vc.get("yolo_model", "yolov8n.pt")).exists()
            except Exception:
                yolo = False
            cpu_clip = self._clip is not None
            out["yolo"] = {"can_run": self.enabled and yolo, "backend": "cpu" if yolo else None}
            out["clip_image"] = {"can_run": self.enabled and cpu_clip, "backend": "cpu" if cpu_clip else None,
                                 "error": None if cpu_clip else self.clip_error}
        yolo_ok, clip_ok = out["yolo"]["can_run"], out["clip_image"]["can_run"] and tab
        out["labeling"] = ("yolo+clip" if yolo_ok and clip_ok else "clip" if clip_ok else
                           "yolo-label-map" if yolo_ok else "none (text only)")
        if self.last:
            out["last"] = self.last
        return out

    # ---- labelling ----
    def label(self, image_bytes: bytes, kb_labels, entries=None, lang: str = "zh"):
        """kb_labels: [(label_zh, [ascii labels])]; entries: the KB entries (their id is what the CLIP label rows map to).
        Returns (label, confidence) or None; the label is the entry's first label in `lang` (an English answer never gets
        a Chinese object name), or a principle phrase (English). Details of the decision are in `self.last`."""
        if not (image_bytes and kb_labels and self.enabled):
            return None
        t = time.perf_counter()
        res, how, backend, self._detail = None, "none", None, {}
        if self.backend == "hailo":
            try:
                res, how = self._label_hailo(image_bytes, kb_labels, entries)
                backend = "hailo"
            except Exception as e:   # worker down, model not loaded, bad image: use the hub's own models if it has them
                self.error = f"hailo: {type(e).__name__}: {str(e)[:200]}"
                res, how, backend = None, "hailo-failed", None
        if backend is None and self.available:
            res, how = self._label_cpu(image_bytes, entries), "yolo+clip"
            backend = "cpu"
        if res and entries:   # (entry_id, score) -> the entry's label in the answer language
            eid, conf = res
            e = next((x for x in entries if x["id"] == eid), None)
            if e is not None:
                labs = ((e.get("en") or {}).get("labels") or [l for l in e.get("labels", []) if l.isascii()]) if lang == "en" \
                    else e.get("labels") or []
                res = ((labs or e.get("labels") or [eid])[0], conf)
                self._detail["entry_id"] = eid
        self.last = {"backend": backend, "how": how if res else how + "(no label)", "ms": int((time.perf_counter() - t) * 1000),
                     **({"label": res[0], "score": round(res[1], 3)} if res else {}), **self._detail}
        return res

    # what the VLM says when there is no object to name, or names the child instead of the thing
    _VLM_NONE = re.compile(r"^(?:nothing|none|no object|n/?a|unknown|i (?:can(?:no|')t|don'?t)\b.*|"
                           r"(?:an? |the )?(?:person|people|girl|boy|child|kid|man|woman|baby|hand|hands|face|"
                           r"cartoon (?:girl|boy|child|character)|character|human|lady|guy|someone)s?)$", re.I)

    # Measured on eval/ugen/vision_calib.py (2026-11-16, 22 images, 6 wordings): asked with an example answer, the 2B VLM
    # repeats the example when it is not sure (it said "a red toy car" for a plain red frame). So the example is an object
    # a child is very unlikely to show, and that answer counts as "not sure". Offering "nothing" instead made it say
    # "nothing" for the balloon and cat photos too.
    DESCRIBE_EN = ("What is the main thing in this picture, not counting any person? Answer with a short noun phrase only, "
                   "like 'a striped umbrella'.")
    _VLM_UNSURE = "striped umbrella"
    # the child, not the thing: a 2B model calls a cartoon child's hair "a blue hat" or "a blue afro hairstyle"
    _VLM_PERSONISH = re.compile(r"\b(?:hair\w*|afro|hats?|caps?|characters?|heads?|faces?|shirts?|dress(?:es)?|cloth\w*|"
                                r"person|people|girls?|boys?|child(?:ren)?|kids?|man|men|woman|women|hands?|texture\w*|"
                                r"pixel\w*|smile|smiley|logo|image|picture|text|screen|background)\b", re.I)

    def vlm_on(self) -> bool:
        """vision.vlm.enabled and a worker with a loaded VLM (Qwen3-VL-2B, /describe)."""
        if not (self.enabled and (self.vc.get("vlm") or {}).get("enabled") and self.backend == "hailo"):
            return False
        hw = self._hailo()
        if hw is None or not hasattr(hw, "describe"):   # the VLM runs in the worker only
            return False
        h = self._hailo_loaded()   # refreshes the cached worker /info (at most every 3 s)
        return bool(h["reachable"] and (((self._info[1] or {}).get("models") or {}).get("vlm") or {}).get("loaded"))

    def describe(self, image_bytes: bytes, question: str = "", lang: str = "en"):
        """Qwen3-VL-2B on the UGen300 (worker POST /describe): a short English noun phrase for the main thing the child
        holds up ("a red balloon"), or None (VLM off / not loaded, nothing clear, it named a person, an error).

        How the pipeline uses it (hub/pipeline.py): only for camera questions ("What is this?", "Why is this ...?") when
        YOLO + CLIP is not confident. The phrase is first matched against the KB's English labels (match_phrase); a match
        is used like a CLIP label (the KB answer follows). Without a match, "What is this?" gets "That looks like <phrase>!"
        plus a question back, and other camera turns get the phrase as a camera note for the chat reply: it names the
        object, never a fact source, and the reply passes hub/guard.py. Details of the call are in self.last_vlm."""
        self.last_vlm = {}
        if not (image_bytes and self.vlm_on()):
            return None
        t = time.perf_counter()
        try:
            from PIL import Image, ImageOps
            shape = ((self._info[1].get("models") or {}).get("vlm") or {}).get("frame_shape") or [288, 512, 3]
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
            vc = self.vc.get("vlm") or {}
            raw = self._hailo().describe(_letterbox_rgb(img, int(shape[1]), int(shape[0])), float(vc.get("timeout_s", 6)),
                                         str(vc.get("prompt") or self.DESCRIBE_EN))
        except Exception as e:
            self.last_vlm = {"error": f"{type(e).__name__}: {str(e)[:160]}", "ms": int((time.perf_counter() - t) * 1000)}
            return None
        phrase = clean_phrase(raw)
        ok = bool(phrase) and not self._VLM_NONE.match(phrase) and self._VLM_UNSURE not in phrase
        ok = ok and not self._VLM_PERSONISH.search(phrase)
        self.last_vlm = {"raw": raw, "phrase": phrase if ok else None, "ms": int((time.perf_counter() - t) * 1000)}
        return phrase if ok else None

    def match_phrase(self, phrase: str, entries, lang: str = "en"):
        """A VLM phrase -> (KB label in `lang`, entry id) when an English label row of the CLIP label table (the KB
        entries' labels and the principle phrases) names its head noun: "a red balloon" -> balloon, "a green apple" ->
        apple. Every content word of the label must be in the phrase, the label must contain the phrase's last word (so
        "a toy dinosaur" never matches a "toy" entry), and every phrase word that is not a plain colour / size / "toy"
        word must be in the label ("a magnifying glass" is not "glasses", "a teddy bear" is not "bear"). Body / people
        topics are left out as for CLIP. Else None."""
        from .recall import content_en
        tab = self._label_table()
        words = content_en(phrase or "")
        if not (tab and words and entries):
            return None
        head, have = words[-1], set(words)
        core = have - _MODIFIERS   # "a red toy dinosaur" -> {dinosaur}; "a magnifying glass" keeps "magnifying"
        skip = tuple(self.vc.get("exclude_topics", ["body", "people"]))
        ok = {e["id"] for e in entries if e.get("topic") not in skip and not e["id"].startswith(tuple(t + "-" for t in skip))}
        best = None
        for eid, lab in zip(tab[1], tab[2]):
            if not (eid in ok or eid.startswith("principle:")):
                continue
            lw = content_en(lab)
            if not lw or head not in lw or not set(lw) <= have or not core <= set(lw):
                continue
            key = (len(lw), eid in ok, -len(lab))   # the most specific label; an entry before a principle phrase
            if best is None or key > best[0]:
                best = (key, eid, lab)
        if best is None:
            return None
        _, eid, lab = best
        if eid.startswith("principle:"):
            return lab, None
        e = next(x for x in entries if x["id"] == eid)
        labs = ((e.get("en") or {}).get("labels") or [lab]) if lang == "en" else (e.get("labels") or [lab])
        return labs[0], eid

    @staticmethod
    def _kb_match(coco: str, kb_labels):
        """KB label (zh) whose English labels include this COCO label (or an alias of it), else None."""
        want = {coco.lower(), *COCO_ALIAS.get(coco.lower(), [])}
        for zh, en in kb_labels:
            if want & {e.lower() for e in en}:
                return zh
        return None

    # Calibrated on eval/ugen/vision_calib.py (2026-11-15): CLIP on a whole webcam frame with a child in it picks body
    # entries (hair, eyebrows, tears, skin colour) and colour-driven ones; the right object usually wins by >= 0.02 over
    # the best entry of ANOTHER object family, a wrong one by less. So: no body / people entries from the camera (the
    # child's words name those), YOLO "person" boxes are never the crop, the margin is taken over another family
    # (cat vs cat-purr is not a contest), and several crops (best non-person box, centre, full frame) are tried.
    def _families(self, entries):
        """entry id -> set of object words (stemmed English label words + id words); entries sharing a word are one family."""
        key = id(entries)
        if getattr(self, "_fam_key", None) != key:
            from .recall import content_en, stem_en
            fam = {}
            for e in entries:
                ws = {w for l in (e.get("en") or {}).get("labels", []) for w in content_en(l)}
                ws |= {stem_en(w) for w in e["id"].split("-", 1)[-1].split("-") if len(w) > 2}
                fam[e["id"]] = ws - {"color", "colour", "big", "far", "small", "water", "food", "make", "keep", "how"}
            self._fam, self._fam_key = fam, key
        return self._fam

    def _clip_pick(self, emb, entries):
        """Image embedding (512, L2-normalised) -> {"id", "score", "margin", "top"} or None.

        Best English label row per KB entry (body / people topics left out, `vision.exclude_topics`); the margin is the gap
        to the best entry of another object family. Rows of the principle library ("principle:<id>", one per
        applies_to_en phrase) take part too: when the best row of all is such a phrase ("ice cube", "boat"), it comes back
        as the id (it names no entry; the principle library uses it as {object})."""
        import numpy as np
        tab = self._label_table()
        if tab is None or not entries:
            return None
        skip = tuple(self.vc.get("exclude_topics", ["body", "people"]))
        ok = {e["id"] for e in entries if e.get("topic") not in skip and not e["id"].startswith(tuple(t + "-" for t in skip))}
        fam = self._families(entries)
        cos = tab[0] @ np.asarray(emb, dtype=np.float32).reshape(-1)
        best, phrase = {}, {}
        for c, eid, lab in zip(cos.tolist(), tab[1], tab[2]):
            if eid in ok:
                if c > best.get(eid, -1.0):
                    best[eid] = c
            elif eid.startswith("principle:") and c > phrase.get(lab.lower(), (-1.0, ""))[0]:
                phrase[lab.lower()] = (c, lab)
        top = sorted(best.items(), key=lambda kv: -kv[1])
        if not top:
            return None
        e0, s0 = top[0]
        runner = next((s for e, s in top[1:] if not (fam.get(e, set()) & fam.get(e0, set()))), -1.0)
        ptop = sorted(phrase.values(), key=lambda v: -v[0])[:2]
        m = float(self.vc.get("clip_margin", 0.02))
        if ptop and ptop[0][0] >= s0 + m:   # a principle phrase only when it clearly beats every entry
            others = [v[0] for v in ptop[1:]] + [s0]
            return {"id": ptop[0][1], "score": ptop[0][0], "margin": ptop[0][0] - max(others), "top": [(ptop[0][1], round(ptop[0][0], 3))]}
        # within the winning family, name the thing by a plain noun: "sun" (sun-hot) rather than "how far is the sun"
        name_of = {e["id"]: ((e.get("en") or {}).get("labels") or [""])[0] for e in entries}
        pick = e0
        if len(name_of.get(e0, "").split()) > 2:
            for e, s in top[1:6]:
                if s0 - s <= 0.02 and fam.get(e, set()) & fam.get(e0, set()) and 0 < len(name_of.get(e, "").split()) <= 2:
                    pick = e
                    break
        return {"id": pick, "score": s0, "margin": s0 - runner, "top": [(e, round(s, 3)) for e, s in top[:3]],
                "family": fam.get(e0, set())}

    def _crops(self, img, dets):
        """[(name, PIL crop)]: the best non-person YOLO box (a little padded), the centre, the full frame."""
        w, h = img.size
        out = []
        min_s = float(self.vc.get("crop_min_score", 0.25))
        for d in dets:
            if d["label"] == "person" or d["score"] < min_s:
                continue
            x1, y1, x2, y2 = d["box"]
            bw, bh = x2 - x1, y2 - y1
            if bw < 24 or bh < 24 or bw * bh > 0.9 * w * h:
                continue
            px, py = bw * 0.1, bh * 0.1
            out.append(("box:" + d["label"], img.crop((int(max(0, x1 - px)), int(max(0, y1 - py)), int(min(w, x2 + px)), int(min(h, y2 + py))))))
            break
        out.append(("centre", img.crop((int(w * .2), int(h * .2), int(w * .8), int(h * .8)))))
        out.append(("full", img))
        return out

    def _decide(self, picks):
        """picks: [(crop name, pick dict)] -> (pick, crop name) | (None, why). Accept a crop whose top clears the floor and
        the family margin (the largest margin wins); else two crops that agree on a family with half the margin each."""
        floor, margin = float(self.vc.get("min_confidence", 0.26)), float(self.vc.get("clip_margin", 0.02))
        good = [(p["margin"], n, p) for n, p in picks if p and p["score"] >= floor and p["margin"] >= margin]
        if good:
            _, n, p = max(good, key=lambda g: g[0])
            return p, n
        half = [(n, p) for n, p in picks if p and p["score"] >= floor and p["margin"] >= margin / 2]
        for i, (n1, a) in enumerate(half):
            for n2, b in half[i + 1:]:
                if a["id"] == b["id"] or (a.get("family") and a.get("family", set()) & b.get("family", set())):
                    return (a if a["score"] >= b["score"] else b), n1 + "+" + n2
        return None, "not sure"

    def _label_hailo(self, image_bytes, kb_labels, entries=None):
        """YOLO on the UGen finds boxes; up to three crops go through the UGen's CLIP image encoder and the precomputed
        label table (_decide). If CLIP is unavailable or not sure, a non-person YOLO label is mapped to a KB label.
        -> ((entry id | phrase, conf) | None, how)."""
        from PIL import Image, ImageOps
        from . import hailo_vision as hv
        hw = self._hailo()
        if hw is None:
            raise RuntimeError("hailo vision is not configured")
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
        lb, s, ox, oy = hv.letterbox(img)
        dets = hw.detect(lb, s, (ox, oy), 0.25)
        self._detail = {"yolo": [(d["label"], d["score"]) for d in dets[:4]]}
        if self._label_table() is not None and self._hailo_loaded()["clip_image"]:
            picks = [(n, self._clip_pick(hw.clip_image(hv.clip_u8(c)), entries)) for n, c in self._crops(img, dets)]
            self._detail["crops"] = {n: {"top": p["top"], "margin": round(p["margin"], 3)} for n, p in picks if p}
            p, why = self._decide(picks)
            if p:
                self._detail["crop"] = why
                return (p["id"], p["score"]), "yolo+clip"
        r = self._yolo_map(dets, kb_labels, entries)
        return (r, "yolo-label-map") if r else (None, "yolo+clip" if self._detail.get("crops") else "yolo-label-map")

    def _yolo_map(self, dets, kb_labels, entries):
        """A confident non-person COCO label that names a KB entry ("cat" -> the cat entry): (entry id, score) or None."""
        floor = float(self.vc.get("yolo_min_score", 0.5))
        skip = tuple(self.vc.get("exclude_topics", ["body", "people"]))
        for d in dets:
            if d["label"] == "person" or d["score"] < floor:
                continue
            want = {d["label"].lower(), *COCO_ALIAS.get(d["label"].lower(), [])}
            for e in entries or []:
                if e.get("topic") in skip:
                    continue
                labs = {l.lower() for l in list(e.get("labels", [])) + list((e.get("en") or {}).get("labels", []))}
                if want & labs:
                    return e["id"], d["score"]
        return None

    def _label_cpu(self, image_bytes, entries=None):
        try:
            import torch
            from PIL import Image
            from ultralytics import YOLO
            if not hasattr(self, "yolo"):
                self.yolo = YOLO(str(resolve(self.cfg, "models") / self.vc.get("yolo_model", "yolov8n.pt")))
            m = self._clip_model()
            if m is None or self._label_table() is None:
                self.error = self.clip_error or self.labels_error
                return None
            clip, pre = m
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            res = self.yolo.predict(img, verbose=False, device=self.device if self.device == "cuda" else "cpu")[0]
            names = res.names if hasattr(res, "names") else {}
            dets = sorted([{"label": names.get(int(c), str(int(c))), "score": float(s), "box": b.tolist()}
                           for b, s, c in zip(res.boxes.xyxy, res.boxes.conf, res.boxes.cls)], key=lambda d: -d["score"])
            picks = []
            for n, crop in self._crops(img, dets):
                with torch.no_grad():
                    f = clip.encode_image(pre(crop).unsqueeze(0).to(self.device))
                    f = (f / f.norm(dim=-1, keepdim=True))[0].float().cpu().numpy()
                picks.append((n, self._clip_pick(f, entries)))
            p, _ = self._decide(picks)
            return (p["id"], p["score"]) if p else None
        except Exception as e:
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
            return None
