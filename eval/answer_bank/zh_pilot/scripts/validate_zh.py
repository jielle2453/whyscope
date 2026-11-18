"""Mechanical checks for zh pilot rows (uses the hub's own rules, read-only).
Usage: python validate_zh.py FILE.jsonl [FILE2.jsonl ...]   -> prints problems; exit 1 if any ERROR.
       python validate_zh.py --json FILE...                    -> JSON {id: {"errors": [...], "warnings": [...]}}

ERRORS (must fix):
  * fields: q_zh, variants_zh (4-6, distinct), a1_zh, a2_zh, ask_back_zh, a1_zh_mix, key_en (0-2 {en, zh}), tw_note
  * a1_zh_mix: null, or a1_zh with exactly ONE English word woven in (hub check_text, 1 sentence, no "用英文說"-type
    quiz lines, keeps 因為 when a1_zh has it); a1_zh itself has no Latin letters
  * a1_zh: exactly 1 sentence; hub wording.check_text (<=18 spoken chars per sentence, banned jargon, rare chars, flattery)
  * a2_zh: 1-2 sentences, hub wording.check_text
  * ask_back_zh: safety.askback_ok, compose.BAD_ASKBACK, wording.ask_ok_pattern (嗎/還是/猜/你覺得), <=30 chars, 1 question
  * no simplified characters (char-level OpenCC s2tw/t2s test, whitelist SIMP_OK) and no mainland-only words (MAINLAND)
    (OpenCC s2twp phrase rewrites are only a WARNING: it also rewrites valid Taiwan words such as 社區, 循環, 打開)
  * variants_zh: >=1 mixed zh+English variant
  * key_en: lowercase English letters/spaces, simple; zh given
  * tw_note: "" or "not_for_tw: ..." or "adapted: ..."
WARNINGS (look at):
  * a1_zh of a why-question without 因為 ; key_en word not in the English a1/a2/q
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from hub import wording, safety, compose  # noqa: E402
from hub.config import to_trad  # noqa: E402
from opencc import OpenCC  # noqa: E402
_S2T, _T2S = OpenCC("s2tw").convert, OpenCC("t2s").convert
SIMP_OK = set("台游里干划")   # valid in Taiwan text although OpenCC treats them as simplified forms
MIX_QUIZ = re.compile(r"用英文|英文怎麼|英文叫什麼|跟我說|你會說|說說看|念念看|唸唸看")


# Proposed exception to hub wording.BANNED (reviewers: 小蟲蟲 for germs suggests worms/parasites in Taiwan; kids know
# 細菌 from hand-washing campaigns). Checked as if it were a plain 2-char word and reported as a WARNING.
HUB_EXCEPT = {"細菌": "小蟲"}


def hubcheck(text, max_sentences, allow, W, name):
    t = text
    for a, b in HUB_EXCEPT.items():
        if a in t:
            W.append(f"{name} uses '{a}' (hub BANNED term; pilot exception, needs a hub rule change)")
            t = t.replace(a, b)
    return wording.check_text(t, max_sentences=max_sentences, allow=allow)


def simplified(t):
    return [c for c in t if c not in SIMP_OK and _S2T(c) != c and _T2S(c) == c]

BANK = {}
for l in open(ROOT / "knowledge" / "answer_bank_en.jsonl", encoding="utf-8"):
    d = json.loads(l); BANK[d["id"]] = d

# Mainland-only words a Taiwanese preschool teacher would not say (TW form in comment).
MAINLAND = ["視頻", "质量", "質量", "土豆", "信息", "軟件", "網絡", "打印", "出租車", "公交", "地鐵", "自行車",
            "摩托車", "菠蘿", "獼猴桃", "酸奶", "方便面", "方便麵", "塑料", "激光", "鼠標", "屏幕", "U盤", "空調",
            "衛生間", "數據", "程序", "博客", "啥", "咋", "唄", "玩兒", "一點兒", "哪兒", "這兒", "那兒", "一會兒",
            "小孩兒", "早上好", "西紅柿", "番茄醬", "幼兒園", "小朋友們好", "搞", "老師好", "水平", "項目",
            "冰棍", "雪糕", "奶茶店", "紅綠燈口", "立交橋", "馬路牙子", "饅頭片", "熊孩子", "寶貝兒",
            "牛奶盒子", "垃圾箱", "互聯網", "手電筒", "電冰箱", "洗衣粉", "公共汽車", "計算機", "攝像頭",
            "充電寶", "保溫杯", "小區", "樓房", "土豆泥", "花生米", "西瓜汁兒", "胳膊肘", "腦袋瓜"]
# allowed although listed above when the TW form is the same word
MAINLAND_OK = {"番茄醬", "幼兒園", "手電筒"}
MAINLAND = [w for w in MAINLAND if w not in MAINLAND_OK]
WHY = re.compile(r"\bwhy\b|how come", re.I)
EN_WORD = re.compile(r"^[a-z][a-z \-]{0,20}$")
LATIN = re.compile(r"[A-Za-z]")
CJK = re.compile(r"[一-鿿]")


def sent_count(s):
    return len(wording.sentences(s))


def check(row):
    E, W = [], []
    rid = row.get("id")
    src = BANK.get(rid)
    if not src:
        return ["unknown id"], W
    for k in ["q_zh", "variants_zh", "a1_zh", "a2_zh", "ask_back_zh", "a1_zh_mix", "key_en", "tw_note"]:
        if k not in row:
            E.append(f"missing {k}")
    if E:
        return E, W
    q, v, a1, a2, ab = row["q_zh"], row["variants_zh"], row["a1_zh"], row["a2_zh"], row["ask_back_zh"]
    allow = frozenset(re.sub(r"[^一-鿿]", "", q + "".join(v)))
    # simplified / mainland
    for name, t in [("q_zh", q), ("a1_zh", a1), ("a2_zh", a2), ("ask_back_zh", ab)] + [(f"variant{i}", x) for i, x in enumerate(v)]:
        if not isinstance(t, str) or not t.strip():
            E.append(f"{name} empty"); continue
        sc = simplified(t)
        if sc:
            E.append(f"{name} simplified characters {sc}")
        tt = to_trad(t)
        if tt != t:
            W.append(f"{name} OpenCC s2twp would rewrite ({t} -> {tt}); fine if it is valid Taiwan usage")
        for w in MAINLAND:
            if w in t:
                E.append(f"{name} mainland word '{w}'")
    if not isinstance(v, list) or not (4 <= len(v) <= 6):
        E.append(f"variants_zh count {len(v) if isinstance(v, list) else '?'} (need 4-6)")
    else:
        if len(set(v)) != len(v) or q in v:
            E.append("variants_zh duplicate (or same as q_zh)")
        if not any(LATIN.search(x) and CJK.search(x) for x in v):
            E.append("variants_zh: no mixed zh+English variant")
    if not CJK.search(q):
        E.append("q_zh has no Chinese")
    # a1
    n1 = sent_count(a1)
    if n1 != 1:
        E.append(f"a1_zh has {n1} sentences (need 1)")
    for p in hubcheck(a1, 1, allow, W, "a1_zh"):
        E.append(f"a1_zh {p}")
    if WHY.search(src["q"]) and "因為" not in a1:
        W.append("a1_zh for a why-question has no 因為")
    if LATIN.search(a1):
        E.append("a1_zh contains Latin letters (must stay pure Chinese)")
    mix = row["a1_zh_mix"]
    if mix is not None:
        words = re.findall(r"[A-Za-z]+(?:[ '-][A-Za-z]+)?", mix) if isinstance(mix, str) else []
        if not isinstance(mix, str) or len(words) != 1:
            E.append(f"a1_zh_mix must be null or contain exactly one English word (found {words})")
        else:
            if sent_count(mix) != 1:
                E.append("a1_zh_mix must be 1 sentence")
            for p in hubcheck(mix, 1, allow, W, "a1_zh_mix"):
                E.append(f"a1_zh_mix {p}")
            if MIX_QUIZ.search(mix):
                E.append("a1_zh_mix quizzes the child on English")
            if "因為" in a1 and "因為" not in mix:
                W.append("a1_zh_mix dropped the 因為 cause")
            if simplified(mix):
                E.append(f"a1_zh_mix simplified characters {simplified(mix)}")
            ke_en = [k.get("en", "").lower() for k in row.get("key_en") or [] if isinstance(k, dict)]
            if words[0].lower() not in ke_en:
                W.append(f"a1_zh_mix word '{words[0]}' is not in key_en")
    # a2
    for p in hubcheck(a2, 2, allow, W, "a2_zh"):
        E.append(f"a2_zh {p}")
    if wording.chars_of(a1) + wording.chars_of(a2) > wording.MAX_TOTAL_CHARS:
        E.append("a1+a2 over 60 chars")
    # ask-back
    if not safety.askback_ok(ab):
        E.append("ask_back_zh fails safety.askback_ok")
    if compose.BAD_ASKBACK.search(ab):
        E.append(f"ask_back_zh hits compose.BAD_ASKBACK '{compose.BAD_ASKBACK.search(ab).group(0)}'")
    if not wording.ask_ok_pattern(ab):
        E.append("ask_back_zh not guessable (needs 嗎/還是/猜/你覺得)")
    if wording.NOT_ALLOWED.search(ab):
        E.append("ask_back_zh feelings/flattery")
    if wording.chars_of(ab) > wording.ASKBACK_MAX:
        E.append(f"ask_back_zh over {wording.ASKBACK_MAX} chars")
    if not ab.rstrip().endswith(("？", "?")):
        E.append("ask_back_zh does not end with ？")
    if len(wording.rare_chars(ab, allow)) > wording.MAX_RARE:
        E.append(f"ask_back_zh rare characters {wording.rare_chars(ab, allow)}")
    if wording.has_banned(ab.replace("細菌", "")):
        E.append("ask_back_zh banned term")
    # key_en
    ke = row["key_en"]
    if not isinstance(ke, list) or not (0 <= len(ke) <= 2):
        E.append("key_en needs 0-2 items")
    else:
        en_text = " ".join([src["a1"], src.get("a2", ""), src["q"]] + src.get("variants", [])).lower()
        for k in ke:
            if not isinstance(k, dict) or not k.get("en") or not k.get("zh"):
                E.append(f"key_en bad item {k}"); continue
            if not EN_WORD.match(k["en"]):
                E.append(f"key_en '{k['en']}' not simple lowercase english")
            if not CJK.search(k["zh"]) or simplified(k["zh"]):
                E.append(f"key_en zh '{k['zh']}' not Traditional Chinese")
            if not re.search(r"\b" + re.escape(k["en"].rstrip("s")), en_text):
                W.append(f"key_en '{k['en']}' not in English q/a1/a2")
    tw = row["tw_note"]
    if tw and not re.match(r"^(not_for_tw|adapted):\s*\S", tw):
        E.append("tw_note must be '' or 'not_for_tw: …' or 'adapted: …'")
    return E, W


def main(argv):
    as_json = "--json" in argv
    files = [a for a in argv if a != "--json"]
    res, nerr, n = {}, 0, 0
    for f in files:
        for l in open(f, encoding="utf-8-sig"):
            if not l.strip():
                continue
            row = json.loads(l); n += 1
            e, w = check(row)
            res[row.get("id")] = {"errors": e, "warnings": w}
            nerr += bool(e)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for rid, r in res.items():
            for e in r["errors"]:
                print(f"ERROR {rid}: {e}")
            for w in r["warnings"]:
                print(f"warn  {rid}: {w}")
        print(f"{n} rows, {nerr} with errors")
    return 1 if nerr else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
