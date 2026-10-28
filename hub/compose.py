"""Compose explanation + question back from an entry's facts, in the Whyscope voice (zh and en).

The first sentence is NEVER produced here (the pipeline speaks entry.first_sentence verbatim).
LLM (Qwen2.5-1.5B-Instruct via transformers on CUDA, or llama-cpp GGUF on CPU) rewrites facts into short, plain
sentences; jieba grounding + novelty checks and the wording rules of hub/wording.py guard it; any failure or timeout
falls back to `template_explanation` (deterministic, facts only, jargon replaced by plain phrases).
"""
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

from . import wording
from .config import resolve, to_trad, torch_device
from .recall import content_en
from .safety import askback_ok

STOP = {"的", "了", "是", "在", "有", "會", "可以", "和", "也", "都", "就", "很", "把", "被", "讓", "跟", "著",
        "一起", "這", "那", "什麼", "嗎", "呢", "吧", "啊", "它", "牠", "他", "她", "我", "你", "們", "個", "種",
        "些", "更", "還", "又", "但", "而", "與", "及", "或", "到", "從", "為", "因為", "所以", "以", "於", "用",
        "要", "能", "對", "給", "不", "沒有", "然後", "如果", "就是", "還是", "比較", "非常"}
_SENT = re.compile(r"[^。！？!?；;\n]+")
NOVELTY_MIN = 0.75  # share of EACH sentence's content bigrams that must come from the entry's own text
BAD_ASKBACK = re.compile(r"你家|你的|你今天|你喜歡|你開心|你難過|朋友|媽媽|爸爸|哥哥|姐姐|弟弟|妹妹|同學|老師")


def content_tokens(s: str) -> set:
    import jieba
    return {t for t in jieba.lcut(s) if t.strip() and t not in STOP and not re.fullmatch(r"[\W_]+", t)}


def grounded(explanation: str, facts: list) -> bool:
    """Every sentence must share >=1 content token (jieba) with some fact."""
    sents = [s.strip() for s in _SENT.findall(explanation) if s.strip()]
    if not sents:
        return False
    fact_toks = [content_tokens(f) for f in facts]
    return all(any(content_tokens(s) & ft for ft in fact_toks) for s in sents)


_FUNC = re.compile(r"[的了是在有會和也都就很把被讓跟著這那嗎呢吧啊喔哦它牠他她我你們個種些更還又但而與及或到從為以於用要能對給不，。！？、；：,.!? ]+")


def _runs_bigrams(s: str) -> set:
    """Character bigrams inside runs of content characters (function characters act as separators)."""
    out = set()
    for run in _FUNC.split(s):
        if len(run) == 1:
            out.add(run)
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    return out


def novelty_ok(text: str, source: str, min_ratio: float) -> bool:
    """At least `min_ratio` of the text's content bigrams must already occur in the source (facts, labels...).
    Blocks the model from adding new knowledge ("防止被天敵吃掉") that the sources never stated."""
    tb = _runs_bigrams(text)
    return not tb or len(tb & _runs_bigrams(source)) / len(tb) >= min_ratio


FILLER = {"變得", "慢慢", "一樣", "通常", "常常", "其實", "大約", "比較", "可能", "所以", "因為", "這樣", "一直", "越來越",
          "好像", "就會", "才會", "才能", "能夠", "知道", "看到", "看起來", "跑掉", "掉下來", "起來", "出來", "很多", "一些",
          "小朋友", "我們", "大家", "牠們", "自己", "樣子", "東西", "有時候", "時候", "地方", "身體"}


def novel_tokens(sentence: str, source: str) -> list:
    """Words of the sentence that the source never uses and that could carry NEW knowledge.

    Synonym verbs / adjectives / adverbs / particles ("透過", "形成", "快速") are tolerated (at most 2 per sentence),
    new nouns and numbers ("慣性", "角質片", "三十") never are: they are what a 1.5B model invents."""
    import jieba.posseg as pseg
    nouns, other = [], []
    for w in pseg.lcut(sentence):
        t = w.word
        if (not t.strip() or len(t) < 2 or t in source or t in FILLER or t in STOP or re.fullmatch(r"[\W_]+", t)):
            continue
        (other if w.flag[:1] in ("v", "d", "a", "p", "c", "u", "r", "z") else nouns).append(t)
    return nouns + (other if len(other) > 2 else [])


