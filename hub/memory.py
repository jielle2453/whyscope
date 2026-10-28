"""Context memory (spec section 5): parent-entered facts + auto topics, stored in SQLite."""
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


class Memory:
    def __init__(self, db):
        self.db = db

    def all(self) -> dict:
        """{key: {value, source, updated_ts}} with decoded values."""
        out = {}
        for r in self.db.mem_all():
            try:
                v = json.loads(r["value"])
            except Exception:
                v = r["value"]
            out[r["key"]] = {"value": v, "source": r["source"], "updated_ts": r["updated_ts"]}
        return out

    def get(self, key, default=None):
        return self.all().get(key, {}).get("value", default)

    def set(self, key, value):
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
        self.db.mem_set(key, json.dumps(value, ensure_ascii=False), "parent")

    def delete(self, key):
        self.db.mem_delete(key)

    def available_bridges(self) -> list:
        """Bridge keys the parent has set to a truthy value."""
        m = self.all()
        return [k for k in BRIDGE_KEYS if m.get(k, {}).get("value") not in (None, False, "", 0)]

    def child_age(self) -> int:
        a = self.get("child_age", 6)
        return a if isinstance(a, int) else 6

    def note_asked(self, topic, obj):
        """Auto-record the last 20 topics / objects asked (newest first)."""
        for key, val in (("recent_topics", topic), ("recent_objects", obj)):
            if val:
                lst = ([val] + list(self.get(key, [])))[:20]
                self.db.mem_set(key, json.dumps(lst, ensure_ascii=False), "auto")
