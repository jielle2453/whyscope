"""Weekly aggregation for the parent page."""
from collections import Counter
from datetime import datetime, timedelta

from .emoji import TOPIC_EMOJI, TOPIC_ZH, emoji_for
from .memory import PARENT_KEYS

BRIDGE_EMOJI = {"has_dog": "🐶", "has_cat": "🐱", "has_sibling": "👧", "likes_dinosaurs": "🦖", "likes_cars": "🚗",
                "has_garden": "🌿", "rides_bike": "🚲"}


def week(db, days: int = 7) -> dict:
    """{total, by_topic, talk_about, unanswered, bridges_used, daily, prev_total, topics} over the last `days` days."""
    ev = db.list_events(days)
    answered = [e for e in ev if e["status"] == "answered"]
    by_topic = Counter(e["topic"] for e in answered if e["topic"])

    talk = {}
    for e in reversed(answered):  # oldest first, so the dict ends up holding the latest event per object
        k = e["object"] or e["kb_id"]
        t = talk.setdefault(k, {"object": k, "topic": e["topic"], "count": 0})
        t.update(count=t["count"] + 1, ask_back=e["ask_back"], event_id=e["id"], talked=bool(e.get("talked")),
                 emoji=emoji_for(k, e["topic"]))
    talk_about = sorted((t for t in talk.values() if t["ask_back"]), key=lambda t: (t["talked"], -t["count"]))[:8]

    unanswered = [{"question": e["question"], "ts": e["ts"], "event_id": e["id"], "talked": bool(e.get("talked"))}
                  for e in ev if e["status"] == "abstained" and (e["question"] or "").strip()]

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
    prev_total = max(0, len(db.list_events(days * 2)) - len(ev))

    return {"total": len(ev), "answered": len(answered),
            "sensitive": sum(1 for e in ev if e["status"] == "sensitive"),
            "by_topic": dict(by_topic.most_common()), "talk_about": talk_about,
            "unanswered": unanswered, "bridges_used": bridges_used,
            "daily": daily, "prev_total": prev_total,
            "topics": [{"topic": t, "zh": TOPIC_ZH.get(t, t), "emoji": TOPIC_EMOJI.get(t, "🔍"), "count": n}
                       for t, n in by_topic.most_common()]}
