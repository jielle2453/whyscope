# Roadmap

## Stage I (done: this prototype)

Laptop hub, `mode: gpu` on an RTX 4060 laptop: text and voice questions, a growing knowledge base, abstention,
sensitive-topic routing, parent page. See [benchmarks.md](benchmarks.md) for what was measured and what was not.

## Stage II: 2026-11-06 to 2026-12-04 (four weeks)

Goal: the same pipeline on a Raspberry Pi 5 with an ASUS UGen300, in a child-safe enclosure, with measured numbers.

| week | dates | work |
|---|---|---|
| W1 | 11-06 to 11-13 | Assemble hardware ([hardware.md](hardware.md)). Check the UGen300 over USB and over PCIe with HailoRT and a GenAI sample. Decide Pi vs mini-PC fallback. Record speech from **20 children** (consent, no names, audio kept only for CER scoring in a separate offline set). |
| W2 | 11-14 to 11-20 | Port modules: SenseVoice-Small ASR, yolov8s + CLIP HEF vision, Hailo GenAI compose. Measure child Mandarin **CER** on the KB vocabulary from the W1 recordings. |
| W3 | 11-21 to 11-27 | End-to-end latency on device. Build and run the 200-question **abstention set** (`eval/abstention_set.jsonl`). Add **streaming TTS** (Piper or Kokoro) so the first sentence starts speaking while the rest is composed. |
| W4 | 11-28 to 12-04 | Enclosure, power and thermal soak. **Wizard-of-Oz** sessions with children. Cut a **10-minute video**. Write up results. |

### Five target metrics

| # | metric | target |
|---|---|---|
| 1 | First word latency (end of speech to first audio) | **<= 2.5 s** |
| 2 | Child Mandarin character error rate on KB vocabulary | **<= 20 %** |
| 3 | Pointing / object recognition accuracy at 0.5 to 1.5 m | **>= 85 %** |
| 4 | Abstention error on 200 questions (wrong answer or wrong abstain) | **<= 10 %** |
| 5 | Energy per question, measured at the wall with a USB power meter | measured and reported (no target yet) |

## After Stage II: watch and wearable clients

The hub already speaks a small HTTP API, so new clients are thin: a push-to-talk watch app or a wearable pendant
that records a question, posts it to a household hub, and plays the answer. Hardware and software for these would
come through **partnerships** with watch and wearable makers, not from building devices in-house. Open questions:
BLE or Wi-Fi link to the hub, battery budget for streaming TTS, and how to keep the parent page the single place
for oversight.
