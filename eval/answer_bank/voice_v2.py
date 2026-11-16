"""Wording check for answer-bank items (same rules as eval/check_voice.py, applied to a1 / a2 / ask_back).
Usage: python voice_v2.py FILE.jsonl [FILE2 ...] [--list]   -> per-file failure rates; --list prints failing texts.
Rules (hub/wording.py): <=12 words per sentence (ask-back <=16), rare-word score <=2, no banned science term,
no flattery, ask-back must be guessable (do you think / or / guess / can you / is it / does) and must not probe the
child's day, feelings, family or friends. The item's own question words are not counted as rare (like the hub's label exemption)."""
import json, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hub import wording as W  # noqa: E402


def allow(d):
    out = set()
    for w in W.words_en(d.get("q", "")):
        b = W._base(w); out.add(b); out.add(W._stem(b))
    return frozenset(out)


def check(kind, text, al):
    out = []
    t = W.plainify_en(text or "")
    lim = W.ASKBACK_MAX_WORDS if kind == "ask_back" else W.MAX_SENT_WORDS
    for s in W.sentences_en(t):
        if len(W.words_en(s)) > lim: out.append("LEN")
        if W.rare_score_en(s, al) > W.MAX_RARE_EN: out.append("RARE")
    if W.has_banned_en(text or ""): out.append("BANNED")
    if W.NOT_ALLOWED_EN.search(text or ""): out.append("FLATTER")
    if kind == "ask_back" and not (W.ask_ok_pattern_en(text) and W.askback_ok_en(text)): out.append("ASKPAT")
    return out


def run(items, show=False):
    c = collections.Counter(); bad = 0
    for d in items:
        al = allow(d); f = []
        for k in ("a1", "a2", "ask_back"):
            p = check(k, d.get(k, ""), al)
            f += [f"{k}:{x}" for x in p]
            if show and p: print(d["id"], k, p, "|", d.get(k))
        for x in set(f): c[x] += 1
        bad += bool(f)
    return len(items), bad, c


if __name__ == "__main__":
    show = "--list" in sys.argv
    for fn in [a for a in sys.argv[1:] if not a.startswith("--")]:
        items = [json.loads(l) for l in open(fn, encoding="utf-8") if l.strip()]
        n, bad, c = run(items, show)
        print(f"{fn}: {n} items, {bad} with any flag ({100*bad/max(n,1):.0f}%)", dict(c.most_common()))
