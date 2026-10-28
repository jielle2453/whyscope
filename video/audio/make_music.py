"""Synthesise the Whyscope score + UI sounds locally (numpy only, no downloads).

Writes to video/public/audio/: music.wav, tick.wav, tick2.wav, pop.wav, stamp.wav, bloom.wav
Music: C major, I-V-vi-IV (C G Am F) at 72 bpm. Quiet pad + sparse piano before the reveal;
a gentle arpeggio enters at the reveal beat (0:26) and resolves on a long C chord at the end.
Length follows src/timeline.json (so it stretches with the narration).
"""
import json, wave, pathlib
import numpy as np

SR = 44100
BPM = 72
BEAT = 60.0 / BPM
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "audio"
OUT.mkdir(parents=True, exist_ok=True)
tl = json.loads((ROOT / "src" / "timeline.json").read_text())
TOTAL = tl["total"] / tl["fps"]
REVEAL = next(b for b in tl["beats"] if b["key"] == "reveal")["start"] / tl["fps"]
CLOSE = next(b for b in tl["beats"] if b["key"] == "close")["start"] / tl["fps"]
rng = np.random.default_rng(7)


def write(name, x, stereo=False):
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(2 if stereo else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def adsr(n, a=0.01, d=0.2, s=0.6, r=0.3):
    t = np.arange(n) / SR
    env = np.ones(n)
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    env[:na] = np.linspace(0, 1, max(na, 1))
    env[na:na + nd] = np.linspace(1, s, nd)[: max(0, n - na)]
    env[na + nd:] = s
    if nr and n > nr:
        env[-nr:] *= np.linspace(1, 0, nr)
    return env


def piano(f, dur, vel=0.5):
    n = int((dur + 1.2) * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for h in range(1, 8):
        amp = 1.0 / h ** 1.35
        dec = 1.1 + 0.9 * h
        det = 1 + 0.0004 * h * h
        y += amp * np.sin(2 * np.pi * f * h * det * t) * np.exp(-dec * t * 0.55)
    y += 0.25 * np.exp(-2.2 * t) * (2 / np.pi) * np.arcsin(np.sin(2 * np.pi * f * t))  # triangle body
    y *= np.minimum(1, t / 0.006)  # attack
    y *= vel
    return y


def pad(freqs, dur, vel=0.15):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for f in freqs:
        for det in (-0.003, 0.0, 0.004):
            y += np.sin(2 * np.pi * f * (1 + det) * t + rng.random() * 6.28)
            y += 0.3 * np.sin(2 * np.pi * 2 * f * (1 + det) * t)
    y /= max(1, len(freqs) * 3)
    return y * adsr(n, a=1.6, d=0.5, s=0.85, r=2.0) * vel


# I-V-vi-IV in C: (root midi, chord tones)
CHORDS = [
    (48, [60, 64, 67]),  # C
    (55, [59, 62, 67]),  # G
    (57, [60, 64, 69]),  # Am
    (53, [60, 65, 69]),  # F
]
BAR = 4 * BEAT
N = int((TOTAL + 4) * SR)
L = np.zeros(N)
R = np.zeros(N)


def put(buf, y, t0, pan=0.5):
    i = int(t0 * SR)
    if i >= N:
        return
    y = y[: N - i]
    gl, gr = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
    L[i:i + len(y)] += y * gl
    R[i:i + len(y)] += y * gr


bar = 0
t = 0.0
while t < TOTAL - 0.1:
    root, tones = CHORDS[bar % 4]
    last = t + BAR >= CLOSE and t >= CLOSE - BAR  # resolve in the closing bar(s)
    if t >= CLOSE - BAR * 0.5:
        root, tones = CHORDS[0]
    # pad: gentle swell, louder after reveal
    level = 0.08 if t < REVEAL else 0.16
    pf = [hz(m) for m in tones] + [hz(root - 12)]
    put(None, pad(pf, BAR + 1.5, level), t, 0.5)
    # bass note on beat 1
    put(None, piano(hz(root - 12), BEAT * 3, 0.32 if t >= REVEAL else 0.18), t, 0.4)
    if t < REVEAL:
        # sparse: a lone chord tone on beat 1 and 3, very soft
        for k, m in enumerate([tones[1], tones[2]]):
            put(None, piano(hz(m + 12), BEAT, 0.14), t + k * 2 * BEAT, 0.45 + 0.1 * k)
    else:
        # chord stab on beat 1 + gentle 8th arpeggio
        for m in tones:
            put(None, piano(hz(m), BEAT * 2, 0.16), t + rng.random() * 0.012, 0.5)
        arp = [tones[0], tones[1], tones[2], tones[1] + 12, tones[2] + 12, tones[1] + 12, tones[2], tones[1]]
        tail = t >= CLOSE - 0.01
        for k, m in enumerate(arp):
            tt = t + k * BEAT / 2
            if tt > CLOSE - 0.05:
                break
            put(None, piano(hz(m + 12), BEAT, 0.20 if t < CLOSE - BAR else 0.12), tt, 0.35 + 0.3 * (k % 2))
    t += BAR
    bar += 1

# final resolve: long, open C major chord + high sparkle
fin = max(CLOSE, TOTAL - 5.0)
for m in (48, 60, 64, 67, 72, 76):
    put(None, piano(hz(m), 4.5, 0.22), fin + 0.05 * (m % 5), 0.5)
put(None, pad([hz(m) for m in (48, 55, 60, 64, 67)], 6.0, 0.22), fin, 0.5)

# reverb: exponential-decay noise impulse response, via FFT convolution
def reverb(x, wet=0.28, secs=2.4):
    n = int(secs * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 2.6)
    ir[0] = 0
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return x + wet * y / (np.abs(y).max() + 1e-9) * np.abs(x).max()


L = reverb(L)
R2 = reverb(R)
R = R2
# slow fade in / out
fade_in = np.minimum(1, np.arange(N) / (SR * 3.0))
end = int(TOTAL * SR)
fade_out = np.ones(N)
fade_out[end - int(2.5 * SR): end] = np.linspace(1, 0, int(2.5 * SR))
fade_out[end:] = 0
g = fade_in * fade_out
L *= g
R *= g
peak = max(np.abs(L).max(), np.abs(R).max())
mus = np.stack([L, R], axis=1)[:end] / peak * 0.9
write("music.wav", mus.reshape(-1), stereo=True)

# ---------- UI sounds ----------
def tick(f=2100, dur=0.07, vel=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) * np.exp(-t * 70) + 0.4 * np.sin(2 * np.pi * f * 2.01 * t) * np.exp(-t * 110)
    y[:20] += np.linspace(0.6, 0, 20) * rng.standard_normal(20) * 0.3
    return y * vel

write("tick.wav", tick(2100))
write("tick2.wav", tick(1560, 0.08, 0.45))

def pop():
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = 380 + 700 * np.exp(-t * 40)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 24) * 0.6

write("pop.wav", pop())

def stamp():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 95 * t * (1 - 0.2 * t)) * np.exp(-t * 11) * 0.9
    nz = rng.standard_normal(n) * np.exp(-t * 60) * 0.3
    return y + nz

write("stamp.wav", stamp())

def bloom():
    dur = 3.2
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.sin(np.pi * np.clip(t / dur, 0, 1) ** 1.6) ** 2  # swell then settle
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    y = 0.0
    cutoff = 300 + 5200 * (t / dur) ** 2
    a = 1 - np.exp(-2 * np.pi * cutoff / SR)
    for i in range(n):
        y += a[i] * (noise[i] - y)
        out[i] = y
    out /= np.abs(out).max()
    sweep = np.sin(2 * np.pi * np.cumsum(180 + 900 * (t / dur) ** 2) / SR) * 0.35
    chime = sum(np.sin(2 * np.pi * hz(m) * t) * np.exp(-(t - 1.9).clip(0) * 2.2) * (t > 1.9) for m in (72, 76, 79)) * 0.12
    return (out * 0.8 + sweep) * env * 0.7 + chime

write("bloom.wav", bloom())
print(f"music {TOTAL:.1f}s written; reveal at {REVEAL:.1f}s, close at {CLOSE:.1f}s")
