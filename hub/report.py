"""Weekly aggregation for the parent page."""
from collections import Counter

from .memory import PARENT_KEYS


def week(db, days: int = 7) -> dict:
    """{total, by_topic, talk_about, unanswered, bridges_used} over the last `days` days."""
    ev = db.list_events(days)
    answered = [e for e in ev if e["status"] == "answered"]
    by_topic = Counter(e["topic"] for e in answered if e["topic"])

    talk = {}
    for e in answered:  # one suggestion per object: what to chat about at dinner
        k = e["object"] or e["kb_id"]
        t = talk.setdefault(k, {"object": k, "topic": e["topic"], "count": 0, "ask_back": e["ask_back"]})
        t["count"] += 1
    talk_about = sorted(talk.values(), key=lambda t: -t["count"])[:8]

    unanswered = [{"question": e["question"], "ts": e["ts"]} for e in ev
                  if e["status"] == "abstained" and (e["question"] or "").strip()]

    bridges = Counter(e["bridge_used"] for e in answered if e["bridge_used"])
    bridges_used = [{"key": k, "label_zh": PARENT_KEYS.get(k, (k,))[0], "count": n} for k, n in bridges.most_common()]

    return {"total": len(ev), "answered": len(answered),
            "sensitive": sum(1 for e in ev if e["status"] == "sensitive"),
            "by_topic": dict(by_topic.most_common()), "talk_about": talk_about,
            "unanswered": unanswered, "bridges_used": bridges_used}
