# Whyscope (好奇鏡)

An on-device "why" tool for children aged 5 to 8. A child speaks or types a question (optionally showing the
camera an object); the hub recognises it, retrieves from a curated, source-cited kids' knowledge base, speaks a
child-level answer plus one question back about the object, and logs the event for a parent page.

**Status: Stage I prototype, laptop mode; Hailo mode planned for Stage II.**

## Why on-device

Children's voices and living rooms should not go to a cloud. Whyscope processes audio and images in memory,
stores only question and answer text, calls no cloud AI at run time, and routes anything sensitive or uncertain to a
parent instead of guessing. See [docs/safety.md](docs/safety.md).

## Quickstart

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1   # venv + deps + models (Linux/macOS: scripts/install.sh)
scripts\run.ps1                                                  # serves http://localhost:8000  (scripts/run.sh)
# open http://localhost:8000/kid  (child)   and   http://localhost:8000/parent  (parent)
# English is the default (questions, answers, speech); add ?lang=zh for Chinese: http://localhost:8000/kid?lang=zh
```

Language: the child and parent pages start in English. The "EN / 中" toggle (or `?lang=zh`) switches the page and the
answer language and also saves the server default (`POST /api/settings {"language": "zh"}`); `POST /api/ask` takes an
optional `lang` ("en" | "zh", default = that setting). Speech recognition (faster-whisper) and the browser voice follow the
language; English answers use an en-US voice (Natural / Aria / Jenny / Samantha / Google US English first).

Add `-Cpu` / `--cpu` to the installer on machines without an NVIDIA GPU and set `mode: cpu` in `config.yaml`.
Optional extras (vision, LLM compose) are in `requirements-optional.txt`; the hub works without them
(object from text, explanation from the entry's first fact).

If the checkout path is very long (over about 140 characters), the Windows installer puts the venv at
`C:\whyscope-venv` instead of `.venv` (CUDA DLLs fail to load from deep paths) and records it in `.venvpath`;
the run script follows that file.

## Screenshots

Taken in the built-in browser at 390 x 844 (phone portrait) with demo data (`scripts/seed_demo.py`: 29 real
questions, back-dated over two weeks; the child is called 小安 only on the parent page).

English is the default (`?lang=en`); the pill toggle "EN / 中" in each header switches to Chinese and is remembered in `localStorage.whyscope_lang`. In English mode the questions, answers, talk-about lines and cheat-sheet talking points are English too.

| Child: answer | Parent: Week | Parent: Cheats |
|---|---|---|
| ![kid answer](docs/screens/v3-kid-en-answer.png) | ![parent week](docs/screens/v3-parent-week-en.png) | ![parent cheats](docs/screens/v3-parent-cheats-en.png) |

## How an answer is spoken (product pass 1)

`POST /api/ask` returns after safety and recall (about 10 ms for text, about 330 ms for voice including ASR) with the
verbatim first sentence, `pending: true` and a `pending_id`; the explanation and the question back are composed in the
background and fetched with `GET /api/ask/{pending_id}` (HTTP 202 until ready; `?wait=1` on the POST gives the old
single-response behaviour). `kid.html` speaks the first sentence at once, polls every 300 ms (up to 8 s) and then speaks
the rest, sentence by sentence, with the sentence being spoken highlighted.

The voice rules live in `hub/wording.py` and are enforced in code: at most 18 characters per sentence, one explanation
sentence for ages 5-6 and two for 7-8, first sentence plus explanation at most 60 characters, no science jargon
(replaced by plain phrases), at most 2 uncommon characters per sentence, no device feelings or flattery, and every
question back is guessable (嗎 / 還是 / 猜 / 你覺得) and never asks about the child's day, feelings, family or friends.
Any LLM output that breaks a rule, repeats the first sentence or adds knowledge that is not in the entry is replaced by a
deterministic rewrite of the entry's own facts. Check it yourself with the server running:
`python eval/check_answers.py --age 6` (and `--age 8`).

English mode has its own rules in the same file: at most 12 words per sentence, at most 2 explanation sentences (1 for
ages 5-6), at most 45 spoken words, a plain-phrase map for about 15 science terms (reflect -> bounce back, ...), and at
most 2 uncommon words per sentence (a word longer than 9 letters counts double). "Common words" are not a hand-written
list: the set is built at startup from every word in the English fields of the knowledge entries plus the plain
phrases. The question back must contain "?" and one of "do you think", "or", "guess", "can you", "is it", "does".
Check: `python eval/check_answers.py --lang en --age 6` and `python eval/run_abstention.py --lang en`.

## Architecture in brief

`listen -> safety -> vision -> recall -> compose -> log`. The first sentence always comes verbatim from the
knowledge entry; a small LLM may only rewrite the entry's facts, with a grounding check and a template fallback.
Details, the modes table and data-flow diagram: [docs/architecture.md](docs/architecture.md).
The binding contract is [docs/spec.md](docs/spec.md).

## Repo map

```
hub/            FastAPI service (server, pipeline, listen, safety, vision, recall, compose, wording, emoji, memory, report, db)
hub/static/     kid.html (child) and parent.html (parent), single-file pages, no CDNs
knowledge/      entries/<topic>/*.json (CC BY-SA 4.0), cheats/*.json, sensitive_rules.json
eval/           run_latency.py, run_abstention.py, check_answers.py, abstention_set.jsonl, abstention_set_en.jsonl
scripts/        install and run scripts, download_models.py, build_common_chars.py, seed_demo.py
docs/           spec, architecture, models, safety, hardware, roadmap, benchmarks
config.yaml     mode (cpu | gpu | hailo), models, thresholds, retention
```

## Measure it

```
.venv\Scripts\python eval\run_latency.py        # per-stage mean / p95, appends to docs/benchmarks.md
.venv\Scripts\python eval\run_abstention.py     # answer/abstain accuracy on eval/abstention_set.jsonl
.venv\Scripts\python eval\run_latency.py --url http://127.0.0.1:8000   # same, through a running server (adds http_first_ms)
.venv\Scripts\python eval\check_answers.py --age 6   # child-voice rules on 10 real answers (server running)
.venv\Scripts\python eval\check_answers.py --lang en   # the same in English (eval/abstention_set_en.jsonl)
.venv\Scripts\python evalun_abstention.py --lang en  # English answer/abstain accuracy
```

## License

Code: Apache-2.0 (`LICENSE`). Knowledge entries: CC BY-SA 4.0 (`knowledge/LICENSE`). Models keep their own
licenses, listed in [docs/models.md](docs/models.md).
