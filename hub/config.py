"""Config loading and small shared helpers."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_CONV = None
_S2T = None


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
    """Simplified -> Traditional (Taiwan) if opencc is installed; otherwise unchanged.
    Text that is already Traditional is returned as is: s2twp's phrase table would otherwise rewrite correct Taiwan
    words (打開 -> 開啟, 社區 -> 社群, 循環 -> 迴圈). Only text with simplified characters (ASR output) is converted."""
    global _CONV, _S2T
    if _CONV is None:
        try:
            from opencc import OpenCC
            _CONV = OpenCC("s2twp").convert
            _S2T = OpenCC("s2t").convert
        except Exception:
            _CONV = _S2T = lambda s: s  # noqa: E731
    if not text or _S2T(text) == text:
        return text
    return _CONV(text)
