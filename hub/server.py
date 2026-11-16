"""FastAPI app (spec section 6). Run: uvicorn hub.server:app --host 0.0.0.0 --port 8000

Every /api call and /healthz carries a device token (hub/auth.py); the gate below decides who may call what and each
handler scopes its data to the caller's household (and, for a wand, to its one child)."""
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import auth as authm
from . import report
from .auth import Auth, AuthError, Ctx
from .config import resolve
from .emoji import emoji_for, TOPIC_EMOJI, TOPIC_EN, TOPIC_ZH
from .memory import AUTO_KEYS, AVATARS, PARENT_KEYS
from .pipeline import Pipeline

VERSION = "0.3.0 (accounts and pairing)"
STATIC = Path(__file__).resolve().parent / "static"
P: Pipeline = None
A: Auth = None


@asynccontextmanager
async def lifespan(app):
    global P, A
    P = Pipeline()
    A = Auth(P.db, P.cfg)
    yield


app = FastAPI(title="Whyscope hub", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")  # avatars, the characters image, the page scripts


@app.exception_handler(AuthError)
async def _auth_error(request, e: AuthError):
    return JSONResponse({"detail": e.detail}, status_code=e.status)


@app.middleware("http")
async def gate(request: Request, call_next):
    """Deny by default: public pages, the pairing redeem and (hub machine only) setup need no token; a wand token reaches
    only its own child's ask / reply / deliveries; everything else is for parents."""
    cls = authm.route_class(request.method, request.url.path)
    if cls == "public":
        return await call_next(request)
    if cls == "local":
        if not A.is_local(request):
            return JSONResponse({"detail": "localhost_only"}, status_code=403)
        request.state.ctx = None
        return await call_next(request)
    try:
        ctx = A.authenticate(request)
    except AuthError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
    if cls == "parent" and ctx.kind == "wand":
        return JSONResponse({"detail": "wand_not_allowed"}, status_code=403)
    request.state.ctx = ctx
    return await call_next(request)


# pages on another origin (a wand paired at the hub's LAN address, opened from elsewhere) may call the API with their token;
# no cookies are used, so nothing is sent unless the page holds a token
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                   allow_headers=["authorization", "content-type", "x-whyscope-pin"], max_age=600)


def _ctx(request: Request) -> Ctx:
    return request.state.ctx


def _children_ids(ctx: Ctx):
    return [c["id"] for c in P.db.children(ctx.household_id)]


def _child(request: Request, ctx: Ctx) -> int:
    """The child this call is about: a wand's own child; a parent's `?child=<id>` (must be in the household; default the first
    child; 0 when the household has none yet, which every query answers with nothing); the dev context's first child."""
    if ctx.kind == "wand":
        return ctx.child_id
    raw = request.query_params.get("child")
    ids = _children_ids(ctx)
    if raw not in (None, ""):
        try:
            cid = int(raw)
        except ValueError:
            raise HTTPException(400, "child must be an integer")
        if cid not in ids:
            raise HTTPException(404, "no such child")
        return cid
    if ctx.kind == "dev":
        return P.db.default_child_id(ctx.household_id)
    return ids[0] if ids else 0


def _may(ctx: Ctx, child_id) -> bool:
    if ctx.kind == "wand":
        return child_id == ctx.child_id
    return child_id is not None and P.db.child_household(child_id) == ctx.household_id


def _event(ctx: Ctx, event_id) -> dict:
    ev = P.db.get_event(event_id)
    if not ev or not _may(ctx, ev["child_id"]):
        raise HTTPException(404, "event not found")   # (another household's id looks the same as no id)
    return ev


def _store():
    """The relay key store (hub/tunnel.py), read fresh each time (the CLI may have set the relay URL since); None when the
    relay packages are not installed."""
    try:
        from .tunnel import Store
        return Store(resolve(P.cfg, "db").parent / "tunnel")
    except Exception:
        return None


def _child_view(c: dict, ctx: Ctx = None) -> dict:
    out = {"id": c["id"], "name": c["name"], "age": c["age"], "avatar": c["avatar"], "household_id": c["household_id"]}
    if ctx is not None and ctx.kind != "wand":
        out["open_todos"] = len(P.db.todo_list(child_id=c["id"]))
    return out


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


