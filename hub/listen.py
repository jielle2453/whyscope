"""ASR: per language faster-whisper on the CPU/GPU (small, beam 1) or Whisper on the UGen300 (listen.backend_by_lang;
the UGen is reached through the worker, and any failure there falls back to faster-whisper). Audio is decoded in memory and never written to disk.

Decoding: PCM16 wav via the stdlib; webm/ogg/mp4 via PyAV (bundles ffmpeg libraries, no ffmpeg binary needed);
last resort an external ffmpeg binary if present.
"""
import io
import shutil
import subprocess
import time

from .config import resolve, to_trad, torch_device

PROMPT = "以下是小朋友用台灣國語問的問題，使用繁體中文。"
PROMPT_EN = "A child asks a short question in English."


class Listener:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = None        # faster-whisper (zh, and the fallback for every language)
        self.error = None
        self.device = torch_device(cfg)
        self._hailo = None       # HailoWhisperRemote (hailo.worker set) or in-process HailoWhisper
        self.hailo_error = None  # why the last UGen call failed
        self.last = {}           # lang -> {"backend": "hailo"|"faster-whisper", "fallback": bool, "ms": int}

    def backend_for(self, lang: str) -> str:
        """Configured backend for a language: listen.backend_by_lang (en: hailo, zh: faster-whisper), else the old
        single listen.backend."""
        lc = self.cfg["listen"]
        return (lc.get("backend_by_lang") or {}).get(lang) or lc.get("backend") or "faster-whisper"

    def _wants_hailo(self, lang: str) -> bool:
        """UGen Whisper for this language: configured AND the hailo side exists (a worker or a whisper HEF)."""
        h = self.cfg.get("hailo") or {}
        return self.backend_for(lang) == "hailo" and bool(h.get("worker") or h.get("whisper_hef"))

    def _hailo_model(self):
        if self._hailo is None:
            from .hailo import HailoWhisper, HailoWhisperRemote
            self._hailo = HailoWhisperRemote(self.cfg) if (self.cfg.get("hailo") or {}).get("worker")                 else HailoWhisper(self.cfg)
        return self._hailo

    def _load(self):
        if self.model is not None:
            return
        from faster_whisper import WhisperModel
        lc = self.cfg["listen"]
        mode = self.cfg.get("mode", "cpu")
        ctype = lc["compute_type"].get(mode, "int8") if self.device == "cuda" else "int8"
        root = str(resolve(self.cfg, "models") / "whisper")
        try:
            self.model = WhisperModel(lc["model"], device=self.device, compute_type=ctype,
                                      download_root=root, local_files_only=True)
        except Exception:
            self.model = WhisperModel(lc["model"], device=self.device, compute_type=ctype, download_root=root)

    def warm(self):
        try:
            self._load()
        except Exception as e:
            self.error = f"{type(e).__name__}: {str(e)[:200]}"

    @staticmethod
    def _decode_wav(data: bytes):
        """PCM16 wav -> float32 mono 16 kHz, stdlib only. Returns None if the file is not plain PCM16."""
        import wave
        import numpy as np
        try:
            with wave.open(io.BytesIO(data)) as w:
                if w.getsampwidth() != 2:
                    return None
                ch, rate, raw = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
        except Exception:
            return None
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        if rate != 16000 and len(x):
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / rate)), np.arange(len(x)), x).astype(np.float32)
        return x

    @staticmethod
    def _decode_av(data: bytes):
        """webm/ogg/mp4/anything PyAV can read -> float32 mono 16 kHz (our own loop: faster-whisper's decoder
        breaks on newer PyAV releases)."""
        import av
        import numpy as np
        res = av.AudioResampler(format="s16", layout="mono", rate=16000)
        parts = []
        with av.open(io.BytesIO(data), mode="r") as c:
            for frame in c.decode(audio=0):
                out = res.resample(frame)
                for f in (out if isinstance(out, list) else [out]):
                    if f is not None:
                        parts.append(f.to_ndarray().reshape(-1))
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts).astype(np.float32) / 32768.0

    def _audio_array(self, data: bytes):
        x = self._decode_wav(data) if data[:4] == b"RIFF" else None
        if x is not None:
            return x
        try:
            return self._decode_av(data)
        except Exception:
            return self._decode_av(self._ffmpeg_to_wav(data))  # last resort: external ffmpeg binary, if present

    @staticmethod
    def _ffmpeg_to_wav(data: bytes) -> bytes:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("cannot decode audio and ffmpeg not found")
        p = subprocess.run([exe, "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
                           input=data, capture_output=True, check=True)
        return p.stdout

    def _fw(self, audio, lang: str) -> str:
        self._load()
        lc = self.cfg["listen"]
        segs, _ = self.model.transcribe(audio, language=lang or lc.get("language", "zh"),
                                        beam_size=int(lc.get("beam_size", 1)), vad_filter=True,
                                        initial_prompt=PROMPT_EN if lang == "en" else PROMPT, condition_on_previous_text=False)
        return "".join(s.text for s in segs).strip()

    def _transcribe(self, audio, lang: str = "zh"):
        """-> (text, backend). The UGen is tried first when configured for `lang`; any error there (worker down, model
        not loaded, timeout) falls back to faster-whisper for this request."""
        if len(audio) < 1600:  # < 0.1 s
            return "", "none"
        want = self._wants_hailo(lang)
        if want:
            try:   # Hailo's Whisper takes no initial prompt or beam size
                text = self._hailo_model().transcribe(audio, lang or self.cfg["listen"].get("language", "zh"))
                self.hailo_error = None
                return text, "hailo"
            except Exception as e:
                self.hailo_error = f"{type(e).__name__}: {str(e)[:200]}"
        self._fallback = want
        return self._fw(audio, lang), "faster-whisper"

    def transcribe_ex(self, data: bytes, lang: str = "zh"):
        """Like transcribe(), but returns (text, backend) where backend is "hailo" or "faster-whisper" (the one that
        answered; "none" for audio too short to try). Also kept in self.last[lang] for /healthz."""
        t = time.perf_counter()
        self._fallback = False
        text, backend = self._transcribe(self._audio_array(data), lang)
        self.last[lang] = {"backend": backend, "fallback": self._fallback, "ms": int((time.perf_counter() - t) * 1000)}
        # Whisper sometimes echoes the prompt on silence.
        prompt = PROMPT_EN if lang == "en" else PROMPT
        if text.replace(" ", "") in prompt.replace(" ", "") and len(text) > 8:
            return "", backend
        return (text.strip() if lang == "en" else to_trad(text).strip()), backend

    def transcribe(self, data: bytes, lang: str = "zh") -> str:
        """Return the transcript ('' if nothing was heard): Traditional script for zh, plain text for en."""
        return self.transcribe_ex(data, lang)[0]
