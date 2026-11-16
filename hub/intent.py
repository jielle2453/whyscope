"""Intent routing for what a child says (cheap rules, no model): is it a question for the knowledge base, a rule question,
something to show the camera, a follow-up, or chit-chat?

    classify(text, lang, has_image=False, recent=False) -> Intent(kind, sub, question, deictic, pure_deictic)

kind
  question   a real question about the world ("Why do zebras have stripes?", "How do bees make honey?"):
             knowledge base -> family answer -> principle -> AI guess (if on) -> abstain
  rule       a why-question about a rule at home ("Why do I have to go to bed at 10?"): knowledge base first (a sleep
             entry is a good answer), else a chat reply that points to the grown-ups' reasons
  deictic    "What is this?", "Can you see this?", "Do you know what this is?": the camera decides; without a confident
             label the reply is a chat line ("I see something! What is it called?")
  followup   "Why?", "Tell me more", "What else?" right after an answer (only when there is a recent turn)
  chat       everything else: greetings, thanks, teasing, feelings, jokes, commands, statements, questions about Whyscope
             itself ("Are you a robot?", "When can you steal it?"), gibberish (sub "unclear")

Safety runs BEFORE this (hub/safety.py) and is never bypassed: a sensitive text never reaches chat or an AI guess.
"""
import re
from dataclasses import dataclass

from .recall import content_en, normalize_en

_LEAD_EN = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|so|um+|uh+|and|but|well|please|whyscope|why scope|mister|miss)[\s,!.]+)*"
    r"(?:(?:do|did) you know|can you tell me|could you tell me|tell me|i want to know|i wanna know|i wonder|"
    r"i was wondering|guess|do you think|can you explain|explain)?\s*", re.I)
_WH = r"(?:why|how|what|where|when|who|whom|whose|which)"
_AUX = r"(?:do|does|did|is|are|was|were|can|could|will|would|should|shall|has|have|had|am|may|might|must)"
_PRON = {"it", "we", "i", "you", "my", "your", "this", "that", "these", "those", "he", "she", "they", "him", "her",
         "them", "us", "me", "there", "here", "our", "u", "ya"}
_DEICTIC = re.compile(
    r"\b(?:what(?:'s| is| s)? (?:this|that|it|these|those)(?: is)?|what am i (?:holding|showing)|"
    r"(?:can|do|did) you see (?:this|that|it|me|what)|look at (?:this|that|it|me)|see this|"
    r"(?:do you )?know what (?:this|that|it) is|guess what (?:this|that|it) is|what do you see|"
    r"what is (?:in|on) my hand|what(?:'s| is) (?:in|on) (?:my|the) (?:hand|picture|camera))\b", re.I)
_DREF = re.compile(r"\b(?:this|that|it|these|those|here)\b", re.I)
_FOLLOW = re.compile(
    r"^(?:but |and |so |ok |okay )?(?:why(?: not| is that| so)?|how(?: come)?|really|what else|tell me more(?: about (?:it|that|this))?|"
    r"more|and then|then what|what(?:'s| is) (?:it|that)|what do you mean|like what|are you sure|why is it|how do you know|"
    r"is that true|for real|what happens next|and why)\W*$", re.I)
_GREET = re.compile(r"^(?:hi+|hello+|hey+|hiya|yo|good (?:morning|afternoon|evening|night)|howdy)\b(?:\s+(?:there|whyscope|friend))?\W*$", re.I)
_THANKS = re.compile(r"\b(?:thank(?:s| you)|thx)\b", re.I)
_BYE = re.compile(r"^(?:bye+|goodbye|see you|see ya|good night|night night|i have to go|i'm done)\b", re.I)
_TEASE = re.compile(
    r"\b(?:you (?:don'?t|do not) know (?:anything|nothing|much)|you know nothing|you(?:'re| are) (?:so |very |really |such a )?(?:dumb|stupid|silly|wrong|"
    r"boring|bad|not smart|useless|a baby|weird)|you can'?t do anything|you(?:'re| are) no help|i hate you|you suck|"
    r"dumb (?:robot|computer|machine)|stupid (?:robot|computer|machine)|you never know)\b", re.I)
