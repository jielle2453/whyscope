"""Offline voice check over ALL entries (reviewed and AI drafts) against the frozen reviewed vocabulary.

For every entry and language it checks, with the same plainify step the pipeline uses:
  first_sentence, every fact (a fact can be spoken as the explanation), the ask-back, and every bridge sentence
  - en: <= 12 words per sentence (ask-back <= 16), rare-word score <= 2 (a word longer than 9 letters counts double),
        no banned science term, no flattery / "I think", ask-back pattern + block list
  - zh: <= 18 characters per sentence (ask-back <= 30), <= 2 characters outside common_chars.txt, no banned term
The entry's own label words (the thing the child just named) are not counted as uncommon, as in hub/compose.py; --strict
turns that off. Uncommon-word / rare-character failures are reported separately ("RARE") because that rule only works while the
common lists are built from reviewed content (see wording.baseline_words_en and scripts/build_common_chars.py).

Usage: python eval/check_voice.py [--rare-only] [--drafts-only] [--list]
"""
import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hub import wording as W  # noqa: E402
from hub.safety import askback_ok  # noqa: E402


def check_en(kind, text, allow=frozenset()):
    out = []
    ss = W.sentences_en(W.plainify_en(text))
    limit = W.ASKBACK_MAX_WORDS if kind == "ask_back" else W.MAX_SENT_WORDS
    for s in ss:
        if len(W.words_en(s)) > limit:
            out.append(("LEN", f"{len(W.words_en(s))} words: {s}"))
        if W.rare_score_en(s, allow) > W.MAX_RARE_EN:
            out.append(("RARE", f"{W.rare_words_en(s, allow)}: {s}"))
    if W.has_banned_en(W.plainify_en(text)):
        out.append(("BANNED", text))
    if W.NOT_ALLOWED_EN.search(text):
        out.append(("FLATTER", text))
    if kind == "ask_back" and not (W.ask_ok_pattern_en(text) and W.askback_ok_en(text)):
        out.append(("ASKPAT", text))
    return out


def check_zh(kind, text, allow=frozenset()):
    out = []
    t = W.plainify(text)
    limit = W.ASKBACK_MAX if kind == "ask_back" else W.MAX_SENT_CHARS
    for s in W.sentences(t):
        if W.chars_of(s) > limit:
            out.append(("LEN", f"{W.chars_of(s)} chars: {s}"))
        if len(W.rare_chars(s, allow)) > W.MAX_RARE:
            out.append(("RARE", f"{W.rare_chars(s, allow)}: {s}"))
    if W.has_banned(t):
        out.append(("BANNED", text))
    if W.NOT_ALLOWED.search(text):
        out.append(("FLATTER", text))
    if kind == "ask_back" and not (W.ask_ok_pattern(text) and askback_ok(text)):
        out.append(("ASKPAT", text))
    return out


def texts(e, lang):
    d = e.get("en", {}) if lang == "en" else e
    yield "first_sentence", d.get("first_sentence", "")
    for f in d.get("facts", []):
        yield "fact", f
    yield "ask_back", d.get("ask_back", "")
    for b in (d.get("bridges") or {}).values():
        yield "bridge", b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rare-only", action="store_true")
    ap.add_argument("--drafts-only", action="store_true")
    ap.add_argument("--strict", action="store_true", help="no exemption for the entry's own label words")
    ap.add_argument("--list", action="store_true", help="print every failing text")
    a = ap.parse_args()
    summary = {}
    ids_rare = {"en": set(), "zh": set()}
    n = 0
    for f in sorted(glob.glob(str(ROOT / "knowledge" / "entries" / "*" / "*.json"))):
        e = json.load(open(f, encoding="utf-8"))
        draft = bool(e.get("draft"))
        if a.drafts_only and not draft:
            continue
        n += 1
        for lang, chk in (("en", check_en), ("zh", check_zh)):
            allow = W.entry_allow_en(e) if lang == "en" else W.entry_allow_zh(e)
            if a.strict:
                allow = frozenset()
            for kind, text in texts(e, lang):
                for code, msg in chk(kind, text, allow):
                    if a.rare_only and code != "RARE":
                        continue
                    key = (("draft" if draft else "reviewed"), lang, code)
                    summary[key] = summary.get(key, 0) + 1
                    if code == "RARE":
                        ids_rare[lang].add(e["id"])
                    if a.list:
                        print(f"{e['id']} [{lang} {kind} {code}] {msg}")
    print(f"\nentries checked: {n}")
    for k in sorted(summary):
        print("  ", k, summary[k])
    print("entries with a RARE failure: en", len(ids_rare["en"]), " zh", len(ids_rare["zh"]))
    sys.exit(1 if any(k[2] in ("RARE", "BANNED", "FLATTER", "ASKPAT") for k in summary) else 0)


if __name__ == "__main__":
    main()
