# UGen300 CLIP image encoder vs CPU CLIP weights

Result: the Hailo `clip_vit_b_32_image_encoder.hef` is the **OpenAI ViT-B/32** image encoder (int8-quantised).
laion2b_s34b_b79k was therefore not downloaded or compared.

## Hub config (use these)

```yaml
vision:
  clip_pretrained: openai
  clip_labels: models/clip/labels_openai.npz   # precomputed text side; hub needs no CLIP text encoder at run time
```
(The `models/` folder is the whyscope data dir: `C:\Users\Jie\Desktop\whyscope\whyscope\models\clip`. The OpenAI CPU weights
are there too, in the HF cache entry `models--timm--vit_base_patch32_clip_224.openai`, open_clip loads them with
`pretrained="openai", cache_dir=<models>/clip`. The old laion2b setting has no weights on disk.)

## Numbers (eval/ugen/clip_match.py, 30 images: 6 photos x {orig, flip, crop, half-size} + 6 synthetic)

| comparison | cosine |
|---|---|
| UGen vs CPU OpenAI, same image | mean 0.961, min 0.933, max 0.973 |
| UGen vs CPU OpenAI, different images | mean 0.626 |
| UGen vs UGen, different images | mean 0.617 |

Note: snapshots 103/104/105 are the same pictures as demo-photos 12/13/14, so the "max" of the different-image rows is
about 1.0 / 0.97 (duplicates, not a mismatch). Same-image cosine of 0.93-0.97 vs about 0.62 across images: a clear match,
the gap from 1.0 is int8 quantisation. Use the UGen embedding and the OpenAI text embeddings together (cosine ~0.96 of the CPU image
vector is enough; zero-shot ranking below is nearly identical).

Preprocessing note: the worker's Python has no Pillow, so the test script sent `Content-Type: application/x-raw-u8`
(224x224x3 crop, shorter side resized to 224 bicubic + centre crop, same as vision_bench.clip_u8). Posting a JPEG gives HTTP 501
with that hint. The hub (which has Pillow) should send the raw crop or have the worker's Pillow available.

## Zero-shot (prompt "a photo of a {label}", English labels, raw cosine; softmax x100 over ~1150 labels is flat, so use a
top-1 margin / min cosine ~0.25 rather than the old softmax min_confidence)

| image | UGen top-3 | CPU top-3 |
|---|---|---|
| 12-film / 103 | balloon .266, beach ball .265, balloon air .265 | beach ball .270, balloon air .268, balloon .266 |
| 13-film / 104 | snail .325, burrow .274, worm .271 | snail .314, burrow .266, acorn .264 |
| 14-film / 105 | owl eye .283, cat fur .277, eye .272 | owl eye .267, cat fur .266, eye .264 |
| synthetic yellow circle | big sun .293, Sun .291, sun .291 | big sun .310, sun .308, Sun .308 |
| synthetic blue | blue sky, blue sea, sky color | blue sea, blue sky, sky color |
| synthetic yellow | lemon, stoplight, butter | lemon, stoplight, banana |

UGen and CPU agree on the top label for all images (the order differs only between near-synonyms).
Many labels are phrases/synonyms of the same entry, so the hub should map the best label to its `entry_id` and take the max per entry.

## Label file

`scripts/build_clip_labels.py` (rerunnable) wrote `models/clip/labels_openai.npz`: 1276 labels (127 zh, 1149 en), arrays
`labels`, `lang`, `entry_id`, `emb` (float16, L2-normalised, 512-d). Chinese labels are included but OpenAI CLIP is
English-only, so match on `lang == "en"` and use `entry_id` to get to the entry (the zh rows are only useful as a fallback).
`knowledge/principles/principles.json` did not exist when it was built; rerun the script once it does (its `applies_to_en` rows
get `entry_id = "principle:<id>"`).

Rebuild: `set PYTHONIOENCODING=utf-8 & set HF_HUB_OFFLINE=1 & C:\whyscope-venv\Scripts\python scripts\build_clip_labels.py --pretrained openai --cache-dir C:\Users\Jie\Desktop\whyscope\whyscope\models\clip`
Re-run the comparison: `C:\whyscope-venv\Scripts\python eval\ugen\clip_match.py openai`