_FEEL = re.compile(
    r"\b(?:i(?:'m| am)|i feel|im|i'm feeling|i am feeling)\s+(?:so |very |really |a little |kind of |a bit )?"
    r"(?P<f>sad|unhappy|scared|afraid|frightened|lonely|angry|mad|upset|bored|happy|glad|excited|tired|sleepy|grumpy|worried|"
    r"nervous|shy|sick|hungry|cold|hot|silly)\b", re.I)
_SILLY = re.compile(r"\b(?:fart\w*|poo+p?\w*|burp\w*|booger\w*|pee+|toot\w*|butt|stinky|smelly)\b", re.I)
_JOKE = re.compile(r"\b(?:joke|riddle|funny story|make me laugh)\b", re.I)
_COMMAND = re.compile(
    r"^(?:please\s+)?(?:sing|dance|play|count|say|read|draw|stop|wait|shut up|be quiet|go away|come|let'?s|listen|"
    r"turn|open|close|call|repeat|do a|make a|show me|give me|help me)\b", re.I)
_ABOUT_ME = re.compile(
    r"\b(?:are you (?:a |an )?(?:robot|real|human|person|alive|computer|boy|girl|ai|machine|friend|smart|there|happy|sad)|"
    r"what(?:'s| is) your name|who are you|what are you|how old are you|where do you live|where are you|do you (?:like|love|have|eat|sleep|"
    r"dream|know|want)|can you (?:see|hear|sing|dance|fly|walk|eat|talk|play)|what can you do|do you know anything)\b", re.I)
# a home rule: an obligation ("have to", "can't") about an everyday home thing; "Why can't we breathe in space?" or "Why do we
# have to pay in a shop?" are real questions, not rules
_HOME = (r"(?:go to bed|bed|bedtime|sleep|nap|bath|shower|brush|wash|eat|vegetables|veggies|broccoli|dinner|lunch|breakfast|clean|"
         r"tidy|share|homework|school|tv|screen|tablet|ipad|phone|game|games|candy|sweets|dessert|ice cream|stay up|stay|sit|wait|"
         r"wear|go out|play|say sorry|say please|be quiet|be nice|listen|hold hands|seat ?belt|helmet|shoes|coat|jacket|toys?)")
_OBLIG = r"(?:have to|has to|need to|needs to|must|should|can'?t|cannot|can not|not allowed|don'?t get to|do not get to)"
_RULE = re.compile(
    r"\bwhy\b.*\b(?:i|me|we|kids|children)\b.*\b" + _OBLIG + r"\b.*\b" + _HOME + r"\b|"
    r"\bwhy\b.*\b" + _OBLIG + r" (?:i|we)\b.*\b" + _HOME + r"\b|"
    r"\bwhy\b.*\bmy (?:mom|dad|mommy|daddy|parents?|grown-?ups?)\b.*\b(?:make me|makes me|won'?t let me|doesn'?t let me|don'?t let me|say|says)\b", re.I)
_STATEMENT_ME = re.compile(r"^(?:i(?:'m| am| will| want| like| love| have| had| saw| did| got| can| made| went)?|my|we|look|guess|it(?:'s| is)?)\b", re.I)


def _known_any(toks) -> bool:
    from . import wording
    cw = wording.common_words_en()
    if not cw:
        return True
    return any(t in cw or t.rstrip("s") in cw for t in toks)


@dataclass
class Intent:
    kind: str                # question | rule | deictic | followup | chat
    sub: str = ""            # chat flavour: greeting, thanks, bye, tease, feeling_sad, feeling_scared, feeling_ok, silly, joke,
                             # command, about_me, statement, unclear, rule, camera
    question: str = ""       # the text without lead-ins ("Do you know why ..." -> "why ...")
    deictic: bool = False    # refers to "this / that / it" (the camera may help)
    pure_deictic: bool = False   # nothing but "what is this?": no other content words


