"""Fill a Whyscope hub with DEMO data for screenshots: real answers from the running server, then back-dated.

Usage (use a throw-away database, never your real one):
  set WHYSCOPE_CONFIG=<config with another paths.db>   then start the server, then
  python scripts/seed_demo.py --url http://127.0.0.1:8000 --db <that db file>
The questions are real /api/ask calls; only the event timestamps are moved into the last 13 days and a few
events are marked "聊過了". Parent facts: name 小安, age 6, dog, dinosaurs, plants.
"""
import argparse
import json
import random
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

THIS_WEEK = [  # (days ago, hour, question)
    (0, 8, "為什麼蝸牛有殼"), (0, 17, "為什麼會有彩虹"), (0, 18, "吸塵器為什麼會吸東西"), (1, 7, "為什麼貓咪晚上眼睛亮亮的"),
    (1, 16, "冰淇淋放在外面，為什麼會流下來"), (1, 19, "為什麼人會死"), (2, 8, "螞蟻為什麼一隊一隊的走呀"),
    (2, 17, "為什麼汽水會冒泡泡"), (2, 18, "為什麼股票會跌"), (3, 9, "月亮為什麼好像跟著我跑"), (3, 17, "氣球為什麼可以飄在天花板上呀"),
    (4, 8, "為什麼我會打噴嚏"), (4, 16, "竹子為什麼一下子就長得好高"), (4, 18, "手機是怎麼想事情的"), (5, 10, "為什麼會打雷"),
    (5, 17, "蜜蜂怎麼會轉圈圈跳舞呀"), (6, 9, "為什麼蝸牛有殼"), (6, 16, "冰箱打開門，裡面為什麼冷冷的"), (6, 18, "我不想活了"),
    (0, 9, "為什麼天空是藍色的"), (1, 9, "為什麼貓咪晚上眼睛亮亮的"), (2, 9, "恐龍為什麼會滅絕"),
]
LAST_WEEK = [(8, 9, "為什麼會有彩虹"), (8, 17, "為什麼蝸牛有殼"), (9, 16, "為什麼我會打哈欠"), (10, 8, "為什麼會下雨"),
             (11, 17, "為什麼小鳥會飛"), (12, 9, "鴿子怎麼知道要飛回家"), (13, 18, "為什麼汽水會冒泡泡")]


def call(url, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    for k, v in (("child_name", "小安"), ("child_age", 6), ("has_dog", True), ("likes_dinosaurs", True), ("has_garden", True)):
        call(a.url + "/api/memory", "POST", {"key": k, "value": v})
    ids = []
    for days, hour, q in THIS_WEEK + LAST_WEEK:
        r = call(a.url + "/api/ask", "POST", {"text": q, "mode": "text"})
        while r.get("pending"):
            time.sleep(0.2)
            try:
                r2 = call(a.url + "/api/ask/" + r["pending_id"])
            except Exception:
                continue
            if not r2.get("pending"):
                r = r2
        ids.append((r["event_id"], days, hour))
        time.sleep(0.05)
    db = sqlite3.connect(a.db)
    now = datetime.now()
    rnd = random.Random(7)
    for eid, days, hour in ids:
        ts = (now - timedelta(days=days)).replace(hour=hour, minute=rnd.randint(0, 59), second=rnd.randint(0, 59), microsecond=0)
        if days == 0 and ts > now:
            ts = now - timedelta(minutes=rnd.randint(5, 60))
        db.execute("UPDATE events SET ts=? WHERE id=?", (ts.isoformat(timespec="seconds"), eid))
    db.execute("UPDATE events SET talked=1 WHERE id IN (SELECT id FROM events WHERE status='answered' ORDER BY id LIMIT 3)")
    db.commit()
    db.close()
    print(f"seeded {len(ids)} events into {a.db}")


if __name__ == "__main__":
    main()