def _plain_bigrams(s: str) -> set:
    t = re.sub(r"[\W_]+", "", s)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def repeats(sentence: str, spoken: str, ratio: float = 0.5) -> bool:
    """True if the sentence mostly restates what was already said (e.g. the first sentence)."""
    sb = _plain_bigrams(sentence)
    return bool(sb) and len(sb & _plain_bigrams(spoken)) / len(sb) >= ratio


# ---------------------------------------------------------------- deterministic pieces
def _fit(sents: list, budget: int) -> list:
    """Longest prefix of `sents` whose spoken length fits the budget (at least the first one)."""
    out, used = [], 0
    for s in sents:
        n = wording.chars_of(s)
        if out and used + n > budget:
            break
        out.append(s)
        used += n
    return out


def template_explanation(entry: dict, age: int, budget: int = wording.MAX_TOTAL_CHARS) -> str:
    """Deterministic fallback: facts[0] (+ facts[1] for 7-8), jargon replaced, <=18 chars per sentence."""
    facts = [wording.plainify(f).strip("。！？ ") for f in entry["facts"]]
    fresh = [f for f in facts if not repeats(f, entry["first_sentence"])]
    facts = fresh or facts   # do not just say the first sentence again
    good = [f for f in facts if not wording.check_text(f, 1)]
    if not good:  # cut a long fact at its first / last clause
        for f in facts:
            for part in [p for p in re.split(r"[，、,]", f) if p]:
                if not wording.check_text(part, 1):
                    good.append(part)
        good = good or [min(facts, key=len)]
    want = 1 if age <= 6 else 2
    picked = _fit(good[:want], budget)
    if len(picked) < want and len(good) > 1 and want == 2 and wording.chars_of(good[0]) > budget:
        picked = [min(good, key=wording.chars_of)]
    return "".join(s + "。" for s in picked)


def pick_ask_back(entry: dict, bridges: list, use_bridge: bool):
    """(ask_back, bridge_key|None). Bridge text comes from the KB; every ask-back is made guessable."""
    if use_bridge:
        for k, v in entry.get("bridges", {}).items():
            if k in bridges and askback_ok(v) and v.strip().endswith(("？", "?")):   # only real questions
                return wording.guessable(v), k
    ask = entry.get("ask_back", "")
    if not ask or not askback_ok(ask):
        ask = f"你覺得{entry['labels'][0]}還有什麼好玩的地方嗎？"
    return wording.guessable(ask), None


def template(entry: dict, age: int = 6, bridges=(), use_bridge=False, budget=wording.MAX_TOTAL_CHARS) -> dict:
    ask, key = pick_ask_back(entry, list(bridges), use_bridge)
    return {"explanation": template_explanation(entry, age, budget), "ask_back": ask, "bridge_used": key,
            "source": "template"}


# ---------------------------------------------------------------- the model
SYSTEM = ("你是「好奇鏡」，一位溫柔的大人，在跟5到8歲的孩子說話。規則：\n"
          "1. 只能用「事實」裡的資訊，不可以加入新知識或新詞，盡量沿用事實的字詞。\n"
          "2. 每一句最多18個字，講具體的東西，用小朋友聽得懂的話，不用科學名詞。\n"
          "3. 不誇獎孩子，不說「我覺得」「我喜歡」，不問孩子今天、心情、家人或朋友的事。\n"
          "4. ask_back 是一個小朋友可以猜的問題（可以回答是或不是，或二選一），不超過25個字。\n"
          "5. 用台灣繁體中文，只輸出一個JSON，不要其他文字。")
# three few-shot turns in the Whyscope voice: (age, facts, output)
SHOTS = [
    (5, ["蚊子的嘴巴像一根細細的針", "只有蚊子媽媽會吸血"],
     {"explanation": "蚊子的嘴巴像細細的針。", "ask_back": "你猜蚊子是用嘴巴吸血，還是用腳吸血？"}),
    (6, ["殼可以保護蝸牛軟軟的身體", "殼會跟著蝸牛一起長大"],
     {"explanation": "殼會保護蝸牛軟軟的身體。", "ask_back": "你覺得蝸牛下雨天會出來嗎？"}),
    (8, ["雲是很多小水滴飄在天空", "水滴變大變重，就會掉下來"],
     {"explanation": "雲是很多小水滴。因為水滴變重了，所以會掉下來。", "ask_back": "你覺得雲裡的水滴越多，雨會變大還是變小？"}),
]


