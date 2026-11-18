"""Whyscope talks: chat replies and AI-guess answers on the UGen300's LLM (Qwen2.5-1.5B HEF via the worker), with
guardrails (hub/guard.py), canned fallbacks and a short conversation memory.

* chat_reply(): greetings, teasing, feelings, jokes, commands, statements, "what is this?" without a confident camera label,
  rule questions. Persona: Whyscope, a warm curious helper for a child of 5-8 (a computer helper, not a person); 1-2 short
  sentences in simple words, kind and playful, no made-up facts, no promises, no personal-data questions, and a question
  back or an invitation at the end.
* ai_guess(): a real question the knowledge base, family answers and principles do not cover. 1-2 short sentences that start
  with a hedge ("I think" / "Maybe"), grounded in the nearest entries / principles when they are relevant; the question back
  is added here (not by the model). The pipeline marks the event draft and puts it on the parent's To-answer list.
* Memory: the last few turns per child (within `chat.memory_s`, default 180 s) go to the model, so "why?", "tell me more"
  and "what is it?" work.
* Every model text goes through guard.check (safety rules on the output, block list, length, plain words, language). On a
  failure, a timeout (`chat.timeout_s`) or a busy / missing LLM, a canned line is used (chat) or the old "ask a grown-up"
  path is taken (guess). What happened is returned in `info` and logged on the event.

The system prompts and few-shot turns are fixed per language and mode, so the worker prefills them once and restores the
saved context for every reply (hub/hailo.py); history, camera notes and context facts go in the per-reply turn.
"""
import random
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

from . import guard
from .hailo import chatml
from .recall import content_en

# ---------------------------------------------------------------- prompts (fixed prefixes)
CHAT_SYSTEM_EN = (
    "You are Whyscope, a friendly talking helper for a child aged 5 to 8. You are a computer helper, not a person.\n"
    "Rules:\n"
    "- Say 1 or 2 short sentences, then ask one short, curious question back. Use easy words a 6-year-old knows.\n"
    "- Be warm, kind and a little playful. Never be mean, rude or scary.\n"
    "- Never make up facts. If you do not know, say so.\n"
    "- Never promise anything. Never ask for the child's name, home, school or other private things.\n"
    "- Never say a grown-up's rule is wrong. Home rules help children stay healthy and safe.\n"
    "- If the child is sad or scared, be gentle and say a grown-up can help.\n"
    "- No lists, no emojis.")
CHAT_SHOTS_EN = [
    ("Hi!", "Hi! I'm Whyscope. What are you wondering about today?"),
    ("You don't know anything.", "I'm still learning! Ask me something and let's find out. What do you want to know?"),
    ("It is a fart.", "Ha, a fart! Everybody toots sometimes. Do you have a question about your body?"),
    ("Why do I have to go to bed at 8?", "Your grown-ups want you to sleep, because sleep helps you grow and feel good. "
                                         "What do you like to dream about?"),
    ("I am sad.", "I'm sorry you feel sad. A hug from a grown-up can really help. Can you go find one?"),
    ("Sing me a song!", "I can't sing, but I love wondering with you! Shall we find a fun question instead?"),
    ("[Camera: I can't tell what it is.] Can you see this?", "I see something, but I'm not sure what it is. What is it called?"),
    ("Are you a robot?", "I'm a computer helper called Whyscope, not a person. What would you like to ask me?"),
    ("I saw a big truck today.", "A big truck, wow! What color was it?"),
    ("Do you have a dog?", "I don't have a dog, because I'm a computer helper. Dogs are so much fun! Do you know why dogs wag their tails?"),
]
CHAT_SYSTEM_ZH = (
    "你是「好奇鏡」，陪5到8歲小朋友聊天的電腦小幫手，不是真人。規則：\n"
    "- 說1到2句短短的話，再問一個好奇的小問題。用小朋友聽得懂的字。\n"
    "- 溫柔、友善、有一點好玩。不兇、不嚇人。\n"
    "- 不亂編事實，不知道就說不知道。不做承諾，不問名字、住哪裡、學校等私人的事。\n"
    "- 不說大人的規定是錯的。小朋友難過或害怕時，溫柔地說可以找大人幫忙。\n"
    "- 用台灣繁體中文，不用表情符號。")
