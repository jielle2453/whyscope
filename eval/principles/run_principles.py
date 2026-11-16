"""Principle-library experiment. Stages:
  retrieval : MiniLM embedding retrieval over principles_draft.json (no UGen)   -> results/retrieval.jsonl
  ugen      : UGen choice among top-5 + answer (one worker request at a time)   -> results/ugen_results.jsonl (resumable)
Run with C:\\whyscope-venv\\Scripts\\python.exe (PYTHONIOENCODING=utf-8). Only touches eval/principles/.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
WORKER = "http://127.0.0.1:8711"
LET = "ABCDE"


def load():
    P = json.load(open(HERE / "principles_draft.json", encoding="utf-8"))["principles"]
    G = json.load(open(HERE / "gold.json", encoding="utf-8"))
    qs = [{**r, "set": "failed"} for r in G["failed"]] + [{**r, "set": "heldout"} for r in G["heldout"]]
    return P, qs


def ptext(p, lang):
    return " ".join([p["name_" + lang]] + p["applies_to_" + lang] + p["facts_" + lang])


# ------------------------------------------------------------------ retrieval
def stage_retrieval():
    import numpy as np
    from sentence_transformers import SentenceTransformer
    P, qs = load()
    m = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                            cache_folder=r"C:\Users\Jie\Desktop\whyscope\whyscope\models\hf", device="cpu")
    emb = {}
    for lang in ("zh", "en"):
        l2 = "zh" if lang == "zh" else "en"
        emb[lang] = m.encode([ptext(p, l2) for p in P], normalize_embeddings=True)
    out = open(HERE / "results" / "retrieval.jsonl", "w", encoding="utf-8")
    for q in qs:
        t = time.perf_counter()
        qe = m.encode([q["q"]], normalize_embeddings=True)[0]
        sims = emb[q["lang"]] @ qe
        dt = time.perf_counter() - t
        order = np.argsort(-sims)[:5]
        out.write(json.dumps({**q, "top5": [{"id": P[i]["id"], "score": round(float(sims[i]), 4)} for i in order],
                              "embed_s": round(dt, 4)}, ensure_ascii=False) + "\n")
    out.close()
    print("retrieval done", len(qs))


# ------------------------------------------------------------------ UGen
def chatml(msgs):
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in msgs)


def worker(path, body, timeout=180):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(WORKER + path, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    with op.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def complete(msgs, prefill, max_new, stop):
    prefix = chatml(msgs[:-1])
    turn = chatml(msgs[-1:]) + "<|im_start|>assistant\n" + prefill
    t = time.perf_counter()
    out = worker("/complete", {"prefix": prefix, "turn": turn, "max_new": max_new, "stop": stop})
    return out["text"], time.perf_counter() - t


# ---- choice prompts
CH_SYS = {
    "zh": ("你是幫忙配對的小助手。孩子問了一個問題，下面有幾個候選的科學道理。"
           "請選出一個最能直接回答這個問題的道理，只回答字母（A到E）。"
           "如果沒有任何一個適合，回答 none。只有道理真的解釋了這個問題才可以選。"),
    "en": ("You are a matching helper. A child asked a question, and below are some candidate science ideas. "
           "Pick the one idea that directly explains the question and answer with its letter only (A to E). "
           "If none of them fits, answer none. Only choose an idea if it really explains the question."),
}
CH_SHOTS = {
    "zh": [
        ("為什麼氣球磨過頭髮會黏在牆上？", [("friction", "摩擦力", "兩個東西互相磨的時候，會有一種擋住動作的力，叫摩擦力。"),
                                       ("static", "靜電", "兩個東西互相磨擦，有時候會帶一點靜電。"),
                                       ("sound", "聲音（振動）", "東西一抖一抖（振動）就會發出聲音。")], "B"),
        ("為什麼我的朋友今天不跟我玩？", [("seasons", "四季", "地球繞著太陽走一大圈，要走一年。"),
                                       ("senses", "五種感覺", "我們用眼睛看、耳朵聽、鼻子聞、舌頭嘗、皮膚摸。"),
                                       ("friction", "摩擦力", "兩個東西互相磨的時候，會有一種擋住動作的力，叫摩擦力。")], "none"),
        ("為什麼雪地靴的鞋底有深深的紋路？", [("sound", "聲音（振動）", "東西一抖一抖（振動）就會發出聲音。"),
                                       ("static", "靜電", "兩個東西互相磨擦，有時候會帶一點靜電。"),
                                       ("friction", "摩擦力", "兩個東西互相磨的時候，會有一種擋住動作的力，叫摩擦力。")], "C"),
    ],
    "en": [
        ("Why does a balloon stick to the wall after I rub it on my hair?",
         [("friction", "Friction", "When two things rub together, a force slows the movement. It is called friction."),
          ("static", "Static electricity", "When two things rub together, they can get a little static electricity."),
          ("sound", "Sound and vibration", "When something shakes back and forth (vibrates), it makes a sound.")], "B"),
        ("Why is my friend not playing with me today?",
         [("seasons", "The seasons", "The Earth goes around the sun once in a year."),
          ("senses", "Our five senses", "We see with our eyes, hear with our ears, smell with our nose, taste with our tongue and feel with our skin."),
          ("friction", "Friction", "When two things rub together, a force slows the movement. It is called friction.")], "none"),
        ("Why do snow boots have deep grooves on the bottom?",
         [("sound", "Sound and vibration", "When something shakes back and forth (vibrates), it makes a sound."),
          ("static", "Static electricity", "When two things rub together, they can get a little static electricity."),
          ("friction", "Friction", "When two things rub together, a force slows the movement. It is called friction.")], "C"),
    ],
}


def cand_block(lang, cands):
    return "\n".join(f"{LET[i]}. {name}: {fact}" for i, (_, name, fact) in enumerate(cands))


def choose(q, lang, cands):
    msgs = [{"role": "system", "content": CH_SYS[lang]}]
    ql, cl = ("問題：", "候選：") if lang == "zh" else ("Question: ", "Candidates:")
    for sq, sc, ans in CH_SHOTS[lang]:
        msgs.append({"role": "user", "content": f"{ql}{sq}\n{cl}\n{cand_block(lang, sc)}"})
        msgs.append({"role": "assistant", "content": '{"choice": "%s"}' % ans})
    msgs.append({"role": "user", "content": f"{ql}{q}\n{cl}\n{cand_block(lang, cands)}"})
    raw, dt = complete(msgs, '{"choice": "', 6, {"quote": '"', "ends": "", "n": 0})
    ch = raw.split('"')[0].strip()
    idx = LET.index(ch[0].upper()) if ch[:1].upper() in LET[:len(cands)] and not ch.lower().startswith("none") and ch else None
    return raw, idx, dt


# ---- answer prompts
AN_SYS = {
    "zh": ("你是「好奇鏡」，一位溫柔的大人，在跟7歲的孩子說話。孩子問了一個問題。"
           "請只用「道理」裡的事，把道理用在孩子問的東西上，用1到2句很短的話回答，每句最多18個字。"
           "用台灣繁體中文，用小朋友聽得懂的話，不用科學名詞，不要列點，不可以加入「道理」裡沒有的知識。"),
    "en": ("You are Whyscope, a gentle grown-up talking with a child aged 7. The child asked a question. "
           "Use ONLY the facts in 'Idea' and apply them to the thing the child asked about. "
           "Answer in 1 or 2 very short sentences (each at most 12 words), with simple words a 6-year-old knows, "
           "no science words, no lists, and nothing that is not in the Idea."),
}
AN_SHOTS = {
    "zh": [
        ("為什麼地毯上推箱子比較難推？", ["兩個東西互相磨的時候，會有一種擋住動作的力，叫摩擦力。", "粗粗的地方摩擦力大，滑滑的地方摩擦力小。", "摩擦會讓東西變熱，也會讓滑動的東西慢慢停下來。"],
         "因為地毯粗粗的，擋住箱子的力比較大。所以箱子比較難推。"),
        ("為什麼氣球可以黏在牆上？", ["兩個東西互相磨擦，有時候會帶一點靜電。", "帶靜電的東西可以吸住小紙屑或頭髮。", "天氣乾乾的時候，比較容易有靜電，碰到東西會啪一下。"],
         "氣球磨過頭髮，會帶一點靜電。帶靜電的氣球就能吸住牆。"),
    ],
    "en": [
        ("Why is it hard to push a box on a carpet?", ["When two things rub together, a force slows the movement. It is called friction.", "Rough surfaces have more friction. Slippery surfaces have less.", "Rubbing makes things warm, and it slowly stops sliding things."],
         "A carpet is rough, so it slows the box a lot. That is why the box is hard to push."),
        ("Why does my balloon stick to the wall?", ["When two things rub together, they can get a little static electricity.", "A thing with static can pull on small bits of paper or hair.", "On dry days there is more static, so you may get a little zap when you touch something."],
         "Rubbing the balloon gives it a little static. The static pulls the balloon onto the wall."),
    ],
}


def answer(q, lang, p):
    facts = p["facts_" + lang]
    fl, ql, il = ("道理：", "孩子的問題：", "") if lang == "zh" else ("Idea: ", "Child's question: ", "")
    msgs = [{"role": "system", "content": AN_SYS[lang]}]
    for sq, sf, sa in AN_SHOTS[lang]:
        msgs.append({"role": "user", "content": f"{fl}{' '.join(sf)}\n{ql}{sq}"})
        msgs.append({"role": "assistant", "content": json.dumps({"answer": sa}, ensure_ascii=False)})
    msgs.append({"role": "user", "content": f"{fl}{' '.join(facts)}\n{ql}{q}"})
    ends = "。！？" if lang == "zh" else ".!?"
    raw, dt = complete(msgs, '{"answer": "', 90 if lang == "zh" else 70, {"quote": '"', "ends": ends, "n": 2})
    return raw, dt


def wording_check(text, lang):
    from hub import wording
    if lang == "zh":
        ss = wording.sentences(text)
        probs = list(wording.check_text(wording.plainify(text), 2))
        if any(wording.chars_of(s) > wording.MAX_SENT_CHARS for s in ss):
            pass
        return {"problems": probs, "n_sent": len(ss), "max_sent_chars": max([wording.chars_of(s) for s in ss] or [0]),
                "total_chars": sum(wording.chars_of(s) for s in ss), "banned": wording.has_banned(text),
                "feelings": bool(wording.NOT_ALLOWED.search(text))}
    ss = wording.sentences_en(text)
    probs = list(wording.check_text_en(wording.plainify_en(text), 2))
    return {"problems": probs, "n_sent": len(ss), "max_sent_words": max([len(wording.words_en(s)) for s in ss] or [0]),
            "total_words": wording.spoken_words(text), "banned": wording.has_banned_en(text),
            "feelings": bool(wording.NOT_ALLOWED_EN.search(text))}


def stage_ugen(limit):
    from hub.config import to_trad
    P, _ = load()
    PD = {p["id"]: p for p in P}
    rows = [json.loads(l) for l in open(HERE / "results" / "retrieval.jsonl", encoding="utf-8")]
    f = HERE / "results" / "ugen_results.jsonl"
    done = {json.loads(l)["id"] for l in open(f, encoding="utf-8")} if f.exists() else set()
    out = open(f, "a", encoding="utf-8")
    n = 0
    for r in rows:
        if r["id"] in done:
            continue
        if limit and n >= limit:
            break
        n += 1
        lang = r["lang"]
        t0 = time.perf_counter()
        cands = [(c["id"], PD[c["id"]]["name_" + lang], PD[c["id"]]["facts_" + lang][0]) for c in r["top5"]]
        rec = {**r}
        try:
            raw_c, idx, dt_c = choose(r["q"], lang, cands)
            rec.update(choice_raw=raw_c, choice_idx=idx, choice_id=(cands[idx][0] if idx is not None else None), choice_s=round(dt_c, 2))
            if idx is not None:
                p = PD[cands[idx][0]]
                raw_a, dt_a = answer(r["q"], lang, p)
                txt = raw_a.split('"')[0].strip()
                rec.update(answer_raw=raw_a, answer_s=round(dt_a, 2))
                rec["answer_opencc"] = to_trad(txt) if lang == "zh" else txt
                rec["wording"] = wording_check(rec["answer_opencc"], lang)
            rec["total_s"] = round(r["embed_s"] + dt_c + rec.get("answer_s", 0), 2)
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        print(r["id"], rec.get("choice_id"), "|", rec.get("answer_opencc", ""), rec.get("error", ""), flush=True)


def stage_oracle():
    """Answer step only, with the GOLD principle, for gold full/partly questions where the UGen choice was not the gold principle."""
    from hub.config import to_trad
    P, _ = load()
    PD = {p["id"]: p for p in P}
    rows = [json.loads(l) for l in open(HERE / "results" / "ugen_results.jsonl", encoding="utf-8")]
    f = HERE / "results" / "oracle_answers.jsonl"
    done = {json.loads(l)["id"] for l in open(f, encoding="utf-8")} if f.exists() else set()
    out = open(f, "a", encoding="utf-8")
    for r in rows:
        if r["id"] in done or r["coverage"] == "none" or r["choice_id"] == r["principle"]:
            continue
        raw_a, dt = answer(r["q"], r["lang"], PD[r["principle"]])
        txt = raw_a.split('"')[0].strip()
        t2 = to_trad(txt) if r["lang"] == "zh" else txt
        out.write(json.dumps({"id": r["id"], "lang": r["lang"], "q": r["q"], "set": r["set"], "principle": r["principle"], "coverage": r["coverage"],
                              "answer_raw": raw_a, "answer_opencc": t2, "answer_s": round(dt, 2), "wording": wording_check(t2, r["lang"])}, ensure_ascii=False) + "\n")
        out.flush()
        print(r["id"], t2, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["retrieval", "ugen", "oracle"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    {"retrieval": stage_retrieval, "oracle": stage_oracle}.get(a.stage, lambda: stage_ugen(a.limit))()


