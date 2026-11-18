"""Real ASR noise for child speech: Windows SAPI TTS (offline) -> child-like voice (pitch/speed up, background noise)
-> faster-whisper small (the hub's zh / fallback model; same family as the UGen's Whisper-Small), English, beam 1.

Two separate profiles so the test noise is not the training noise:
  train: voice Zira, SAPI rate -3..0, pitch/speed factor 1.15-1.35, white noise at 18-32 dB SNR, seed 1
  test:  voice Hanhan (zh-TW voice reading English: a Taiwanese-accent stand-in) for 60% of clips, Zira for 40%;
         SAPI rate -1..+2, factor 1.10-1.30 (Hanhan) / 1.38-1.55 (Zira, outside the training range), pink noise + 60 Hz
         hum at 10-22 dB SNR, seed 2
Pitch: the 16 kHz clip is resampled to 1/f of its length and played at 16 kHz, so pitch and formants rise by f and speech
is f times faster (a child-like voice); the SAPI rate sets the speaking speed independently.

Usage: python asr_noise.py <in.jsonl with key,text> <out.jsonl> --profile train|test [--work DIR]
The whisper weights are read from a local cache only (models/whisper or the sibling checkout); nothing is downloaded.
"""
import argparse
import json
import random
import subprocess
import sys
from math import gcd
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly, lfilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WHISPER = [ROOT / "models" / "whisper", ROOT.parent / "whyscope" / "models" / "whisper"]
SR = 16000


def whisper_path():
    for root in WHISPER:
        snaps = list((root / "models--Systran--faster-whisper-small" / "snapshots").glob("*/model.bin"))
        if snaps:
            return str(snaps[0].parent)
    sys.exit("faster-whisper small not found locally; not downloading")


def profile(name, rng):
    if name == "train":
        return {"voice": "Microsoft Zira Desktop", "rate": rng.randint(-3, 0), "f": rng.uniform(1.15, 1.35),
                "noise": "white", "snr": rng.uniform(18, 32)}
    if rng.random() < 0.6:
        return {"voice": "Microsoft Hanhan Desktop", "rate": rng.randint(-1, 2), "f": rng.uniform(1.10, 1.30),
                "noise": "pink+hum", "snr": rng.uniform(10, 22)}
    return {"voice": "Microsoft Zira Desktop", "rate": rng.randint(-1, 2), "f": rng.uniform(1.38, 1.55),
            "noise": "pink+hum", "snr": rng.uniform(10, 22)}


def childify(x, p, rng):
    x = x.astype(np.float32) / 32768.0
    f = p["f"]
    up = 100
    down = int(round(100 * f))
    g = gcd(up, down)
    y = resample_poly(x, up // g, down // g).astype(np.float32)
    nrng = np.random.default_rng(rng.randrange(1 << 30))
    n = nrng.standard_normal(len(y)).astype(np.float32)
    if p["noise"].startswith("pink"):   # 1/f noise (Paul Kellet's filter approximation) + mains hum
        b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        a = [1, -2.494956002, 2.017265875, -0.522189400]
        n = lfilter(b, a, n).astype(np.float32)
        t = np.arange(len(y)) / SR
        n = n / (np.std(n) + 1e-9) + 0.5 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
    ps = np.mean(y ** 2) + 1e-12
    pn = np.mean(n ** 2) + 1e-12
    y = y + n * np.sqrt(ps / (pn * 10 ** (p["snr"] / 10)))
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.9
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--profile", choices=["train", "test"], required=True)
    ap.add_argument("--work", default="")
    a = ap.parse_args()
    seed = 1 if a.profile == "train" else 2
    rng = random.Random(seed)
    rows = [json.loads(l) for l in open(a.inp, encoding="utf-8") if l.strip()]
    work = Path(a.work or (HERE / "work" / f"tts_{a.profile}_{Path(a.inp).stem}"))
    work.mkdir(parents=True, exist_ok=True)
    params = {}
    with open(work / "list.tsv", "w", encoding="utf-8") as f:
        for r in rows:
            p = profile(a.profile, rng)
            params[r["key"]] = p
            txt = " ".join(str(r["text"]).replace("\t", " ").split())
            f.write(f"{r['key']}\t{p['voice']}\t{p['rate']}\t{txt}\n")
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "tts_sapi.ps1"),
                    str(work / "list.tsv"), str(work / "wav")], check=True)
    import os
    import torch   # its lib folder has the cuBLAS / cuDNN DLLs that ctranslate2 needs on Windows
    os.add_dll_directory(str(Path(torch.__file__).parent / "lib"))
    from faster_whisper import WhisperModel
    try:
        m = WhisperModel(whisper_path(), device="cuda", compute_type="float16")
    except Exception:
        m = WhisperModel(whisper_path(), device="cpu", compute_type="int8")
    with open(a.out, "w", encoding="utf-8") as fo:
        for i, r in enumerate(rows):
            p = params[r["key"]]
            sr, x = wavfile.read(work / "wav" / f"{r['key']}.wav")
            assert sr == SR
            y = childify(x, p, rng)
            segs, _ = m.transcribe(y, language="en", beam_size=1, vad_filter=False, condition_on_previous_text=False)
            asr = "".join(s.text for s in segs).strip()
            fo.write(json.dumps({**r, "asr": asr, "tts": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items()}},
                                ensure_ascii=False) + "\n")
            if i % 200 == 0:
                print(i, r["text"], "->", asr, flush=True)


if __name__ == "__main__":
    main()
