"""FastAPI app (spec section 6). Run: uvicorn hub.server:app --host 0.0.0.0 --port 8000"""
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import report
from .emoji import emoji_for, TOPIC_EMOJI, TOPIC_EN, TOPIC_ZH
from .memory import AUTO_KEYS, PARENT_KEYS
from .pipeline import Pipeline

VERSION = "0.2.0 (product pass 1)"
STATIC = Path(__file__).resolve().parent / "static"
P: Pipeline = None


@asynccontextmanager
async def lifespan(app):
    global P
    P = Pipeline()
    yield


app = FastAPI(title="Whyscope hub", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")  # avatars and the characters image


def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def root():
    return RedirectResponse("/kid")


@app.get("/kid")
def kid():
    return _no_cache(FileResponse(STATIC / "kid.html", media_type="text/html"))


@app.get("/parent")
def parent():
    return _no_cache(FileResponse(STATIC / "parent.html", media_type="text/html"))


@app.get("/healthz")
def healthz():
    return {"ok": True, **P.status()}


@app.post("/api/ask")
async def ask(request: Request, wait: int = 0):
    """Accepts multipart (text/audio/image/mode/lang) or JSON {text, mode, lang}. `lang` is "en" or "zh" and defaults
    to the `language` setting (default "en").

    Returns after recall/safety with the first sentence and `pending: true` + `pending_id` (explanation and ask_back
    are empty); fetch the rest with GET /api/ask/{pending_id}. `?wait=1` blocks and returns the complete answer."""
    t0 = time.perf_counter()
    text, mode, audio, image, lang = "", "text", None, None, None
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
        text, mode, lang = body.get("text") or "", body.get("mode") or "text", body.get("lang")
    else:
        form = await request.form()
        text, mode, lang = form.get("text") or "", form.get("mode") or "text", form.get("lang")
        if form.get("audio") is not None and hasattr(form["audio"], "read"):
            audio = await form["audio"].read() or None
        if form.get("image") is not None and hasattr(form["image"], "read"):
            image = await form["image"].read() or None
    if mode not in ("text", "voice"):
        mode = "voice" if audio else "text"
    if wait:
        return await run_in_threadpool(P.ask, str(text), audio, image, mode, True, lang)
    return await run_in_threadpool(P.ask_first, str(text), audio, image, mode, True, t0, lang)


@app.get("/api/ask/{pending_id}")
def ask_result(pending_id: str):
    """The completed answer (`pending: false`), or HTTP 202 `{"pending": true}` while it is still being composed."""
    res = P.poll(pending_id)
    if res is None:
        raise HTTPException(404, "unknown pending_id")
    if res.get("pending"):
        return JSONResponse({"pending": True, "pending_id": pending_id}, status_code=202)
    return res


@app.get("/api/events")
def events(days: int = 7):
    return [{**e, "emoji": P.emoji_of(e["object"], e["topic"]) if e["status"] == "answered" else "",
             "topic_zh": TOPIC_ZH.get(e["topic"], ""), "topic_en": TOPIC_EN.get(e["topic"], ""),
             "talked": bool(e.get("talked"))} for e in P.db.list_events(days)]


@app.post("/api/events/{event_id}/talked")
def event_talked(event_id: int):
    if not P.db.get_event(event_id):
        raise HTTPException(404, "event not found")
    P.db.mark_talked(event_id)
    return {"ok": True}


@app.get("/api/snapshots")
def snapshots_list():
    """Moments: events that have a local photo, newest first (metadata only; the image is served per id below)."""
    out = []
    for e in P.db.snapshot_events():
        if P.snap_path(e["id"]).exists():
            out.append({**e, "emoji": P.emoji_of(e["object"], e["topic"]) if e["status"] == "answered" else ""})
    return out


@app.get("/api/snapshots/{name}")
def snapshot_get(name: str):
    """The saved photo of an event (`<event_id>.jpg`); 404 unless the file exists."""
    stem, dot, ext = name.rpartition(".")
    if not (dot and ext == "jpg" and stem.isdigit()) or not P.snap_path(stem).exists():
        raise HTTPException(404, "no snapshot")
    resp = FileResponse(P.snap_path(stem), media_type="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-cache"   # revalidate (ids can be reused after "clear all")
    return resp


@app.delete("/api/snapshots/{event_id}")
def snapshot_delete(event_id: int):
    P.delete_snapshot(event_id)
    return {"ok": True}


@app.delete("/api/snapshots")
def snapshots_delete_all():
    return {"ok": True, "deleted": P.delete_all_snapshots()}


@app.get("/api/report/week")
def report_week(lang: str = None):
    """Weekly numbers; the talk-about lines come back in `lang` (default: the `language` setting)."""
    return report.week(P.db, 7, P.norm_lang(lang), P.entry_map(), P.emoji_of)


@app.get("/api/cheats")
def cheats(days: int = 30, lang: str = None):
    """Sensitive events joined with their cheat sheet. With lang=en the top-level `deflection`, `talking_points` and
    `what_not_to_say` are the English ones; the cheat's `en` object is passed through untouched as `en`."""
    lang = P.norm_lang(lang)
    out = []
    for e in P.db.list_events(days, status="sensitive"):
        cat = e["sensitive_category"]
        c = P.safety.cheat(cat) or {}
        en = c.get("en") or {}
        use_en = lang == "en" and bool(en)
        out.append({"lang": lang, "en": en or None, "event_id": e["id"], "ts": e["ts"], "question": e["question"], "category": cat,
                    "category_zh": c.get("category_zh") or P.safety.zh.get(cat, cat),
                    "urgent": bool(c.get("urgent", cat == "self_harm")), "cheat_done": bool(e["cheat_done"]),
                    "deflection_zh": c.get("deflection_zh") or e["first_sentence"],
                    "deflection": en.get("deflection") or e["first_sentence"] if use_en else
                    c.get("deflection_zh") or e["first_sentence"],
                    "talking_points": en.get("talking_points", {}) if use_en else c.get("talking_points", {}),
                    "what_not_to_say": en.get("what_not_to_say", []) if use_en else c.get("what_not_to_say", []),
                    "sources": c.get("sources", []), "has_cheat_sheet": bool(c)})
    return out


@app.post("/api/cheats/{event_id}/done")
def cheat_done(event_id: int):
    if not P.db.get_event(event_id):
        raise HTTPException(404, "event not found")
    P.db.mark_cheat_done(event_id)
    return {"ok": True}


@app.get("/api/memory")
def memory_get():
    mem = P.memory.all()
    objs = (mem.get("recent_objects") or {}).get("value") or []
    return {"memory": mem, "emoji": {o: P.emoji_of(o) for o in objs},
            "keys": [{"key": k, "label_zh": v[0], "type": v[1]} for k, v in PARENT_KEYS.items()],
            "auto_keys": [{"key": k, "label_zh": v} for k, v in AUTO_KEYS.items()]}


@app.post("/api/memory")
async def memory_set(request: Request):
    body = await request.json()
    try:
        P.memory.set(body.get("key"), body.get("value"))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/memory")
def memory_delete(key: str):
    P.memory.delete(key)
    return {"ok": True}


@app.delete("/api/memory/{key}")
def memory_delete_path(key: str):
    P.memory.delete(key)
    return {"ok": True}


def _settings():
    return {"retention_days": int(P.db.setting_get("retention_days", P.cfg.get("retention_days", 30))),
            "snapshots": bool(P.db.setting_get("snapshots", False)),
            "snapshots_retention_days": int(P.db.setting_get("snapshots_retention_days", 30)),
            "snapshot_count": P.snapshot_count(),
            "cloud_fallback": False, "mode": P.cfg.get("mode"), "version": VERSION, "language": P.default_lang(),
            "topics": {t: {"zh": TOPIC_ZH[t], "en": TOPIC_EN[t], "emoji": TOPIC_EMOJI[t]} for t in TOPIC_ZH}}


@app.get("/api/settings")
def settings_get():
    return _settings()


@app.post("/api/settings")
async def settings_set(request: Request):
    body = await request.json()
    if "retention_days" in body:
        try:
            d = int(body["retention_days"])
        except (TypeError, ValueError):
            raise HTTPException(400, "retention_days must be an integer")
        if not 1 <= d <= 365:
            raise HTTPException(400, "retention_days must be 1-365")
        P.db.setting_set("retention_days", d)
        P.db.purge(d)
        P.sweep_snapshots()
    if "snapshots" in body:
        if not isinstance(body["snapshots"], bool):
            raise HTTPException(400, "snapshots must be true or false")
        P.db.setting_set("snapshots", body["snapshots"])
    if "snapshots_retention_days" in body:
        try:
            d = int(body["snapshots_retention_days"])
        except (TypeError, ValueError):
            raise HTTPException(400, "snapshots_retention_days must be an integer")
        if not 1 <= d <= 365:
            raise HTTPException(400, "snapshots_retention_days must be 1-365")
        P.db.setting_set("snapshots_retention_days", d)
        P.sweep_snapshots()
    if "language" in body:
        if body["language"] not in ("en", "zh"):
            raise HTTPException(400, "language must be 'en' or 'zh'")
        P.db.setting_set("language", body["language"])
    if body.get("cloud_fallback"):
        raise HTTPException(400, "cloud_fallback is not available")
    return _settings()


@app.post("/api/data/clear")
def data_clear():
    """Delete all events (and their local photos) and auto-recorded memory. Parent-entered facts are kept (delete them separately)."""
    P.db.clear_events()
    P.delete_all_snapshots()
    P.db.mem_clear_auto()
    return {"ok": True}


@app.get("/api/data/export")
def data_export():
    """Records and settings as JSON. Photos are never included (events only carry a 0/1 `snapshot` flag)."""
    body = json.dumps(P.db.export_all(), ensure_ascii=False, indent=2)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="whyscope-export.json"'})
