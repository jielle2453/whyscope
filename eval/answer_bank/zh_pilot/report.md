# zh pilot layer: report (2026-11-18)

Pilot of a Traditional Chinese (Taiwan) layer on top of the fact-checked English bank, for bilingual Taiwanese
children aged 5-8. This calibrates style before the full 5,139-item bank. **Nothing in the bank, the hub code or the
configs was changed.**

## 1. Counts

| | |
|---|---|
| Items | **300** non-sensitive items (of 5,056), all **101 topics** (1 each + proportional, largest remainder), seed `20261118`; ids in `pilot_ids.json` |
| Fields per item | q_zh, variants_zh (5-6 each; 1,555 variants in all), a1_zh, **a1_zh_mix**, a2_zh, ask_back_zh, key_en, tw_note |
| a1_zh | one sentence, median 16 / max 18 spoken characters; 234 of 300 start from 因為 (the rest are what-is / yes-no / "nobody knows" items) |
| a1_zh_mix (option A) | **47 / 300 (16 %)** have one English word woven in; 253 are null on purpose |
| key_en (option C) | 252 items with 2 words, 43 with 1, 5 with none |
| tw_note | 8 `not_for_tw`, 8 `adapted` (list in section 5) |
| Hub rule check | 300 / 300 pass `scripts/validate_zh.py` (hub wording/safety rules, see section 2). 11 items use 細菌 and 4 use 病菌 (see open question 1) |

## 2. Style rules used

These are the writer brief (`scripts/writer_brief.md`) plus the reviewer policy (`scripts/fixer_brief.md`):

- **Voice.** A warm Taiwanese preschool teacher. Not a mainland textbook and not a translation.
- **Taiwan wording.** 馬鈴薯, 影片, 計程車, 捷運, 腳踏車, 機車, 冷氣, 塑膠, 優格, 牠 for animals, 裡/著. No 兒化 and no 啥/咋/搞.
- **q_zh.** How a 5-8-year-old says it, using kid words (便便, 哈啾, 狗狗).
- **variants_zh.** 4-6 variants with varied sentence frames. They include:
  - spoken forms and reduplication;
  - at least one fragment;
  - at least one zh+English mix ("為什麼 zebra 有條紋");
  - optionally an ASR slip (噴涕, 班馬).
