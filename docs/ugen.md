# What runs on the ASUS UGen300, and why

Whyscope uses the ASUS UGen300 USB (Hailo-10H, 8 GB, HailoRT 5.3.2) as the family computer's **ears, eyes and helper**. The
device is attached to a laptop host (verified on Windows 11; Ubuntu 24.04 is supported by ASUS but not yet run by us). Bring-up notes and the
exact steps are in [hardware.md](hardware.md); raw measurements are in [benchmarks.md](benchmarks.md).

## One process, one shared device, four models

Only one process can open the UGen300 over USB (a second one fails with `LIBUSB_ERROR_ACCESS`). So `hub/hailo_worker.py` is the
**device manager**: it listens on `127.0.0.1:8711` only, opens one shared VDevice and loads four models on it at the same time.
The hub never touches the device; it calls the worker over localhost (`hub/hailo.py`, `hub/hailo_vision.py`).

| model | job | endpoint | where the hub uses it |
|---|---|---|---|
| LLM, Qwen2.5-1.5B class HEF (Q4, about 2.46 GB) | parent assistant drafts; explanation rewrite | `/prime`, `/complete` | `hub/assistant.py`, `hub/compose.py` |
| Whisper-Small | English speech recognition | `/transcribe?lang=en` | `hub/listen.py` |
| YOLOv8s | find the main object in the camera frame | `/detect` | `hub/vision.py` |
| CLIP ViT-B/32 image encoder | match the object to a knowledge entry | `/clip_image` | `hub/vision.py` |
| optional: Qwen3-VL-2B HEF (`hailo.vlm_hef`), in place of the LLM | names what the child holds up when CLIP is not sure | `/describe` | `hub/vision.py`, `hub/pipeline.py` |

`POST /info` lists the loaded models (and the error of any that failed; the others keep working). Loading takes about 16 s in
all (LLM 8-12 s, Whisper-Small 3.2 s, YOLOv8s 0.3 s, CLIP 0.6 s). LLM and Whisper calls are serialized by one lock
(`GENAI_LOCK`); each vision model has its own lock. If the worker is down, the hub falls back to faster-whisper, its own
vision models and template answers, and recovers when the worker restarts (`/healthz` has a `ugen` block that shows which
backend answered).

## Ears: English speech recognition

* Whisper-Small on the UGen300: **WER 1.4 %**, about **1.0-1.2 s per clip** when the device is idle. This equals
  faster-whisper small on the CPU in accuracy, so the UGen does the work without a quality loss and frees the CPU.
* Whisper-Base was also measured (WER 3.4 %, 0.43 s) and not chosen: it saves about 0.6 s but doubles the error rate.
* Config: `listen.backend_by_lang: {en: hailo, zh: faster-whisper}`.

## Eyes: object recognition

* YOLOv8s runs in about **20 ms** (23-28 ms measured through the worker) and picks the main object.
* The CLIP image encoder is the OpenAI ViT-B/32 weights, int8: its embedding matches the CPU OpenAI model with **cosine 0.961**
  on the same image (min 0.933), against about 0.62 between different images ([eval/ugen/clip_match.md](../eval/ugen/clip_match.md)).
* The text side is precomputed (`scripts/build_clip_labels.py`, `models/clip/labels_openai.npz`), so **no CLIP text encoder
  runs at run time**: one image embedding is compared with the label table.
* The photo is processed in memory and is never stored.

## Which language models fit (measured 2026-11-16)

Two newer Hailo model zoo HEFs were probed next to Whisper-Small, YOLOv8s and CLIP (1.5 A USB power; tokens/s on a short
prompt; "context" = the saved prompt prefix the worker restores per call):

| setup | loads? | load time (all models) | text speed | first token | context size / restore |
|---|---|---|---|---|---|
| Qwen2.5-1.5B + rest (**default**) | yes | 11.7 s | 5.7 tokens/s | 0.48 s | 44 MB / 0.8 s |
| Qwen3-1.7B + rest | yes | 13-18 s | 3.75 tokens/s | 0.82 s | 147 MB / about 3 s |
| Qwen3-VL-2B + rest | yes | 14.7-15.6 s | 3.5 tokens/s | 0.84 s (text), 1.7 s (image) | 147 MB / 3.3 s |
| Qwen3-1.7B + Qwen3-VL-2B + rest | **no** | - | - | - | - |

**One GenAI model per device.** The second LLM/VLM fails with `HAILO_INVALID_OPERATION(6)` "Failed to acquire KV-Cache.
KV-Cache is already in use by another model". So the VLM can only come *instead of* the text LLM; the worker then uses the
VLM for text too (`hailo.vlm_hef` set, `hailo.llm_hef` empty: `/info` shows `llm.shared_with: vlm`).

