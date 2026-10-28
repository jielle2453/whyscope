"""Recolor hair/clothes and remove the snail from the generated character image.
usage: recolor.py <src> <out> [hair_hex] [girl_hex] [boy_hex]
"""
import sys, colorsys, numpy as np
from PIL import Image

src, out = sys.argv[1], sys.argv[2]
HAIR = sys.argv[3] if len(sys.argv) > 3 else "#3B2B2B"
GIRL = sys.argv[4] if len(sys.argv) > 4 else "#9FE3C6"
BOY = sys.argv[5] if len(sys.argv) > 5 else "#FFB48A"

def hex_rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

im = Image.open(src).convert("RGB")
W, Hh = im.size
rgb = np.asarray(im).astype(np.float32) / 255
hsv = np.asarray(im.convert("HSV")).astype(np.float32)
H, S, V = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
yy, xx = np.mgrid[0:Hh, 0:W]

blueish = (H > 185) & (H < 265) & (S > 0.10)
lens = (xx - 522) ** 2 + (yy - 402) ** 2 < 72 ** 2
blueish &= ~lens
# blend weight for anti-aliased edges (low S = mixed with yellow background)
w = np.clip((S - 0.10) / 0.35, 0, 1)

girl = xx < 672
# spatial rules: hair sits above these lines; the girl's top starts under her chin
girl_hair = blueish & girl & (yy < 535) & ~((xx > 368) & (xx < 535) & (yy > 462))
boy_hair = blueish & ~girl & ((yy < 478) | ((xx > 985) & (yy < 505)))
hair = girl_hair | boy_hair
cloth = blueish & ~hair

def blend(mask, new):
    m = mask & (w > 0)
    a = w[m][:, None]
    rgb[m] = rgb[m] * (1 - a) + new[m] * a

# hair: compress contrast so the fuzzy texture reads as soft highlights, not speckle
t = np.array(hex_rgb(HAIR if HAIR != "keep" else "#000000"), dtype=np.float32)
vref = np.median(V[hair & (w > 0.9)])
shade = (0.55 + 0.6 * (V / vref))[..., None]
hair_new = np.clip(t[None, None, :] * shade, 0, 1)
if HAIR != "keep":
    blend(hair, hair_new)

def hue_image(target_hex):
    th, ts, tv = colorsys.rgb_to_hsv(*hex_rgb(target_hex))
    s2 = 0.45 * S + 0.55 * ts
    v2 = np.clip(V * (0.7 + 0.4 * tv), 0, 1)
    # vectorised hsv->rgb
    i = np.floor(th * 6) % 6; f = th * 6 - np.floor(th * 6)
    p, q, u = v2 * (1 - s2), v2 * (1 - s2 * f), v2 * (1 - s2 * (1 - f))
    table = {0: (v2, u, p), 1: (q, v2, p), 2: (p, v2, u), 3: (p, q, v2), 4: (u, p, v2), 5: (v2, p, q)}
    r, g, b = table[int(i)]
    return np.stack([r, g, b], axis=-1)

if HAIR != "keep":
    blend(cloth & girl, hue_image(GIRL))
    blend(cloth & ~girl, hue_image(BOY))

# remove the snail: fill with the local background colour, feathered
x0, y0, x1, y1 = 596, 500, 850, 740
# vertical gradient fitted on clean background pixels in the middle column band
ys_clean = np.r_[np.arange(0, 470), np.arange(728, Hh)]
col = rgb[ys_clean, 690:720].mean(axis=1)            # (n, 3)
coef = np.polyfit(ys_clean, col, 1)                  # (2, 3)
yr = np.arange(y0, y1)
bg_rows = (coef[0][None, :] * yr[:, None] + coef[1][None, :]).astype(np.float32)
patch = np.repeat(bg_rows[:, None, :], x1 - x0, axis=1)
patch += np.random.default_rng(1).normal(0, 0.003, patch.shape).astype(np.float32)
fy = np.minimum(np.arange(y1 - y0), np.arange(y1 - y0)[::-1]) / 28.0
fx = np.minimum(np.arange(x1 - x0), np.arange(x1 - x0)[::-1]) / 28.0
f = np.clip(np.minimum(fy[:, None], fx[None, :]), 0, 1)[..., None]
rgb[y0:y1, x0:x1] = rgb[y0:y1, x0:x1] * (1 - f) + np.clip(patch, 0, 1) * f

Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(out)
print("saved", out)
