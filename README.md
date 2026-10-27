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
```

Add `-Cpu` / `--cpu` to the installer on machines without an NVIDIA GPU and set `mode: cpu` in `config.yaml`.
Optional extras (vision, LLM compose) are in `requirements-optional.txt`; the hub works without them
(object from text, explanation from the entry's first fact).

## Screenshots

- Child page: `docs/img/kid.png` (placeholder)
- Parent page, 本週: `docs/img/parent-week.png` (placeholder)
- Parent page, 家長小抄: `docs/img/parent-cheats.png` (placeholder)

## Architecture in brief

`listen -> safety -> vision -> recall -> compose -> log`. The first sentence always comes verbatim from the
knowledge entry; a small LLM may only rewrite the entry's facts, with a grounding check and a template fallback.
Details, the modes table and data-flow diagram: [docs/architecture.md](docs/architecture.md).
The binding contract is [docs/spec.md](docs/spec.md).

## Repo map

```
hub/            FastAPI service (server, pipeline, listen, safety, vision, recall, compose, memory, report, db)
hub/static/     kid.html (child) and parent.html (parent), single-file pages, no CDNs
knowledge/      entries/<topic>/*.json (CC BY-SA 4.0), cheats/*.json, sensitive_rules.json
eval/           run_latency.py, run_abstention.py, abstention_set.jsonl
scripts/        install and run scripts, download_models.py
docs/           spec, architecture, models, safety, hardware, roadmap, benchmarks
config.yaml     mode (cpu | gpu | hailo), models, thresholds, retention
```

## Measure it

```
.venv\Scripts\python eval\run_latency.py        # per-stage mean / p95, appends to docs/benchmarks.md
.venv\Scripts\python eval\run_abstention.py     # answer/abstain accuracy on eval/abstention_set.jsonl
```

## License

Code: Apache-2.0 (`LICENSE`). Knowledge entries: CC BY-SA 4.0 (`knowledge/LICENSE`). Models keep their own
licenses, listed in [docs/models.md](docs/models.md).
