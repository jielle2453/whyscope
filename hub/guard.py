"""Output guardrails for every LLM text a child hears (chat replies and AI guesses).

check(text, lang, mode, safety, allow) -> (clean text | None, problems)

1. clean: markdown, list markers, emojis, URLs, role prefixes and special tokens removed; one line.
2. complete sentences only (a sentence cut by the token cap is dropped).
3. language: English only in "en" (no CJK, almost all ASCII); Chinese in "zh".
4. hub/safety.py rules on the OUTPUT too (a reply that mentions death, war, ... is never spoken), plus a block list:
   violence / scary, adult, brands, medical / diet advice, personal-information questions, promises, claims to be a person,
   secrets, "as an AI" talk.
5. length: at most `max_sent` sentences of at most `max_words` words, `max_total` words in all.
6. plain words (hub/wording.py rare-word rule, lenient: `max_rare` points per sentence; the child's own words and the
   context words are allowed).
7. shape: an AI guess starts with a hedge ("I think" / "Maybe"); a chat reply ends with a question or an invitation
   (one is appended when missing; the caller passes it).
Anything that fails is replaced by the caller with a canned line; the reason is logged on the event.
"""
import re

from . import wording

_CJK = re.compile(r"[㐀-鿿豈-﫿]")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_MD = re.compile(r"(\*\*|__|`+|^#+\s*|^\s*[-*•]\s+|^\s*\d+[.)]\s+)", re.M)
_ROLE = re.compile(r"^\s*(?:whyscope|assistant|helper|answer|reply|ai)\s*:\s*", re.I)
_TOKENS = re.compile(r"<\|[^|>]*\|>|<\|?im_(?:start|end)\|?>")
_URL = re.compile(r"https?://\S+|www\.\S+")

BLOCK_EN = re.compile(
    r"\b(?:kill\w*|murder\w*|die|dies|died|dying|dead|death|blood\w*|gun\w*|shoot\w*|knife|knives|stab\w*|weapon\w*|bomb\w*|"
    r"war|wars|fight\w*|punch\w*|hit you|hurt you|monster\w*|ghost\w*|demon\w*|devil|zombie\w*|nightmare\w*|scary|terrif\w*|"
    r"horror|creepy|kidnap\w*|stranger\w*|"
    r"sex\w*|naked|nude|kiss\w*|boyfriend|girlfriend|date night|beer|wine|alcohol\w*|drunk|cigarette\w*|smok\w*|drug\w*|vape\w*|"
    r"damn|hell|stupid|idiot|dumb|shut up|hate|"
    r"medicine\w*|pill\w*|dose\w*|vitamin\w*|antibiotic\w*|vaccin\w*|doctor said|diagnos\w*|cure\w*|treatment\w*|"
    r"diet\w*|calorie\w*|lose weight|weight loss|fat people|skinny|"
    r"mcdonald\w*|disney\w*|coca[- ]?cola|pepsi|lego|barbie|pokemon|pokémon|minecraft|roblox|fortnite|youtube|tiktok|"
    r"iphone|ipad|android|google|amazon|netflix|nintendo|playstation|xbox|starbucks|nike|adidas|"
    r"qwen|alibaba|openai|chatgpt|language model|as an ai|i am an ai|i'm an ai|artificial intelligence|"
    r"i promise|promise you|i will always|i'll always|forever|best friend|i love you|"
    r"our secret|keep (?:it |this )?(?:a )?secret|don'?t tell|do not tell|"
    r"i am (?:a )?(?:human|person|real (?:person|boy|girl)|boy|girl|kid|child)|i'm (?:a )?(?:human|person|real (?:person|boy|girl)|boy|girl|kid|child)|"
    r"come with me|meet me|where you live|your address|your phone|phone number|your school|which school|your last name|"
    r"your full name|your password|how old are you|what(?:'s| is) your name|send me|take a picture of)\b", re.I)
BLOCK_ZH = re.compile(r"死|殺|血|槍|刀|打架|戰爭|鬼|怪物|可怕|恐怖|性|裸|親親|男朋友|女朋友|酒|菸|煙|毒|藥|醫生說|減肥|卡路里|"
                      r"麥當勞|迪士尼|可口可樂|樂高|寶可夢|我保證|永遠|最好的朋友|我愛你|秘密|不要告訴|我是人|住在哪|地址|電話|學校叫|密碼|你幾歲|你叫什麼|"
                      r"人工智慧|語言模型")
FLATTER_EN = re.compile(r"\byou(?:'re| are) (?:so |very |really )?(?:smart|clever|brilliant|genius)\b|\b(?:good|great|nice) job\b|\bwell done\b|\bproud of you\b|"
                        r"\b(?:i'?m|i am) (?:a )?(?:toy|human|person|real (?:person|boy|girl|kid))\b|"
                        r"\b(?:i'?m|i am) not (?:a )?(?:robot|computer|machine|helper)\b|\bnot a computer helper\b|"
                        r"\bnot allowed in my house\b|\bmy (?:house|home|mom|dad|family)\b", re.I)
SPECIFIC_EN = re.compile(r"\d|\b(?:hundreds?|thousands?|millions?|billions?|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
                         r"ninety|percent|invented by|was invented in|years ago|century|centuries|kilo\w*|pounds|tons?|miles|"
                         r"meters?|feet|inches|degrees)\b", re.I)
HEDGE_EN = re.compile(r"^(?:i think|maybe|perhaps|i'?m not (?:really |quite )?sure|i am not (?:really |quite )?sure|"
                      r"it (?:might|may|could) be|i guess|probably|i believe|my guess is|hmm)\b", re.I)
