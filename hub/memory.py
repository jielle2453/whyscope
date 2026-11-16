"""Context memory (spec section 5), per child: parent-entered facts + auto topics, stored in SQLite.

The child's name, age and avatar live on the child's row (table `children`); the bridges (has_dog ...) and the
auto-recorded topics live in `child_memory`. `all()` still returns them as one flat dict, so the parent page is unchanged.
`child_id=None` means the household's first child (one-child setups and scripts)."""
import json

# key -> (Chinese label, type). Types: bool | str | int
PARENT_KEYS = {
    "has_dog": ("家裡有狗狗", "bool"),
    "has_cat": ("家裡有貓咪", "bool"),
    "has_sibling": ("有兄弟姊妹（例：妹妹兩歲）", "str"),
    "likes_dinosaurs": ("喜歡恐龍", "bool"),
    "likes_cars": ("喜歡車子", "bool"),
    "has_garden": ("家裡有花園", "bool"),
    "rides_bike": ("會騎腳踏車", "bool"),
    "child_name": ("孩子的名字（只顯示在家長頁面）", "str"),
    "child_age": ("孩子的年齡（5–8）", "int"),
    "avatar": ("頭像（girl / boy / emoji）", "str"),
}
AVATARS = ("girl", "boy", "emoji")
AUTO_KEYS = {"recent_topics": "最近問過的主題", "recent_objects": "最近問過的東西"}
BRIDGE_KEYS = ["has_dog", "has_cat", "has_sibling", "likes_dinosaurs", "likes_cars", "has_garden", "rides_bike"]
ROW_KEYS = {"child_name": "name", "child_age": "age", "avatar": "avatar"}   # memory key -> column of the children table


class Memory:
    def __init__(self, db):
        self.db = db

    def _cid(self, child_id):
        return child_id or self.db.default_child_id()

    def all(self, child_id=None) -> dict:
        """{key: {value, source, updated_ts}} with decoded values."""
        cid = self._cid(child_id)
        out = {}
        for r in self.db.mem_all(cid):
            try:
                v = json.loads(r["value"])
            except Exception:
                v = r["value"]
            out[r["key"]] = {"value": v, "source": r["source"], "updated_ts": r["updated_ts"]}
        ch = self.db.child_get(cid) or {}
        for k, col in ROW_KEYS.items():
            if ch.get(col) not in (None, "") and not (k == "child_name" and ch[col] == "My child"):   # "My child" is the placeholder
                out[k] = {"value": ch[col], "source": "parent", "updated_ts": ch.get("created")}
        return out

    def get(self, key, default=None, child_id=None):
        return self.all(child_id).get(key, {}).get("value", default)

    def set(self, key, value, child_id=None):
        """Set a parent-entered key; raises ValueError on invalid key/value."""
        if key not in PARENT_KEYS:
            raise ValueError(f"unknown key: {key}")
        typ = PARENT_KEYS[key][1]
        if typ == "bool":
            value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on", "是")
        elif typ == "int":
            value = int(value)
            if not 5 <= value <= 8:
                raise ValueError("child_age must be 5-8")
        else:
            value = str(value).strip()
            if key == "avatar" and value not in AVATARS:
                raise ValueError("avatar must be girl, boy or emoji")
            if key == "child_name" and not value:
                raise ValueError("name is empty")
        cid = self._cid(child_id)
        if key in ROW_KEYS:
            self.db.child_update(cid, **{ROW_KEYS[key]: value})
        else:
            self.db.mem_set(key, json.dumps(value, ensure_ascii=False), "parent", cid)

    def delete(self, key, child_id=None):
        if key in ROW_KEYS:   # the row keeps a value: a name falls back to the placeholder, age to 6, avatar to girl
            self.db.child_update(self._cid(child_id), **{ROW_KEYS[key]: {"child_name": "My child", "child_age": 6, "avatar": "girl"}[key]})
        else:
            self.db.mem_delete(key, self._cid(child_id))

    def available_bridges(self, child_id=None) -> list:
        """Bridge keys the parent has set to a truthy value."""
        m = self.all(child_id)
        return [k for k in BRIDGE_KEYS if m.get(k, {}).get("value") not in (None, False, "", 0)]

    def child_age(self, child_id=None) -> int:
        a = self.get("child_age", 6, child_id)
        return a if isinstance(a, int) else 6

    def note_asked(self, topic, obj, child_id=None):
        """Auto-record the last 20 topics / objects asked (newest first)."""
        for key, val in (("recent_topics", topic), ("recent_objects", obj)):
            if val:
                lst = ([val] + list(self.get(key, [], child_id)))[:20]
                self.db.mem_set(key, json.dumps(lst, ensure_ascii=False), "auto", self._cid(child_id))
