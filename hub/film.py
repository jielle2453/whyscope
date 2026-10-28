"""Nostalgic film look for snapshots: warm tone, lifted blacks, soft contrast, vignette, grain.

Usage as a module: film.apply(PIL.Image) -> PIL.Image
Usage as a CLI:    python -m hub.film <in> <out> [--strength 1.0]
"""
from __future__ import annotations
import sys
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


JPEG_QUALITY = 45  # old-phone look: visible compression blocks


def apply(im: Image.Image, strength: float = 1.0, max_side: int = 640) -> Image.Image:
    """Old-phone look: low resolution, soft, noisy, warm, faded, vignetted."""
    im = im.convert("RGB")
    w, h = im.size
    # old sensor: downscale hard, then a cheap bilinear upscale so pixels look slightly smeared
    small = max(1, int(max(w, h) * 0.75))
    scale = min(1.0, min(max_side, small) / max(w, h))
    im = im.resize((max(1, int(w * scale * 0.8)), max(1, int(h * scale * 0.8))), Image.BILINEAR)
    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
    s = max(0.0, min(1.5, strength))

    # 1. softer, slightly desaturated
    im = ImageEnhance.Color(im).enhance(1 - 0.22 * s)
    im = ImageEnhance.Contrast(im).enhance(1 - 0.12 * s)

    a = np.asarray(im).astype(np.float32) / 255.0

    # 2. lifted blacks and a gentle roll-off in the highlights (faded print)
    a = 0.06 * s + a * (1 - 0.06 * s)
    a = np.where(a > 0.8, 0.8 + (a - 0.8) * (1 - 0.25 * s), a)

    # 3. warm cast: a little more red, a little less blue, green in between
    a[..., 0] = np.clip(a[..., 0] * (1 + 0.06 * s) + 0.015 * s, 0, 1)
    a[..., 1] = np.clip(a[..., 1] * (1 + 0.015 * s), 0, 1)
    a[..., 2] = np.clip(a[..., 2] * (1 - 0.08 * s) + 0.01 * s, 0, 1)

    # 4. vignette
    hh, ww = a.shape[:2]
    yy, xx = np.mgrid[0:hh, 0:ww]
    r = np.sqrt(((xx - ww / 2) / (ww / 2)) ** 2 + ((yy - hh / 2) / (hh / 2)) ** 2)
    vig = 1 - np.clip((r - 0.55) / 0.9, 0, 1) ** 1.6 * 0.38 * s
    a *= vig[..., None]

    # 5. sensor noise: luminance grain plus a little colour noise, stronger in the shadows
    rng = np.random.default_rng(7)
    lum = rng.normal(0, 0.035 * s, (hh, ww, 1)).astype(np.float32)
    chroma = rng.normal(0, 0.012 * s, (hh, ww, 3)).astype(np.float32)
    shadow_boost = (1.4 - a.mean(axis=2, keepdims=True))
    a = np.clip(a + lum * shadow_boost + chroma, 0, 1)

    out = Image.fromarray((a * 255).astype(np.uint8))
    # 6. a cheap plastic lens: soft, with a hint of over-sharpening halos like old phone processing
    out = out.filter(ImageFilter.GaussianBlur(radius=0.9 * s))
    out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    return out


def save(im: Image.Image, path: str, strength: float = 1.0) -> None:
    """Apply the look and write a heavily compressed JPEG (4:2:0 chroma), like an old phone."""
    apply(im, strength).save(path, "JPEG", quality=JPEG_QUALITY, subsampling=2, optimize=True)


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    strength = 1.0
    if "--strength" in sys.argv:
        strength = float(sys.argv[sys.argv.index("--strength") + 1])
    src, dst = args[0], args[1]
    save(Image.open(src), dst, strength)
    print("saved", dst)
