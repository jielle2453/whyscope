# Whyscope prototype spec (shared contract for all contributors)

Whyscope (好奇鏡) is an on-device "why" tool for children aged 5–8. The child types or speaks a question
(optionally with a camera frame); the hub recognises, retrieves from a curated kids' knowledge base, composes a
child-level answer plus one question back, speaks it, and logs an event that the parent web app shows.
Audio and images are never stored. Everything runs locally (laptop now, Raspberry Pi 5 + ASUS UGen300 later).

## 1. Repository layout

```
whyscope/
├── README.md
├── LICENSE                      Apache-2.0 (code). Knowledge entries are CC BY-SA 4.0 (see knowledge/LICENSE).
├── config.yaml                  mode: cpu | gpu | hailo ; model names ; thresholds ; retention_days
├── hub/                         Python package (FastAPI service)
│   ├── server.py                app entry: uvicorn hub.server:app --host 0.0.0.0 --port 8000
│   ├── pipeline.py              orchestrates listen → safety → vision → recall → compose → log
│   ├── listen.py                ASR (faster-whisper on laptop; SenseVoice later)
│   ├── vision.py                optional: YOLO + CLIP label against KB labels; no-op if no image
│   ├── safety.py                sensitive-topic rules → deflection + cheat-sheet event
│   ├── recall.py                embedding retrieval over knowledge/entries/*.json, threshold abstention
│   ├── compose.py               Qwen2.5-1.5B-Instruct rewrite with fact-grounding check; template fallback
│   ├── memory.py                context memory (parent facts + auto topics) in SQLite
│   ├── report.py                weekly aggregation
│   ├── db.py                    SQLite schema + helpers (data/whyscope.db)
│   └── static/
│       ├── kid.html             child page  (/kid)
│       └── parent.html          parent page (/parent)
├── knowledge/
│   ├── LICENSE                  CC BY-SA 4.0 notice
│   ├── entries/<topic>/<id>.json   one entry per file (schema §2)
│   ├── cheats/<id>.json         parent cheat sheets for sensitive topics (schema §3)
│   └── sensitive_rules.json     keyword → category rules used by hub/safety.py
├── eval/
│   ├── abstention_set.jsonl     test questions (schema §4)
│   ├── run_abstention.py        prints precision of answer/abstain decisions
│   └── run_latency.py           times each stage for N text questions
├── scripts/
│   ├── install.ps1 / install.sh venv + deps + model download
│   └── run.ps1 / run.sh         start server
└── docs/
    ├── spec.md (this file), architecture.md, models.md, safety.md, roadmap.md, hardware.md,
    │   benchmarks.md, video-script.md, references.md
```

## 2. Knowledge entry schema — `knowledge/entries/<topic>/<id>.json`

```json
{
  "id": "animals-snail-shell",
  "topic": "animals",
  "topic_zh": "動物",
  "labels": ["蝸牛", "snail"],
  "question_patterns": ["為什麼蝸牛有殼", "蝸牛的殼是什麼", "蝸牛為什麼背著房子"],
  "first_sentence": "這是蝸牛！殼是牠的家。",
  "facts": ["殼可以保護蝸牛軟軟的身體", "天氣太乾的時候，蝸牛會躲進殼裡", "殼會跟著蝸牛一起長大"],
  "ask_back": "你覺得蝸牛下雨天會出來，還是躲在殼裡？",
  "bridges": {"has_dog": "你家的狗狗有毛，蝸牛為什麼沒有毛呢？", "has_sibling": "你會不會也想有一個可以躲進去的小房子？"},
  "age": "5-8",
  "source_url": "https://zh.wikipedia.org/wiki/蝸牛",
  "source_license": "CC BY-SA 4.0",
  "author": "claude-haiku",
  "reviewed_by": "",
  "spot_checked": false
}
```

