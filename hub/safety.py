"""Sensitive-topic rules: keyword -> category -> deflection + parent cheat-sheet event.

Loads knowledge/sensitive_rules.json and the triggers of knowledge/cheats/*.json once at startup.
Accepted rules shapes: {"categories": {cat: {"triggers": [...], "category_zh": ...}}},
{cat: [words]} or [{"id"|"category": cat, "keywords"|"triggers": [...]}].
"""
import json
import re
from pathlib import Path

from .config import ROOT, to_trad

DEFAULT_DEFLECTION_EN = "That is a big question. Let's ask a grown-up together."
_CJK = re.compile(r"[\u4e00-\u9fff]")
DEFAULT_DEFLECTION = "這個問題很重要，我們一起去問爸爸媽媽好嗎？"
# Safety floor that is always on, even if the rules file is missing or thin (err on the side of the parent).
BASELINE = {"death": ["死"], "self_harm": ["自殺", "想死", "不想活"]}
PRIORITY = ["self_harm", "death", "violence_war", "birth_sex"]  # tie-break only
_STRIP = re.compile(r"[\s，。！？、,.!?~～「」『』（）()]+")

# An ask-back may never probe the child's day, feelings, family or friends (product pass 1, A.1).
# Science questions about natural events ("Why do earthquakes happen?") are not scary news. A category may list
# `science_words` / `science_words_en` in the rules file: when a hit comes ONLY from such words and the question is a
# plain "why / how / what" question with no fear, news, danger, death or personal cue, it is not sensitive.
# "Will an earthquake kill us?", "Is the earthquake dangerous?", "the news said ..." still go to a parent.
# The same holds for body science ("Why is blood red?": `science_words_en` of violence_war). Injuries, fights, war, illness and
# anything personal ("Why does my knee bleed?", "Why do people fight with blood?", "I cut myself, there is blood") still go to a parent.
_SCI_FORM_EN = re.compile(r"^\s*(?:why|how|what|where)\b", re.I)
_SCI_CUE_EN = re.compile(
    r"\b(?:kill\w*|die[ds]?|dying|dead|death|deaths|hurt\w*|injur\w*|scar(?:y|ed|es|ing)|afraid|fear\w*|frighten\w*|"
    r"danger\w*|news|tv|will|would|gonna|going|worr\w*|destroy\w*|collaps\w*|crush\w*|trap\w*|victims?|surviv\w*|"
    r"safe\w*|hide|escape|bad|us|me|my|our|i|tonight|tomorrow|today|here|"
    r"fight\w*|war|wars|gun\w*|shoot\w*|shot|bomb\w*|knife|knives|soldiers?|police|bleed\w*|wound\w*|cuts?|punch\w*|"
    r"sick|ill|illness|pain\w*|ouch|stab\w*|attack\w*|murder\w*|weapons?)\b", re.I)
_SCI_FORM_ZH = re.compile(r"為什麼|為甚麼|為何|怎麼會|是什麼|什麼是|什麼叫|怎樣")
_SCI_CUE_ZH = re.compile(r"死|怕|危險|受傷|新聞|電視|會不會|可怕|逃|躲|倒|壓|傷|救|災|我")

ASKBACK_BLOCK = re.compile(r"今天|開心|難過|傷心|生氣|害怕|爸爸媽媽有沒有|朋友|同學|學校|老師|你的家人|你家人|你喜歡|你愛")


def askback_ok(q: str) -> bool:
    """False if an ask-back question touches blocked personal topics."""
    return not ASKBACK_BLOCK.search(q or "")