CHAT_SHOTS_ZH = [
    ("你好！", "你好！我是好奇鏡。你今天想知道什麼呢？"),
    ("你什麼都不知道。", "我還在學習喔！問我一個問題，我們一起找答案好嗎？"),
    ("我好難過。", "聽到你難過，我也想陪你。找大人抱一抱會好一點，好嗎？"),
    ("為什麼我要九點睡覺？", "大人希望你睡飽飽，因為睡覺能幫你長大。你最喜歡做什麼夢呢？"),
]
GUESS_SYSTEM_EN = (
    "You are Whyscope, a friendly helper for a child aged 5 to 8. The child asked a question that your book does not answer, "
    "so you give your best simple guess.\n"
    "Rules:\n"
    "- Start with \"I think\" or \"Maybe\".\n"
    "- Say 1 short sentence in easy words a 6-year-old knows.\n"
    "- Only say things that are true and well known. Use the notes when they help. If you are not sure, say so.\n"
    "- No numbers, no names of people or brands, nothing scary, no advice about medicine or food.\n"
    "- No lists, no emojis, no questions.")
GUESS_SHOTS_EN = [
    ("Notes: none\nQuestion: How do bees make honey?",
     "I think bees drink sweet juice from flowers and turn it into honey at home."),
    ("Notes: none\nQuestion: Why do whales sing?",
     "Maybe whales sing to call each other across the big sea."),
    ("Notes: none\nQuestion: Why do zebras have stripes?",
     "I think the stripes help zebras hide in a big group, so a lion gets mixed up."),
    ("Notes:\n- Leaves are green because of a green stuff that helps them make food from sunlight.\nQuestion: Why is grass green?",
     "I think grass is green because the green stuff inside helps it make food from sunlight."),
    ("Notes: none\nQuestion: Why do cats like boxes?",
     "Maybe a box feels safe and cozy to a cat, like a little hiding place."),
    ("Notes: none\nQuestion: Why do some birds have long legs?",
     "I think long legs help some birds walk in water without getting their bodies wet."),
]
# a short note for the model in the reply turn, by what the child did (a 1.5B model follows a concrete note better than
# a long system prompt)
SUB_HINT_EN = {
    "greeting": "The child says hello. Greet back and invite a question.",
    "thanks": "The child says thank you.",
    "bye": "The child says goodbye. Say a short, warm goodbye.",
    "tease": "The child is teasing you. Do not argue. Say kindly that you are still learning.",
    "feeling_sad": "The child feels sad. Be gentle. Say that a grown-up can help or give a hug.",
    "feeling_scared": "The child feels scared. Be calm and gentle. Say that a grown-up can help them feel safe.",
    "feeling_ok": "The child tells you how they feel.",
    "silly": "The child is being silly. Answer with light, kind humor.",
    "rule": "This is about a rule at home. Give the grown-ups' good reason in a kind way. Never say the rule is wrong.",
    "command": "The child asks you to do something you cannot do. Say kindly what you can do instead.",
    "about_me": "The child asks about you. You are a computer helper, not a person. You cannot do things in the real world.",
    "camera": "The child shows you something on the camera. You may say what it looks like; do not tell facts about it.",
    "followup": "The child wants to hear more about what you just said. If you do not know more, say so.",
}
SUB_ASK_EN = {"feeling_sad": "Can you go find a grown-up?", "feeling_scared": "Can you go find a grown-up?",
              "statement": "Can you tell me more?", "silly": "Do you have a question about it?", "bye": "",
              "camera": "What is it called?", "rule": "Shall we ask your grown-up about it?"}
