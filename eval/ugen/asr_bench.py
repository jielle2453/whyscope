"""Speech recognition benchmark: Whisper on the UGen300 (Hailo Speech2Text) vs faster-whisper on CPU / GPU.

Each backend transcribes every WAV (16 kHz mono) of a question set and writes one JSONL line per file:
{"backend", "id", "lang", "ref", "hyp", "sec", "audio_sec"}. Score with eval/ugen/asr_score.py.

    # UGen300 (needs the HailoRT venv; nothing else may hold the device)
    C:\\whyscope-hailo-venv\\Scripts\\python eval\\ugen\\asr_bench.py hailo --hef <Whisper-Base.hef> --wavs <dir> --out <file>
    # faster-whisper (the hub venv)
    C:\\whyscope-venv\\Scripts\\python eval\\ugen\\asr_bench.py fw --model small --device cpu --wavs <dir> --out <file>
"""
import argparse
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def load_wav(p: Path) -> np.ndarray:
    with wave.open(str(p), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, p
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return (a.astype(np.float32) / 32768.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backend", choices=["hailo", "fw"])
    ap.add_argument("--hef")
    ap.add_argument("--model", default="small")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--wavs", required=True)
    ap.add_argument("--questions", default=str(ROOT / "eval" / "kid_questions.jsonl"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    qs = [json.loads(l) for l in Path(a.questions).read_text(encoding="utf-8").splitlines() if l.strip()]
    wavs = Path(a.wavs)
    t0 = time.perf_counter()
    if a.backend == "hailo":
        from hailo_platform import VDevice
        from hailo_platform.genai import Speech2Text, Speech2TextTask
        params = VDevice.create_params()
        params.group_id = "SHARED"
        vd = VDevice(params)
        s2t = Speech2Text(vd, a.hef)
        name = "hailo:" + Path(a.hef).stem

        def run(audio, lang):
            segs = s2t.generate_all_segments(audio_data=audio, task=Speech2TextTask.TRANSCRIBE, language=lang,
                                             timeout_ms=30000)
            return "".join(s.text for s in (segs or [])).strip()
    else:
        if a.device == "cuda":
            import torch  # noqa: F401  (puts torch's CUDA DLLs, cublas included, on the DLL search path)
        from faster_whisper import WhisperModel
        root = Path(r"C:\Users\Jie\Desktop\whyscope\whyscope\models\whisper")
        ctype = "float16" if a.device == "cuda" else "int8"
        m = WhisperModel(a.model, device=a.device, compute_type=ctype, download_root=str(root))
        name = f"fw:{a.model}:{a.device}"

        def run(audio, lang):
            segs, _ = m.transcribe(audio, language=lang, beam_size=1, vad_filter=False)
            return "".join(s.text for s in segs).strip()
    load_s = time.perf_counter() - t0
    print(f"{name} loaded in {load_s:.1f} s", flush=True)

    # warm-up (first call pays one-time costs)
    run(load_wav(wavs / f"{qs[0]['id']}.wav"), qs[0]["lang"])
    with open(a.out, "w", encoding="utf-8") as f:
        for q in qs:
            audio = load_wav(wavs / f"{q['id']}.wav")
            t = time.perf_counter()
            hyp = run(audio, q["lang"])
            sec = time.perf_counter() - t
            f.write(json.dumps({"backend": name, "id": q["id"], "lang": q["lang"], "ref": q["q"], "hyp": hyp,
                                "sec": round(sec, 3), "audio_sec": round(len(audio) / 16000, 2),
                                "load_sec": round(load_s, 2)}, ensure_ascii=False) + "\n")
            print(f"{q['id']} {sec:5.2f}s  {hyp}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
