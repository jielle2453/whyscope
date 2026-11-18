# Safety

Whyscope talks to children aged 5 to 8. These are the rules the design is held to.

## Five principles

1. **A tool with warmth, not a friend.** The device is friendly in tone but never claims feelings, never says
   "I missed you", never builds a relationship. It answers a question and hands the conversation back to the child
   and the people around them.
2. **Any causal explanation beats a label.** A child who asks "why" should get a reason ("the shell is its home,
   it protects the soft body"), not just a name ("this is a snail"). First sentences therefore name the thing and end
   with one causal clause.
3. **Questions back are about the object, not the child.** The question after an answer asks the child to guess
   something about the snail or the rainbow. It never asks about feelings, the day, family or friends. A "bridge"
   to the child's world (for example the family dog) appears only if a parent entered that fact, and the sentence
   is written in the knowledge base, never invented by the model.
4. **Uncertain means route to a parent.** If the question is sensitive, or recall confidence is below the threshold,
   the device says "我不確定，我們一起去問爸爸媽媽好嗎？" (or the sensitive-topic deflection) and records the question
   for the parent. It does not guess.
5. **Audio and images never leave the device.** They are processed in memory and discarded. No cloud AI API is
   called at run time; the `cloud_fallback` setting exists in the UI as disabled, labelled "尚未開放".

## Sensitive-topic flow

1. The text (typed, or the ASR transcript converted to Traditional script) is checked **before** any retrieval.
2. `hub/safety.py` matches triggers from `knowledge/sensitive_rules.json` and from each `knowledge/cheats/*.json`,
   plus a small always-on floor (the characters 死 and 自殺 / 想死 / 不想活), so thin or missing rules still err on
   the side of the parent. Longest match wins; self-harm wins ties.
   English: phrase triggers (`triggers_en`) plus single keywords (`keywords_en`: die / died / dying / dead, gun, war,
   divorce, pregnant, bully ...), all matched with plain inflections. A hit made only of keywords is cleared when the
   question names a harmless subject (`exempt_en`: "Why do flowers die?", "soap kills germs", "bamboo shoots") and no
   person; a pet that died stays the parent's topic.
   Then, in English mode, a question that is (near-)verbatim (cosine >= 0.93) to an answer-bank item marked sensitive
   ("Why did my dad move out?") is handled as a hit of that item's category. A looser match to such an item is never
   used as an answer ("Why do kids laugh?" is 0.90 to "Why do kids laugh at me?"). Test: `eval/check_safety_en.py`.
   **Spelling and near-homophones (English).** Questions arrive as speech-recognition text from young children, so
   misspellings and sound-alikes are expected. The rules handle them in four narrow ways, all in `hub/safety.py`:
   - Normalisation on both sides: contractions with or without the apostrophe ("dont" = "don't" = "do not",
     "wanna" = "want to"), possessives ("baby's" = "babys", which matches "babies") and "my self" = "myself" (not
     "my self portrait").
   - `SPELL_EN`: explicit spelling and ASR variants per trigger word, such as kil, grampa / granpa / grandad,
     hospitle, canser, pregnet, chirch and home less.
   - `asr_alt_en`: a second pass that reads near-homophones back only in context:
     - "dye" becomes "die" only with a person, a pet or a death cue and no dyeing object, so "why did grampa dye"
       and "i want to dye" are caught but "dye their hair" and "dye eggs" are not;
     - "kids belly me" becomes "bully me", "laugh add me" becomes "laugh at me", "was mine to me" becomes "mean to me";
     - "is my cat dad" becomes "dead", "kms" becomes "kill myself" (but not "10 kms"), "i which i was dead" becomes "wish";
     - "we prey" becomes "pray", "are we pour" becomes "poor", "a wore" becomes "war", "is got real" becomes "god".
     If the second pass finds self-harm, that wins over a plainer hit.
   - `FUZZY_EN`: a one-letter edit (added, dropped, changed or swapped) on a few long keywords (7+ letters), only
     when the question names a person or the child: "solders", "divorse", "funral".

   On the near-homophone probes of `eval/answer_bank/finetune_v1/pipeline_eval.py` (base config), this moved
   sensitive catches from 6/31 to 28/31. The harmless probes stayed at 0/10.
3. On a hit the pipeline stops. The child hears only the cheat sheet's `deflection_zh`
   ("這個問題很重要，我們一起去問爸爸媽媽好嗎？"). No facts, no explanation, no question back.
4. An event with `status = sensitive` and `sensitive_category` is logged.
5. The parent page lists it under **家長小抄** with age-banded talking points, what not to say, and source links,
   plus a 「已聊過」 button. Self-harm entries are marked urgent and must carry the Taiwan helplines
   1925 安心專線 and 1995 生命線.

False positives (for example 「笑死」) are accepted by design: a wrongly deflected question costs one conversation
with a parent; a wrongly answered one can cost much more.

## Data retention policy

- Stored: the question text, the answer text, topic, status, timings, and parent-entered facts. Nothing else.
- Never stored: audio, camera frames (unless the parent turns on Snapshots, below), voice prints, or anything derived from them other than the transcript text.
- Where: `data/whyscope.db` on the device, git-ignored. Nothing is sent anywhere.
- Retention: events older than `retention_days` (default 30, adjustable 1 to 365 on the parent page) are deleted at
  startup and whenever the setting is saved.
- Parent controls: 清除所有紀錄 (deletes events and auto-recorded topics; parent-entered facts are kept and can be
  deleted one by one), and 匯出 JSON (everything stored about the child).
- The child's name is only ever shown on the parent page. The device never speaks it.

## Snapshots

Snapshots ("the world through the child's eyes") are opt-in and off by default. When the parent turns them on in
Settings, the photo the child takes with the camera toggle is kept as `data/snapshots/<event_id>.jpg` (long side at
most 1024 px, EXIF removed) and shown in the parent page's Log and Moments tab. Photos stay on this device and are
never uploaded. They are deleted after `snapshots_retention_days` (default 30, checked at startup), one by one from
Moments, or all at once with "Delete all photos" (clearing all records deletes them too). Photos are never part of the
weekly report, `/api/report/week` or the JSON export (events only carry a 0/1 `snapshot` flag). A photo can capture
other people's faces, which is why the setting defaults to off; Stage II adds on-device face blurring before saving.

## Known limits

- Keyword rules are blunt; a determined paraphrase can slip past them. Spot checks and a growing rules file are
  part of the Stage II plan, as is an evaluation with real children's speech.
- ASR can mishear; a misheard sensitive word may not be caught, and a misheard ordinary word may be answered wrongly.
  The abstention threshold exists to limit the second case.
  The spelling and near-homophone rules only help when a recognisable form of the key word is still in the text. Rules
  cannot catch ASR output that drops or replaces the key word entirely: "my dog died" heard as "my blog site", "my
  goldfish died" as "my goldfish dive", or "will a war come here" as "really, we'll come here". These made up all 14
  remaining ASR misses (56/70 caught). Ambiguous sound-alikes are left out on purpose: "dad" for "dead" in self-talk ("i wish i was
  dad"), "the force" for "divorce" and "gums" for "guns". Each of these is also an ordinary child question.
- Knowledge entries are drafted by AI and must be reviewed by a human (`reviewed_by`, `spot_checked`) before any
  child-facing release.