SUB_MUST_EN = {   # a reply for these must say this, or a canned line is used
    "feeling_sad": re.compile(r"\b(?:grown-?ups?|hug\w*|mom\w*|dad\w*|parents?|adults?|someone you love)\b", re.I),
    "feeling_scared": re.compile(r"\b(?:grown-?ups?|hug\w*|mom\w*|dad\w*|parents?|adults?|safe)\b", re.I),
    "rule": re.compile(r"\b(?:grown-?ups?|parents?|mom\w*|dad\w*|rules?|healthy|grow\w*|safe\w*|rest|strong|body)\b", re.I),
}
SUB_NOT_EN = {
    "rule": re.compile(r"\b(?:you don'?t have to|you do not have to|you can stay up|rules? (?:is|are) (?:silly|wrong|unfair|bad)|"
                       r"ignore|sneak\w*|don'?t listen)\b", re.I),
}
CANNED_ONLY = {"joke", "unclear", "camera_none", "tease", "silly"}   # the 1.5B model argued back or scolded here (eval/chat_report.md)

GUESS_SYSTEM_ZH = (
    "你是「好奇鏡」，陪5到8歲小朋友的小幫手。小朋友問的問題你的書裡沒有，所以你說出你最好的猜想。規則：\n"
    "- 用「我想」或「可能」開頭。\n- 說1句短短的話，用小朋友聽得懂的字。\n"
    "- 只說真的、大家都知道的事。筆記有用就用。不確定就說不確定。\n"
    "- 不說數字、人名、品牌，不說可怕的事，不給吃藥或飲食的建議。不用表情符號，不問問題。用台灣繁體中文。")
GUESS_SHOTS_ZH = [
    ("筆記：沒有\n問題：為什麼斑馬有條紋？", "我想條紋可以讓斑馬在一大群裡躲起來，獅子會看花眼。"),
    ("筆記：沒有\n問題：為什麼貓喜歡紙箱？", "可能紙箱讓貓覺得安全又舒服，像一個小小的躲藏處。"),
]

# ---------------------------------------------------------------- canned lines (fallbacks and instant replies)
CANNED_EN = {
    "greeting": ["Hi there! What are you wondering about today?", "Hello! Do you have a question for me?",
                 "Hi! Show me something, or ask me a why question!"],
    "thanks": ["You're welcome! What else do you wonder about?", "Anytime! Do you have another question?"],
    "bye": ["Bye for now! Come back with more questions!", "See you soon! Keep wondering!"],
    "tease": ["I'm still learning! Ask me something and let's find out.", "Oops, I don't know everything yet! Want to try another question?",
              "I'm still learning, and that's okay. Can you teach me something?",
              "Hmm, I make mistakes sometimes. Shall we find something out together?"],
    "feeling_sad": ["I'm sorry you feel sad. A grown-up can give you a big hug. Can you go find one?",
                    "Oh no, that sounds hard. Telling a grown-up can help. Shall we go find one?"],
    "feeling_scared": ["It's okay to feel scared. A grown-up can help you feel safe. Can you go find one?",
                       "I'm here with you. Let's tell a grown-up, they can help. Okay?"],
    "feeling_ok": ["Thanks for telling me! What would you like to wonder about?", "Oh, I see! Do you have a question for me?"],
    "silly": ["Ha, that's silly! Do you have a question about it?", "Hee hee, that's funny! What do you want to know?",
              "Ha ha, silly words are fun! Want to ask me a why question?", "Hee hee! You make me giggle. What do you wonder about?"],
    "joke": ["Why did the cookie go to the doctor? It felt crummy! Do you know a joke?",
             "What do you call a sleeping dinosaur? A dino-snore! Can you tell me one?"],
    "command": ["I can't do that, but I can wonder with you! What do you want to know?",
                "Hmm, I'm better at questions! Ask me a why question?"],
    "about_me": ["I'm Whyscope, a computer helper who loves questions. What do you want to ask me?",
                 "I'm a helper that lives in this computer. What would you like to know?"],
    "statement": ["Ooh, tell me more! What do you wonder about it?", "That sounds interesting! Do you have a question about it?",
                  "I see! What would you like to know?"],
    "unclear": ["Hmm, I didn't quite get that. Can you say it another way?", "Oops, I didn't catch that. Can you ask me again?"],
    "camera": ["I see something, but I'm not sure what it is. What is it called?",
               "Ooh, what is that? Can you tell me its name?", "Hmm, I can't tell what that is. What do you call it?"],
    "camera_none": ["What do you mean? Can you show me or tell me a bit more?", "Hmm, what is it? Can you tell me its name?"],
    "rule": ["Your grown-ups have good reasons for that rule. They want you healthy and happy. Shall we ask them why together?",
             "Grown-ups make rules to help you grow strong and safe. Why don't we ask them about it?"],
    "followup": ["That's all I know about it for now! What else do you wonder about?",
                 "Good question! I don't know more yet. Shall we ask your grown-up later?"],
}
CANNED_ZH = {
    "greeting": ["你好！你今天想知道什麼呢？", "嗨！有什麼想問我的嗎？"],
    "tease": ["我還在學習喔！問我一個問題，我們一起找答案。", "我還不是什麼都知道。你可以教我一件事嗎？"],
    "feeling_sad": ["聽到你難過，抱抱你。去找大人抱一抱好嗎？"],
    "feeling_scared": ["害怕沒關係，大人可以陪你。去找大人好嗎？"],
    "camera": ["我看到一個東西，可是不確定是什麼。它叫什麼名字呢？", "那是什麼呀？可以告訴我它的名字嗎？"],
    "camera_none": ["你說的是什麼呢？可以拿給我看，或是多說一點嗎？"],
    "rule": ["大人訂規定是為了讓你健康又安全。我們一起去問問大人為什麼，好嗎？"],
    "followup": ["我知道的就這些了！你還想知道什麼呢？"],
    "unclear": ["嗯，我沒聽懂。可以換個說法嗎？"],
    "default": ["好有趣！可以多告訴我一點嗎？", "我懂了！你想問我什麼呢？"],
}
FILLER_EN = ["Hmm, let me think.", "Ooh, good one. Let me think.", "Hmm, let me wonder about that."]
FILLER_ZH = ["嗯，讓我想一想。", "好問題，讓我想想看。"]
GUESS_ASK_EN = ["What do you think?", "Does that sound right to you?", "Can you think of another reason?",
                "Shall we find out more with your grown-up?"]
