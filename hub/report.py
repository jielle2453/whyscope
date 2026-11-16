"""Weekly aggregation for the parent page."""
from collections import Counter
from datetime import datetime, timedelta

from .emoji import TOPIC_EMOJI, TOPIC_EN, TOPIC_ZH, emoji_for
from .memory import PARENT_KEYS
from .recall import normalize, normalize_en

BRIDGE_EMOJI = {"has_dog": "🐶", "has_cat": "🐱", "has_sibling": "👧", "likes_dinosaurs": "🦖", "likes_cars": "🚗",
                "has_garden": "🌿", "rides_bike": "🚲"}


def week(db, days: int = 7, lang: str = "zh", entries: dict = None, emoji_of=None, todo_states: dict = None, child_id=None) -> dict:
    """{total, by_topic, talk_about, unanswered, bridges_used, daily, prev_total, topics} over the last `days` days,
    for one child (`child_id`; None = the household's first child, 0 = nobody, an empty report).

    `lang` picks the language of the talk-about lines: an event asked in another language is looked up in the
    knowledge base (`entries`: id -> entry) so the line (ask-back, object name) comes back in `lang`."""
    entries = entries or {}
    emoji_of = emoji_of or emoji_for
    child_id = db.default_child_id() if child_id is None else child_id
    # chit-chat ("hi", "you're silly") is not a why: it stays in the moments log but out of the weekly counts
    ev = [e for e in db.list_events(days, child_id=child_id) if e["status"] != "chat"]
    answered = [e for e in ev if e["status"] == "answered"]
    by_topic = Counter(e["topic"] for e in answered if e["topic"])

    def in_lang(e):
        """(object name, ask_back) of an answered event in `lang`."""
        elang, ent = e.get("lang") or "zh", entries.get(e["kb_id"])
        if elang == lang or not ent:
            return e["object"], e["ask_back"]
        if lang == "en":
            en = ent.get("en") or {}
            return (en.get("labels") or [e["object"]])[0], en.get("ask_back") or e["ask_back"]
        return ent["labels"][0], ent.get("ask_back") or e["ask_back"]

    talk = {}
    for e in reversed(answered):  # oldest first, so the dict ends up holding the latest event per object
        k = e["kb_id"] or e["object"]
        if not k:   # an AI guess has no object: it is reviewed in the to-answer list instead
            continue
        obj, ask = in_lang(e)
        t = talk.setdefault(k, {"object": obj, "topic": e["topic"], "count": 0})
        t.update(object=obj, count=t["count"] + 1, ask_back=ask, event_id=e["id"], talked=bool(e.get("talked")),
                 emoji=emoji_of(obj, e["topic"]), lang=lang)
    talk_about = sorted((t for t in talk.values() if t["ask_back"]), key=lambda t: (t["talked"], -t["count"]))[:8]

    # one row per question (the same question asked twice is one line, with a count); a question that has a to-answer item
    # is handled there (open, approved or dismissed), so it is not listed here again
    todo_states, seen, unanswered = todo_states or {}, {}, []
    for e in ev:   # newest first
        q = (e["question"] or "").strip()
        if e["status"] != "abstained" or not q:
            continue
        elang = e.get("lang") or "zh"
        key = ((normalize_en(q) if elang == "en" else normalize(q)), elang)
        if key in todo_states:
            continue
        if key in seen:
            seen[key]["count"] += 1
            seen[key]["talked"] = seen[key]["talked"] and bool(e.get("talked"))
            continue
        seen[key] = {"question": q, "ts": e["ts"], "event_id": e["id"], "talked": bool(e.get("talked")), "lang": elang, "count": 1}
        unanswered.append(seen[key])

    bridge_objs = {}
    for e in answered:
        if e["bridge_used"]:
            bridge_objs.setdefault(e["bridge_used"], []).append(e["object"])
    bridges = Counter(e["bridge_used"] for e in answered if e["bridge_used"])
    bridges_used = [{"key": k, "label_zh": PARENT_KEYS.get(k, (k,))[0], "count": n, "emoji": BRIDGE_EMOJI.get(k, "💬"),
                     "objects": list(dict.fromkeys(bridge_objs.get(k, [])))} for k, n in bridges.most_common()]

    today = datetime.now().date()
    per_day = Counter((e["ts"] or "")[:10] for e in ev)
    daily = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily.append({"date": d.isoformat(), "weekday": "一二三四五六日"[d.weekday()], "count": per_day.get(d.isoformat(), 0)})
    prev_total = max(0, sum(1 for e in db.list_events(days * 2, child_id=child_id) if e["status"] != "chat") - len(ev))

    return {"lang": lang, "total": len(ev), "answered": len(answered),
            "sensitive": sum(1 for e in ev if e["status"] == "sensitive"),
            "by_topic": dict(by_topic.most_common()), "talk_about": talk_about,
            "unanswered": unanswered, "bridges_used": bridges_used,
            "daily": daily, "prev_total": prev_total,
            "topics": [{"topic": t, "zh": TOPIC_ZH.get(t, t), "en": TOPIC_EN.get(t, t), "emoji": TOPIC_EMOJI.get(t, "🔍"), "count": n}
                       for t, n in by_topic.most_common()]}
