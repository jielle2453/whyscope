"""SQLite schema and helpers (spec section 7). Never stores audio or image bytes (opt-in snapshots live as files;
the events table only holds a 0/1 `snapshot` flag)."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, ts TEXT, mode TEXT, question TEXT, object TEXT, topic TEXT, kb_id TEXT,
  status TEXT, first_sentence TEXT, explanation TEXT, ask_back TEXT, bridge_used TEXT,
  sensitive_category TEXT, cheat_done INTEGER DEFAULT 0, latency_total_ms INTEGER, latency_json TEXT);
CREATE TABLE IF NOT EXISTS memory(key TEXT PRIMARY KEY, value TEXT, source TEXT, updated_ts TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    """Thin wrapper: one short-lived connection per call (thread-safe)."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = self._c()
        try:
            c.executescript(SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
            if "talked" not in cols:   # product pass 1: parent marks "聊過了" (additive migration)
                c.execute("ALTER TABLE events ADD COLUMN talked INTEGER DEFAULT 0")
            if "lang" not in cols:     # English mode: language of the question and answer (additive migration)
                c.execute("ALTER TABLE events ADD COLUMN lang TEXT DEFAULT 'zh'")
            if "snapshot" not in cols:  # opt-in photos: 1 when data/snapshots/<id>.jpg exists (additive migration)
                c.execute("ALTER TABLE events ADD COLUMN snapshot INTEGER DEFAULT 0")
            c.commit()
        finally:
            c.close()

    def _c(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _run(self, sql, args=(), fetch=False):
        c = self._c()
        try:
            cur = c.execute(sql, args)
            rows = [dict(r) for r in cur.fetchall()] if fetch else cur.lastrowid
            c.commit()
            return rows
        finally:
            c.close()

    # ---- events ----
    def insert_event(self, **e) -> int:
        lat = e.get("latency_ms") or {}
        return self._run(
            "INSERT INTO events(ts,mode,question,object,topic,kb_id,status,first_sentence,explanation,ask_back,"
            "bridge_used,sensitive_category,latency_total_ms,latency_json,lang) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now(), e.get("mode"), e.get("question"), e.get("object"), e.get("topic"), e.get("kb_id"),
             e.get("status"), e.get("first_sentence"), e.get("explanation"), e.get("ask_back"),
             e.get("bridge_used"), e.get("sensitive_category"), int(lat.get("total", 0)),
             json.dumps(lat, ensure_ascii=False), e.get("lang") or "zh"))

    def list_events(self, days=7, status=None):
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        sql, args = "SELECT * FROM events WHERE ts>=?", [cutoff]
        if status:
            sql += " AND status=?"
            args.append(status)
        return self._run(sql + " ORDER BY id DESC", args, fetch=True)

    def update_event(self, event_id, **f):
        """Second phase of an answer: fill explanation / ask_back / bridge_used / latency."""
        cols = {k: v for k, v in f.items() if k in ("explanation", "ask_back", "bridge_used", "status", "object")}
        lat = f.get("latency_ms")
        sets, args = [f"{k}=?" for k in cols], list(cols.values())
        if lat is not None:
            sets += ["latency_total_ms=?", "latency_json=?"]
            args += [int(lat.get("total", 0)), json.dumps(lat, ensure_ascii=False)]
        if sets:
            self._run(f"UPDATE events SET {', '.join(sets)} WHERE id=?", (*args, event_id))

    def mark_talked(self, event_id):
        self._run("UPDATE events SET talked=1 WHERE id=?", (event_id,))

    def get_event(self, event_id):
        r = self._run("SELECT * FROM events WHERE id=?", (event_id,), fetch=True)
        return r[0] if r else None

    def set_snapshot(self, event_id, on=True):
        self._run("UPDATE events SET snapshot=? WHERE id=?", (1 if on else 0, event_id))

    def snapshot_events(self):
        """Events that have a photo, newest first (no image data, only the fields the Moments view needs)."""
        return self._run("SELECT id,ts,question,object,topic,status,first_sentence,lang FROM events "
                         "WHERE snapshot=1 ORDER BY id DESC", fetch=True)

    def clear_snapshot_flags(self):
        self._run("UPDATE events SET snapshot=0 WHERE snapshot=1")

    def mark_cheat_done(self, event_id):
        self._run("UPDATE events SET cheat_done=1 WHERE id=?", (event_id,))

    def purge(self, retention_days):
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat(timespec="seconds")
        self._run("DELETE FROM events WHERE ts<?", (cutoff,))

    def clear_events(self):
        self._run("DELETE FROM events")

    # ---- memory ----
    def mem_all(self):
        return self._run("SELECT * FROM memory", fetch=True)

    def mem_set(self, key, value_json, source):
        self._run("INSERT INTO memory(key,value,source,updated_ts) VALUES(?,?,?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value, source=excluded.source, "
                  "updated_ts=excluded.updated_ts", (key, value_json, source, now()))

    def mem_delete(self, key):
        self._run("DELETE FROM memory WHERE key=?", (key,))

    def mem_clear_auto(self):
        self._run("DELETE FROM memory WHERE source='auto'")

    # ---- settings ----
    def setting_get(self, key, default=None):
        r = self._run("SELECT value FROM settings WHERE key=?", (key,), fetch=True)
        return json.loads(r[0]["value"]) if r else default

    def setting_set(self, key, value):
        self._run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value)))

    def export_all(self):
        return {"exported_ts": now(), "events": self._run("SELECT * FROM events", fetch=True),
                "memory": self.mem_all(), "settings": self._run("SELECT * FROM settings", fetch=True)}