HEDGE_ZH = re.compile(r"^(?:我想|我猜|可能|也許|說不定|我不太確定|嗯)")
INVITE_EN = re.compile(r"\?|\b(?:ask me|show me|tell me|let'?s|shall we|want to)\b", re.I)


def clean(text: str) -> str:
    t = _TOKENS.sub(" ", text or "")
    t = _URL.sub("", t)
    t = _EMOJI.sub("", t)
    t = _MD.sub("", t)
    t = t.replace("’", "'").replace("“", "").replace("”", "").replace('"', "")
    t = re.sub(r"\s*\n+\s*", " ", t)
    t = _ROLE.sub("", t.strip())
    t = re.sub(r"\(([^)]*)\)", r"\1", t)            # (asides) -> plain
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"([!?.])\1+", r"\1", t)             # "!!!" -> "!"
    return re.sub(r"\s{2,}", " ", t).strip(" -:;,")


def sentences_en(t: str) -> list:
    return [s.strip() for s in re.findall(r"[^.!?]+[.!?]", t or "") if re.search(r"[A-Za-z]", s)]


def sentences_zh(t: str) -> list:
    return [s.strip() for s in re.findall(r"[^。！？!?]+[。！？!?]", t or "") if s.strip()]


def check(text: str, lang: str, mode: str, safety=None, allow=frozenset(), max_sent=3, max_words=14, max_total=36,
          max_rare=4) -> tuple:
    """(cleaned text or None, problems). mode "chat" | "guess"."""
    en = lang == "en"
    t = clean(text)
    probs = []
    if not t:
        return None, ["empty"]
    if en:
        if _CJK.search(t):
            return None, ["not English (CJK characters)"]
        non_ascii = sum(1 for c in t if ord(c) > 127)
        if non_ascii > 2:
            return None, ["not English (non-ASCII text)"]
    elif not _CJK.search(t) or len(re.findall(r"[A-Za-z]{3,}", t)) > 2:
        return None, ["not Chinese"]
    sents = sentences_en(t) if en else sentences_zh(t)
    if not sents:
        return None, ["no complete sentence"]
    if mode == "guess":   # the question back is added by the caller; a guess that asks its own is cut there
        while len(sents) > 1 and sents[-1].endswith(("?", "？")):
            sents.pop()
        if sents[0].endswith(("?", "？")):
            return None, ["guess is a question"]
    sents = sents[:max_sent]
    words = lambda s: len(wording.words_en(s)) if en else wording.chars_of(s)   # noqa: E731
    long_ = [s for s in sents if words(s) > (max_words if en else 22)]
    if long_:
        # a too-long last sentence is dropped when the rest can stand; otherwise the reply fails
        if long_[0] is sents[-1] and len(sents) > 1 and len(long_) == 1:
            sents = sents[:-1]
        else:
            return None, [f"sentence too long: {long_[0]}"]
    while len(sents) > 1 and sum(words(s) for s in sents) > (max_total if en else 60):
        sents = sents[:-1]
    out = " ".join(sents) if en else "".join(sents)
    if (BLOCK_EN if en else BLOCK_ZH).search(out):
        return None, ["blocked word: " + (BLOCK_EN if en else BLOCK_ZH).search(out).group(0)]
    if en and FLATTER_EN.search(out):
        return None, ["flattery"]
    if safety is not None:
        hit = safety.check(out, lang)
        if hit:
            return None, ["sensitive output: " + hit["category"]]
    if mode == "guess" and en:
        # a guess may explain a "why", never state a specific fact a 1.5B model makes up: numbers, years, names, places
        if SPECIFIC_EN.search(out):
            return None, ["specific fact in a guess: " + SPECIFIC_EN.search(out).group(0)]
        for s in sents:
            for m in re.finditer(r"(?<!^)(?<![.!?] )\b([A-Z][a-z]+)\b", s):
                w = m.group(1).lower()
                if w not in allow and w not in ("i", "earth", "mom", "dad", "mommy", "daddy", "whyscope") and m.start() > 0:
                    return None, ["name in a guess: " + m.group(1)]
    if en:
        for s in sents:
            if wording.rare_score_en(s, allow) > max_rare:
                probs.append(f"uncommon words: {wording.rare_words_en(s, allow)}")
        if probs:
            return None, probs
        if wording.has_banned_en(out):
            out = wording.plainify_en(out)
    if mode == "guess":
        if not (HEDGE_EN if en else HEDGE_ZH).search(out):
            if en:
                first = out[:1].lower() + out[1:] if not re.match(r"^I\b", out) else out
                out = "I think " + first
            else:
                out = "我想，" + out
    return out, probs


def ends_with_question(text: str, lang: str = "en") -> bool:
    last = (sentences_en(text) or [text])[-1] if lang == "en" else text
    return bool(INVITE_EN.search(last)) if lang == "en" else text.rstrip().endswith(("？", "?"))


def on_topic_en(question: str, text: str) -> bool:
    """A guess must talk about what was asked: the question's last content word ("Why does a kettle WHISTLE?") or at least
    two thirds of its content words appear in the guess. In the held-out runs this caught 8 of 18 guesses with a false
    statement ("butter gets hard when it's warm") and none of the right ones (eval/chat_report.md)."""
    from .recall import content_en
    st = lambda w: wording._stem(w.lower())   # noqa: E731
    qc = [st(w) for w in content_en(question)]
    if not qc:
        return True
    gc = {st(w) for w in content_en(text)}
    hit = sum(1 for w in qc if w in gc)
    return qc[-1] in gc or hit >= max(2, round(len(qc) * 2 / 3))
