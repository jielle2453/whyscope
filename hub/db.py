"""SQLite schema and helpers (spec section 7). Never stores audio or image bytes (opt-in snapshots live as files;
the events table only holds a 0/1 `snapshot` flag).

Accounts (docs/architecture.md, "Accounts and pairing"): households > children / parents / devices. Events, to-answer
items and deliveries belong to a child; family answers and settings belong to a household (shared by its children).
The migration is additive: an existing database becomes household 1 / child 1 (user_version 2) and the old `memory` and
`settings` tables are left in place (no longer read)."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_HH = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, ts TEXT, mode TEXT, question TEXT, object TEXT, topic TEXT, kb_id TEXT,
  status TEXT, first_sentence TEXT, explanation TEXT, ask_back TEXT, bridge_used TEXT,
  sensitive_category TEXT, cheat_done INTEGER DEFAULT 0, latency_total_ms INTEGER, latency_json TEXT);
CREATE TABLE IF NOT EXISTS memory(key TEXT PRIMARY KEY, value TEXT, source TEXT, updated_ts TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
-- parent assistant: questions the device could not answer (one open row per question), its draft, the parent's decision
CREATE TABLE IF NOT EXISTS todo(
  id INTEGER PRIMARY KEY, ts TEXT, last_ts TEXT, event_id INTEGER, question TEXT, norm TEXT, lang TEXT, count INTEGER DEFAULT 1,
  status TEXT DEFAULT 'pending',   -- pending | drafting | ready | approved | dismissed
  draft TEXT, partial_draft TEXT, context TEXT, wording TEXT, draft_ms INTEGER DEFAULT 0, drafted_ts TEXT,
  final TEXT, resolved_ts TEXT, family_id INTEGER);
-- answers a parent approved: asked again, the child gets this one (near-duplicate question, high threshold)
CREATE TABLE IF NOT EXISTS family_answers(
  id INTEGER PRIMARY KEY, question TEXT, lang TEXT, answer TEXT, embedding BLOB, source_event INTEGER, todo_id INTEGER, approved_ts TEXT);
-- approved answers waiting to be told to the child (the kid page polls /api/deliveries)
CREATE TABLE IF NOT EXISTS deliveries(
  id INTEGER PRIMARY KEY, family_id INTEGER, question TEXT, answer TEXT, lang TEXT, ts TEXT, delivered_ts TEXT);
-- accounts
CREATE TABLE IF NOT EXISTS households(id INTEGER PRIMARY KEY, name TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS children(
  id INTEGER PRIMARY KEY, household_id INTEGER, name TEXT, age INTEGER DEFAULT 6, avatar TEXT DEFAULT 'girl',
  created TEXT, archived INTEGER DEFAULT 0);
-- per-child memory: bridges (has_dog ...) and the auto-recorded recent topics / objects
CREATE TABLE IF NOT EXISTS child_memory(
  child_id INTEGER, key TEXT, value TEXT, source TEXT, updated_ts TEXT, PRIMARY KEY(child_id, key));
CREATE TABLE IF NOT EXISTS household_settings(household_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(household_id, key));
CREATE TABLE IF NOT EXISTS parents(
  id INTEGER PRIMARY KEY, household_id INTEGER, name TEXT, pin_salt BLOB, pin_hash BLOB, created TEXT);
CREATE TABLE IF NOT EXISTS devices(
  id INTEGER PRIMARY KEY, household_id INTEGER, kind TEXT,          -- wand | parent
  child_id INTEGER, parent_id INTEGER, name TEXT, token_hash TEXT UNIQUE, created TEXT, last_seen TEXT,
  revoked INTEGER DEFAULT 0, tunnel_id TEXT);                      -- tunnel_id: the relay device id (hub/tunnel.py), if paired for the relay
CREATE TABLE IF NOT EXISTS pairing_codes(
  code_hash TEXT PRIMARY KEY, household_id INTEGER, kind TEXT, child_id INTEGER, parent_id INTEGER, name TEXT,
  created TEXT, expires TEXT, used INTEGER DEFAULT 0, tunnel_id TEXT);
"""