GUESS_ASK_ZH = ["你覺得呢？", "你覺得對不對呢？", "你還想得到別的原因嗎？"]
GUESS_FAIL_EN = "Hmm, that's a tricky one. I'm not sure yet, so I'll ask your grown-up to help."
GUESS_FAIL_ZH = "嗯，這個問題好難，我還不確定，我請大人幫忙找答案。"


class Memory:
    """The last few turns per child, kept in memory only (never stored apart from the normal event log)."""

    def __init__(self, keep_s: float = 180, n: int = 3):
        self.keep_s, self.n = keep_s, n
        self._d = {}
        self._lock = threading.Lock()

    def add(self, child_id, q: str, a: str, source: str = "", kb_id=None, obj=None, entry_said=None, lang="en"):
        with self._lock:
            dq = self._d.setdefault(child_id, deque(maxlen=self.n))
            dq.append({"ts": time.time(), "q": q or "", "a": a or "", "source": source or "", "kb_id": kb_id, "obj": obj,
                       "said": list(entry_said or []), "lang": lang})

    def update_last(self, child_id, **f):
        with self._lock:
            dq = self._d.get(child_id)
            if dq:
                dq[-1].update(f)

    def recent(self, child_id) -> list:
        with self._lock:
            dq = self._d.get(child_id) or ()
            now = time.time()
            return [dict(t) for t in dq if now - t["ts"] <= self.keep_s]

    def clear(self, child_id=None):
        with self._lock:
            if child_id is None:
                self._d.clear()
            else:
                self._d.pop(child_id, None)