@app.get("/pair")
def pair_page():
    return _no_cache(FileResponse(STATIC / "pair.html", media_type="text/html"))


@app.get("/setup")
def setup_page():
    return _no_cache(FileResponse(STATIC / "setup.html", media_type="text/html"))   # hub machine only (the gate)


@app.get("/healthz")
def healthz():
    return {"ok": True, **P.status()}


@app.get("/api/ping")
def ping(request: Request):
    """Cheap reachability check with the token (the pages time it to choose the LAN or the relay)."""
    return {"ok": True, "kind": _ctx(request).kind}


@app.get("/api/me")
def me(request: Request):
    """Who this token is: household, child (a wand's own) or the household's children (a parent), device, and how to reach the hub."""
    ctx = _ctx(request)
    hh = P.db.household_get(ctx.household_id) or {}
    out = {"kind": ctx.kind, "dev": ctx.kind == "dev", "household": {"id": hh.get("id"), "name": hh.get("name")},
           "device": ({"id": ctx.device["id"], "name": ctx.device["name"], "kind": ctx.device["kind"]} if ctx.device else None),
           "allow_localhost_dev": A.allow_dev, "child": None, "parent": None, "children": []}
    if ctx.kind == "wand":
        out["child"] = _child_view(P.db.child_get(ctx.child_id), ctx)
    else:
        out["children"] = [_child_view(c, ctx) for c in P.db.children(ctx.household_id)]
        if ctx.parent_id:
            pr = P.db.parent_get(ctx.parent_id) or {}
            out["parent"] = {"id": pr.get("id"), "name": pr.get("name")}
        if ctx.kind == "dev":   # an old-style page with no token acts as the first child
            out["child"] = _child_view(P.db.child_get(P.db.default_child_id(ctx.household_id)), ctx)
        st = _store()
        out["relay"] = bool(st and st.relay)
    return out


# ------------------------------------------------------------------ setup (hub machine only) and pairing
@app.get("/api/setup/state")
def setup_state(request: Request):
    hhs = [{"id": h, "name": P.db.household_get(h)["name"], "parents": len(P.db.parents(h)), "children": len(P.db.children(h))}
           for h in P.db.household_ids()]
    st = _store()
    return {"households": hhs, "adopt": next((h["id"] for h in hhs if not h["parents"]), None), "lan_url": A.lan_url(request),
            "relay": bool(st and st.relay), "version": VERSION}


@app.post("/api/setup")
async def setup(request: Request):
    """First run on the hub machine: creates the household (an existing one without parents, e.g. the one made from an old
    database, is adopted so its history stays) and its first parent (name + PIN), and returns the parent QR code to scan.
    {household_name, parent_name, pin, new_household?: true} (new_household adds one more household to this hub)."""
    b = await request.json()
    free = [h for h in P.db.household_ids() if not P.db.parents(h)]
    if free and not b.get("new_household"):
        hh = free[0]
        if str(b.get("household_name") or "").strip():
            P.db.household_rename(hh, str(b["household_name"]).strip()[:40])
    else:
        hh = P.db.household_add(str(b.get("household_name") or "").strip()[:40] or "My household")
    pid = A.make_parent(hh, b.get("parent_name"), str(b.get("pin") or ""))
    pairing = A.create_pairing(hh, "parent", None, pid, f"{str(b.get('parent_name')).strip()}'s phone", A.lan_url(request), _store())
    return {"household_id": hh, "parent_id": pid, "pairing": pairing}


@app.post("/api/pair")
async def pair(request: Request):
    """The scanning device trades the one-time code for its token: {code, name?, pin?} (an invited parent sends name + pin).
    The token is returned once."""
    b = await request.json()
    ip = request.client.host if request.client else ""
    res = await run_in_threadpool(A.redeem, str(b.get("code") or ""), b.get("name"), b.get("pin"), ip)
    ch = P.db.child_get(res["child_id"]) if res["child_id"] else None
    return {**res, "child": _child_view(ch) if ch else None, "household": (P.db.household_get(res["household_id"]) or {}).get("name")}


@app.get("/api/children")
def children_list(request: Request):
    ctx = _ctx(request)
    return [_child_view(c, ctx) for c in P.db.children(ctx.household_id)]


