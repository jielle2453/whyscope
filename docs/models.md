# Models

Every model the prototype uses or plans to use. "Version" for Hugging Face models means the snapshot downloaded by
`scripts/download_models.py` at install time (the files land in `models/`, which is git-ignored).
Licenses are as published by the model authors; check them again before shipping a product.

| stage | model | version / source | runs on (cpu / gpu / hailo) | license | link |
|---|---|---|---|---|---|
| listen | Whisper **small** via faster-whisper (CTranslate2) | `Systran/faster-whisper-small`, faster-whisper package | CPU int8 / CUDA float16 / replaced by SenseVoice | MIT | https://huggingface.co/Systran/faster-whisper-small |
| listen (Stage II) | SenseVoice-Small | FunASR release | CPU on Pi 5 | FunASR Model Open Source License | https://github.com/FunAudioLLM/SenseVoice |
| recall | paraphrase-multilingual-MiniLM-L12-v2 | `sentence-transformers/...` snapshot | CPU / CUDA / CPU | Apache-2.0 | https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 |
| compose | Qwen2.5-1.5B-Instruct | `Qwen/Qwen2.5-1.5B-Instruct` snapshot | llama-cpp GGUF Q4_K_M (CPU) / transformers fp16 (CUDA) / Hailo GenAI | Apache-2.0 | https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct |
| vision (optional) | YOLOv8n | Ultralytics `yolov8n.pt` | CPU / CUDA / yolov8s on Hailo | AGPL-3.0 (check terms before shipping) | https://github.com/ultralytics/ultralytics |
| vision (optional) | OpenCLIP ViT-B-32 | `laion2b_s34b_b79k` | CPU / CUDA / CLIP HEF on Hailo | MIT (code and weights) | https://github.com/mlfoundations/open_clip |
| text helpers | jieba (tokenizer for the grounding check) | PyPI | CPU | MIT | https://github.com/fxsjy/jieba |
| text helpers | OpenCC (simplified to Traditional, pure-Python port) | PyPI `opencc-python-reimplemented` | CPU | Apache-2.0 | https://github.com/yichen0831/opencc-python |
| speak | Browser `speechSynthesis`, zh-TW voice | the operating system or browser voices | the child's browser | OS-dependent | https://developer.mozilla.org/docs/Web/API/SpeechSynthesis |
| speak (Stage II) | Piper or Kokoro, Chinese voice | planned | CPU on Pi 5 | MIT / Apache-2.0, to be confirmed per voice | https://github.com/rhasspy/piper , https://github.com/hexgrad/kokoro |
| accelerator | Hailo-10H on ASUS UGen300 | Hailo GenAI runtime | hailo mode only | vendor | https://hailo.ai |

## Status per mode

| mode | status |
|---|---|
| gpu | implemented and measured on an RTX 4060 laptop (see [benchmarks.md](benchmarks.md)) |
| cpu | implemented, same code path with `device=cpu`; the llama-cpp GGUF path is written but unverified |
| hailo | **planned, unverified on UGen300**: SenseVoice-Small, yolov8s and CLIP HEF, Hailo GenAI LLM, Piper/Kokoro TTS |

## Knowledge base license

Knowledge entries paraphrase Chinese Wikipedia (CC BY-SA 4.0) or public-domain sources and are released under
CC BY-SA 4.0 (`knowledge/LICENSE`). The code is Apache-2.0.