CHILD_FIELDS = ("name", "age", "avatar")


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
            if "reply" not in cols:     # reply turn: the child's answer to the question back and how it went
                c.execute("ALTER TABLE events ADD COLUMN reply TEXT")
                c.execute("ALTER TABLE events ADD COLUMN reply_result TEXT")
            if "snapshot" not in cols:  # opt-in photos: 1 when data/snapshots/<id>.jpg exists (additive migration)
                c.execute("ALTER TABLE events ADD COLUMN snapshot INTEGER DEFAULT 0")
            if "source" not in cols:    # where the answer came from: entry:<id> | principle:<id> | family:<id> | abstain | sensitive
                c.execute("ALTER TABLE events ADD COLUMN source TEXT")
                c.execute("ALTER TABLE events ADD COLUMN draft INTEGER DEFAULT 0")     # 1 = from an unreviewed (AI draft) library
                c.execute("ALTER TABLE events ADD COLUMN partial INTEGER DEFAULT 0")   # 1 = the principle only partly answers
            if "intent" not in cols:    # chat turn (2026-11-15): what the child said (question | rule | deictic | followup | chat:<sub>)
                c.execute("ALTER TABLE events ADD COLUMN intent TEXT")
                c.execute("ALTER TABLE events ADD COLUMN llm TEXT")      # JSON: model text, guard result, fallback, ms (chat / ai_guess)
            if "origin" not in {r[1] for r in c.execute("PRAGMA table_info(todo)")}:   # abstain | ai_guess (the child heard the draft)
                c.execute("ALTER TABLE todo ADD COLUMN origin TEXT DEFAULT 'abstain'")
            # accounts: every event / to-answer item / delivery belongs to a child, every family answer to a household.
            # Rows from before the accounts existed read as child 1 / household 1 through the column default.
            for tbl, col in (("events", "child_id"), ("todo", "child_id"), ("deliveries", "child_id"), ("family_answers", "household_id")):
                if col not in {r[1] for r in c.execute(f"PRAGMA table_info({tbl})")}:
                    c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} INTEGER DEFAULT 1")
            c.execute("CREATE INDEX IF NOT EXISTS idx_events_child ON events(child_id, ts)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_todo_child ON todo(child_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_devices_token ON devices(token_hash)")
            self._migrate_accounts(c)
            c.commit()
        finally:
            c.close()

    @staticmethod
    def _migrate_accounts(c):
        """user_version 2: household 1 and (when there is old data) child 1; per-child memory and per-household settings."""
        if c.execute("PRAGMA user_version").fetchone()[0] >= 2:
            return
        if not c.execute("SELECT 1 FROM households LIMIT 1").fetchone():
            c.execute("INSERT INTO households(id,name,created) VALUES(?,?,?)", (DEFAULT_HH, "My household", now()))
        mem = {r[0]: (r[1], r[2], r[3]) for r in c.execute("SELECT key,value,source,updated_ts FROM memory")}
        legacy = bool(mem) or any(c.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() for t in ("events", "todo", "family_answers", "deliveries"))
        if legacy and not c.execute("SELECT 1 FROM children LIMIT 1").fetchone():
            def val(k, d):
                try:
                    return json.loads(mem[k][0]) if k in mem else d
                except ValueError:
                    return d
            age = val("child_age", 6)
            c.execute("INSERT INTO children(id,household_id,name,age,avatar,created) VALUES(1,?,?,?,?,?)",
                      (DEFAULT_HH, str(val("child_name", "") or "My child"), age if isinstance(age, int) else 6,
                       val("avatar", "girl") if val("avatar", "girl") in ("girl", "boy", "emoji") else "girl", now()))
            for k, (v, src, ts) in mem.items():
                if k not in ("child_name", "child_age", "avatar"):
                    c.execute("INSERT OR IGNORE INTO child_memory(child_id,key,value,source,updated_ts) VALUES(1,?,?,?,?)", (k, v, src, ts))
        for k, v in c.execute("SELECT key,value FROM settings").fetchall():
            c.execute("INSERT OR IGNORE INTO household_settings(household_id,key,value) VALUES(?,?,?)", (DEFAULT_HH, k, v))
        c.execute("PRAGMA user_version=2")

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

    def _one(self, sql, args=()):
        r = self._run(sql, args, fetch=True)
        return r[0] if r else None

    # ---- households, children ----
    def household_ids(self):
        return [r["id"] for r in self._run("SELECT id FROM households ORDER BY id", fetch=True)]

    def household_get(self, hh):
        return self._one("SELECT * FROM households WHERE id=?", (hh,))

    def household_add(self, name) -> int:
        return self._run("INSERT INTO households(name,created) VALUES(?,?)", (name, now()))

    def household_rename(self, hh, name):
        self._run("UPDATE households SET name=? WHERE id=?", (name, hh))

    def default_household_id(self) -> int:
        ids = self.household_ids()
        return ids[0] if ids else self.household_add("My household")

    def children(self, hh=None, archived=False):
        sql, args = "SELECT * FROM children WHERE archived=?", [1 if archived else 0]
        if hh is not None:
            sql += " AND household_id=?"
            args.append(hh)
        return self._run(sql + " ORDER BY id", args, fetch=True)

    def child_get(self, child_id):
        return self._one("SELECT * FROM children WHERE id=?", (child_id,)) if child_id else None

    def child_add(self, hh, name, age=6, avatar="girl") -> int:
        return self._run("INSERT INTO children(household_id,name,age,avatar,created) VALUES(?,?,?,?,?)",
                         (hh, name, age, avatar, now()))

    def child_update(self, child_id, **f):
        cols = {k: v for k, v in f.items() if k in CHILD_FIELDS}
        if cols:
            self._run(f"UPDATE children SET {', '.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), child_id))

    def child_household(self, child_id):
        c = self.child_get(child_id)
        return c["household_id"] if c else None

    def default_child_id(self, hh=None) -> int:
        """The household's first child (created as "My child" when there is none: scripts that call the API with no account)."""
        hh = hh or self.default_household_id()
        ch = self.children(hh)
        return ch[0]["id"] if ch else self.child_add(hh, "My child")

    def _child_filter(self, child_id, household_id, col="child_id"):
        if child_id is not None:
            return f" AND {col}=?", [child_id]
        if household_id is not None:
            return f" AND {col} IN (SELECT id FROM children WHERE household_id=?)", [household_id]
        return "", []

    # ---- events ----
    def insert_event(self, child_id=None, ts=None, **e) -> int:
        lat = e.get("latency_ms") or {}
        return self._run(
            "INSERT INTO events(ts,mode,question,object,topic,kb_id,status,first_sentence,explanation,ask_back,"
            "bridge_used,sensitive_category,latency_total_ms,latency_json,lang,source,draft,partial,child_id,intent,llm) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts or now(), e.get("mode"), e.get("question"), e.get("object"), e.get("topic"), e.get("kb_id"),
             e.get("status"), e.get("first_sentence"), e.get("explanation"), e.get("ask_back"),
             e.get("bridge_used"), e.get("sensitive_category"), int(lat.get("total", 0)),
             json.dumps(lat, ensure_ascii=False), e.get("lang") or "zh", e.get("source"),
             1 if e.get("draft") else 0, 1 if e.get("partial") else 0, child_id or self.default_child_id(), e.get("intent"),
             json.dumps(e["llm"], ensure_ascii=False) if e.get("llm") else None))

    def list_events(self, days=7, status=None, child_id=None, household_id=None):
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        sql, args = "SELECT * FROM events WHERE ts>=?", [cutoff]
        if status:
            sql += " AND status=?"
            args.append(status)
        extra, a = self._child_filter(child_id, household_id)
        return self._run(sql + extra + " ORDER BY ts DESC, id DESC", args + a, fetch=True)

    def update_event(self, event_id, **f):
        """Second phase of an answer: fill explanation / ask_back / bridge_used / latency."""
        cols = {k: v for k, v in f.items() if k in ("explanation", "ask_back", "bridge_used", "status", "object", "first_sentence",
                                                    "source", "draft", "intent")}
        if "llm" in f:
            cols["llm"] = json.dumps(f["llm"], ensure_ascii=False) if f["llm"] else None
        lat = f.get("latency_ms")
        sets, args = [f"{k}=?" for k in cols], list(cols.values())
        if lat is not None:
            sets += ["latency_total_ms=?", "latency_json=?"]
            args += [int(lat.get("total", 0)), json.dumps(lat, ensure_ascii=False)]
        if sets:
            self._run(f"UPDATE events SET {', '.join(sets)} WHERE id=?", (*args, event_id))

    def set_reply(self, event_id, reply, result):
        self._run("UPDATE events SET reply=?, reply_result=? WHERE id=?", (reply, result, event_id))

    def mark_talked(self, event_id):
        self._run("UPDATE events SET talked=1 WHERE id=?", (event_id,))

    def get_event(self, event_id):
        return self._one("SELECT * FROM events WHERE id=?", (event_id,))

    def set_snapshot(self, event_id, on=True):
        self._run("UPDATE events SET snapshot=? WHERE id=?", (1 if on else 0, event_id))

    def snapshot_events(self, child_id=None, household_id=None):
        """Events that have a photo, newest first (no image data, only the fields the Moments view needs)."""
        extra, a = self._child_filter(child_id, household_id)
        return self._run("SELECT id,ts,question,object,topic,status,first_sentence,lang,child_id FROM events "
                         "WHERE snapshot=1" + extra + " ORDER BY id DESC", a, fetch=True)

    def clear_snapshot_flags(self, household_id=None):
        extra, a = self._child_filter(None, household_id)
        self._run("UPDATE events SET snapshot=0 WHERE snapshot=1" + extra, a)

    def mark_cheat_done(self, event_id):
        self._run("UPDATE events SET cheat_done=1 WHERE id=?", (event_id,))

    def purge(self, retention_days, household_id=None):
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat(timespec="seconds")
        extra, a = self._child_filter(None, household_id)
        self._run("DELETE FROM events WHERE ts<?" + extra, [cutoff] + a)
        self._run("DELETE FROM todo WHERE last_ts<?" + extra, [cutoff] + a)
        self._run("DELETE FROM deliveries WHERE ts<?" + extra, [cutoff] + a)

    def clear_events(self, household_id=None):
        extra, a = self._child_filter(None, household_id)
        for t in ("events", "todo", "deliveries"):
            self._run(f"DELETE FROM {t} WHERE 1=1" + extra, a)

    # ---- parent assistant: to-answer items ----
    TODO_OPEN = ("pending", "drafting", "ready")

    def todo_add(self, event_id, question, norm, lang, child_id=None) -> int:
        """A new open item, or (same child question, already open) the existing one with its count raised."""
        child_id = child_id or self.default_child_id()
        r = self._run("SELECT id FROM todo WHERE norm=? AND lang=? AND child_id=? AND status IN ('pending','drafting','ready')",
                      (norm, lang, child_id), fetch=True)
        if r:
            self._run("UPDATE todo SET count=count+1, last_ts=?, event_id=? WHERE id=?", (now(), event_id, r[0]["id"]))
            return r[0]["id"]
        return self._run("INSERT INTO todo(ts,last_ts,event_id,question,norm,lang,child_id) VALUES(?,?,?,?,?,?,?)",
                         (now(), now(), event_id, question, norm, lang, child_id))

    def todo_add_guess(self, event_id, question, norm, lang, child_id, draft, context_json, wording_json) -> int:
        """An AI guess the child already heard: an open item (or the existing open one for the same question) with the guess
        as its ready draft, so the parent can approve it (-> family answer) or correct it."""
        child_id = child_id or self.default_child_id()
        r = self._run("SELECT id,status FROM todo WHERE norm=? AND lang=? AND child_id=? AND status IN ('pending','drafting','ready')",
                      (norm, lang, child_id), fetch=True)
        if r:
            self._run("UPDATE todo SET count=count+1, last_ts=?, event_id=? WHERE id=?", (now(), event_id, r[0]["id"]))
            # the draft becomes what the child just heard (also over an earlier assistant draft): approving keeps it,
            # "Write again" asks the parent assistant for a fresh one
            self._run("UPDATE todo SET status='ready', draft=?, partial_draft='', context=?, wording=?, drafted_ts=?, draft_ms=0, origin='ai_guess' "
                      "WHERE id=?", (draft, context_json, wording_json, now(), r[0]["id"]))
            return r[0]["id"]
        return self._run("INSERT INTO todo(ts,last_ts,event_id,question,norm,lang,child_id,status,draft,context,wording,drafted_ts,origin) "
                         "VALUES(?,?,?,?,?,?,?,'ready',?,?,?,?,'ai_guess')",
                         (now(), now(), event_id, question, norm, lang, child_id, draft, context_json, wording_json, now()))

    def todo_list(self, statuses=None, child_id=None, household_id=None):
        sts = list(statuses or self.TODO_OPEN)
        extra, a = self._child_filter(child_id, household_id)
        return self._run(f"SELECT * FROM todo WHERE status IN ({','.join('?' * len(sts))})" + extra + " ORDER BY id", sts + a, fetch=True)

    def todo_get(self, item_id):
        return self._one("SELECT * FROM todo WHERE id=?", (item_id,))

    def todo_update(self, item_id, **f):
        cols = {k: v for k, v in f.items() if k in ("status", "draft", "partial_draft", "context", "wording", "draft_ms",
                                                    "drafted_ts", "final", "resolved_ts", "family_id", "origin")}
        if cols:
            self._run(f"UPDATE todo SET {', '.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), item_id))

    def todo_next(self):
        """The oldest item that still needs a draft (pending, or a drafting one that was interrupted)."""
        return self._one("SELECT * FROM todo WHERE status IN ('pending','drafting') ORDER BY id LIMIT 1")

    def todo_states(self, child_id=None):
        """{(norm, lang): latest status} over one child's items: lets the report hide questions the parent already handled."""
        out = {}
        extra, a = self._child_filter(child_id, None)
        for r in self._run("SELECT norm,lang,status FROM todo WHERE 1=1" + extra + " ORDER BY id", a, fetch=True):
            out[(r["norm"], r["lang"])] = r["status"]
        return out

    # ---- family answers (per household) and deliveries (per child) ----
    def family_add(self, question, lang, answer, embedding: bytes, source_event, todo_id, household_id=None) -> int:
        return self._run("INSERT INTO family_answers(question,lang,answer,embedding,source_event,todo_id,approved_ts,household_id) VALUES(?,?,?,?,?,?,?,?)",
                         (question, lang, answer, embedding, source_event, todo_id, now(), household_id or self.default_household_id()))

    def family_all(self, with_embedding=True, household_id=None):
        cols = "id,question,lang,answer,source_event,todo_id,approved_ts,household_id" + (",embedding" if with_embedding else "")
        if household_id is None:
            return self._run(f"SELECT {cols} FROM family_answers ORDER BY id", fetch=True)
        return self._run(f"SELECT {cols} FROM family_answers WHERE household_id=? ORDER BY id", (household_id,), fetch=True)

    def family_get(self, fid):
        return self._one("SELECT id,household_id FROM family_answers WHERE id=?", (fid,))

    def family_delete(self, fid):
        self._run("DELETE FROM family_answers WHERE id=?", (fid,))

    def delivery_add(self, family_id, question, answer, lang, child_id=None) -> int:
        return self._run("INSERT INTO deliveries(family_id,question,answer,lang,ts,child_id) VALUES(?,?,?,?,?,?)",
                         (family_id, question, answer, lang, now(), child_id or self.default_child_id()))

    def deliveries_pending(self, child_id=None):
        extra, a = self._child_filter(child_id, None)
        return self._run("SELECT * FROM deliveries WHERE delivered_ts IS NULL" + extra + " ORDER BY id", a, fetch=True)

    def delivery_get(self, did):
        return self._one("SELECT * FROM deliveries WHERE id=?", (did,))

    def delivery_done(self, did):
        self._run("UPDATE deliveries SET delivered_ts=? WHERE id=? AND delivered_ts IS NULL", (now(), did))

    # ---- memory (per child) ----
    def mem_all(self, child_id=None):
        return self._run("SELECT * FROM child_memory WHERE child_id=?", (child_id or self.default_child_id(),), fetch=True)

    def mem_set(self, key, value_json, source, child_id=None):
        self._run("INSERT INTO child_memory(child_id,key,value,source,updated_ts) VALUES(?,?,?,?,?) "
                  "ON CONFLICT(child_id,key) DO UPDATE SET value=excluded.value, source=excluded.source, "
                  "updated_ts=excluded.updated_ts", (child_id or self.default_child_id(), key, value_json, source, now()))

    def mem_delete(self, key, child_id=None):
        self._run("DELETE FROM child_memory WHERE child_id=? AND key=?", (child_id or self.default_child_id(), key))

    def mem_clear_auto(self, household_id=None):
        extra, a = self._child_filter(None, household_id, "child_id")
        self._run("DELETE FROM child_memory WHERE source='auto'" + extra, a)

    # ---- settings (per household) ----
    def setting_get(self, key, default=None, hh=None):
        r = self._run("SELECT value FROM household_settings WHERE household_id=? AND key=?", (hh or DEFAULT_HH, key), fetch=True)
        return json.loads(r[0]["value"]) if r else default

    def setting_set(self, key, value, hh=None):
        self._run("INSERT INTO household_settings(household_id,key,value) VALUES(?,?,?) "
                  "ON CONFLICT(household_id,key) DO UPDATE SET value=excluded.value", (hh or DEFAULT_HH, key, json.dumps(value)))

    def export_all(self, household_id):
        """One household's records. Never other households', never tokens or PIN hashes."""
        ex, a = self._child_filter(None, household_id)
        hh = household_id
        return {"exported_ts": now(), "household": self.household_get(hh), "children": self.children(hh, archived=False),
                "events": self._run("SELECT * FROM events WHERE 1=1" + ex, a, fetch=True),
                "memory": self._run("SELECT * FROM child_memory WHERE 1=1" + ex, a, fetch=True),
                "settings": self._run("SELECT key,value FROM household_settings WHERE household_id=?", (hh,), fetch=True),
                "todo": self._run("SELECT * FROM todo WHERE 1=1" + ex, a, fetch=True),
                "family_answers": self.family_all(False, hh),
                "deliveries": self._run("SELECT * FROM deliveries WHERE 1=1" + ex, a, fetch=True)}

    # ---- parents, devices, pairing codes ----
    def parent_add(self, hh, name, pin_salt: bytes, pin_hash: bytes) -> int:
        return self._run("INSERT INTO parents(household_id,name,pin_salt,pin_hash,created) VALUES(?,?,?,?,?)",
                         (hh, name, pin_salt, pin_hash, now()))

    def parent_get(self, pid):
        return self._one("SELECT * FROM parents WHERE id=?", (pid,))

    def parents(self, hh):
        return self._run("SELECT id,household_id,name,created FROM parents WHERE household_id=? ORDER BY id", (hh,), fetch=True)

    def device_add(self, hh, kind, name, token_hash, child_id=None, parent_id=None, tunnel_id=None) -> int:
        return self._run("INSERT INTO devices(household_id,kind,child_id,parent_id,name,token_hash,created,tunnel_id) VALUES(?,?,?,?,?,?,?,?)",
                         (hh, kind, child_id, parent_id, name, token_hash, now(), tunnel_id))

    def device_by_token(self, token_hash):
        return self._one("SELECT * FROM devices WHERE token_hash=?", (token_hash,))

    def device_get(self, did):
        return self._one("SELECT * FROM devices WHERE id=?", (did,))

    def devices(self, hh):
        return self._run("SELECT id,household_id,kind,child_id,parent_id,name,created,last_seen,revoked,tunnel_id FROM devices "
                         "WHERE household_id=? ORDER BY id", (hh,), fetch=True)

    def device_revoke(self, did):
        self._run("UPDATE devices SET revoked=1 WHERE id=?", (did,))

    def device_touch(self, did):
        self._run("UPDATE devices SET last_seen=? WHERE id=?", (now(), did))

    def pair_add(self, code_hash, hh, kind, child_id, parent_id, name, expires, tunnel_id=None):
        self._run("INSERT INTO pairing_codes(code_hash,household_id,kind,child_id,parent_id,name,created,expires,tunnel_id) VALUES(?,?,?,?,?,?,?,?,?)",
                  (code_hash, hh, kind, child_id, parent_id, name, now(), expires, tunnel_id))

    def pair_get(self, code_hash):
        return self._one("SELECT * FROM pairing_codes WHERE code_hash=?", (code_hash,))

    def pair_take(self, code_hash) -> bool:
        """Mark a code used; True only for the first caller (one-time)."""
        c = self._c()
        try:
            cur = c.execute("UPDATE pairing_codes SET used=1 WHERE code_hash=? AND used=0", (code_hash,))
            c.commit()
            return cur.rowcount == 1
        finally:
            c.close()

    def pair_sweep(self):
        """Delete expired or used codes; returns the relay device ids of the unused expired ones (to be revoked)."""
        t = now()
        stale = self._run("SELECT tunnel_id FROM pairing_codes WHERE used=0 AND expires<? AND tunnel_id IS NOT NULL", (t,), fetch=True)
        self._run("DELETE FROM pairing_codes WHERE expires<? OR used=1", (t,))
        return [r["tunnel_id"] for r in stale]