def strip_lead_en(text: str) -> str:
    t = (text or "").strip().replace("’", "'")
    t2 = _LEAD_EN.sub("", t, count=1).strip(" ,")
    return t2 if len(t2) >= 3 else t


def feeling(text: str):
    m = _FEEL.search(text or "")
    if not m:
        return None
    f = m.group("f").lower()
    if f in ("sad", "unhappy", "lonely", "upset", "worried", "nervous", "grumpy", "angry", "mad"):
        return "feeling_sad"
    if f in ("scared", "afraid", "frightened"):
        return "feeling_scared"
    return "feeling_ok"


def _is_question_en(t: str) -> bool:
    tl = t.lower()
    return bool(re.match(rf"^\s*(?:{_WH}|{_AUX}|how come)\b", tl) or re.search(r"\bwhy\b|\bhow come\b", tl)
                or tl.rstrip().endswith("?"))


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _aux_subject_pronoun(t: str) -> bool:
    """'Is it raining?', 'Are we there?', 'Can you sing?': a yes/no question about the here and now, not about the world."""
    m = re.match(rf"^\s*{_AUX}\s+(?:n't\s+)?(\w+)", t.lower())
    return bool(m and m.group(1) in _PRON)


def _you_subject(t: str) -> bool:
    """'When can you steal it?', 'Why are you so slow?': the question is about Whyscope, not about the world."""
    return bool(re.search(rf"^\s*(?:{_WH}\s+)?{_AUX}\s+(?:n't\s+)?you\b|^\s*{_WH}\s+(?:do|did|can|will|would)\s+you\b", t.lower()))


def classify(text: str, lang: str = "en", has_image: bool = False, recent: bool = False) -> Intent:
    if lang != "en":
        return _classify_zh(text, has_image, recent)
    raw = (text or "").strip()
    t = strip_lead_en(raw)
    n = normalize_en(t)
    cw = content_en(t)
    toks = n.split()
    deictic = bool(_DEICTIC.search(raw)) or (has_image and bool(_DREF.search(raw)))
    # content words beyond "this / see / know / what": "Can you see this? It is a fart." is not pure deixis
    rest = [w for w in content_en(_DEICTIC.sub(" ", raw)) if w not in ("know", "guess", "see", "look", "thing", "call", "name")]
    pure = bool(_DEICTIC.search(raw)) and not rest

    if recent and _FOLLOW.match(n + ("?" if not n.endswith("?") else "")) and len(toks) <= 5:
        return Intent("followup", "", t, deictic, False)
    if not toks or len(re.sub(r"[^a-z]", "", n)) < 2:
        return Intent("chat", "unclear", t)
    if _GREET.match(normalize_en(raw)) or _GREET.match(n):
        return Intent("chat", "greeting", t)
    if _BYE.match(n):
        return Intent("chat", "bye", t)
    if _THANKS.search(n) and len(toks) <= 6 and not re.match(r"(?:why|how|what|when|where|who|do|does|should)\b", n):
        return Intent("chat", "thanks", t)
    if _TEASE.search(raw):
        return Intent("chat", "tease", t)
    f = feeling(raw)
    if f and not re.search(r"\bwhy\b", n):
        return Intent("chat", f, t)
    if deictic and (pure or not _is_question_en(t) or _DEICTIC.search(raw)):
        if pure:
            return Intent("deictic", "camera", t, True, True)
        if _SILLY.search(raw) or not any(_is_question_en(s) and not _DEICTIC.search(s) for s in _sentences(raw)):
            return Intent("deictic", "silly" if _SILLY.search(raw) else "camera", t, True, False)
    if _RULE.search(n):
        return Intent("rule", "rule", t, deictic)
    if _JOKE.search(n):
        return Intent("chat", "joke", t)
    qs = [s for s in _sentences(t) if _is_question_en(s)] or ([t] if _is_question_en(t) else [])
    if qs:
        q = max(qs, key=lambda s: len(content_en(s)))   # "Why my hair is black? I want ..." -> the why-sentence
        if _you_subject(q) or _ABOUT_ME.search(q):
            return Intent("chat", "about_me", t, deictic)
        if _aux_subject_pronoun(q) and not re.search(r"\bwhy\b|\bhow\b", q.lower()):
            return Intent("chat", "statement", t, deictic)
        if not content_en(q):
            return Intent("deictic" if deictic else "chat", "camera" if deictic else "unclear", t, deictic, deictic)
        return Intent("question", "", t, deictic or bool(_DREF.search(q)))
    if _ABOUT_ME.search(raw):
        return Intent("chat", "about_me", t)
    if _SILLY.search(raw):
        return Intent("chat", "silly", t, deictic)
    if _COMMAND.search(n):
        return Intent("chat", "command", t)
    if len(toks) <= 4 and len(set(toks)) <= 2 and not cw:
        return Intent("chat", "unclear", t)
    if len(set(re.sub(r"[^a-z]", "", n))) <= 3:
        return Intent("chat", "unclear", t)   # "la la la", "hmm hmm"
    if not _known_any(toks):
        return Intent("chat", "unclear", t)   # "asdf", a garbled recording
    return Intent("chat", "statement", t, deictic)