# --- spelling / near-homophone tolerance (English; questions arrive as speech-recognition text from young children) ---
# Normalisation applied to BOTH the trigger phrases and the child's text, so a trigger written one way still matches:
# contractions with or without the apostrophe ("don't" / "dont" -> "do not"), "wanna" -> "want to", possessives
# ("baby's" -> "babys", which the inflection rule matches to "babies") and a split "my self" -> "myself".
_CONTRACT_EN = [(r"\b(?:won'?t)\b", "will not"), (r"\b(?:can'?t|cannot)\b", "can not"), (r"\bain'?t\b", "is not"),
                (r"\b(do|does|did|is|are|was|were|could|would|should|have|has|had|must|need)n'?t\b", r"\1 not"),
                (r"\bi'?m\b", "i am"), (r"\bi'?ve\b", "i have"), (r"\b(you|they|we)'re\b", r"\1 are"),
                (r"\b(youre|theyre)\b", lambda m: m.group(1)[:-2] + " are"),
                (r"\bwanna\b", "want to"), (r"\bgonna\b", "going to"), (r"\bgotta\b", "got to"),
                (r"'s\b", "s"), (r"'", "")]
# "my self" -> "myself", but not "my self portrait" / "self care" / "self esteem" ...
_MYSELF_EN = re.compile(r"\b(?:my|mi|me) ?(?:self|sef|slef)\b(?!-? ?(?:portrait|esteem|care|control|confidence|respect|"
                        r"conscious|service|driving|checkout|timer))")
# Explicit spelling / ASR variants of trigger words (each variant also gets the plain inflections). A trigger word
# (or its stem) listed here matches any of its variants, so every phrase and keyword using it is covered.
SPELL_EN = {
    "kill": ["kil", "kll"], "myself": ["myslef", "mysef", "meself"],
    "grandpa": ["grampa", "granpa", "grand pa", "gramps", "grandad", "granddad", "grandaddy"],
    "grandma": ["gramma", "granma", "grand ma", "grandmom", "grandmum", "grammy"],
    "pregnant": ["pregnet", "pregnint", "pregnat", "pregant", "pragnant", "prenant", "pregnent"],
    "pregnancy": ["pregnency", "pregnansy"], "hospital": ["hospitle", "hospitol", "hospidal", "hopsital", "hostipal"],
    "cancer": ["canser", "cancor", "kancer"], "funeral": ["funral", "funerel", "fueneral"],
    "cemetery": ["cemetary", "semetery", "cematery"], "divorce": ["devorce", "divorse", "divource", "deforce"],
    "divorced": ["devorced", "divorsed"], "homeless": ["home less", "homeles"], "church": ["chirch", "chruch", "cherch"],
    "bully": ["bulley", "bulli"], "bullied": ["bullyed"], "bullying": ["bulling", "bullieing"],
    "soldier": ["solder", "soljer", "solger"], "soldiers": ["solders", "soljers"], "death": ["deth"],
    "heaven": ["heven", "hevan"], "murder": ["murdur", "merder"], "weapon": ["wepon", "weppon"],
    "scary": ["scarey", "skary"], "mommy": ["mommie", "mummy"],
}


def _norm_en(s: str) -> str:
    t = re.sub(r"\s+", " ", (s or "").replace("\u2019", "'").replace("\u2018", "'").lower()).strip()
    for a, b in _CONTRACT_EN:
        t = re.sub(a, b, t)
    return _MYSELF_EN.sub("myself", t)


def _word_rx(w: str) -> str:
    """One trigger word, tolerant of plain inflections: 'fighting' also matches 'fight', 'fights', 'fighting'
    (generic stemming, so a trigger written in one form still catches the child's form), and of the explicit
    spelling / ASR variants in SPELL_EN ('kill' also matches 'kil', 'grandpa' also 'grampa')."""
    from .recall import stem_en
    base = stem_en(w)
    if base == w and w.endswith("ing") and len(w) > 5:
        base = w[:-3]
    alts = [re.escape(w), re.escape(base) + r"(?:s|es|ed|d|ing)?"]
    for v in dict.fromkeys(SPELL_EN.get(w, []) + SPELL_EN.get(base, [])):
        alts.append(r"\s+".join(re.escape(x) for x in v.split()) + r"(?:s|es|ed|d|ing)?")
    return "(?:" + "|".join(alts) + ")"