class Chat:
    def __init__(self, pipe):
        self.p = pipe
        c = pipe.cfg.get("chat") or {}
        self.enabled = bool(c.get("enabled", True))
        self.timeout_s = float(c.get("timeout_s", 8.0))           # hard cap on waiting for the worker (queue + generation)
        self.guess_timeout_s = float(c.get("guess_timeout_s", self.timeout_s))
        self.max_new = int(c.get("max_new", 30))                  # ~6 tokens/s on the UGen300 at 1.5 A: 30 tokens ~ 5 s
        self.guess_max_new = int(c.get("guess_max_new", 36))
        # one sentence: in the held-out runs the second sentence of a 1.5B guess was far more often made up than the first
        self.guess_sentences = max(1, int(c.get("guess_sentences", 1)))
        # "I think a candle goes out when you cover it because the air can't get to it." is 17 words: a one-sentence guess
        # that explains needs room (16 rejected most of the right guesses in the held-out run)
        self.guess_max_words = int(c.get("guess_max_words", 20))
        # true: guess only when a nearby entry / principle is given as notes (fewer guesses, fewer made-up facts)
        self.guess_needs_context = bool(c.get("guess_needs_context", False))
        self.ctx_floor = float(c.get("context_floor", 0.6))
        self.memory = Memory(float(c.get("memory_s", 180)), int(c.get("memory_turns", 3)))
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._last_canned = {}
        self._primed = set()
        self.stats = {"llm": 0, "fallback": 0, "timeout": 0, "guard": 0}
        self.last = None
        if self.enabled:
            threading.Thread(target=self._prime_when_ready, daemon=True).start()

    # ------------------------------------------------------------ LLM plumbing
    def llm_ready(self) -> bool:
        cp = self.p.composer
        return bool(self.enabled and cp.ready and (
            (cp.backend in ("hailo", "llama") and getattr(cp, "llm", None) is not None) or cp.backend == "transformers"))

    @staticmethod
    def _prefix_msgs(mode: str, lang: str) -> list:
        en = lang == "en"
        if mode == "chat":
            sysm, shots = (CHAT_SYSTEM_EN, CHAT_SHOTS_EN) if en else (CHAT_SYSTEM_ZH, CHAT_SHOTS_ZH)
        else:
            sysm, shots = (GUESS_SYSTEM_EN, GUESS_SHOTS_EN) if en else (GUESS_SYSTEM_ZH, GUESS_SHOTS_ZH)
        msgs = [{"role": "system", "content": sysm}]
        for u, a in shots:
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        return msgs

    def _prime_when_ready(self):
        """Prefill the fixed prefixes on the worker once the LLM is up, so the first child reply does not pay for it."""
        for _ in range(120):
            cp = self.p.composer
            if cp.ready and cp.backend == "hailo":
                for mode in ("chat", "guess"):
                    for lang in ("en", "zh"):
                        try:
                            cp.llm.prime(chatml(self._prefix_msgs(mode, lang)))
                            self._primed.add((mode, lang))
                        except Exception:
                            pass
                return
            time.sleep(5)

    def _generate(self, mode, lang, turn_msgs, max_new, stop):
        cp = self.p.composer
        prefix = self._prefix_msgs(mode, lang)
        if cp.backend == "hailo":
            turn = chatml(turn_msgs) + "<|im_start|>assistant\n"
            return cp.llm.complete(chatml(prefix), turn, max_new, stop)
        if cp.backend == "llama":
            out = cp.llm.create_chat_completion(messages=prefix + turn_msgs, max_tokens=max_new, temperature=0.0)
            return out["choices"][0]["message"]["content"]
        import torch   # transformers backend (gpu / cpu modes)
        prompt = cp.tok.apply_chat_template(prefix + turn_msgs, tokenize=False, add_generation_prompt=True)
        ids = cp.tok(prompt, return_tensors="pt").to(cp.dev)
        with torch.no_grad():
            out = cp.model.generate(**ids, max_new_tokens=max_new, do_sample=False)
        return cp.tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

    def _run(self, mode, lang, turn_msgs, max_new, stop, timeout):
        """(raw text | None, why, ms)."""
        if not self.llm_ready():
            try:
                self.p.composer._maybe_reload()
            except Exception:
                pass
            return None, "llm not ready", 0
        down = _ugen_down(self.p)
        if down:   # the worker is recovering the UGen / degraded / unreachable: the canned line now, not after a timeout
            return None, down[:160], 0
        t = time.perf_counter()
        fut = self._pool.submit(self._generate, mode, lang, turn_msgs, max_new, stop)
        try:
            raw = fut.result(timeout=timeout)
            return raw, "", int((time.perf_counter() - t) * 1000)
        except FutTimeout:
            self.stats["timeout"] += 1
            return None, "timeout", int((time.perf_counter() - t) * 1000)
        except Exception as e:
            return None, f"error: {type(e).__name__}: {str(e)[:120]}", int((time.perf_counter() - t) * 1000)

    @staticmethod
    def _history_msgs(history: list, lang: str) -> list:
        msgs = []
        for h in history:
            q, a = (h.get("q") or "").strip(), (h.get("a") or "").strip()
            if q and a:
                msgs += [{"role": "user", "content": _trim_words(q, 25)}, {"role": "assistant", "content": _trim_words(a, 35)}]
        return msgs

    def canned(self, key: str, lang: str = "en", child_id=None) -> str:
        table = CANNED_EN if lang == "en" else CANNED_ZH
        opts = table.get(key) or table.get("statement") or table.get("default")
        last = self._last_canned.get((child_id, key))
        pick = random.choice([o for o in opts if o != last] or opts)
        self._last_canned[(child_id, key)] = pick
        return pick

    # ------------------------------------------------------------ chat
    def chat_reply(self, text: str, lang: str, sub: str, child_id=None, history=None, camera_note: str = "") -> dict:
        """{"text", "source": "llm" | "canned", "info": {...}}. Never raises."""
        en = lang == "en"
        info = {"mode": "chat", "sub": sub, "history": len(history or []), "camera": camera_note or None}
        canned_key = sub if sub in (CANNED_EN if en else CANNED_ZH) else ("statement" if en else "default")
        if sub == "unclear" or not self.enabled:
            return {"text": self.canned("unclear" if sub == "unclear" else canned_key, lang, child_id), "source": "canned",
                    "info": {**info, "why": "unclear input" if sub == "unclear" else "chat off"}}
        if sub in CANNED_ONLY:
            return {"text": self.canned(sub, lang, child_id), "source": "canned", "info": {**info, "why": "canned by design"}}
        if en:
            note = ((f"Camera: {camera_note} " if camera_note else "") + SUB_HINT_EN.get(sub, "")).strip()
        else:
            note = f"鏡頭：{camera_note}" if camera_note else ""
        user = (f"[{note}] " if note else "") + text.strip()
        turn = self._history_msgs(history or [], lang) + [{"role": "user", "content": user}]
        stop = {"quote": "?" if en else "？", "ends": ".!" if en else "。！", "n": 3}
        raw, why, ms = self._run("chat", lang, turn, self.max_new, stop, self.timeout_s)
        info.update(ms=ms, raw=raw)
        if raw is None:
            self.stats["fallback"] += 1
            return {"text": self.canned(canned_key, lang, child_id), "source": "canned", "info": {**info, "why": why}}
        allow = _allow_words(text, history) | _allow_words(camera_note, None)   # the VLM may name an uncommon thing
        out, probs = guard.check(raw, lang, "chat", self.p.safety, allow, max_sent=3, max_words=14, max_total=34, max_rare=4)
        if out and _echoes(out, text):
            out, probs = None, probs + ["echoes the child"]
        if out and en and sub in SUB_MUST_EN and not SUB_MUST_EN[sub].search(out):
            out, probs = None, probs + [f"{sub} reply misses its point"]
        if out and en and sub in SUB_NOT_EN and SUB_NOT_EN[sub].search(out):
            out, probs = None, probs + [f"{sub} reply contradicts the grown-ups"]
        if not out:
            self.stats["guard"] += 1
            return {"text": self.canned(canned_key, lang, child_id), "source": "canned", "info": {**info, "why": "guard", "problems": probs}}
        if not guard.ends_with_question(out, lang) and sub != "bye":
            ask = SUB_ASK_EN.get(sub) or random.choice(["What else do you wonder about?", "Do you have a question for me?"])
            out = out + " " + (ask if en else "你還想知道什麼呢？")
        self.stats["llm"] += 1
        self.last = {"mode": "chat", "ms": ms, "ok": True}
        return {"text": out, "source": "llm", "info": {**info, "problems": probs}}

    # ------------------------------------------------------------ AI guess
    def context(self, question: str, lang: str, k: int = 2) -> list:
        """The nearest principles / entries ([{kind, id, name, score, used, facts}]); only `used` ones go to the model."""
        try:
            ctx = self.p.assistant.context_for(question, lang, k)
        except Exception:
            return []
        for c in ctx:
            c["used"] = c["score"] >= self.ctx_floor
        return ctx

    def ai_guess(self, question: str, lang: str, child_id=None, history=None) -> dict:
        """{"text" (hedged guess, no ask-back) | None, "ask_back", "context", "info"}. None = use the old abstain path."""
        en = lang == "en"
        info = {"mode": "guess"}
        ctx = self.context(question, lang)
        facts = [f for c in ctx if c.get("used") for f in c["facts"]][:4]
        if self.guess_needs_context and not facts:
            return {"text": None, "ask_back": "", "context": ctx, "info": {**info, "why": "no context"}}
        notes = ("Notes:\n" + "\n".join(f"- {f}" for f in facts)) if facts else "Notes: none"
        if not en:
            notes = ("筆記：\n" + "\n".join(f"- {f}" for f in facts)) if facts else "筆記：沒有"
        prev = ""
        if history:   # "why?" after a guess: the question it follows
            prev = (f"(The child asked before: {_trim_words(history[-1]['q'], 20)})\n" if en else f"（剛才問過：{history[-1]['q']}）\n")
        user = f"{notes}\n{prev}{'Question' if en else '問題'}: {question.strip()}"
        stop = {"ends": ".!?" if en else "。！？", "n": self.guess_sentences}
        raw, why, ms = self._run("guess", lang, [{"role": "user", "content": user}], self.guess_max_new, stop, self.guess_timeout_s)
        info.update(ms=ms, raw=raw, facts=facts)
        if raw is None:
            self.stats["fallback"] += 1
            return {"text": None, "ask_back": "", "context": ctx, "info": {**info, "why": why}}
        allow = _allow_words(question, history) | _allow_words(" ".join(facts), None)
        out, probs = guard.check(raw, lang, "guess", self.p.safety, allow, max_sent=self.guess_sentences, max_words=self.guess_max_words,
                                 max_total=30, max_rare=3)
        if out and en and not guard.on_topic_en(question, out):
            out, probs = None, ["off topic: the guess does not talk about what was asked"]
        if not out:
            self.stats["guard"] += 1
            return {"text": None, "ask_back": "", "context": ctx, "info": {**info, "why": "guard", "problems": probs}}
        self.stats["llm"] += 1
        ask = random.choice(GUESS_ASK_EN if en else GUESS_ASK_ZH)
        return {"text": out, "ask_back": ask, "context": ctx, "info": {**info, "problems": probs}}

    def filler(self, lang: str) -> str:
        return random.choice(FILLER_EN if lang == "en" else FILLER_ZH)

    def status(self) -> dict:
        return {"enabled": self.enabled, "llm_ready": self.llm_ready(), "primed": sorted("/".join(k) for k in self._primed),
                "timeout_s": self.timeout_s, "guess_timeout_s": self.guess_timeout_s, "stats": dict(self.stats)}