def _user_msg(age, facts, said=""):
    rule = ("explanation 只寫1句，句子要短，要具體" if age <= 6
            else "explanation 寫2句，把兩個事實各說一句；事實裡有原因的話，才用一次「因為…所以…」")
    fl = "\n".join(f"- {f}" for f in facts)
    said = f"已經說過：{said}（不要再說一次）\n" if said else ""
    return f"孩子{age}歲。\n事實：\n{fl}\n{said}{rule}，每句不超過18個字，事實裡沒有的東西不要說。輸出JSON：{{\"explanation\":…,\"ask_back\":…}}"


# ---------------------------------------------------------------- English (english-mode.md section 2)
_SENT_EN = re.compile(r"[^.!?\n]+[.!?]*")
BAD_ASKBACK_EN = re.compile(r"\byour\b|\byou(?:'re| are) (?:so|very)\b", re.I)
NOVELTY_MIN_EN = 0.7


def en_view(entry: dict) -> dict:
    """The entry with its English fields at the top level (labels, first_sentence, facts, ask_back, bridges)."""
    en = entry.get("en") or {}
    return {**entry, "labels": en.get("labels") or entry.get("labels", []),
            "first_sentence": en.get("first_sentence", ""), "facts": en.get("facts") or [],
            "ask_back": en.get("ask_back", ""), "bridges": en.get("bridges") or {}}


def _clean_en(s: str) -> str:
    return (s or "").replace("’", "'").strip()


def _split_en(text: str) -> list:
    return [s.strip() for s in _SENT_EN.findall(text or "") if re.search(r"[A-Za-z0-9]", s)]


def grounded_en(explanation: str, facts: list) -> bool:
    """Every sentence shares >= 1 content word (stemmed) with some fact."""
    sents = _split_en(explanation)
    if not sents:
        return False
    fact_toks = [set(content_en(f)) for f in facts]
    return all(any(set(content_en(s)) & ft for ft in fact_toks) for s in sents)


def novel_words_en(sentence: str, source: str) -> list:
    """Content words of the sentence that the source never uses (candidates for invented knowledge)."""
    src = set(content_en(source))
    return [w for w in content_en(sentence) if w not in src]


def novelty_ok_en(sentence: str, source: str, max_novel: int = 1) -> bool:
    cw = content_en(sentence)
    nov = novel_words_en(sentence, source)
    if any(w.isdigit() for w in nov):
        return False
    return not cw or (len(nov) <= max_novel and (len(cw) - len(nov)) / len(cw) >= NOVELTY_MIN_EN)


def repeats_en(sentence: str, spoken: str, ratio: float = 0.6) -> bool:
    """True if the sentence mostly restates what was already said (e.g. the first sentence)."""
    sw = set(content_en(sentence))
    return bool(sw) and len(sw & set(content_en(spoken))) / len(sw) >= ratio


def _fit_en(sents: list, budget: int) -> list:
    out, used = [], 0
    for s in sents:
        n = len(wording.words_en(s))
        if out and used + n > budget:
            break
        out.append(s)
        used += n
    return out


def _end(s: str) -> str:
    s = s.strip(" ,;:")
    return s if s.endswith((".", "!", "?")) else s + "."


def template_explanation_en(entry: dict, age: int, budget: int = wording.MAX_TOTAL_WORDS) -> str:
    """Deterministic fallback: facts[0] (+ facts[1] for 7-8) of the English entry, jargon replaced."""
    ev = en_view(entry)
    facts = [wording.plainify_en(_clean_en(f)) for f in ev["facts"]]
    fresh = [f for f in facts if not repeats_en(f, ev["first_sentence"])]
    facts = fresh or facts
    good = [f for f in facts if not wording.check_text_en(f, 1)]
    if not good:   # cut a long fact at a clause boundary
        for f in facts:
            for part in re.split(r",\s*|\s+(?:and|because|when|so|but)\s+", f):
                part = part.strip(" .!")
                if len(wording.words_en(part)) >= 3:
                    part = _end(part[:1].upper() + part[1:])
                    if not wording.check_text_en(part, 1):
                        good.append(part)
        if not good:
            good = [min(facts, key=lambda f: len(wording.words_en(f)))] if facts else [ev["first_sentence"]]
    want = 1 if age <= 6 else 2
    picked = _fit_en(good[:want], budget)
    return " ".join(_end(s) for s in picked)


