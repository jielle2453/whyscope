# English mode (spec addendum)

Whyscope becomes bilingual with **English as the default**: the child asks in English, the device answers and
speaks in English, the parent app shows English content. Chinese (zh) stays fully working behind `?lang=zh` /
the EN / 中 toggle / the `language` setting.

## 1. Data: English fields on every knowledge entry and cheat sheet

`knowledge/entries/<topic>/<id>.json` gains an `"en"` object (all other fields unchanged):

```json
"en": {
  "labels": ["snail"],
  "question_patterns": ["why does a snail have a shell", "what is this", "why does the snail carry a house", "what is the shell for"],
  "first_sentence": "This is a snail! The shell is its home.",
  "facts": ["The shell keeps the snail's soft body safe.", "When it is too dry, the snail hides inside.", "The shell grows with the snail."],
  "ask_back": "Do you think a snail comes out in the rain, or hides in its shell?",
  "bridges": {"has_dog": "Your dog has fur. Why do you think a snail has none?"}
}
```
Rules: `first_sentence` ≤ 12 words, names the thing + one cause; `facts` 2–4 items ≤ 14 words each, words a
6-year-old knows (no scientific terms; say "bounce back" not "reflect", "tiny bits" not "molecules");
`ask_back` one guessable question about the OBJECT (yes/no or "A or B"), never about the child's day/feelings/family;
`question_patterns` 3–6 ways a child says it incl. "what is this"; `bridges` keys only from the memory keys.
Translate the meaning, not the words; keep facts supported by the same `source_url`.

`knowledge/cheats/<id>.json` gains `"en"`: `{"deflection": "...", "triggers": [...], "talking_points": {"5-6": [...], "7-8": [...]}, "what_not_to_say": [...]}`.
`deflection` ≤ 14 words, warm, routes to a grown-up, never answers. `triggers`: 8–14 English words/phrases a child
would say (die, dead, died, heaven, where do babies come from, fight, gun, war, divorce, sick, cancer, kill myself,
want to die, money, poor, god, bullied, earthquake news…). `knowledge/build_rules.py` must emit both `triggers` (zh)
and `triggers_en` into `knowledge/sensitive_rules.json`.

## 2. Pipeline: `lang` everywhere

- `POST /api/ask` accepts `lang` ("en"|"zh"); default = settings `language` (default "en"). Events store `lang`.
- `listen.py`: faster-whisper `language=lang`.
- `safety.py`: match zh triggers on zh text and en triggers (case-insensitive, word-boundary) on en text; always-on
  self-harm terms in both languages.
- `recall.py`: build one index per language from `labels + question_patterns` of that language (zh from the top-level
  fields, en from `en`). Gibberish pre-check per language. Same threshold.
- `compose.py` + `wording.py`: English rule set: every sentence ≤ 12 words; explanation ≤ 2 sentences; total spoken
  ≤ 45 words; banned-term → plain-phrase map in English (reflect→bounce back, evaporate→turn into water in the air,
  bacteria→tiny tiny bugs, molecules→tiny bits, gravity→the pull of the Earth, oxygen→the air we breathe,
  vibrate→wiggle very fast, reflex→happens by itself, nutrients→good stuff in food, carbon dioxide→the gas that makes bubbles…);
  a common-words list `hub/data/common_words_en.txt` built offline from the Dolch + Fry 1,000 lists (public domain,
  write them into the file from memory, no download) plus all words in the English entries; max 2 uncommon words
  per sentence. English few-shot prompt for Qwen in the Whyscope voice. Ask-back pattern: contains "?" and one of
  "do you think", "or", "guess", "can you", "is it", "does". Reaction lines in English ("Good question!", "Oh, you noticed!")
  at most 1 in 3. Age rules identical. Template fallback `template_explanation(entry, age, lang)`.
- `report.py` / cheats API: return the `en` content when `lang=en`.
- `eval/check_answers.py --lang en`: same assertions in English (word-based). `eval/abstention_set_en.jsonl`: 60 lines
  (25 in_kb, 12 near_kb, 15 out_kb, 8 nonsense) translated from the zh set.

## 3. Pages

- Kid page: when lang=en, speech synthesis picks an en-US/en-GB voice (prefer names containing "Aria", "Jenny",
  "Samantha", "Google US English", "Natural"), rate 0.95; spoken text is the English answer. The typed/spoken
  question is sent with `lang`. The EN / 中 toggle switches both chrome and answer language and stores
  `whyscope_lang`; it also calls `POST /api/settings {language}` so the server default follows.
- Parent page: cheats show `en` talking points; "Talk about" lines use the `en.ask_back`; everything else already
  i18n.

## 4. Verification

1. `/api/ask` with `{"text":"why does a snail have a shell","lang":"en"}` → answered, English first sentence verbatim.
2. `{"text":"why do people die","lang":"en"}` → sensitive, English deflection; `{"text":"why do stocks go down","lang":"en"}` → abstained.
3. Voice: synthesize an English WAV with Windows SAPI ("why do cats' eyes glow at night") → transcript contains "cat".
4. `eval/check_answers.py --lang en` 10/10; `eval/run_abstention.py --lang en` ≥ 85 %.
5. Kid page in the built-in browser at 390×844, lang=en: ask, see English answer; screenshot `docs/screens/v3-kid-en-answer.png`.
6. README quickstart updated: default English, `?lang=zh` for Chinese; benchmarks.md gets the English numbers.
