# Reviewer brief: zh pilot layer (independent review)

You review Chinese (Traditional, Taiwan) text written for Whyscope, an offline "why" companion for bilingual
Taiwanese children aged 5-8. You did not write it. Be strict and specific. Do not edit the files; report.

Each input row: `id`, `en` (the English item: q, a1, a2, ask_back; its facts were fact-checked 3 times and are the
ground truth), `zh` (fields to review):
- q_zh, variants_zh: how a Taiwanese 5-8-year-old would ask it (variants: spoken forms, fragments, one mixed with a
  simple English word, maybe a speech-recognition slip; slips are intentional).
- a1_zh: the first spoken sentence, pure Chinese, one sentence, <=18 spoken characters, gives the cause (因為…) for why
  questions.
- a1_zh_mix: null, or a1_zh with at most ONE simple English word woven in. English is a light side benefit, never the
  focus. It must sound natural and unforced (as a Taiwanese bilingual-kindergarten teacher would say it), must not
  quiz the child, and must not let the English word replace or obscure the cause.
- a2_zh: the follow-up answer to "為什麼？", 1-2 sentences, each <=18 characters.
- ask_back_zh: one guessable question about the object (not about the child's day/feelings/family/friends/school).
- key_en: 0-2 simple concrete English words a bilingual kindergarten would teach, with the Taiwan Chinese word.
- tw_note: "" / "not_for_tw: reason" (item doesn't fit Taiwan) / "adapted: what changed".

Judge each row on:
1. **faithfulness**: zh says nothing the English does not support. Simplifying/dropping detail is fine; a new fact,
   cause, number, example, or a stronger claim (often→always, hedge removed) is a MUST-fix. Also flag a
   meaning change from mistranslation.
2. **age**: words a 5-8-year-old (注音 stage) understands; concrete; not babyish beyond reason.
3. **tw_naturalness**: sounds like a Taiwanese preschool teacher, not a mainland textbook and not translationese.
   Flag mainland words (視頻 質量 土豆 信息 出租車 地鐵 自行車 摩托車 空調 塑料 酸奶 啥 兒化 …), unnatural word order,
   calques of English structure, wrong measure words.
4. **askback**: guessable, about the object, natural.
5. **mix**: a1_zh_mix natural and unforced? (or should it be null?)
6. **key_en**: simple and concrete? zh correct for Taiwan?
7. **tw_note**: missing a needed not_for_tw/adapted note, or a wrong one? Is any Taiwan localization true?
8. **query**: do q_zh/variants sound like real kids, and are they the same question as the English q?

Severity: `must` = should be changed before shipping (wrong/added fact, unnatural or mainland wording, a child would
not understand, bad ask-back, forced mix). `nit` = optional polish.
When you suggest a replacement for a1_zh/a2_zh/a1_zh_mix keep it one short sentence (<=18 Chinese characters per
sentence); ask-backs must contain 嗎/還是/猜/你覺得 and must not contain 今天 開心 難過 傷心 生氣 害怕 朋友 同學 學校 老師
你喜歡 你愛 你家 你的 爸爸 媽媽 哥哥 姐姐 弟弟 妹妹 (note 小朋友 contains 朋友).

Output one JSON per input row, same order:
{"id": "...", "verdict": "pass" | "fix", "issues": [{"field": "a1_zh", "kind": "faithfulness|age|tw_naturalness|mainland|askback|mix|key_en|tw_note|query", "severity": "must|nit", "problem": "...", "suggestion": "..."}]}
verdict is "fix" if and only if there is at least one `must` issue. Pass rows may list nits.
