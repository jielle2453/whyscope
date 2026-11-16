"""Can several models share the UGen300 (one process, one VDevice, group_id SHARED)? HailoRT venv only.

    python eval\\ugen\\share_bench.py <scenario> --out <json> [--whisper <hef>] [--hold s]

scenarios (components are loaded in the order given, then called interleaved for ROUNDS rounds, then released):
    a   whisper + yolo + clip          b   whisper + llm          c   llm + yolo + clip
    d   swap: whisper -> release -> llm -> release -> whisper again (timed)
    hold-whisper   process 1 of the two-process test: load whisper, transcribe every 2 s for --hold seconds
    llm-only       process 2 of the two-process test: load the llm, 3 generations
    hold-llm / whisper-only   the same test the other way round
Every step records time, exception text and whether the output is still right.
"""
import argparse
import gc
import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from hailo_models import MODELS, Infer, make_vdevice  # noqa: E402

SP = Path(r"C:\Users\Jie\AppData\Local\Temp\claude\57443cdb2b122bd0\0ec9328b-c5a1-4a54-8d2f-8e114e8ca926\scratchpad")
LLM_HEF = Path(os.environ["LOCALAPPDATA"]) / "hailo-ollama" / "models" / "blob" / \
    "sha256_0856a10c2b804cfe1590b80aa5e28369eb7169a9b36de836420a0b8cdf5b8d05"
WAVS = ["zh-001", "zh-002", "zh-003", "en-001", "en-002", "en-003"]
ROUNDS = 3
LOG = []


