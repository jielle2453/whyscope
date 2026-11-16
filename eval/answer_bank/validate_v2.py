"""Validate a writer file for bank v2.  Usage: python validate_v2.py parts_v2/w01_body.jsonl [--list]
Checks: valid JSON per line; fields id, topic, q, variants (3-5 strings), a1, a2, ask_back, confidence (high|medium), notes;
id format <prefix>-n<WW><NNN> with prefix in bod/ani/pfd/sky/thg/soc; unique ids; no duplicate q in the file;
q not identical (normalised) to an old-bank question or variant. Then runs the wording check (voice_v2.py)."""
import json, re, sys, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_v2  # noqa: E402
FIELDS = ["id", "topic", "q", "variants", "a1", "a2", "ask_back", "confidence", "notes"]
IDRX = re.compile(r"^(bod|ani|pfd|sky|thg|soc)-n\d{2}\d{3,4}$")


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower().replace("'", "")).split())


def main(fn, show):
    old = set()
    for l in open(HERE / "bank_en.jsonl", encoding="utf-8"):
        d = json.loads(l)
        for t in [d["q"]] + d["variants"]:
            old.add(norm(t))
    items, errs, ids, qs = [], [], set(), set()
    for n, l in enumerate(open(fn, encoding="utf-8-sig"), 1):
        if not l.strip():
            continue
        try:
            d = json.loads(l)
        except Exception as e:
            errs.append(f"line {n}: bad JSON {e}"); continue
        miss = [f for f in FIELDS if f not in d]
        if miss: errs.append(f"line {n} {d.get('id')}: missing {miss}")
        if not IDRX.match(str(d.get("id", ""))): errs.append(f"line {n}: bad id {d.get('id')}")
        if d.get("id") in ids: errs.append(f"line {n}: duplicate id {d.get('id')}")
        ids.add(d.get("id"))
        v = d.get("variants")
        if not (isinstance(v, list) and 3 <= len(v) <= 5 and all(isinstance(x, str) and x.strip() for x in v)):
            errs.append(f"line {n} {d.get('id')}: variants must be 3-5 strings")
        if d.get("confidence") not in ("high", "medium"): errs.append(f"line {n} {d.get('id')}: confidence")
        for k in ("q", "a1", "a2", "ask_back", "topic"):
            if not str(d.get(k, "")).strip(): errs.append(f"line {n} {d.get('id')}: empty {k}")
        q = norm(d.get("q"))
        if q in qs: errs.append(f"line {n} {d.get('id')}: duplicate q in file: {d.get('q')}")
        if q in old: errs.append(f"line {n} {d.get('id')}: q already in old bank: {d.get('q')}")
        qs.add(q)
        items.append(d)
    print(f"{fn}: {len(items)} items, {len(errs)} schema errors")
    for e in errs[:60]: print("  ", e)
    n, bad, c = voice_v2.run(items, show)
    print(f"wording: {bad}/{n} items with a flag", dict(c.most_common()))
    print("topics:", dict(collections.Counter(d.get("topic") for d in items).most_common()))


if __name__ == "__main__":
    main(sys.argv[1], "--list" in sys.argv)
