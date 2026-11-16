# Models

Every model the code actually uses, per mode (`config.yaml` `mode: cpu | gpu | hailo`). Hugging Face and Ultralytics
weights are downloaded by `scripts/download_models.py` into `models/` (git-ignored). Licenses are as published by the model
authors; check them again before shipping a product. Nothing here is planned-only: SenseVoice and Piper/Kokoro are not in
the code and were removed from this page.

## Models in use

| stage | model | source / file | cpu mode | gpu mode | hailo mode | role |
|---|---|---|---|---|---|---|
| listen (zh, and fallback for every language) | Whisper small via faster-whisper (CTranslate2) | `Systran/faster-whisper-small` in `models/whisper` (`listen.model: small`) | CPU int8 | CUDA float16 | CPU int8 (Chinese; also answers when the UGen fails) | speech to text |
| listen (English) | Whisper-Small HEF (Whisper-Base HEF also measured, not chosen) | `hailo.whisper_hef` | CPU faster-whisper | CPU faster-whisper unless `listen.backend_by_lang.en: hailo` and a worker is set | UGen300 via `hub/hailo_worker.py` (`/transcribe?lang=en`) | English speech to text, WER 1.4% |
| recall, principles, family | paraphrase-multilingual-MiniLM-L12-v2 | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` in `models/hf` | CPU | CUDA | CPU | sentence embeddings for question matching |
| compose | Qwen2.5-1.5B-Instruct | cpu: GGUF `*qwen2.5-1.5b*q4_k_m*.gguf` in `models/` via llama-cpp-python if present, else `Qwen/Qwen2.5-1.5B-Instruct` via transformers fp32; gpu: transformers fp16; hailo: `hailo.llm_hef` (HEF from hailo-ollama `qwen2.5:1.5b`) | CPU | CUDA | UGen300 | rewrites a curated entry's facts under a grounding check (template fallback); in hailo mode also drafts parent answers (`hub/assistant.py`) |
| text model, measured not default | Qwen3-1.7B-Instruct HEF (Hailo model zoo) | `hailo.llm_hef` | - | - | UGen300 (fits, but more false guesses and slower: [eval/model_ab_report.md](../eval/model_ab_report.md)) | none by default |
| vision: describe (optional) | Qwen3-VL-2B-Instruct HEF (Hailo model zoo v5.3.0, 3.19 GB) | `hailo.vlm_hef`, `config.hailo-vlm.yaml` | - | - | UGen300, replaces the text LLM (one GenAI model per device) | names the held-up object when CLIP is not sure (`/describe`); off by default, see [ugen.md](ugen.md) |
| vision: detect | YOLOv8n (`vision.yolo_model: yolov8n.pt`, Ultralytics) / yolov8s HEF (`hailo.yolo_hef`) | `models/yolov8n.pt` | CPU | CUDA | UGen300 if `vision.backend: hailo` (else CPU) | finds the main object |
| vision: match | CLIP ViT-B/32 OpenAI weights via open_clip (`ViT-B-32-quickgelu`, `openai`) / CLIP image-encoder HEF (`hailo.clip_image_hef`) | `models/clip` | CPU | CUDA | UGen300 if `vision.backend: hailo` | image embedding compared with the precomputed label table `models/clip/labels_openai.npz` (`scripts/build_clip_labels.py`); no CLIP text encoder at run time |
| text helpers | jieba | PyPI | CPU | CPU | CPU | tokenizer for the grounding check |
| text helpers | OpenCC `s2twp` | PyPI `opencc-python-reimplemented` | CPU | CPU | CPU | simplified to Traditional (Taiwan) |
| speak | browser `speechSynthesis` | the child's phone/browser voices (`hub/static/kid.html`) | browser | browser | browser | reads answers aloud; there is no server-side TTS |

Safety rules, wording rules and the quiz are plain code and JSON, no model. Vision is optional (needs `ultralytics` and
`open_clip_torch`, see `requirements-optional.txt`); Qwen via transformers/llama-cpp is optional too (template answers
without it). Licenses: Whisper MIT; MiniLM Apache-2.0; Qwen2.5-1.5B Apache-2.0; Qwen3-1.7B and Qwen3-VL-2B Apache-2.0; YOLOv8 AGPL-3.0 (check terms before
shipping); CLIP / open_clip MIT; jieba MIT; OpenCC port Apache-2.0; browser voices OS-dependent. Hailo HEFs are subject to
Hailo's and ASUS's terms.

## Status per mode

| mode | status |
|---|---|
| gpu | implemented and measured on an RTX 4060 laptop (see [benchmarks.md](benchmarks.md)); current default in `config.yaml` |
| cpu | implemented, same code path on CPU; the llama-cpp GGUF path is written but unverified |
| hailo | **verified on the ASUS UGen300 USB (Windows 11, HailoRT 5.3.2)**: LLM, Whisper-Small (English), YOLOv8s and CLIP image encoder on one shared VDevice through the worker; Chinese ASR stays on CPU faster-whisper. See [ugen.md](ugen.md), [hardware.md](hardware.md) |

## Knowledge base license

Knowledge entries paraphrase Chinese Wikipedia (CC BY-SA 4.0) or public-domain sources and are released under
CC BY-SA 4.0 (`knowledge/LICENSE`). The code is Apache-2.0.
