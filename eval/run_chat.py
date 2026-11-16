"""Ask a question set through a running hub (POST /api/ask, phase 1 + polling, like the kid page) and record every reply.

    set PYTHONIOENCODING=utf-8
    C:\\whyscope-venv\\Scripts\\python eval\\run_chat.py eval\\chat_set_en.jsonl  [--out eval\\chat_results\\chat_en.jsonl]
    C:\\whyscope-venv\\Scripts\\python eval\\run_chat.py eval\\heldout_en_v3.jsonl [--out ...]

Input lines: {"id", "q", ...}; optional "image" ("photo:<demo photo>" from ..\\whyscope\\brand\\demo-photos, or
"child:<avatar png>" from hub/static: a child in front of the camera) and "chain" (the id of the previous item: asked as a
follow-up in the same conversation; every other item starts a new conversation with "reset": true).
Output lines: the input plus the hub's kind / intent / source / first sentence / explanation / ask-back / llm info and the
latency seen by the client: phase 1 (`t_first_ms`, what a kid page can show / speak at once: a KB first sentence, a
canned line, or for an LLM reply the thinking filler) and `t_reply_ms` (the full reply text is there).
Judging is a separate step (an AI judge reads the output; see eval/chat_report.md).
The hub must allow token-less loopback calls (auth.allow_localhost_dev); events land on household 1's first child.
"""
import io
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({})).open


def image_bytes(spec: str) -> bytes:
    kind, name = spec.split(":", 1)
    p = (ROOT.parent / "whyscope" / "brand" / "demo-photos" / name) if kind == "photo" else (ROOT / "hub" / "static" / name)
    from PIL import Image
    im = Image.open(p).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def post_ask(url, text, lang, reset, image=None):
    if image is None:
        body = json.dumps({"text": text, "lang": lang, "reset": reset}).encode()
        req = urllib.request.Request(url + "/api/ask", body, {"Content-Type": "application/json"})
    else:
        b = uuid.uuid4().hex
        parts = []
        for k, v in (("text", text), ("lang", lang), ("reset", "1" if reset else "0"), ("mode", "text")):
            parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"f.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode()
                     + image + b"\r\n")
        parts.append(f"--{b}--\r\n".encode())
        req = urllib.request.Request(url + "/api/ask", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={b}"})
    with OPEN(req, timeout=60) as r:
        return json.loads(r.read())


def get(url):
    try:
        with OPEN(urllib.request.Request(url), timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def run(path, url="http://127.0.0.1:8000", lang="en", out=None):
    items = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    res = []
    for it in items:
        img = image_bytes(it["image"]) if it.get("image") else None
        t0 = time.perf_counter()
        r = post_ask(url, it["q"], it.get("lang", lang), not it.get("chain"), img)
        t_first = (time.perf_counter() - t0) * 1000
        full = r
        if r.get("pending") and r.get("pending_id"):
            while time.perf_counter() - t0 < 30:
                time.sleep(0.1)
                st, j = get(url + "/api/ask/" + r["pending_id"])
                if st == 200 and not j.get("pending"):
                    full = j
                    break
        t_reply = (time.perf_counter() - t0) * 1000
        llm = full.get("llm") or {}
        row = {**it, "kind": full.get("kind"), "intent": full.get("intent"), "source": full.get("source"), "status": full.get("status"),
               "first_sentence": full.get("first_sentence"), "explanation": full.get("explanation"), "ask_back": full.get("ask_back"),
               "reaction": full.get("reaction"), "filler": r.get("filler"), "llm_source": llm.get("source") or ("llm" if llm.get("raw") else None),
               "llm_why": llm.get("why"), "llm_problems": llm.get("problems"), "llm_raw": llm.get("raw"), "vision": full.get("vision"),
               "sensitive_category": full.get("sensitive_category"), "event_id": full.get("event_id") or r.get("event_id"),
               "server_first_ms": (full.get("latency_ms") or {}).get("first_sentence"), "llm_ms": llm.get("ms"),
               "t_first_ms": round(t_first), "t_reply_ms": round(t_reply)}
        res.append(row)
        said = " ".join(x for x in (row["reaction"], row["first_sentence"], row["explanation"], row["ask_back"]) if x)
        print(f"{it['id']:8s} {t_reply / 1000:5.1f}s {row['kind'] or '-':9s} {str(row['intent']):18s} {it['q'][:45]!r:48s} -> {said[:150]}")
        time.sleep(0.3)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in res) + "\n", encoding="utf-8")
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    out = a[a.index("--out") + 1] if "--out" in a else None
    url = a[a.index("--url") + 1] if "--url" in a else "http://127.0.0.1:8000"
    run(a[0], url, out=out)