def log(kind, **kw):
    kw = {"t": round(time.time() % 100000, 1), "kind": kind, **kw}
    LOG.append(kw)
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def wav(i):
    with wave.open(str(SP / "wav100" / f"{i}.wav"), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


class Whisper:
    def __init__(self, vd, hef):
        from hailo_platform.genai import Speech2Text
        self.s2t = Speech2Text(vd, hef)

    def run(self, i):
        from hailo_platform.genai import Speech2TextTask
        segs = self.s2t.generate_all_segments(audio_data=wav(i), task=Speech2TextTask.TRANSCRIBE,
                                              language=i[:2], timeout_ms=30000)
        return "".join(s.text for s in (segs or [])).strip()

    def close(self):
        try:
            self.s2t.release()
        except Exception:
            pass
        self.s2t = None


class LLM:
    def __init__(self, vd, hef):
        from hailo_platform.genai import LLM as L
        self.llm = L(vd, hef)

    def run(self, _=None):
        p = ("<|im_start|>system\nYou answer a child's question in one short sentence.<|im_end|>\n"
             "<|im_start|>user\nWhy is the sky blue?<|im_end|>\n<|im_start|>assistant\n")
        self.llm.clear_context()
        return self.llm.generate_all(prompt=p, temperature=0.1, seed=42, max_generated_tokens=40).strip()

    def close(self):
        try:
            self.llm.release()
        except Exception:
            pass
        self.llm = None


class Yolo:
    def __init__(self, vd):
        self.m = Infer(vd, MODELS + r"\yolov8s.hef")
        self.x = np.load(SP / "vision" / "yolo_in_0.npy")

    def run(self, _=None):
        r = list(self.m.run(self.x).values())[0]
        return sorted([(c, round(float(a[4]), 2)) for c, arr in enumerate(r) for a in np.asarray(arr).reshape(-1, 5) if a[4] >= 0.5])

    def close(self):
        self.m.close()


class Clip:
    def __init__(self, vd):
        self.m = Infer(vd, MODELS + r"\clip_vit_b_32_image_encoder.hef")
        self.x = np.load(SP / "vision" / "clip_in_0.npy")
        self.ref = None

    def run(self, _=None):
        e = np.asarray(list(self.m.run(self.x).values())[0], dtype=np.float32).reshape(-1)
        e /= np.linalg.norm(e)
        if self.ref is None:
            self.ref = e
        return round(float(e @ self.ref), 4)   # 1.0 = identical to the first call after loading

    def close(self):
        self.m.close()


def make(name, vd, whisper_hef):
    return {"whisper": lambda: Whisper(vd, whisper_hef), "llm": lambda: LLM(vd, str(LLM_HEF)),
            "yolo": lambda: Yolo(vd), "clip": lambda: Clip(vd)}[name]()


def load(name, vd, whisper_hef):
    t = time.perf_counter()
    try:
        m = make(name, vd, whisper_hef)
        log("load", model=name, ok=True, sec=round(time.perf_counter() - t, 2))
        return m
    except Exception as e:
        log("load", model=name, ok=False, sec=round(time.perf_counter() - t, 2), error=f"{type(e).__name__}: {str(e)[:300]}")
        return None


def call(name, m, arg=None):
    t = time.perf_counter()
    try:
        out = m.run(arg)
        log("call", model=name, arg=arg, ok=True, sec=round(time.perf_counter() - t, 2), out=out)
        return out
    except Exception as e:
        log("call", model=name, arg=arg, ok=False, sec=round(time.perf_counter() - t, 2), error=f"{type(e).__name__}: {str(e)[:300]}")
        return None


def release(name, m):
    t = time.perf_counter()
    try:
        m.close()
    except Exception as e:
        log("release", model=name, ok=False, error=str(e)[:200])
        return
    del m
    gc.collect()
    log("release", model=name, ok=True, sec=round(time.perf_counter() - t, 2))


def combo(names, vd, whisper_hef):
    ms = {}
    for n in names:
        m = load(n, vd, whisper_hef)
        if m is None:
            break
        ms[n] = m
        if n in ("whisper", "llm"):      # exercise each model right after loading, so a failure shows at once
            call(n, m, WAVS[0] if n == "whisper" else None)
    if len(ms) == len(names):
        for r in range(ROUNDS):
            for n, m in ms.items():
                call(n, m, (WAVS[(r * 2 + 1) % 6] if n == "whisper" else None))
    for n in reversed(list(ms)):
        release(n, ms[n])
    ms.clear()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--out", required=True)
    ap.add_argument("--whisper", default=MODELS + r"\Whisper-Base.hef")
    ap.add_argument("--hold", type=float, default=60)
    a = ap.parse_args()
    t0 = time.perf_counter()
    try:
        vd = make_vdevice()
        log("vdevice", ok=True, sec=round(time.perf_counter() - t0, 2))
    except Exception as e:
        log("vdevice", ok=False, error=f"{type(e).__name__}: {str(e)[:300]}")
        Path(a.out).write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    s = a.scenario
    if s in ("a", "b", "c"):
        combo({"a": ["whisper", "yolo", "clip"], "b": ["whisper", "llm"], "c": ["llm", "yolo", "clip"]}[s], vd, a.whisper)
    elif s == "d":
        for step in ("whisper", "llm", "whisper", "llm"):
            m = load(step, vd, a.whisper)
            if m:
                call(step, m, WAVS[0] if step == "whisper" else None)
                release(step, m)
    elif s in ("hold-whisper", "hold-llm"):
        name = s.split("-")[1]
        m = load(name, vd, a.whisper)
        end = time.time() + a.hold
        while m and time.time() < end:
            call(name, m, WAVS[3] if name == "whisper" else None)
            time.sleep(2)
        if m:
            release(name, m)
    elif s in ("llm-only", "whisper-only"):
        name = s.split("-")[0]
        m = load(name, vd, a.whisper)
        for k in range(3 if m else 0):
            call(name, m, WAVS[k] if name == "whisper" else None)
        if m:
            release(name, m)
    t = time.perf_counter()
    del vd
    gc.collect()
    log("vdevice_released", sec=round(time.perf_counter() - t, 2))
    Path(a.out).write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