**Which text model.** A/B on 65 fresh questions and the 50-turn chat set ([eval/model_ab_report.md](../eval/model_ab_report.md),
AI-judged): Qwen2.5 has the fewest false statements in AI guesses (8/41 against 15/42 for Qwen3 and 13/46 for Qwen3-VL) and is
the only one with a reply under 6 s (guess median 4.9 s against 8.8 s and 7.8 s). Qwen2.5 stays the default.

**Restarting the worker.** A force-killed worker leaves the device in a bad state: the next LLM load fails with
`HAILO_INTERNAL_FAILURE(8)` until a process that opened the device exits normally. `POST /shutdown` releases every model and
the VDevice and exits; `scripts\start_ugen.ps1 -RestartWorker` uses it (and only kills after 30 s).

## Eyes, part 2: the VLM (optional, off by default)

With `config.hailo-vlm.yaml` (`hailo.vlm_hef` = Qwen3-VL-2B, `llm_hef` empty, `vision.vlm.enabled: true`):

* **CLIP stays the fast path.** YOLOv8s + CLIP answer first (about 0.1 s). Only when CLIP is not sure and the child asks a
  "what is this?" style question does the hub call `/describe` (raw RGB frame letterboxed to 512x288).
* The VLM is asked for a short noun phrase. The phrase is matched to the KB label table first (`Vision.match_phrase`: head noun
  and every label word must match); a match gives the normal curated answer. No match: a pure "what is this?" gets
  "Ooh, that looks like a toy car! ..." (checked by the wording guard), any other question gets the phrase as a note
  to the chat model ("it looks like ..."), which may say what it looks like but must not tell facts about it.
* Phrases about people, hair, faces, clothes, screens or textures are dropped (`exclude_topics: [body, people]` for the camera),
  and so is the prompt's own example phrase, which the 2B model repeats when it is not sure.

Calibration (`python eval/ugen/vision_calib.py --vlm`, 22 test images, mostly synthetic):

| | right | wrong | missed | correctly nothing | median / p90 |
|---|---|---|---|---|---|
| CLIP only | 11 | 2 | 3 | 6 | 112 / 128 ms |
| VLM only (phrase matched to KB) | 5 | 0 | 11 | 6 | 2777 / 2788 ms |
| CLIP first, VLM when CLIP is unsure | 11 | 2 | 3 | 6 | +2.8 s on unsure frames |

The VLM never gave a wrong KB label, but it rescued none of CLIP's 3 misses here; its value is the "looks like" line for
things the KB does not have (a blue fuzzy toy, a toy car). It is sensitive to the prompt wording and to JPEG re-encoding.
Because it also replaces the faster text model (replies about 3 s slower, more false guesses), **it is off by default**.

## Helper: the parent assistant

When a question is not covered, the child hears "I'm not sure, I'll ask your grown-up" and the question lands in the parent's
**To answer** list. After `assistant.idle_s` (20 s) without a child request, the UGen's LLM drafts an answer in the background:
at most 3 short sentences plus a "Try it together" idea, grounded in the 3 best-matching principles or entries, checked against
the wording rules, written one sentence per worker call so a child request waits at most for the sentence in flight. A parent
approves, edits or dismisses it; the approved text is delivered to the child ("Your grown-up found the answer!") and stored as a
**family answer** for the household. The draft is labelled "Draft written by the device. Check it before your child hears it."

**Why the LLM does not answer children directly.** The 1.5B model hallucinates facts (`eval/principles/report.md`: even with the
right principle it reverses or invents facts in about half of its answers; `eval/coverage_report.md`: false statements in many
Wikipedia-grounded answers). So children get curated, reviewed or parent-approved text; the LLM only drafts for a person to check,
and may only rewrite a curated entry's own facts under a grounding check with a template fallback.

## What stays on the CPU, and why

| stage | where | why |
|---|---|---|
| Chinese speech recognition | faster-whisper (CPU) | UGen Whisper CER is 10.7-15.3 % against 2.7 % on CPU. An honest limitation: Chinese is secondary and stays on the CPU |
| Question matching (recall, principles, family) | MiniLM sentence embeddings (CPU) | a text-embedding model is small and fast (about 7 ms); not worth a device slot |
| Safety rules, wording rules, quiz | plain code and JSON | deterministic; no model needed |
| Text to speech | the client's browser voice | no server TTS in this prototype |

## Power note

The test laptop's USB-C ports advertise only 1.5 A, so the UGen300 may run in reduced-performance mode there; the measured numbers
were taken at 1.5 A and a 3.0 A port may be faster.

## Reproduce

`python scripts/check_ugen.py`, the worker's `POST /info`, `eval/ugen/` (ASR, vision, CLIP match, sharing benchmarks), and
`python eval/run_latency.py`. Numbers re-measured for the submission: {{LATENCY_FIRST_SENTENCE_P50}} (voice question to
first sentence), {{DRAFT_LATENCY_S}} (parent draft per item).
