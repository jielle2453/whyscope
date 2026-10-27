"""FastAPI app (spec section 6). Run: uvicorn hub.server:app --host 0.0.0.0 --port 8000"""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import report
from .memory import AUTO_KEYS, PARENT_KEYS
from .pipeline import Pipeline

STATIC = Path(__file__).resolve().parent / "static"
P: Pipeline = None


@asynccontextmanager
async def lifespan(app):
    global P
    P = Pipeline()
    yield


app = FastAPI(title="Whyscope hub", lifespan=lifespan)


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
async def ask(request: Request):
    """Accepts multipart (text/audio/image/mode) or JSON {text, mode}."""
    text, mode, audio, image = "", "text", None, None
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
        text, mode = body.get("text") or "", body.get("mode") or "text"
    else:
        form = await request.form()
        text, mode = form.get("text") or "", form.get("mode") or "text"
        if form.get("audio") is not None and hasattr(form["audio"], "read"):
            audio = await form["audio"].read() or None
        if form.get("image") is not None and hasattr(form["image"], "read"):
            image = await form["image"].read() or None
    if mode not in ("text", "voice"):
        mode = "voice" if audio else "text"
    res = await run_in_threadpool(P.ask, str(text), audio, image, mode)
    return res


@app.get("/api/events")
def events(days: int = 7):
    return P.db.list_events(days)


@app.get("/api/report/week")
def report_week():
    return report.week(P.db)


@app.get("/api/cheats")
def cheats(days: int = 30):
    """Sensitive events joined with their cheat sheet."""
    out = []
    for e in P.db.list_events(days, status="sensitive"):
        cat = e["sensitive_category"]
        c = P.safety.cheat(cat) or {}
        out.append({"event_id": e["id"], "ts": e["ts"], "question": e["question"], "category": cat,
                    "category_zh": c.get("category_zh") or P.safety.zh.get(cat, cat),
                    "urgent": bool(c.get("urgent", cat == "self_harm")), "cheat_done": bool(e["cheat_done"]),
                    "deflection_zh": c.get("deflection_zh") or e["first_sentence"],
                    "talking_points": c.get("talking_points", {}), "what_not_to_say": c.get("what_not_to_say", []),
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
    return {"memory": mem,
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
            "cloud_fallback": False, "mode": P.cfg.get("mode")}


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
    if body.get("cloud_fallback"):
        raise HTTPException(400, "cloud_fallback is not available")
    return _settings()


@app.post("/api/data/clear")
def data_clear():
    """Delete all events and auto-recorded memory. Parent-entered facts are kept (delete them separately)."""
    P.db.clear_events()
    P.db.mem_clear_auto()
    return {"ok": True}


@app.get("/api/data/export")
def data_export():
    body = json.dumps(P.db.export_all(), ensure_ascii=False, indent=2)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="whyscope-export.json"'})
