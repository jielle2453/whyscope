# Architecture

Whyscope (好奇鏡) is one small service (the **hub**) with two web clients: a child page and a parent page.
Nothing leaves the machine. The binding contract is [spec.md](spec.md); this file is the readable overview.

## Data flow

```
 CHILD CLIENT  /kid                          HUB (FastAPI, hub/)                              PARENT  /parent
 ┌──────────────────────┐   POST /api/ask   ┌────────────────────────────────────────┐
 │ hold-to-talk (audio) │ ───────────────►  │ 1 listen   faster-whisper  audio→text  │
 │ or typed text        │   multipart       │ 2 safety   keyword rules → sensitive?  │──► event(sensitive) ─┐
 │ optional camera frame│                   │ 3 vision   YOLO+CLIP (optional)        │                      │
 │                      │                   │ 4 recall   MiniLM cosine vs KB index   │                      │
 │ shows + speaks:      │ ◄───────────────  │            score < threshold → abstain │──► event(abstained)  │
 │  first_sentence      │   JSON answer     │ 5 compose  Qwen2.5-1.5B rewrite of     │                      │
 │  explanation         │                   │            facts, grounded, 6 s cap,   │                      │
 │  ask_back            │                   │            else template fallback      │                      │
 │ (browser TTS, zh-TW) │                   │ 6 log      SQLite event (no media)     │──► event(answered) ──┤
 └──────────────────────┘                   └────────────────────────────────────────┘                      │
                                                    ▲ knowledge/entries/*/*.json (CC BY-SA 4.0)             ▼
                                                    │ knowledge/cheats/*.json, sensitive_rules.json    本週 · 問題紀錄 · 家長小抄
                                                    │                                                  孩子的世界 · 設定
                                                    └── memory (parent facts → "bridges" to the child's world)
```

Key rules (spec section 8):

- The **first sentence is always the knowledge entry's own sentence**, spoken verbatim. The LLM never writes it,
  and nothing waits for the LLM before it can be spoken (`latency_ms.first_sentence` measures this).
- The LLM may only rewrite the entry's `facts` into one or two short sentences. A jieba grounding check
  requires every sentence to share a content word with a fact; otherwise, or on timeout or error,
  `explanation = facts[0]` and `ask_back = entry.ask_back`.
- Bridges (e.g. `has_dog`) are KB sentences, inserted verbatim only when the parent has set the matching memory key.
- Audio and image bytes live in memory for the duration of one request and are never written to disk or to SQLite.

## Components

| module | job |
|---|---|
| `hub/server.py` | HTTP API, static pages, startup (model preload, retention purge) |
| `hub/pipeline.py` | orchestration and per-stage timing |
| `hub/listen.py` | faster-whisper ASR, decoded in memory (PyAV), Traditional-script output |
| `hub/safety.py` | rules from `sensitive_rules.json` + cheat triggers, plus an always-on floor |
| `hub/vision.py` | optional YOLO crop + CLIP zero-shot over KB labels; no-op if packages are missing |
| `hub/recall.py` | sentence-transformers index over `labels + question_patterns`, cosine, threshold |
| `hub/compose.py` | LLM rewrite with grounding check and template fallback |
| `hub/memory.py`, `hub/db.py`, `hub/report.py` | parent facts, SQLite, weekly aggregation |

## Modes (config.yaml `mode`, spec section 9)

| stage   | cpu (any laptop)            | gpu (RTX 4060 laptop, **current default**) | hailo (Pi 5 + UGen300, Stage II) |
|---------|-----------------------------|---------------------------------------------|----------------------------------|
| listen  | faster-whisper small, int8  | faster-whisper small, float16               | SenseVoice-Small (CPU)           |
| vision  | yolov8n + open_clip ViT-B-32 | same, on CUDA                              | yolov8s + CLIP HEF on Hailo      |
| recall  | MiniLM-L12 multilingual     | same                                        | same (CPU)                       |
| compose | Qwen2.5-1.5B Q4_K_M via llama-cpp-python | transformers fp16 on CUDA      | Hailo GenAI                      |
| speak   | browser SpeechSynthesis zh-TW | same                                      | Piper/Kokoro zh (CPU)            |

The `hailo` column is a plan. The code treats `mode: hailo` like `cpu` today.

## Network and browser notes

The hub binds to `0.0.0.0:8000`. Browsers only allow microphone and camera on `localhost` or HTTPS, so open
`http://localhost:8000/kid` on the hub machine itself; for another device on the LAN put the hub behind HTTPS
(for example a self-signed certificate on a reverse proxy) or use the typed-question box, which works over plain HTTP.