@app.post("/api/children")
async def children_add(request: Request):
    """Add a child to the household: {name, age?, avatar?}."""
    ctx = _ctx(request)
    b = await request.json()
    name = str(b.get("name") or "").strip()
    if not name or len(name) > 24:
        raise HTTPException(400, "name is required (up to 24 characters)")
    try:
        age = int(b.get("age") or 6)
    except (TypeError, ValueError):
        raise HTTPException(400, "age must be an integer")
    if not 5 <= age <= 8:
        raise HTTPException(400, "age must be 5-8")
    av = b.get("avatar") or "girl"
    if av not in AVATARS:
        raise HTTPException(400, "avatar must be girl, boy or emoji")
    cid = P.db.child_add(ctx.household_id, name, age, av)
    return _child_view(P.db.child_get(cid), ctx)


@app.post("/api/pairing")
async def pairing_create(request: Request):
    """A one-time pairing code and QR URL (PIN required): {kind: "wand", child_id} or {kind: "parent"} (an invitation)."""
    ctx = _ctx(request)
    A.require_pin(request, ctx)
    b = await request.json()
    kind, child_id, name = b.get("kind"), None, ""
    if kind == "wand":
        try:
            child_id = int(b.get("child_id"))
        except (TypeError, ValueError):
            raise HTTPException(400, "child_id is required")
        ch = P.db.child_get(child_id)
        if not ch or ch["household_id"] != ctx.household_id:
            raise HTTPException(404, "no such child")
        name = f"Wand for {ch['name']}"
    elif kind != "parent":
        raise HTTPException(400, "kind must be wand or parent")
    return A.create_pairing(ctx.household_id, kind, child_id, None, name, A.lan_url(request), _store())


@app.get("/api/devices")
def devices_list(request: Request):
    ctx = _ctx(request)
    kids = {c["id"]: c["name"] for c in P.db.children(ctx.household_id)}
    pars = {p["id"]: p["name"] for p in P.db.parents(ctx.household_id)}
    cur = (ctx.device or {}).get("id")
    return [{"id": d["id"], "kind": d["kind"], "name": d["name"], "child_id": d["child_id"], "child": kids.get(d["child_id"]),
             "parent": pars.get(d["parent_id"]), "created": d["created"], "last_seen": d["last_seen"], "revoked": bool(d["revoked"]),
             "relay": bool(d["tunnel_id"]), "current": d["id"] == cur} for d in P.db.devices(ctx.household_id)]


@app.delete("/api/devices/{device_id}")
def device_revoke(device_id: int, request: Request):
    """Revoke a device (PIN required): its token stops working at once and its relay key is revoked too."""
    ctx = _ctx(request)
    A.require_pin(request, ctx)
    d = P.db.device_get(device_id)
    if not d or d["household_id"] != ctx.household_id:
        raise HTTPException(404, "no such device")
    P.db.device_revoke(device_id)
    if d.get("tunnel_id") and _store():
        _store().revoke(d["tunnel_id"])
    return {"ok": True}


# ------------------------------------------------------------------ the child's calls (a wand: its own child only)
@app.post("/api/ask")
async def ask(request: Request, wait: int = 0):
    """Accepts multipart (text/audio/image/mode/lang/asked_at) or JSON {text, mode, lang, asked_at}. `lang` is "en" or "zh"
    and defaults to the household's `language` setting (default "en"). `asked_at` (ISO 8601) is the original time of a
    question a wand kept in its curiosity jar while it was offline: the event is logged with that time.

    Returns after recall/safety with the first sentence and `pending: true` + `pending_id` (explanation and ask_back
    are empty); fetch the rest with GET /api/ask/{pending_id}. `?wait=1` blocks and returns the complete answer."""
    t0 = time.perf_counter()
    ctx = _ctx(request)
    child = _child(request, ctx)
    if not child:
        raise HTTPException(400, "add a child first")
    text, mode, audio, image, lang, asked_at = "", "text", None, None, None, None
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
        text, mode, lang, asked_at = body.get("text") or "", body.get("mode") or "text", body.get("lang"), body.get("asked_at")
    else:
        form = await request.form()
        text, mode, lang, asked_at = form.get("text") or "", form.get("mode") or "text", form.get("lang"), form.get("asked_at")
        if form.get("audio") is not None and hasattr(form["audio"], "read"):
            audio = await form["audio"].read() or None
        if form.get("image") is not None and hasattr(form["image"], "read"):
            image = await form["image"].read() or None
    if mode not in ("text", "voice"):
        mode = "voice" if audio else "text"
    if str((body if "application/json" in request.headers.get("content-type", "") else form).get("reset") or "").lower() in ("1", "true"):
        P.chat.memory.clear(child)   # "reset": start a new conversation (no follow-up context)
    if wait:
        return await run_in_threadpool(P.ask, str(text), audio, image, mode, True, lang, child, asked_at)
    return await run_in_threadpool(P.ask_first, str(text), audio, image, mode, True, t0, lang, child, asked_at)


