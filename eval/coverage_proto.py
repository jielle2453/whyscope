"""Experiment: reference-corpus coverage prototype (no hub changes).

For each question in eval/kid_questions.jsonl:
  1. retrieve intro extracts from Simple English Wikipedia (en) / zh.wikipedia.org (zh, variant zh-tw + opencc),
     cached as JSON under --cache (about 1 request per second when not cached);
  2. pick the 2-4 most relevant sentences (multilingual MiniLM embedding + keyword overlap);
  3. ask the UGen300 worker (hub/hailo.py HailoLLMRemote protocol: POST /complete) to answer in child language
     using ONLY the passage;
  4. apply the hub's child-voice rules (hub/wording.py) and a grounding check; keep the raw output too.

Usage (hub may keep running; the worker serves one request at a time, so do not call the hub meanwhile):
  python eval/coverage_proto.py --out <results.jsonl> [--cache <dir>] [--limit N] [--no-gen]
Results are appended per question; ids already present in --out are skipped (resume).
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

UA = "WhyscopeEval/0.1 (research prototype)"
WORKER = "http://127.0.0.1:8711"
API = {"en": "https://simple.wikipedia.org/w/api.php", "zh": "https://zh.wikipedia.org/w/api.php"}
MAX_NEW = {"en": 80, "zh": 90}

EN_STOP = set("""why do does did is are was were can could will would i my me we our you your the a an to of in on at it its
this that these those so when what how who which have has had be been being get got make makes made things thing
some any there their they them he she his her and or but if then than too very really just always never often
sometimes up down out off over under into from with without for by as""".split())
ZH_STOP = set("为什么 为何 什么 怎么 如何 是 的 了 在 有 会 要 可以 能 我 我们 你 他 它 那么 这么 一直 有时候 都 就 也 很 吗 呢 吧 一个 一粒 让 把 被 跟 和 才 不 没有 为 时候".split())

SYS = {
    "en": ("You are Whyscope, a gentle grown-up talking with a child aged 7. Answer the child's question in at most "
           "3 very short sentences (each at most 12 words), using ONLY the information in the passage. Use simple words "
           "a 6-year-old knows and no science words. Do not add anything that is not in the passage. "
           "If the passage does not answer the question, say only: I don't know."),
    "zh": ("你是「好奇鏡」，一位溫柔的大人，在跟7歲的孩子說話。請只用「資料」裡的資訊，用最多3句很短的話"
           "（每句最多18個字）回答孩子的問題。用台灣繁體中文，用小朋友聽得懂的話，不用科學名詞，"
           "不可以加入資料裡沒有的東西。如果資料沒有回答這個問題，只說「我不知道」。"),
}


# ------------------------------------------------------------------ retrieval
def keywords(q: str, lang: str) -> str:
    if lang == "en":
        ws = re.findall(r"[a-z]+", q.lower().replace("'", " "))
        ks = [w for w in ws if w not in EN_STOP and len(w) > 1]
        return " ".join(ks)
    import jieba
    from opencc import OpenCC
    jieba.setLogLevel(60)
    qs = re.sub("[会著着]", " ", OpenCC("t2s").convert(q.replace("會", " ")))         # jieba's dictionary is simplified-centric; zh.wikipedia search accepts it
    ks = []
    for w in jieba.lcut(qs):
        w = w.strip()
        if w and w not in ZH_STOP and not re.fullmatch(r"[\W_]+", w) and w not in ks:
            ks.append(w)
    return " ".join(ks)


class Wiki:
    def __init__(self, cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.last = 0.0

    def get(self, lang: str, params: dict) -> tuple:
        """(json, seconds spent on the network when first fetched). Cached on disk."""
        params = {"format": "json", "formatversion": "2", **params}
        if lang == "zh":
            params["variant"] = "zh-tw"
        key = hashlib.sha1((lang + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:20]
        f = self.cache / f"{lang}_{key}.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            return d["data"], d["fetch_s"]
        wait = 1.05 - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        url = API[lang] + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        t = time.perf_counter()
        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                break
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"wikipedia fetch failed: {last_err}")
        dt = time.perf_counter() - t
        self.last = time.time()
        f.write_text(json.dumps({"params": params, "fetch_s": dt, "data": data}, ensure_ascii=False), encoding="utf-8")
        return data, dt

    def retrieve(self, q: str, lang: str, n: int = 3):
        kw = keywords(q, lang)
        fetch = 0.0
        sr, dt = self.get(lang, {"action": "query", "list": "search", "srsearch": kw, "srlimit": 5, "srnamespace": 0,
                                 "srprop": ""})
        fetch += dt
        titles = [h["title"] for h in (sr.get("query") or {}).get("search", [])]
        docs = []
        if titles:
            ex, dt = self.get(lang, {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
                                     "exlimit": min(len(titles), 5), "redirects": 1, "titles": "|".join(titles)})
            fetch += dt
            pages = {p["title"]: p.get("extract", "") for p in (ex.get("query") or {}).get("pages", [])}
            for t in titles:
                txt = pages.get(t, "")
                if not txt.strip() or re.search(r"may refer to|可以指|可能指|消歧義|多義", txt[:300]):
                    continue
                docs.append({"title": t, "text": txt.strip()})
                if len(docs) >= n:
                    break
        return kw, titles, docs, fetch


# ------------------------------------------------------------------ passage selection
_ST = None


def embedder():
    global _ST
    if _ST is None:
        from sentence_transformers import SentenceTransformer
        _ST = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                                  cache_folder=r"C:\Users\Jie\Desktop\whyscope\whyscope\models\hf", device="cpu")
    return _ST


def split_sents(text: str, lang: str):
    text = re.sub(r"\([^)]*\)|（[^）]*）", "", text)       # drop parentheticals (pronunciations, dates)
    parts = re.split(r"(?<=[。！？!?])|(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p and len(p.strip()) > (6 if lang == "zh" else 20)]


def pick_passage(q: str, kw: str, docs: list, lang: str, k: int = 3):
    """Most relevant k sentences over the first 8 sentences of each hit; returns (passage, best_cos, hit_title)."""
    from sentence_transformers import util
    cands = []
    for rank, d in enumerate(docs):
        for i, s in enumerate(split_sents(d["text"], lang)[:8]):
            cands.append((rank, i, d["title"], s))
    if not cands:
        return "", 0.0, ""
    m = embedder()
    qe = m.encode([q], normalize_embeddings=True)
    se = m.encode([c[3] for c in cands], normalize_embeddings=True)
    cos = util.cos_sim(qe, se)[0].tolist()
    kws = [w for w in kw.split() if len(w) > (1 if lang == "zh" else 3)]
    scored = []
    for (rank, i, title, s), c in zip(cands, cos):
        bonus = 0.08 * sum(1 for w in kws if w.lower() in s.lower()) + (0.05 if i == 0 else 0) - 0.03 * rank
        scored.append((c + bonus, c, rank, i, title, s))
    scored.sort(key=lambda x: -x[0])
    top = scored[0]
    chosen = [x for x in scored if x[2] == top[2]][:k]          # sentences from the best hit only
    chosen.sort(key=lambda x: x[3])
    limit = 160 if lang == "zh" else 600
    out, used = [], 0
    for x in chosen:
        if out and used + len(x[5]) > limit:
            break
        out.append(x[5])
        used += len(x[5])
    sep = "" if lang == "zh" else " "
    return sep.join(out), round(max(c for _, c, *_ in scored), 3), top[4]


# ------------------------------------------------------------------ generation
def chatml(msgs):
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in msgs)


def worker(path, body, timeout=120):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # localhost: never via a proxy
    req = urllib.request.Request(WORKER + path, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    with op.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def generate(q: str, passage: str, lang: str):
    prefix = chatml([{"role": "system", "content": SYS[lang]}])
    if lang == "zh":
        user = f"資料：{passage}\n\n孩子的問題：{q}\n請用最多3句很短的話回答。"
        stop = {"quote": "", "ends": "。！？", "n": 3}
    else:
        user = f"Passage: {passage}\n\nChild's question: {q}\nAnswer in at most 3 very short sentences."
        stop = {"quote": "", "ends": ".!?", "n": 3}
    turn = chatml([{"role": "user", "content": user}]) + "<|im_start|>assistant\n"
    t = time.perf_counter()
    out = worker("/complete", {"prefix": prefix, "turn": turn, "max_new": MAX_NEW[lang], "stop": stop})
    dt = time.perf_counter() - t
    if "text" not in out:
        raise RuntimeError(str(out))
    return out["text"].strip(), dt


# ------------------------------------------------------------------ checks
def checks(raw: str, passage: str, lang: str) -> dict:
    from hub import wording
    from hub.config import to_trad
    c = {}
    if lang == "zh":
        txt = wording.plainify(to_trad(raw))
        ss = wording.sentences(txt)
        c["idk"] = bool(re.search(r"我不知道", txt)) and len(txt) < 12
        c["language_ok"] = bool(re.search(r"[\u4e00-\u9fff]", txt)) and len(re.findall(r"[A-Za-z]", txt)) <= 3
        c["sentence_count_ok"] = 0 < len(ss) <= 3
        c["sentence_len_ok"] = all(wording.chars_of(s) <= wording.MAX_SENT_CHARS for s in ss) and bool(ss)
        c["total_len_ok"] = sum(wording.chars_of(s) for s in ss) <= wording.MAX_TOTAL_CHARS
        c["rare_ok"] = all(len(wording.rare_chars(s)) <= wording.MAX_RARE for s in ss)
        c["jargon_ok"] = not wording.has_banned(txt)
        c["voice_ok"] = not wording.NOT_ALLOWED.search(txt)
        from hub.compose import content_tokens
        pt = content_tokens(passage)
        toks = [content_tokens(s) for s in ss]
        allt = set().union(*toks) if toks else set()
        c["grounded_ratio"] = round(len(allt & pt) / len(allt), 2) if allt else 0.0
        c["grounded_ok"] = bool(ss) and all(t & pt for t in toks) and c["grounded_ratio"] >= 0.6
    else:
        txt = wording.plainify_en(raw)
        ss = wording.sentences_en(txt)
        c["idk"] = bool(re.search(r"don't know|do not know", txt, re.I)) and len(wording.words_en(txt)) < 8
        c["language_ok"] = not re.search(r"[\u4e00-\u9fff]", txt) and bool(wording.words_en(txt))
        c["sentence_count_ok"] = 0 < len(ss) <= 3
        c["sentence_len_ok"] = bool(ss) and all(len(wording.words_en(s)) <= wording.MAX_SENT_WORDS for s in ss)
        c["total_len_ok"] = wording.spoken_words(txt) <= wording.MAX_TOTAL_WORDS
        c["rare_ok"] = all(wording.rare_score_en(s) <= wording.MAX_RARE_EN for s in ss)
        c["jargon_ok"] = not wording.has_banned_en(txt)
        c["voice_ok"] = not wording.NOT_ALLOWED_EN.search(txt)
        from hub.recall import content_en
        pt = set(content_en(passage))
        toks = [set(content_en(s)) for s in ss]
        allt = set().union(*toks) if toks else set()
        c["grounded_ratio"] = round(len(allt & pt) / len(allt), 2) if allt else 0.0
        c["grounded_ok"] = bool(ss) and all(t & pt for t in toks) and c["grounded_ratio"] >= 0.6
    c["clean_text"] = txt
    base = ["language_ok", "sentence_count_ok", "sentence_len_ok", "jargon_ok", "voice_ok", "grounded_ok"]
    c["pass_relaxed"] = (not c["idk"]) and all(c[k] for k in base)          # everything except total-length and rare-word caps
    c["pass_strict"] = c["pass_relaxed"] and c["total_len_ok"] and c["rare_ok"]   # the hub's full voice rules
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=r"C:\Users\Jie\AppData\Local\Temp\claude\57443cdb2b122bd0\0ec9328b-c5a1-4a54-8d2f-8e114e8ca926\scratchpad\wiki_cache")
    ap.add_argument("--questions", default=str(REPO / "eval" / "kid_questions.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-gen", action="store_true", help="retrieval + passage only (no UGen300 call)")
    a = ap.parse_args()
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
    if a.limit:
        qs = qs[:a.limit]
    done = set()
    if Path(a.out).exists():
        done = {json.loads(l)["id"] for l in open(a.out, encoding="utf-8") if l.strip()}
    wiki = Wiki(Path(a.cache))
    out = open(a.out, "a", encoding="utf-8")
    for q in qs:
        if q["id"] in done:
            continue
        lang = q["lang"]
        t0 = time.perf_counter()
        rec = {**q}
        try:
            kw, titles, docs, fetch_s = wiki.retrieve(q["q"], lang)
            if lang == "zh":
                from hub.config import to_trad
                for d in docs:
                    d["text"] = to_trad(d["text"])
                    d["title"] = to_trad(d["title"])
            t1 = time.perf_counter()
            passage, best_cos, title = pick_passage(q["q"], kw, docs, lang)
            select_s = time.perf_counter() - t1
            rec.update(keywords=kw, search_titles=titles, hit_titles=[d["title"] for d in docs], passage_title=title,
                       passage=passage, best_cos=best_cos, fetch_s=round(fetch_s, 2), select_s=round(select_s, 3))
            if passage and not a.no_gen:
                raw, gen_s = generate(q["q"], passage, lang)
                rec.update(raw=raw, gen_s=round(gen_s, 2), **{"chk": checks(raw, passage, lang)})
                rec["total_s"] = round(fetch_s + select_s + gen_s, 2)
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        print(q["id"], rec.get("passage_title"), rec.get("gen_s"), (rec.get("raw") or "")[:60].replace("\n", " "), rec.get("error", ""),
              flush=True)


if __name__ == "__main__":
    main()