def pick_ask_back_en(entry: dict, bridges: list, use_bridge: bool):
    """(ask_back, bridge_key|None) from the English entry; every ask-back is made guessable."""
    ev = en_view(entry)
    if use_bridge:
        for k, v in ev["bridges"].items():
            if k in bridges and wording.askback_ok_en(v) and v.strip().endswith("?"):
                return wording.guessable_en(v), k
    ask = ev["ask_back"]
    if not ask or not wording.askback_ok_en(ask):
        ask = f"Can you guess one more thing about the {(ev['labels'] or ['thing'])[0]}?"
    return wording.guessable_en(ask), None


def template_en(entry: dict, age: int = 6, bridges=(), use_bridge=False, budget=wording.MAX_TOTAL_WORDS) -> dict:
    ask, key = pick_ask_back_en(entry, list(bridges), use_bridge)
    return {"explanation": template_explanation_en(entry, age, budget), "ask_back": ask, "bridge_used": key,
            "source": "template"}


SYSTEM_EN = ("You are Whyscope, a gentle grown-up talking with a child aged 5 to 8. Rules:\n"
             "1. Use only the information in the facts. Do not add new knowledge or new words; reuse the words of the facts.\n"
             "2. Every sentence has at most 12 words. Talk about concrete things in words a 6-year-old knows. No science words.\n"
             "3. Never praise the child. Never say \"I think\" or \"I like\". Never ask about the child's day, feelings, family or friends.\n"
             "4. ask_back is one question the child can guess (yes or no, or \"A or B\"), at most 15 words, about the thing itself.\n"
             "5. Output exactly one JSON object and nothing else.")
SHOTS_EN = [
    (5, ["A mosquito's mouth is like a thin needle.", "Only mother mosquitoes drink blood."],
     {"explanation": "A mosquito's mouth is like a thin needle.",
      "ask_back": "Do you think a mosquito drinks blood with its mouth, or its feet?"}),
    (6, ["The shell keeps the snail's soft body safe.", "The shell grows with the snail."],
     {"explanation": "The shell keeps the snail's soft body safe.",
      "ask_back": "Do you think a snail comes out in the rain?"}),
    (8, ["A cloud is a lot of tiny water drops in the sky.", "When the drops get big and heavy, they fall down."],
     {"explanation": "A cloud is a lot of tiny water drops. When the drops get heavy, they fall down.",
      "ask_back": "Do you think more drops make big rain, or small rain?"}),
]


def _user_msg_en(age, facts, said=""):
    rule = ("Write 1 short, concrete sentence for explanation" if age <= 6
            else "Write 2 sentences for explanation, one for each fact; use \"because\" once only if a fact gives a reason")
    fl = "\n".join(f"- {f}" for f in facts)
    said = f"Already said: {said} (do not say it again)\n" if said else ""
    return (f"The child is {age} years old.\nFacts:\n{fl}\n{said}{rule}, at most 12 words per sentence, "
            f"nothing that is not in the facts. Output JSON: {{\"explanation\": ..., \"ask_back\": ...}}")