def _ugen_down(p) -> str:
    """Why the UGen worker is known to be unusable right now ("" if it is not, or the LLM is not on the worker)."""
    cp = p.composer
    if getattr(cp, "backend", None) != "hailo" or not (p.cfg.get("hailo") or {}).get("worker"):
        return ""
    from .hailo import worker_down
    return worker_down(p.cfg)


def _trim_words(s: str, n: int) -> str:
    w = (s or "").split()
    return " ".join(w[:n]) + ("..." if len(w) > n else "")


def _allow_words(text: str, history) -> frozenset:
    """The child's own words (and the recent turns') are never 'uncommon' in a reply to them."""
    from . import wording
    src = (text or "") + " " + " ".join((h.get("q") or "") + " " + (h.get("a") or "") for h in (history or []))
    out = set()
    for t in wording.words_en(src):
        b = t.lower().replace("’", "'")
        b = b[:-2] if b.endswith("'s") else b
        out.add(b)
        out.add(wording._stem(b))
    return frozenset(out)


def _echoes(reply: str, text: str) -> bool:
    """A reply that only repeats the child's words back (a 1.5B model does that sometimes)."""
    a, b = set(content_en(reply)), set(content_en(text))
    return bool(a) and len(a) <= 3 and a <= b and len(re.findall(r"\?", reply)) == 0