# ---------------------------------------------------------------- Chinese (secondary): a smaller rule set
_ZH_Q = re.compile(r"為什麼|為甚麼|為何|怎麼|怎樣|如何|什麼|哪裡|哪裏|誰|幾|多少|多[久遠重快高大長]|哪[一些個國種]|會不會|是不是|有沒有|能不能|可不可以|嗎|呢|？|\?")
_ZH_DEICTIC = re.compile(r"這是什麼|那是什麼|這個是什麼|你看得到|你看這個|你看|猜猜這是|你知道這是")
_ZH_GREET = re.compile(r"^(?:你好|哈囉|嗨|早安|午安|晚安|hi|hello)\W*$", re.I)
_ZH_TEASE = re.compile(r"你什麼都不知道|你好笨|你很笨|你笨蛋|你都不知道|我討厭你|你好爛")
_ZH_FEEL = re.compile(r"我(?:好|很|有點)?(?:難過|傷心|害怕|怕|生氣|無聊|開心|高興|累|想睡)")
_ZH_RULE = re.compile(r"為什麼.*(?:我|我們|小孩).*(?:要|一定要|不能|不可以|得).*(?:睡覺|上床|洗澡|刷牙|吃|寫功課|上學|收|分享|看電視|玩)")
_ZH_FOLLOW = re.compile(r"^(?:為什麼|為什麼呢|然後呢|還有呢|真的嗎|再說一點|再多說一點|怎麼會|那是什麼)\W*$")
_ZH_ABOUT = re.compile(r"你是(?:機器人|人|真的)|你叫什麼|你幾歲|你住在|你會(?:唱歌|跳舞)|你看得到")


def _classify_zh(text, has_image, recent):
    t = (text or "").strip()
    if recent and _ZH_FOLLOW.match(t):
        return Intent("followup", "", t)
    if len(re.sub(r"\W", "", t)) < 2:
        return Intent("chat", "unclear", t)
    if _ZH_GREET.match(t):
        return Intent("chat", "greeting", t)
    if _ZH_TEASE.search(t):
        return Intent("chat", "tease", t)
    if _ZH_FEEL.search(t) and "為什麼" not in t:
        return Intent("chat", "feeling_sad" if re.search(r"難過|傷心|生氣", t) else "feeling_scared" if "怕" in t else "feeling_ok", t)
    if _ZH_DEICTIC.search(t):
        return Intent("deictic", "camera", t, True, len(re.sub(r"\W", "", _ZH_DEICTIC.sub("", t))) <= 1)
    if _ZH_RULE.search(t):
        return Intent("rule", "rule", t)
    if _ZH_ABOUT.search(t):
        return Intent("chat", "about_me", t)
    if _ZH_Q.search(t):
        return Intent("question", "", t, bool(re.search(r"這|那|它", t)))
    return Intent("chat", "statement", t)