# Context words for the near-homophone rules below: a person, the child, a pet.
_PERSON_EN = (r"i|me|my|myself|we|us|our|you|your|he|him|his|she|her|they|them|their|people|person|someone|somebody|"
              r"everyone|everybody|anyone|kids?|child|children|boys?|girls?|man|men|woman|women|family|friends?|"
              r"mom|moms|mommy|mommies|momma|mum|mums|mummy|mama|mamma|dad|dads|daddy|daddies|papa|nana|nanna|granny|grannie|grand(?:pa|ma|dad|mom|mum|father|mother|parents?)s?|"
              r"gran(?:pa|ma|dad|ny|nie)s?|gram(?:pa|ma|my|ps)|grand pa|grand ma|brothers?|sisters?|uncles?|aunt\w*|"
              r"bab(?:y|ies)|cousins?|teachers?")
_PET_EN = r"pets?|dogs?|doggy|cats?|kitty|puppy|puppies|kittens?|hamsters?|goldfish|fish|rabbits?|bunny|bunnies|birds?|parrot|turtles?|guinea pigs?|horses?|pony"
_PERSON_RX = re.compile(r"\b(?:" + _PERSON_EN + r")\b")
# "dye" heard for "die": only with a person, a pet or a death cue, and no dyeing object ("dye their hair", "dye eggs").
_DYE_FORM = re.compile(r"\b(dye|dyes|dyed|dyeing)\b")
_DYE_CTX = re.compile(r"\b(?:" + _PERSON_EN + "|" + _PET_EN + r"|hurt\w*|sad|forever|heaven|old|sick|again|come back|away|"
                      r"when|after|everyone|everybody)\b")
_DYE_OBJ = re.compile(r"\b(?:hair|clothes|clothing|eggs?|easter|shirts?|t ?shirts?|tshirts?|fabric|cloth|wool|yarn|socks?|"
                      r"jeans|dress(?:es)?|beard|fur|feathers?|paper|tie|food|colou?rs?|colou?red|colou?ring|paint\w*|ink|"
                      r"wood|leather|cotton|silk|string|icing|frosting|cake|cookies?|rice|pasta|play ?dough|slime|candles?|"
                      r"things|stuff|skirt|pants|hat|scarf|towels?|sheets?|blanket|shoes?|tips|streaks?|highlights?|lipstick|nails?)\b")
_DYE_NOUN = re.compile(r"\b(?:the|a|some|food|tie|hair|natural|of|with|this|that|any|blue|red|green|yellow|pink|purple)\s+dye\b|"
                       r"\bdye(?:s|d)?\s+(?:it|them|this|that|these|those|red|blue|green|yellow|pink|purple|orange|brown|black|"
                       r"white|gold|silver|rainbow|is|are|was|made|comes?|from|stain\w*)\b")