@app.get("/api/ask/{pending_id}")
def ask_result(pending_id: str, request: Request):
    """The completed answer (`pending: false`), or HTTP 202 `{"pending": true}` while it is still being composed."""
    ctx = _ctx(request)
    res = P.poll(pending_id, _child(request, ctx))
    if res is None:
        raise HTTPException(404, "unknown pending_id")
    if res.get("pending"):
        return JSONResponse({"pending": True, "pending_id": pending_id}, status_code=202)
    return res


@app.post("/api/reply")
async def reply(request: Request):
    """The child's answer to the question back: JSON {event_id, choice (index, -1 = I don't know) | text, lang} or
    multipart with `audio`. Returns {result: right|wrong|both|open|idk|unknown, choice, say, heard}."""
    ctx = _ctx(request)
    choice, text, audio, lang, eid = None, "", None, None, None
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
        eid, choice, text, lang = body.get("event_id"), body.get("choice"), body.get("text") or "", body.get("lang")
    else:
        form = await request.form()
        eid, text, lang = form.get("event_id"), form.get("text") or "", form.get("lang")
        choice = form.get("choice")
        if form.get("audio") is not None and hasattr(form["audio"], "read"):
            audio = await form["audio"].read() or None
    try:
        eid = int(eid)
        choice = None if choice in (None, "") else int(choice)
    except (TypeError, ValueError):
        raise HTTPException(400, "event_id and choice must be integers")
    ev = _event(ctx, eid)
    try:
        return await run_in_threadpool(P.reply, eid, choice, str(text), audio, lang, ev["child_id"])
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/deliveries")
def deliveries_list(request: Request):
    """Approved answers the child has not heard yet. The kid page polls this, says "Your grown-up found the answer!",
    speaks `answer`, then calls POST /api/deliveries/{id}/done."""
    ctx = _ctx(request)
    return P.db.deliveries_pending(_child(request, ctx))


@app.post("/api/deliveries/{delivery_id}/done")
def delivery_done(delivery_id: int, request: Request):
    d = P.db.delivery_get(delivery_id)
    if not d or not _may(_ctx(request), d["child_id"]):
        raise HTTPException(404, "delivery not found")
    P.db.delivery_done(delivery_id)
    return {"ok": True}


# ------------------------------------------------------------------ the parent's calls (one household, `?child=<id>`)
@app.get("/api/events")
def events(request: Request, days: int = 7):
    child = _child(request, _ctx(request))
    return [{**e, "emoji": P.emoji_of(e["object"], e["topic"]) if e["status"] == "answered" else "",
             "topic_zh": TOPIC_ZH.get(e["topic"], ""), "topic_en": TOPIC_EN.get(e["topic"], ""),
             "talked": bool(e.get("talked"))} for e in P.db.list_events(days, child_id=child)]


@app.post("/api/events/{event_id}/talked")
def event_talked(event_id: int, request: Request):
    _event(_ctx(request), event_id)
    P.db.mark_talked(event_id)
    return {"ok": True}


def _item(ctx: Ctx, item_id: int) -> dict:
    it = P.db.todo_get(item_id)
    if not it or not _may(ctx, it["child_id"]):
        raise HTTPException(404, "item not found")
    return it


@app.get("/api/todo")
def todo_list(request: Request):
    """Parent assistant: questions the device could not answer, oldest first, each with the device's draft (written while
    no child was asking), the principles / entries it was grounded in, and the wording check. Open items only
    (pending, drafting, ready). A draft is only ever shown here, never to a child."""
    child = _child(request, _ctx(request))
    return {"items": P.assistant.items(child), "assistant": P.assistant.status(child)}