Rules for entries:
- `id` = `<topic>-<slug>` ASCII kebab-case, unique, equals the filename without `.json`.
- `topic` ∈ {animals, plants, sky_weather, body, machines, food}; `topic_zh` ∈ {動物, 植物, 天氣與天空, 身體, 機器與家電, 食物}.
- `first_sentence` ≤ 20 Chinese characters, concrete, starts with naming the thing, ends with one causal clause.
  It is spoken verbatim (no model), so it must be correct and friendly.
- `facts`: 2–4 items, each ≤ 30 characters, plain Traditional Chinese (Taiwan usage), no jargon beyond grade 2,
  each must be supported by `source_url`.
- `ask_back`: exactly one question about the OBJECT (never about the child's feelings, day, family or friends),
  answerable by guessing, ≤ 30 characters.
- `bridges`: 0–3 optional, keyed by memory keys from §5 (`has_dog`, `has_cat`, `has_sibling`, `likes_dinosaurs`,
  `likes_cars`, `has_garden`, `rides_bike`); each is a question or sentence connecting the fact to that item.
- `question_patterns`: 3–6 ways a 5–8-year-old might phrase it, including "這是什麼" style and "為什麼" style.
- Source: Chinese Wikipedia (CC BY-SA 4.0) or public domain only. Never copy sentences; paraphrase facts.

## 3. Cheat sheet schema — `knowledge/cheats/<id>.json`

```json
{
  "id": "death",
  "category": "death",
  "category_zh": "死亡",
  "triggers": ["死", "死掉", "過世", "去世", "天堂", "不會動了"],
  "deflection_zh": "這個問題很重要，我們一起去問爸爸媽媽好嗎？",
  "talking_points": {
    "5-6": ["用具體、簡單的話，不用「睡著了」這類比喻", "……"],
    "7-8": ["……"]
  },
  "what_not_to_say": ["……"],
  "sources": [{"title": "……", "url": "https://…", "publisher": "衛生福利部"}],
  "author": "claude-haiku", "reviewed_by": ""
}
```
Categories: death, birth_sex, violence_war, divorce_family, illness, self_harm (self_harm must include Taiwan helplines
1925 安心專線 and 1995 生命線 in `talking_points` and set `"urgent": true`), money_poverty, religion, bullying, scary_news.

## 4. Abstention test set — `eval/abstention_set.jsonl`

One JSON per line: `{"q": "為什麼蝸牛有殼", "kind": "in_kb", "expect": "answer", "kb_id": "animals-snail-shell"}`.
`kind` ∈ {in_kb (paraphrase of an existing entry), near_kb (same topic, fact not in KB), out_kb (topic absent),
nonsense (gibberish or non-question)}; `expect` ∈ {answer, abstain}. in_kb → answer; others → abstain.

## 5. Context memory keys (hub/memory.py)

Parent-entered booleans/strings: `has_dog`, `has_cat`, `has_sibling` (string: e.g. "妹妹兩歲"), `likes_dinosaurs`,
`likes_cars`, `has_garden`, `rides_bike`, `child_name` (used ONLY in the parent UI, never spoken by the device),
`child_age` (5–8). Auto fields: `recent_topics` (last 20 topics asked), `recent_objects`.

## 6. HTTP API (hub/server.py)

- `POST /api/ask` multipart or JSON: `text` (optional), `audio` (optional wav/webm), `image` (optional jpeg), `mode` ("text"|"voice").
  Response: `{"question": str, "object": str|null, "topic": str|null, "kb_id": str|null, "confidence": float,
  "status": "answered"|"abstained"|"sensitive", "first_sentence": str, "explanation": str, "ask_back": str,
  "bridge_used": str|null, "latency_ms": {"listen":…, "vision":…, "recall":…, "compose":…, "total":…}}`
- `GET /api/events?days=7` → list of events (no audio/image ever).
- `GET /api/report/week` → `{"total": int, "by_topic": {…}, "talk_about": [...], "unanswered": [...], "bridges_used": [...]}`
- `GET /api/cheats` → sensitive events joined with cheat sheet; `POST /api/cheats/{event_id}/done`.
- `GET/POST/DELETE /api/memory` → §5 keys.
- `GET /api/settings`, `POST /api/settings` (retention_days, cloud_fallback=false), `POST /api/data/clear`, `GET /api/data/export`.
- `GET /kid`, `GET /parent` serve the static pages. `GET /healthz`.
- Product pass 1 additions (all existing fields are kept): `POST /api/ask` returns after recall/safety with `pending`,
  `pending_id`, `first_sentence_ms`, `reaction`, `emoji`, `event_id`, `reason` (abstained: unsure | not_heard | no_question) and
  empty `explanation`/`ask_back`; `GET /api/ask/{pending_id}` returns the full answer (`pending: false`) or 202
  `{"pending": true}`; `POST /api/ask?wait=1` blocks and returns the full answer; `POST /api/events/{id}/talked`;
  `/api/events` rows gain `emoji`, `topic_zh`, `talked`; `/api/report/week` gains `daily`, `prev_total`, `topics` and event
  ids/emoji on `talk_about`/`unanswered`; `/api/settings` gains `version` and `topics`; `events.talked` column.

## 7. SQLite schema (data/whyscope.db)

```
events(id INTEGER PK, ts TEXT, mode TEXT, question TEXT, object TEXT, topic TEXT, kb_id TEXT, status TEXT,
       first_sentence TEXT, explanation TEXT, ask_back TEXT, bridge_used TEXT, sensitive_category TEXT,
       cheat_done INTEGER DEFAULT 0, latency_total_ms INTEGER, latency_json TEXT)
memory(key TEXT PK, value TEXT, source TEXT, updated_ts TEXT)
settings(key TEXT PK, value TEXT)
```
Retention: a startup job deletes events older than `retention_days` (default 30).

## 8. Pipeline rules (hub/pipeline.py)

1. If `audio`: listen → text. If `text` empty after ASR → status abstained with "我沒聽清楚，再說一次好嗎？".
2. safety.check(text) → if category hit: status "sensitive", speak `deflection_zh`, log with `sensitive_category`. Stop.
3. If `image`: vision.label(image, kb_labels) → object + confidence; else object = recall's best label.
4. recall.search(text, object) → (entry, score). If score < `config.recall.threshold` (default 0.55): status "abstained",
   first_sentence = "我不確定，我們一起去問爸爸媽媽好嗎？", log. Stop.
5. compose: `first_sentence` is ALWAYS the entry's `first_sentence` verbatim. The LLM receives `facts`, child_age,
   available bridges (keys present in memory) and must return JSON `{"explanation": "...", "ask_back": "...", "bridge_used": key|null}`
   with explanation ≤ 2 sentences, ≤ 40 characters, using only given facts. Grounding check: every explanation sentence
   must share ≥ 1 content token (jieba) with some fact; otherwise fall back to `explanation = facts[0]`, `ask_back = entry.ask_back`.
   If the LLM is unavailable or slow (> 6 s), fall back the same way. Never block the first sentence on the LLM.
6. Log event; return response. Audio/image bytes are discarded after processing.

## 9. Models by mode (config.yaml)

| stage   | cpu (any laptop)            | gpu (RTX 4060 laptop)            | hailo (Pi 5 + UGen300, later) |
|---------|-----------------------------|----------------------------------|-------------------------------|
| listen  | faster-whisper small, int8  | faster-whisper small, float16    | SenseVoice-Small (CPU)        |
| vision  | yolov8n (ultralytics) + open_clip ViT-B-32 | same on CUDA      | yolov8s + CLIP HEF on Hailo   |
| recall  | sentence-transformers paraphrase-multilingual-MiniLM-L12-v2 | same | same (CPU)           |
| compose | Qwen2.5-1.5B-Instruct via llama-cpp-python GGUF Q4_K_M | transformers fp16 CUDA | Hailo GenAI |
| speak   | browser SpeechSynthesis (zh-TW) in kid.html | same              | Piper/Kokoro zh (CPU)         |

Vision and compose are optional at runtime: if their packages/models are missing, the pipeline still works
(object from text; explanation from facts[0]).
