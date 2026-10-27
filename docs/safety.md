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
- Never stored: audio, camera frames, voice prints, or anything derived from them other than the transcript text.
- Where: `data/whyscope.db` on the device, git-ignored. Nothing is sent anywhere.
- Retention: events older than `retention_days` (default 30, adjustable 1 to 365 on the parent page) are deleted at
  startup and whenever the setting is saved.
- Parent controls: 清除所有紀錄 (deletes events and auto-recorded topics; parent-entered facts are kept and can be
  deleted one by one), and 匯出 JSON (everything stored about the child).
- The child's name is only ever shown on the parent page. The device never speaks it.

## Known limits

- Keyword rules are blunt; a determined paraphrase can slip past them. Spot checks and a growing rules file are
  part of the Stage II plan, as is an evaluation with real children's speech.
- ASR can mishear; a misheard sensitive word may not be caught, and a misheard ordinary word may be answered wrongly.
  The abstention threshold exists to limit the second case.
- Knowledge entries are drafted by AI and must be reviewed by a human (`reviewed_by`, `spot_checked`) before any
  child-facing release.