@app.post("/api/todo/{item_id}/approve")
async def todo_approve(item_id: int, request: Request):
    """Approve the draft as it is, or the parent's own text (JSON {"answer": "..."}). Stores a family answer
    (asked again, the child gets it) and queues a delivery for the kid page."""
    _item(_ctx(request), item_id)
    body = {}
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
    try:
        return await run_in_threadpool(P.assistant.approve, item_id, body.get("answer"))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/todo/{item_id}/dismiss")
def todo_dismiss(item_id: int, request: Request):
    _item(_ctx(request), item_id)
    try:
        return P.assistant.dismiss(item_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/todo/{item_id}/redraft")
def todo_redraft(item_id: int, request: Request):
    """Throw the draft away and let the device write a new one when the child is not asking."""
    _item(_ctx(request), item_id)
    try:
        return P.assistant.redraft(item_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/family")
def family_list(request: Request):
    """Answers a parent approved (the child gets one when a near-duplicate question is asked again). Shared by the household's children."""
    return P.db.family_all(with_embedding=False, household_id=_ctx(request).household_id)


@app.delete("/api/family/{family_id}")
def family_delete(family_id: int, request: Request):
    f = P.db.family_get(family_id)
    if not f or f["household_id"] != _ctx(request).household_id:
        raise HTTPException(404, "answer not found")
    P.family.delete(family_id)
    return {"ok": True}


@app.get("/api/snapshots")
def snapshots_list(request: Request):
    """Moments: events that have a local photo, newest first (metadata only; the image is served per id below)."""
    child = _child(request, _ctx(request))
    out = []
    for e in P.db.snapshot_events(child_id=child):
        if P.snap_path(e["id"]).exists():
            out.append({**e, "emoji": P.emoji_of(e["object"], e["topic"]) if e["status"] == "answered" else ""})
    return out


@app.get("/api/snapshots/{name}")
def snapshot_get(name: str, request: Request):
    """The saved photo of an event (`<event_id>.jpg`); 404 unless the file exists."""
    stem, dot, ext = name.rpartition(".")
    if not (dot and ext == "jpg" and stem.isdigit()) or not P.snap_path(stem).exists():
        raise HTTPException(404, "no snapshot")
    _event(_ctx(request), int(stem))
    resp = FileResponse(P.snap_path(stem), media_type="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-cache"   # revalidate (ids can be reused after "clear all")
    return resp


@app.delete("/api/snapshots/{event_id}")
def snapshot_delete(event_id: int, request: Request):
    _event(_ctx(request), event_id)
    P.delete_snapshot(event_id)
    return {"ok": True}


@app.delete("/api/snapshots")
def snapshots_delete_all(request: Request):
    return {"ok": True, "deleted": P.delete_all_snapshots(_ctx(request).household_id)}


@app.get("/api/report/week")
def report_week(request: Request, lang: str = None):
    """Weekly numbers; the talk-about lines come back in `lang` (default: the household's `language` setting)."""
    ctx = _ctx(request)
    child = _child(request, ctx)
    return report.week(P.db, 7, P.norm_lang(lang, ctx.household_id), P.entry_map(), P.emoji_of, P.db.todo_states(child), child)


@app.get("/api/cheats")
def cheats(request: Request, days: int = 30, lang: str = None):
    """Sensitive events joined with their cheat sheet. With lang=en the top-level `deflection`, `talking_points` and
    `what_not_to_say` are the English ones; the cheat's `en` object is passed through untouched as `en`."""
    ctx = _ctx(request)
    lang = P.norm_lang(lang, ctx.household_id)
    out = []
    for e in P.db.list_events(days, status="sensitive", child_id=_child(request, ctx)):
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
def cheat_done(event_id: int, request: Request):
    _event(_ctx(request), event_id)
    P.db.mark_cheat_done(event_id)
    return {"ok": True}


@app.get("/api/memory")
def memory_get(request: Request):
    child = _child(request, _ctx(request))
    mem = P.memory.all(child) if child else {}
    objs = (mem.get("recent_objects") or {}).get("value") or []
    return {"memory": mem, "emoji": {o: P.emoji_of(o) for o in objs}, "child_id": child,
            "keys": [{"key": k, "label_zh": v[0], "type": v[1]} for k, v in PARENT_KEYS.items()],
            "auto_keys": [{"key": k, "label_zh": v} for k, v in AUTO_KEYS.items()]}


@app.post("/api/memory")
async def memory_set(request: Request):
    child = _child(request, _ctx(request))
    if not child:
        raise HTTPException(400, "add a child first")
    body = await request.json()
    try:
        P.memory.set(body.get("key"), body.get("value"), child)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/memory")
def memory_delete(key: str, request: Request):
    child = _child(request, _ctx(request))
    if child:
        P.memory.delete(key, child)
    return {"ok": True}


@app.delete("/api/memory/{key}")
def memory_delete_path(key: str, request: Request):
    return memory_delete(key, request)


def _settings(hh):
    db = P.db
    return {"retention_days": int(db.setting_get("retention_days", P.cfg.get("retention_days", 30), hh)),
            "snapshots": bool(db.setting_get("snapshots", False, hh)),
            "snapshots_retention_days": int(db.setting_get("snapshots_retention_days", 30, hh)),
            "snapshot_count": P.snapshot_count(hh), "ai_guess": P.ai_guess_on(hh),
            "cloud_fallback": False, "mode": P.cfg.get("mode"), "version": VERSION, "language": P.default_lang(hh),
            "topics": {t: {"zh": TOPIC_ZH[t], "en": TOPIC_EN[t], "emoji": TOPIC_EMOJI[t]} for t in TOPIC_ZH}}


@app.get("/api/settings")
def settings_get(request: Request):
    return _settings(_ctx(request).household_id)


@app.post("/api/settings")
async def settings_set(request: Request):
    """Household settings. Everything except the display language needs the parent's PIN."""
    ctx = _ctx(request)
    hh = ctx.household_id
    body = await request.json()
    if set(body) - {"language"}:
        A.require_pin(request, ctx)
    if "retention_days" in body:
        try:
            d = int(body["retention_days"])
        except (TypeError, ValueError):
            raise HTTPException(400, "retention_days must be an integer")
        if not 1 <= d <= 365:
            raise HTTPException(400, "retention_days must be 1-365")
        P.db.setting_set("retention_days", d, hh)
        P.db.purge(d, hh)
        P.sweep_snapshots()
    if "snapshots" in body:
        if not isinstance(body["snapshots"], bool):
            raise HTTPException(400, "snapshots must be true or false")
        P.db.setting_set("snapshots", body["snapshots"], hh)
    if "snapshots_retention_days" in body:
        try:
            d = int(body["snapshots_retention_days"])
        except (TypeError, ValueError):
            raise HTTPException(400, "snapshots_retention_days must be an integer")
        if not 1 <= d <= 365:
            raise HTTPException(400, "snapshots_retention_days must be 1-365")
        P.db.setting_set("snapshots_retention_days", d, hh)
        P.sweep_snapshots()
    if "ai_guess" in body:   # uncovered questions: hedged AI guess (checked by the parent afterwards) or the old "ask a grown-up"
        if not isinstance(body["ai_guess"], bool):
            raise HTTPException(400, "ai_guess must be true or false")
        P.db.setting_set("ai_guess", body["ai_guess"], hh)
    if "language" in body:
        if body["language"] not in ("en", "zh"):
            raise HTTPException(400, "language must be 'en' or 'zh'")
        P.db.setting_set("language", body["language"], hh)
    if body.get("cloud_fallback"):
        raise HTTPException(400, "cloud_fallback is not available")
    return _settings(hh)


@app.post("/api/data/clear")
def data_clear(request: Request):
    """Delete all of the household's events (and their local photos) and auto-recorded memory (PIN required).
    Parent-entered facts are kept (delete them separately)."""
    ctx = _ctx(request)
    A.require_pin(request, ctx)
    P.db.clear_events(ctx.household_id)
    P.delete_all_snapshots(ctx.household_id)
    P.db.mem_clear_auto(ctx.household_id)
    return {"ok": True}


@app.get("/api/data/export")
def data_export(request: Request):
    """The household's records and settings as JSON (PIN required). Photos, tokens and PIN hashes are never included."""
    ctx = _ctx(request)
    A.require_pin(request, ctx)
    body = json.dumps(P.db.export_all(ctx.household_id), ensure_ascii=False, indent=2)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="whyscope-export.json"'})
