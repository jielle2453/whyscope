"""Compose explanation + question back from an entry's facts.

The first sentence is NEVER produced here (the pipeline speaks entry.first_sentence verbatim).
LLM (Qwen2.5-1.5B-Instruct via transformers on CUDA, or llama-cpp GGUF on CPU) rewrites facts into
<=2 short sentences; a jieba grounding check guards it; any failure/timeout -> template fallback.
"""
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

from .config import resolve, to_trad, torch_device

STOP = {"的", "了", "是", "在", "有", "會", "可以", "和", "也", "都", "就", "很", "把", "被", "讓", "跟", "著",
        "一起", "這", "那", "什麼", "嗎", "呢", "吧", "啊", "它", "牠", "他", "她", "我", "你", "們", "個", "種",
        "些", "更", "還", "又", "但", "而", "與", "及", "或", "到", "從", "為", "因為", "所以", "以", "於", "用",
        "要", "能", "對", "給", "不", "沒有", "然後", "如果", "就是", "還是", "比較", "非常"}
_SENT = re.compile(r"[^。！？!?；;\n]+")
NOVELTY_MIN = 0.75  # share of the explanation's content bigrams that must come from the entry's own text
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


def template(entry: dict) -> dict:
    """Spec fallback: facts[0] + the entry's own question back."""
    return {"explanation": entry["facts"][0], "ask_back": entry.get("ask_back", ""),
            "bridge_used": None, "source": "template"}


class Composer:
    def __init__(self, cfg: dict):
        self.cfg = cfg["compose"]
        self.full_cfg = cfg
        self.backend = None          # "transformers" | "llama" | None
        self.ready = False
        self.error = None
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
        self.llm = Llama(model_path=str(gguf), n_ctx=1024, verbose=False)
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
    def _prompt(self, entry, age, bridges):
        nl = chr(10)
        facts = nl.join(f"- {f}" for f in entry["facts"])
        bl = {k: v for k, v in entry.get("bridges", {}).items() if k in bridges}
        bridge_txt = nl.join(f"{k}: {v}" for k, v in bl.items()) or "（無）"
        sys = ("你是給5到8歲孩子的科學小幫手。只能使用「事實」裡的資訊，不可以加入事實裡沒有的新知識或新詞。"
               "盡量沿用事實的原句和字詞，只做簡化。用台灣繁體中文。只輸出一個JSON，不要其他文字。")
        example = ('{"explanation": "殼可以保護蝸牛軟軟的身體。", "ask_back": "你覺得蝸牛下雨天會出來嗎？", '
                   '"bridge_used": null}')
        user = (f"例子{nl}事實：{nl}- 殼可以保護蝸牛軟軟的身體{nl}- 殼會跟著蝸牛一起長大{nl}輸出：{example}{nl}{nl}"
                f"現在{nl}孩子年齡：{age}歲{nl}事實：{nl}{facts}{nl}可用的連結（key: 句子）：{nl}{bridge_txt}{nl}"
                "輸出JSON，explanation 最多2句、全部不超過40字，只用事實；ask_back 是一個關於這個東西的問句，"
                f"不超過30字；bridge_used 是上面某個key或 null。{nl}參考的問句：{entry.get('ask_back', '')}")
        return sys, user

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

    def _run(self, entry, age, bridges) -> str:
        sys, user = self._prompt(entry, age, bridges)
        msgs = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
        return self._generate(msgs, int(self.cfg.get("max_new_tokens", 120)))

    @staticmethod
    def _parse(raw: str):
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    def _validate(self, d, entry, bridges):
        """Return a clean result dict or None if the model output is unusable."""
        if not isinstance(d, dict):
            return None
        source = " ".join(entry["facts"] + [entry["first_sentence"]] + list(entry.get("labels", [])))
        exp = to_trad(str(d.get("explanation", "")).strip())
        sents = [s.strip() for s in _SENT.findall(exp) if s.strip()][:2]
        exp = "。".join(sents) + "。" if sents else ""
        # spec 8.5 grounding (shared content token) plus a stricter no-new-knowledge check
        if (not exp or len(exp) > 40 or not grounded(exp, entry["facts"])
                or not novelty_ok(exp, source, NOVELTY_MIN)):
            return None
        bkey = d.get("bridge_used")
        bridge = entry.get("bridges", {})
        if bkey in bridge and bkey in bridges:
            ask = bridge[bkey]            # bridge text comes from the KB verbatim
        else:
            bkey = None
            ask = to_trad(str(d.get("ask_back", "")).strip())
            asrc = source + " " + entry.get("ask_back", "")
            if (not ask or len(ask) > 30 or not ask.endswith(("？", "?")) or BAD_ASKBACK.search(ask)
                    or not novelty_ok(ask, asrc, NOVELTY_MIN)):
                ask = entry.get("ask_back", "")
        return {"explanation": exp, "ask_back": ask, "bridge_used": bkey, "source": "llm"}

    def compose(self, entry: dict, age: int, bridges: list) -> dict:
        """Return {explanation, ask_back, bridge_used, source}; never raises, never blocks > timeout.

        Circuit breaker: after 2 consecutive timeouts (a CPU-only machine) the LLM is skipped for 10 requests
        and then probed again, so a slow model does not add the full timeout to every answer."""
        if not (self.cfg.get("enabled", True) and self.ready):
            return template(entry)
        if self._timeouts >= 2 and self._skipped < 10:
            self._skipped += 1
            return {**template(entry), "source": "template(llm-too-slow)"}
        self._skipped = 0
        try:
            fut = self._pool.submit(self._run, entry, age, bridges)
            raw = fut.result(timeout=float(self.cfg.get("timeout_s", 6.0)))
            self._timeouts = 0
            res = self._validate(self._parse(raw), entry, bridges)
            return res or {**template(entry), "source": "template(grounding)"}
        except FutTimeout:
            self._timeouts += 1
            return {**template(entry), "source": "template(timeout)"}
        except Exception:
            return {**template(entry), "source": "template(error)"}


def cfg_mode(cfg):
    return cfg.get("mode", "cpu")


def jieba_quiet():
    import jieba
    jieba.setLogLevel(60)