class Composer:
    def __init__(self, cfg: dict):
        self.cfg = cfg["compose"]
        self.full_cfg = cfg
        self.backend = None          # "transformers" | "llama" | None
        self.ready = False
        self.error = None
        self.last_reject = ""
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._timeouts = 0
        self._skipped = 0
        jieba_quiet()
        if self.cfg.get("enabled", True):
            threading.Thread(target=self._load, daemon=True).start()

    # ---- loading (background so the server starts fast) ----
    def _load(self):
        try:
            if cfg_mode(self.full_cfg) == "cpu" and self._load_llama():
                return
            self._load_transformers()
        except Exception as e:  # missing package, no model, OOM ...
            self.error = f"{type(e).__name__}: {str(e)[:200]}"
            self.ready = False

    def _load_llama(self) -> bool:
        gguf = next(iter(resolve(self.full_cfg, "models").glob("*qwen2.5-1.5b*q4_k_m*.gguf")), None)
        if not gguf:
            return False
        from llama_cpp import Llama  # optional dependency
        self.llm = Llama(model_path=str(gguf), n_ctx=1536, verbose=False)
        self.backend, self.ready = "llama", True
        return True

    def _load_transformers(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        name = self.cfg["model"]
        cache = str(resolve(self.full_cfg, "models") / "hf")
        dev = torch_device(self.full_cfg)
        kw = dict(cache_dir=cache)
        try:
            self.tok = AutoTokenizer.from_pretrained(name, local_files_only=True, **kw)
            self.model = AutoModelForCausalLM.from_pretrained(
                name, torch_dtype=torch.float16 if dev == "cuda" else torch.float32,
                local_files_only=True, **kw)
        except Exception:
            self.tok = AutoTokenizer.from_pretrained(name, **kw)
            self.model = AutoModelForCausalLM.from_pretrained(
                name, torch_dtype=torch.float16 if dev == "cuda" else torch.float32, **kw)
        self.model.to(dev).eval()
        self.dev = dev
        self.backend, self.ready = "transformers", True
        self._generate([{"role": "user", "content": "hi"}], 4)  # warm-up (CUDA kernels)

    # ---- generation ----
    def _messages(self, entry, age, lang="zh"):
        if lang == "en":
            ev = en_view(entry)
            msgs = [{"role": "system", "content": SYSTEM_EN}]
            for a, facts, out in SHOTS_EN:
                msgs.append({"role": "user", "content": _user_msg_en(a, facts)})
                msgs.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
            msgs.append({"role": "user", "content": _user_msg_en(age, ev["facts"], ev["first_sentence"])})
            return msgs
        msgs = [{"role": "system", "content": SYSTEM}]
        for a, facts, out in SHOTS:
            msgs.append({"role": "user", "content": _user_msg(a, facts)})
            msgs.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
        msgs.append({"role": "user", "content": _user_msg(age, entry["facts"], entry["first_sentence"])})
        return msgs

    def _generate(self, msgs, max_new) -> str:
        """Run the LLM on chat messages; returns raw JSON-ish text (assistant output is prefilled with '{')."""
        prefill = '{"explanation": "'
        if self.backend == "llama":
            out = self.llm.create_chat_completion(messages=msgs, max_tokens=max_new, temperature=0.0)
            return out["choices"][0]["message"]["content"]
        import torch
        prompt = self.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True) + prefill
        ids = self.tok(prompt, return_tensors="pt").to(self.dev)
        with torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                                      stop_strings=["}"], tokenizer=self.tok)
        return prefill + self.tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

    def _run(self, entry, age, lang="zh") -> str:
        return self._generate(self._messages(entry, age, lang), int(self.cfg.get("max_new_tokens", 120)))

    @staticmethod
    def _parse(raw: str):
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    def _reject(self, why):
        self.last_reject = why
        return None

    def _validate(self, d, entry, age, bridges, use_bridge, budget):
        """Return a clean result dict or None if the model output is unusable."""
        if not isinstance(d, dict):
            return None
        source = " ".join(entry["facts"] + [entry["first_sentence"]] + list(entry.get("labels", [])))
        exp = to_trad(str(d.get("explanation", "")).strip())
        sents = _fit([s.strip() for s in _SENT.findall(exp) if s.strip()][:1 if age <= 6 else 2], budget)
        exp = "。".join(sents) + "。" if sents else ""
        # spec 8.5 grounding (shared content token) plus a stricter no-new-knowledge check. Comparisons the model
        # invents ("像雨衣") are NOT allowed: in testing they produced false statements.
        if not exp:
            return self._reject("empty")
        if not grounded(exp, entry["facts"]):
            return self._reject("not grounded: " + exp)
        bad = [s for s in sents if not novelty_ok(s, source, NOVELTY_MIN) or len(novel_tokens(s, source)) > 0]
        if bad:
            return self._reject(f"new knowledge: {bad[0]} {novel_tokens(bad[0], source)}")
        if any(repeats(s, entry["first_sentence"]) for s in sents):
            return self._reject("repeats the first sentence: " + exp)
        exp = wording.plainify(exp)
        probs = wording.check_text(exp, 1 if age <= 6 else 2)
        if probs or wording.chars_of(exp) > budget:
            return self._reject(f"wording {probs} / budget {budget}: {exp}")
        ask, bkey = pick_ask_back(entry, bridges, use_bridge)
        if not bkey:   # the model may propose its own ask-back; it must pass every guard, else the entry's is used
            mine = to_trad(str(d.get("ask_back", "")).strip())
            asrc = source + " " + entry.get("ask_back", "")
            if (mine and len(mine) <= wording.ASKBACK_MAX and mine.endswith(("？", "?"))
                    and wording.ask_ok_pattern(mine) and askback_ok(mine) and not BAD_ASKBACK.search(mine)
                    and not wording.NOT_ALLOWED.search(mine) and not wording.has_banned(mine)
                    and not wording.check_text(mine, 1)
                    and novelty_ok(mine, asrc, 0.75)):
                ask = mine
        return {"explanation": exp, "ask_back": ask, "bridge_used": bkey, "source": "llm"}

    def _validate_en(self, d, entry, age, bridges, use_bridge, budget):
        """English twin of _validate: grounding, no new knowledge, wording rules, guessable ask-back."""
        if not isinstance(d, dict):
            return None
        ev = en_view(entry)
        source = " ".join(ev["facts"] + [ev["first_sentence"]] + list(ev["labels"]))
        exp = wording.plainify_en(_clean_en(str(d.get("explanation", ""))))
        sents = _fit_en(_split_en(exp)[:1 if age <= 6 else 2], budget)
        exp = " ".join(_end(s) for s in sents)
        if not sents:
            return self._reject("empty")
        if not grounded_en(exp, ev["facts"]):
            return self._reject("not grounded: " + exp)
        bad = [s for s in sents if not novelty_ok_en(s, source)]
        if bad:
            return self._reject(f"new knowledge: {bad[0]} {novel_words_en(bad[0], source)}")
        if any(repeats_en(s, ev["first_sentence"]) for s in sents):
            return self._reject("repeats the first sentence: " + exp)
        probs = wording.check_text_en(exp, 1 if age <= 6 else 2)
        if probs or wording.spoken_words(exp) > budget:
            return self._reject(f"wording {probs} / budget {budget}: {exp}")
        ask, bkey = pick_ask_back_en(entry, bridges, use_bridge)
        if not bkey:
            mine = _clean_en(str(d.get("ask_back", "")))
            asrc = source + " " + ev["ask_back"]
            if (mine and len(wording.words_en(mine)) <= wording.ASKBACK_MAX_WORDS and mine.endswith("?")
                    and wording.ask_ok_pattern_en(mine) and wording.askback_ok_en(mine) and not BAD_ASKBACK_EN.search(mine)
                    and not wording.NOT_ALLOWED_EN.search(mine) and not wording.has_banned_en(mine)
                    and wording.rare_score_en(mine) <= wording.MAX_RARE_EN
                    and novelty_ok_en(mine, asrc, 2)):
                ask = mine
        return {"explanation": exp, "ask_back": ask, "bridge_used": bkey, "source": "llm"}

    def compose(self, entry: dict, age: int, bridges: list, use_bridge: bool = False,
                budget: int = None, lang: str = "zh") -> dict:
        """Return {explanation, ask_back, bridge_used, source}; never raises, never blocks > timeout.

        Circuit breaker: after 2 consecutive timeouts (a CPU-only machine) the LLM is skipped for 10 requests
        and then probed again, so a slow model does not add the full timeout to every answer."""
        en = lang == "en"
        if budget is None:
            budget = wording.MAX_TOTAL_WORDS if en else wording.MAX_TOTAL_CHARS
        base = template_en if en else template
        tpl = lambda why="": {**base(entry, age, bridges, use_bridge, budget),  # noqa: E731
                              "source": "template" + (f"({why})" if why else "")}
        if not (self.cfg.get("enabled", True) and self.ready):
            return tpl()
        if self._timeouts >= 2 and self._skipped < 10:
            self._skipped += 1
            return tpl("llm-too-slow")
        self._skipped = 0
        try:
            fut = self._pool.submit(self._run, entry, age, lang)
            raw = fut.result(timeout=float(self.cfg.get("timeout_s", 6.0)))
            self._timeouts = 0
            res = (self._validate_en if en else self._validate)(self._parse(raw), entry, age, bridges, use_bridge, budget)
            return res or tpl("grounding")
        except FutTimeout:
            self._timeouts += 1
            return tpl("timeout")
        except Exception:
            return tpl("error")


def cfg_mode(cfg):
    return cfg.get("mode", "cpu")


def jieba_quiet():
    import jieba
    jieba.setLogLevel(60)