- **a1_zh.** Exactly one sentence of at most 18 spoken characters (the hub's `MAX_SENT_CHARS`). It gives the cause with 因為, not a word-for-word translation, and is always pure Chinese.
- **a2_zh.** 1-2 sentences of at most 18 characters each. a1 + a2 is at most 60 characters (the hub's `MAX_TOTAL_CHARS`).
- **Hub wording rules.**
  - `wording.check_text` applies: no banned jargon (反射 → 彈回來, 能量 → 力氣 …), at most 2 uncommon characters per sentence, no device feelings or flattery.
  - Characters that appear in the item's own q_zh/variants are exempt from the uncommon-character limit. This is the pilot's stand-in for the hub's `labels`.
- **ask_back_zh.**
  - Must pass `safety.askback_ok`, `compose.BAD_ASKBACK` and `wording.ask_ok_pattern` (嗎/還是/猜/你覺得), at most 30 characters, ending with ？.
  - About the object, never the child's day, feelings, family or school.
  - Added after review: it must be a real guess, not a re-ask of what a1/a2 just said.
- **a1_zh_mix.** null, or a1_zh with exactly ONE simple English word.
  - It must sound natural and unforced, never quiz the child, and never let the word carry the cause.
  - The word must also be in key_en.
- **key_en.** 0-2 concrete words a bilingual kindergarten teaches, preferably words from the English a1. No abstract or science words.
- **Faithfulness.** Simplify or drop, never add a fact, number or stronger claim. Keep hedges (科學家猜, 沒有人確定).
- **Germs.** 細菌 for bacteria and 病菌 for disease germs (colds), never 小蟲蟲. This is a reviewer finding and conflicts with the hub (open question 1).
- **Scripts and character forms.**
  - No simplified characters, checked per character with OpenCC s2tw/t2s.
  - OpenCC `s2twp` phrase rewrites are only a warning, because it also rewrites correct Taiwan words (open question 6).

## 3. Reviews and pass rates

| Stage | Who | Result |
|---|---|---|
| Writers | 6 subagents × 50 items, each self-validated to 0 errors | 300 rows |
| Mix pass | 2 subagents (after the bilingual-mode decision): a1_zh_mix + key_en pruning | 48 mix sentences |
| **Review 1** | 3 fresh reviewers × 100: faithfulness, age, Taiwan naturalness, ask-back, mix, key_en, tw_note, query | **256 / 300 pass = 85.3 %** (no must-fix); 131 rows had no comment at all |
| Fix 1 | 3 fixers: all 51 must issues fixed (0 rejected), plus policy nits (germs, re-asking ask-backs, off-topic variants, tw_notes) | 159 rows changed |
| **Review 2** | 2 fresh reviewers on the 159 changed rows | **151 / 159 pass = 95.0 %**; the 8 must issues were fixed by the lead (not re-reviewed) |
| **Final** | | 292 / 300 (97.3 %) passed the latest review they got; 8 fixed after review 2 |

**Must issues in review 1, by kind:**

| Kind | Count | Typical problem |
|---|---|---|
| ask-back | 23 | The ask-back mostly re-asked what a2 had just said. |
| faithfulness | 10 | 小蟲蟲 for germs (reads as worms or parasites); "over a thousand years" written as 一千多年; "leans away" written as 背著太陽 |
| Taiwan naturalness | 10 | Calques: 肚子癢癢的 ("tickly"), 真的又溫柔的話, 照顧大大的心情, 有人下一個到 |
| forced mix | 3 | — |
| tw_note | 2 | — |
| age | 2 | — |
| query | 1 | — |

- **Mainland words:** none found by any reviewer.
- **Reviewer strictness varied:** 89, 87 and 80 passes per 100. The strictest reviewer graded re-asking ask-backs as must-fix; the other two graded them as nits.
- **Mix naturalness:** reviewers called 3 of the 48 mix sentences forced (94 % natural). The fixes:
  - 森林叫 forest → null;
  - 雪叫 snow → "snow 是從雲裡掉下來…";
  - one sentence restructured.

  Review 2 found no forced mix sentence. Reviewer verdicts are in `work/rev_out_*.jsonl` and `work/rerev_out_*.jsonl`, fix notes in `work/fix_notes.json`.

## 4. Retrieval sanity check

**Test set.** 60 child questions (40 Chinese, 20 mixed), written by a subagent that saw only the English q/a1 of 60 pilot items (seed 60) and never the zh text (`retrieval/heldout_zh.jsonl`).

**Method.** Same model (`paraphrase-multilingual-MiniLM-L12-v2`) and scoring as `eval/answer_bank/retrieve.py`: an item's score is the maximum cosine over its rows. "ans@0.80" means top-1 correct AND score ≥ the hub's `answer_bank.threshold` of 0.80. "wrong@0.80" means a wrong item clears 0.80, so a wrong answer would be spoken. The script is `scripts/retrieval_eval.py`; results are in `retrieval/results.json`.

| Index | Items | Top-1 | Top-3 | MRR | ans@0.80 | wrong@0.80 | Median gold score |
|---|---|---|---|---|---|---|---|
| zh: q_zh + variants_zh | 300 | **0.950** | 1.000 | 0.975 | **0.917** | 0.017 | 0.94 |
| zh, q_zh only | 300 | 0.933 | 0.983 | 0.960 | 0.733 | 0.033 | 0.90 |
| en, cross-lingual (Chinese question vs English q/variants) | 300 | 0.867 | 0.967 | 0.918 | 0.633 | 0.017 | 0.83 |
| zh + en | 300 | 0.950 | 1.000 | 0.975 | 0.917 | 0.017 | 0.94 |
| **en_full, cross-lingual, whole bank (today's hub, no zh layer)** | 5,139 | **0.717** | 0.850 | 0.791 | **0.517** | **0.200** | 0.83 |
| **zh + en_full: whole bank + zh rows for the 300 pilot items** | 5,139 | **0.917** | 0.967 | 0.945 | **0.883** | 0.050 | 0.94 |

Mixed questions behave like Chinese ones: zh top-1 is 0.95 for both groups.

**Robustness check.** 17 of the 60 test questions are near-copies (character ratio ≥ 0.8) of a zh variant; 6 are exact copies. Short kid questions such as 森林是什麼 collide naturally. Without those 17 questions the ordering holds:

| Index | Top-1 | ans@0.80 | wrong@0.80 |
|---|---|---|---|
| zh | 0.93 | 0.88 | 0.02 |
| en (cross-lingual) | 0.84 | 0.54 | 0.02 |
| en_full | 0.67 | 0.42 | 0.21 |
| zh + en_full | 0.88 | 0.84 | 0.07 |

**Finding: the zh variants are needed.** The multilingual model does bridge the languages for *ranking* inside a small set: 0.87 top-1 within the pilot. It does not bridge them for *confidence* or at *scale*:

- Against the English text, the correct item's score is about 0.83. Only half the Chinese questions would clear the 0.80 answer threshold.
- On the full English bank, 1 in 5 Chinese questions would get a confidently wrong answer.
- Adding zh rows lifts confident-correct answers from 0.52 to 0.88 and cuts confident-wrong ones from 0.20 to 0.05.
- The variants matter most for confidence: q_zh alone ranks almost as well (0.93) but clears 0.80 only 73 % of the time, against 92 % with variants.

**Caveats.**
- 60 questions, all written by a model, not real ASR transcripts.
- The pilot-only index is easier than a full zh bank will be.
- The hub's own zh path (recall.py `to_trad` normalization, coverage penalty) was not simulated.

## 5. tw_note list

**not_for_tw (8).** The fields are still filled faithfully; the team decides whether to keep each item.

| id | Item | Reason |
|---|---|---|
| sky-n07042 | frost patterns on windows | almost never seen in Taiwan (only high mountains) |
| sky-n07039 | icicles drip | as above |
| soc-n10101 | "bless you" | English-speaking custom; may still suit bilingual kids |
| pfd-n05108 | daisies in the lawn | mown lawns with Bellis daisies are uncommon |
| pfd-n06008 | lime vs green lemon | Taiwan's everyday green 檸檬 is botanically a lime, so the answer may confuse |
| pfd-n06340 | must I eat crusts | the "curly hair" myth in a2 is unknown in Taiwan; a2 could be dropped |
| thg-n09379 | crosswalk button beeps | push-button crossings are less common in Taiwan |
| ani-n04005 | seagulls steal food | rare in Taiwan; content unchanged |

**adapted (8):**

| id | What changed |
|---|---|
| sky-n08024 | "light at bedtime" → evening |
| bod-n01316 | ask-back: beets → red dragon fruit (火龍果). True, but a fact not in the English; please confirm. |
| pfd-059 | tulips → spring flowers in general (variants generalised) |
| ani-n04259 | dropped "toads don't give you warts" (Western folklore; 疣 too hard) |
| bod-n02063 | "why is a cold called a cold" → why 感冒 is "cold" in English |
| ani-n04182 | woodlice → 西瓜蟲 |
| soc-n11211 | football → 橄欖球 (足球 = soccer in Taiwan) |
| ani-n04174 | dropped the UK autumn house-spider season |

**Borderline items left unflagged:**
- sky-011 (snow): snow is a general concept.
- ani-n03322: the ask-back mentions opossums.
- soc-n11116 (coins): the writer avoided asking whose face is on Taiwan's coins.

## 6. Open questions

1. **Hub conflict on 細菌.**
   - `hub/wording.py` bans 細菌 and rewrites it to 很小很小的小蟲蟲. Reviewers rated that a must-fix: in Taiwan 肚子裡的小蟲蟲 and 起司裡的小蟲蟲 suggest worms and maggots, and kids know 細菌 from hand-washing campaigns.
   - The pilot uses 細菌 in 11 items and 病菌 (allowed) in 4, for cold and cough germs. `validate_zh.py` treats 細菌 as a warning-only exception; the hub's check_text would reject or rewrite those lines today.
   - Options: drop 細菌 from REPLACEMENTS/BANNED, or use 病菌 everywhere disease is meant. 病菌 does not fit good bacteria (cheese, gut).
2. **The hub's uncommon-character list (964 characters) is the tightest constraint.**
   - It forced writers off normal words: 照顧, 死, 試試看, 遊樂設施, 橡膠, 千斤頂, and 蒼蠅 next to 咬. Some lines lost detail as a result.
   - Writers sometimes added a variant just to make characters exempt (e.g. 拜託/禮貌). The hub exempts only `labels`, so a real import needs a labels field or a broader list.
3. **The 18-character a1 limit** works, but it costs detail in about 15 items (dropped clauses are noted in the writer reports). Should zh allow up to 20, as first briefed?
4. **Ask-back rule.** Add "must not be answerable from a1/a2" to the style rules. It was the most common must-fix, and the English bank has the same pattern in places.
   - Side effect: `askback_ok` blocks 小朋友 because it contains 朋友.
5. **not_for_tw policy.** Keep the 8 items for bilingual kids, drop them, or localize? Western folklore inside a2 (crusts, warts) is a recurring type to watch for at scale.
6. **OpenCC side finding (hub).** `hub.config.to_trad` (s2twp) rewrites correct Taiwan text: 社區→社群, 水循環→水迴圈, 打開→開啟, 指針→指標, 只→隻, 台→臺. recall.py, safety.py, listen.py and compose.py all run it, so Taiwan text can be mangled. Worth a separate check; not changed here.
7. **Retrieval collisions to expect at scale:**
   - 打嗝 covers both burp and hiccup;
   - generic variants (pfd-059 spring flowers) may steal questions from neighbouring items;
   - duplicate bank items (What is a forest? appears twice).
8. **key_en.** American spelling (color). 5 items have no word. "up" and "learn" were flagged as too abstract and remain.
9. **a1_zh_mix rate.** 16 % of items. Is that the right density for "light side benefit", or should it be even rarer, for example only when the child used English?

## 7. Files

| File | Contents |
|---|---|
| `pilot_zh.jsonl` | id + new fields only: q_zh, variants_zh, a1_zh, a1_zh_mix, a2_zh, ask_back_zh, key_en, tw_note |
| `pilot_ids.json` | seed, per-topic allocation, ids |
| `review_sample.md` | 30 items side by side with an empty verdict column |
| `retrieval/` | heldout_src.jsonl (what the question writer saw), heldout_zh.jsonl (60 questions), results.json |
| `scripts/` | select_pilot.py, validate_zh.py, retrieval_eval.py, make_review_sample.py, plus the writer, reviewer and fixer briefs |
| `batches/`, `work/` | audit trail: writer inputs and outputs, mix pass, reviewer verdicts, fixes, v1→v4 |

To rebuild: `select_pilot.py` → (writers) → `validate_zh.py pilot_zh.jsonl` → `retrieval_eval.py` → `make_review_sample.py`. Run with `HF_HUB_OFFLINE=1` and `C:\whyscope-venv\Scripts\python.exe`.