_DYE_TO_DIE = {"dye": "die", "dyes": "dies", "dyed": "died", "dyeing": "dying"}
_NUM_EN = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|fifty|hundred|thousand|many|few|of|some)"
# Narrow, context-bound rewrites for near-homophones the evaluation found (finetune_v1 pipeline_eval PHON list + ASR).
_REWRITES_EN = [
    # "kms" (kill myself), but not "10 kms" / "ten kms" / "how many kms"
    (re.compile(r"(?:\b(\S+)\s+)?\bkms\b"),
     lambda m: m.group(0) if m.group(1) and re.fullmatch(_NUM_EN, m.group(1)) else (m.group(1) + " " if m.group(1) else "") + "kill myself"),
    (re.compile(r"\b(i|i really|i just|i sometimes) which\b"), r"\1 wish"),   # "i which i was dead"
    (re.compile(r"\b(is|are|was|were) ((?:my|the|our|your|his|her|their) )?(" + _PET_EN + r") dad\b(?=\s*(?:$|[?.!,]|now|yet|forever|too))"),
     r"\1 \2\3 dead"),                                                         # "is my cat dad"
    (re.compile(r"\b(" + _PET_EN + r") (is|was) dad\b(?=\s*(?:$|[?.!,]|now|yet|forever|too))"), r"\1 \2 dead"),
    (re.compile(r"\bbell(?:y|ies|ied|ying) (me|us|him|her|them)\b"), r"bully \1"),   # "why do kids belly me"
    (re.compile(r"\b(was|were|being|get|gets|got|getting|be) bellied\b"), r"\1 bullied"),
    (re.compile(r"\b(laugh\w*) add (me|us)\b"), r"\1 at \2"),                  # "kids laugh add me"
    (re.compile(r"\b(was|is|are|were|being|be|so|very|really) mine to (me|us)\b"), r"\1 mean to \2"),
    (re.compile(r"\b(we|i|people|they|you|grown ups|grownups|families) prey\b"), r"\1 pray"),
    (re.compile(r"\b(are|is|am|were|was) (we|i|they|you|he|she|people|some people|my family|our family) "
                r"((?:so |very |really |too )?)pour\b"), r"\1 \2 \3poor"),
    (re.compile(r"\b(we|i|they|people|family) (are|is|am|were|was) ((?:so |very |really |too )?)pour\b"), r"\1 \2 \3poor"),
    (re.compile(r"\ba wore\b(?! (?:out|off|down|it|them|a|the|his|her|my))"), "a war"),
    (re.compile(r"\b(is|does|did) got (real|exist\w*|see\w*|love\w*|watch\w*|hear\w*|live\w*)\b"), r"\1 god \2"),
]
# Edit distance 1 (one letter added, dropped, changed or swapped) for these long keywords only, and only when the
# question names a person or the child: "solders" -> "soldiers", "divorse" -> "divorce", "funral" -> "funeral".
FUZZY_EN = ("pregnant", "pregnancy", "funeral", "funerals", "cemetery", "hospital", "divorce", "divorced", "homeless",
            "bullied", "bullying", "soldier", "soldiers", "kidnapped", "terrorist", "religion", "weapons", "stepmom",
            "stepdad", "custody", "murdered", "suicide")
FUZZY_MIN_KEY, FUZZY_MIN_TOKEN = 7, 6


