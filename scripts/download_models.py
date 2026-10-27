"""Download all models into ./models (run inside the venv). Quiet by design."""
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
MODELS = ROOT / cfg["paths"]["models"]
MODELS.mkdir(exist_ok=True)
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def step(name, fn):
    try:
        fn()
        print(f"[ok]   {name}")
    except Exception as e:  # keep going; the hub degrades gracefully
        print(f"[skip] {name}: {type(e).__name__}: {str(e)[:150]}")


def whisper():
    from faster_whisper import download_model
    download_model(cfg["listen"]["model"], cache_dir=str(MODELS / "whisper"))


def minilm():
    from huggingface_hub import snapshot_download
    snapshot_download("sentence-transformers/" + cfg["recall"]["model"],
                      cache_dir=str(MODELS / "hf"))


def qwen():
    from huggingface_hub import snapshot_download
    snapshot_download(cfg["compose"]["model"], cache_dir=str(MODELS / "hf"),
                      allow_patterns=["*.json", "*.safetensors", "*.txt"])


step("faster-whisper " + cfg["listen"]["model"], whisper)
step("MiniLM " + cfg["recall"]["model"], minilm)
if "--no-llm" not in sys.argv:
    step("compose LLM " + cfg["compose"]["model"], qwen)
print("models dir:", MODELS)
