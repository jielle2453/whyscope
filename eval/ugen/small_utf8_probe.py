"""Does Whisper-Small on the UGen emit broken UTF-8 (U+FFFD) in zh because of per-token byte decoding?
Compares generate_all_text, generate_all_segments and the raw token ids' decoding, on a few zh wavs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hailo_models import MODELS, make_vdevice  # noqa: E402
from share_bench import wav  # noqa: E402
from hailo_platform.genai import Speech2Text, Speech2TextTask  # noqa: E402

vd = make_vdevice()
s = Speech2Text(vd, MODELS + r"\Whisper-Small.hef")
for i in ["zh-002", "zh-012", "zh-024", "zh-004"]:
    a = wav(i)
    t = s.generate_all_text(audio_data=a, task=Speech2TextTask.TRANSCRIBE, language="zh")
    g = "".join(x.text for x in s.generate_all_segments(audio_data=a, task=Speech2TextTask.TRANSCRIBE, language="zh"))
    print(i, "text:", repr(t), "| segs:", repr(g), flush=True)
    t2 = s.generate_all_text(audio_data=a, task=Speech2TextTask.TRANSCRIBE, language="zh", repetition_penalty=1.1)
    print("   rep1.1:", repr(t2), flush=True)
s.release()