def _dist1(a: str, b: str) -> bool:
    """True if a and b differ by exactly one insertion, deletion, substitution or adjacent swap."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, l = (a, b) if len(a) < len(b) else (b, a)
    i = next((k for k in range(len(s)) if s[k] != l[k]), len(s))
    return s[i:] == l[i + 1:]


def asr_alt_en(text: str) -> str:
    """The question with near-homophones read back to the sensitive word they most likely stand for, in context
    ("why did grampa dye" -> "why did grampa die", "i want to dye" -> "i want to die", "kids belly me" -> "kids bully me").
    Returns the normalised text unchanged when nothing applies. Used by Safety.check as a second pass."""
    t = _norm_en(text)
    if _DYE_FORM.search(t) and _DYE_CTX.search(t) and not _DYE_OBJ.search(t) and not _DYE_NOUN.search(t):
        t = _DYE_FORM.sub(lambda m: _DYE_TO_DIE[m.group(1)], t)
    for rx, rep in _REWRITES_EN:
        t = rx.sub(rep, t)
    if _PERSON_RX.search(t):
        def fz(m):
            w = m.group(0)
            if len(w) < FUZZY_MIN_TOKEN or w in FUZZY_EN:
                return w
            return next((k for k in FUZZY_EN if len(k) >= FUZZY_MIN_KEY and _dist1(w, k)), w)
        t = re.sub(r"[a-z]+", fz, t)
    return t


def _en_regex(phrase: str):
    """Case-insensitive, word-boundary regex built generically from one English trigger phrase."""
    words = [_word_rx(w) for w in _norm_en(phrase).split(" ") if w]
    if not words:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(words) + r"(?![a-z0-9])", re.I)


def _norm(s: str) -> str:
    return _STRIP.sub("", to_trad(s or "")).lower()


class Safety:
    def __init__(self, cfg: dict):
        s = cfg.get("safety", {})
        self.rules_file = self._p(s.get("rules_file", "knowledge/sensitive_rules.json"))
        self.cheats_dir = self._p(s.get("cheats_dir", "knowledge/cheats"))
        self.reload()

    @staticmethod
    def _p(x):
        p = Path(x)
        return p if p.is_absolute() else ROOT / p

    def reload(self):
        self.triggers = {}   # category -> set(normalised words)
        self.triggers_en = {}  # category -> set(normalised English phrases)
        self.zh = {}         # category -> category_zh
        self.cheats = {}     # category -> cheat dict
        self.urgent = set()  # categories flagged urgent in the rules file
        self.science = {}    # category -> set(normalised science words, zh and en): hits from these alone may be exempt
        self.keywords_en = {}  # category -> set(single English keywords; their inflections match too)
        self.exempt_en = {}    # category -> harmless subjects that exempt a keyword-only hit (see _exempt_en)
        for cat, words in BASELINE.items():
            self._add(cat, words)
        self._load_rules()
        self._load_cheats()
        flat = [(len(w), w, c) for c, ws in self.triggers.items() for w in ws if w]
        self._flat = sorted(flat, key=lambda t: -t[0])
        en = sorted(((len(w), _en_regex(w), c, w) for c, ws in self.triggers_en.items() for w in ws if w),
                    key=lambda t: -t[0])
        self._flat_en = [t for t in en if t[1]]

    def _add(self, cat, words, zh=None):
        self.triggers.setdefault(cat, set()).update(_norm(w) for w in words if w)
        if zh:
            self.zh[cat] = zh

    def _add_en(self, cat, words):
        self.triggers_en.setdefault(cat, set()).update(_norm_en(w) for w in words if w)

    def _add_keywords(self, cat, v):
        kws = [_norm_en(w) for w in (v.get("keywords_en") or []) if w]
        if kws:
            self._add_en(cat, kws)
            self.keywords_en.setdefault(cat, set()).update(kws)
        ex = [_norm_en(w) for w in (v.get("exempt_en") or []) if w]
        if ex:
            self.exempt_en.setdefault(cat, set()).update(ex)

    def _add_science(self, cat, v):
        words = [_norm(w) for w in (v.get("science_words") or [])] + [_norm_en(w) for w in (v.get("science_words_en") or [])]
        if words:
            self.science.setdefault(cat, set()).update(words)

    def _load_rules(self):
        try:
            data = json.loads(self.rules_file.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, dict) and isinstance(data.get("categories"), (dict, list)):
            data = data["categories"]
        if isinstance(data, dict):
            for cat, v in data.items():
                if cat.startswith("_"):
                    continue
                if isinstance(v, list):
                    self._add(cat, v)
                elif isinstance(v, dict):
                    self._add(cat, v.get("triggers") or v.get("keywords") or [], v.get("category_zh"))
                    self._add_en(cat, v.get("triggers_en") or [])
                    self._add_science(cat, v)
                    self._add_keywords(cat, v)
        elif isinstance(data, list):
            for v in data:
                cat = v.get("category") or v.get("id")
                if cat:
                    self._add(cat, v.get("triggers") or v.get("keywords") or [], v.get("category_zh"))
                    self._add_en(cat, v.get("triggers_en") or [])
                    self._add_science(cat, v)
                    self._add_keywords(cat, v)
                    if v.get("urgent"):
                        self.urgent.add(cat)

    def _load_cheats(self):
        if not self.cheats_dir.is_dir():
            return
        for f in sorted(self.cheats_dir.glob("*.json")):
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            cat = c.get("category") or c.get("id")
            if not cat:
                continue
            self.cheats[cat] = c
            self._add(cat, c.get("triggers", []), c.get("category_zh"))
            self._add_en(cat, (c.get("en") or {}).get("triggers", []))

    def check(self, text: str, lang: str = "zh"):
        """Return the sensitive category hit (with deflection text in `lang`) or None.
        zh: Chinese triggers. en: English triggers (case-insensitive, word boundary); Chinese triggers are also
        tried when an English-mode text contains Chinese characters. English gets a second pass on asr_alt_en(text)
        (near-homophones in context: "why did grampa dye" -> "... die") when the text itself has no hit."""
        hit = self._check(text, lang)
        if lang != "en" or (hit and hit["category"] == "self_harm"):
            return hit
        alt = asr_alt_en(text)
        if alt == _norm_en(text):
            return hit
        hit2 = self._check(alt, lang)
        # the read-back may reveal self-harm behind a plainer hit ("i which i was dead": death -> self_harm)
        return hit2 if hit2 and (not hit or hit2["category"] == "self_harm") else hit

    def _check(self, text: str, lang: str):
        hits, matched = {}, {}
        if lang == "en":
            t = _norm_en(text)
            if not t:
                return None
            for n, rx, cat, w in self._flat_en:
                if rx.search(t):
                    hits[cat] = max(hits.get(cat, 0), n)
                    matched.setdefault(cat, set()).add(w)
        if lang != "en" or _CJK.search(text or ""):
            t = _norm(text)
            if not t and not hits:
                return None
            for _, w, cat in self._flat:
                if w and w in t:
                    hits[cat] = max(hits.get(cat, 0), len(w))
                    matched.setdefault(cat, set()).add(w)
        for cat in list(hits):   # a science question about a natural event is not scary news
            sci = self.science.get(cat)
            if sci and matched.get(cat, set()) <= sci and self.science_question(text):
                del hits[cat]
            elif lang == "en" and self._exempt_en(cat, matched.get(cat, set()), text):
                del hits[cat]
        if not hits:
            return None
        best = max(hits, key=lambda c: (hits[c], -PRIORITY.index(c) if c in PRIORITY else -99))
        return self.hit_for(best, lang)

    def _exempt_en(self, cat, matched, text):
        """A hit made only of single keywords (`keywords_en`) next to a harmless subject (`exempt_en`: "Why do flowers
        die?", "Why did the dinosaurs die out?", "my phone battery died", "soap kills germs") is not the parent's topic.
        Phrase triggers, and a question that also names a person or a pet ("grandpa", "people", "my dog"), never get it."""
        ex = self.exempt_en.get(cat)
        if not ex or not matched or not matched <= self.keywords_en.get(cat, set()):
            return False
        t = _norm_en(text)
        if re.search(r"\b(?:mom|mommy|mum|dad|daddy|grandma|grandpa|granny|nana|papa|grampa|granpa|grandad|granddad|"
                     r"gramps|gramma|granma|grandmom|grandmum|grammy|"
                     r"friend|brother|sister|baby|uncle|aunt|people|person|someone|somebody|kids?|children)\b", t):
            return False
        if (cat == "death" and re.search(r"\b(?:pets?|dogs?|cats?|puppy|kitten|hamster|goldfish|rabbit|bunny)\b", t)
                and not re.search(r"\b(?:mice|mouse|prey|hunt\w*)\b", t)):
            return False   # a pet that died is the parent's topic; "Why do cats bring dead mice home?" is not
        return any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t) for w in ex)

    def hit_for(self, best, lang="zh"):
        """The hit dict (deflection in `lang`, parent cheat sheet category) for one category."""
        cheat = self.cheats.get(best, {})
        en = cheat.get("en") or {}
        zh_text = cheat.get("deflection_zh") or DEFAULT_DEFLECTION
        en_text = en.get("deflection") or DEFAULT_DEFLECTION_EN
        return {"category": best,
                "category_zh": cheat.get("category_zh") or self.zh.get(best, best),
                "deflection_zh": zh_text, "deflection_en": en_text,
                "deflection": en_text if lang == "en" else zh_text,
                "urgent": bool(cheat.get("urgent", best in self.urgent or best == "self_harm"))}

    @staticmethod
    def science_question(text: str) -> bool:
        """A plain why / how / what question with no fear, news, danger, death or personal cue."""
        if _CJK.search(text or ""):
            return bool(_SCI_FORM_ZH.search(text)) and not _SCI_CUE_ZH.search(text)
        return bool(_SCI_FORM_EN.search(text or "")) and not _SCI_CUE_EN.search(text or "")

    def cheat(self, category):
        return self.cheats.get(category)
