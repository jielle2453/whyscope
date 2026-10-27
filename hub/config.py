"""Config loading and small shared helpers."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_CONV = None


def load_config(path=None) -> dict:
    """Load config.yaml (or $WHYSCOPE_CONFIG / explicit path)."""
    p = Path(path or os.environ.get("WHYSCOPE_CONFIG") or ROOT / "config.yaml")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(cfg: dict, key: str) -> Path:
    """Resolve cfg['paths'][key] against the repo root."""
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else ROOT / p


def torch_device(cfg: dict) -> str:
    """'cuda' when mode is gpu and CUDA is available, else 'cpu'."""
    if cfg.get("mode") == "gpu":
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
    return "cpu"


def to_trad(text: str) -> str:
    """Simplified -> Traditional (Taiwan) if opencc is installed; otherwise unchanged."""
    global _CONV
    if _CONV is None:
        try:
            from opencc import OpenCC
            _CONV = OpenCC("s2twp").convert
        except Exception:
            _CONV = lambda s: s  # noqa: E731
    return _CONV(text)
