# Answer bank round 2: 1,182 -> 5,090 items (2026-11-16)

How does coverage change when the fact-checked English bank (retrieved on the device, never generated) grows from 1,182 to about
5,000 items? All verdicts are AI judgments (one judge, one run, one subset seed). Read the caveats before quoting a number.
(Written from the round-2 agent's report; its own Write call was refused.)

## Bank
- `bank_en_v2.jsonl`: the 1,182 frozen round-1 items (unchanged, same order) + **3,908 new** = **5,090**. `FROZEN_v2` written before the
  evaluation. Round 1 stays reproducible (bank_en.jsonl, FROZEN, parts/, retrieval_top.json, sheet.txt untouched; a rerun gives the old
  bank the same top-1 for 147/147 queries).
- Same fields as round 1 (id, topic, q, 3-5 variants, a1, a2, ask_back, confidence, notes, check); new ids `<group>-nWWNNN`, same 6 groups.
- Plan (`parts_v2/plan.json`, `plan.md`): 12 writer scopes with subtopic quotas; the 8 known gaps assigned. Camera labels: the hub's CLIP
  table (`models/clip/labels_openai.npz`, 1,640 rows, 1,048 unique English names); 785 assigned, 263 plurals/synonyms merged into them.
- Writing: 12 writers, 4,098 items; 83 marked sensitive (ask_back points to a grown-up); 411 medium confidence.
- Dedup: score = highest cosine between any row of the item and any row of an old or other new item. 965 new items >= 0.90 -> 650 unique
  pairs, each judged by three reviewers. 194 same question: 17 dropped as duplicates of old items, 174 of other new items. 138 colliding
  variants removed from 125 items in "different" pairs. Most >= 0.90 pairs were different questions (one short variant pushes the score
  up), so a plain 0.90 cut would have removed many good items.

### Fact check (3 independent checkers, each covering all new items: 11,724 checks)
| new items | items | share | round 1 |
|---|---|---|---|
| true (>= 2 of 3) | 3,439 | 88.0% | 87.0% |
| simplified (acceptable) | 415 | 10.6% | 11.6% |
| fixed (>= 2 of 3; texts reconciled) | 54 | 1.4% | 1.4% |
| dropped | 0 | 0% | 0% |

- **Round 1 actually had one check per item** (check_A/B/C each cover a third: 419/382/381), not three as its report said (now corrected).
- All three agreed on 3,261 items; all three judged 3,816 acceptable.
- 38 items marked "fix" by only one checker kept their text (majority rule); listed with the suggested text in `parts_v2/minority_fixes.jsonl`.
  Some are real problems (e.g. "you can tell how deep water is by its colour"). **Team should review this file.**
- Variants: 61 flagged by >= 2 checkers removed; 154 flagged by one kept. 18 new items now have < 3 variants (3 have one).
- Typical fixes: a1 describing instead of answering (pine cones, kneecap, eye of a typhoon, adoption); outdated science (hail layers,
  blue blueberries); unsafe ask_backs (looking at the sun, crossing the road, whispering with a lost voice); a sensitive answer that
  dodged ("Will my grown-ups die?" now answers honestly).
- Wording (hub rules, `voice_v2.py`): 7 of 3,908 new items flagged (one rare word). Old bank: 1,011 of 1,182 flagged (mostly ask_backs
  that don't invite a guess, sentences > 12 words) — not changed, round 1 is frozen.
- Camera labels by string match: labels with no item 355 -> 44 (mostly spelling misses); labels with >= 2 items 252 -> 606.

## Method
`retrieve_v2.py`: same model, normalisation and scoring as `retrieve.py`. Same 145 questions: heldout_en_v3 (80) + guess_fresh_en (65).
R = answers the exact question, P = same topic other aspect, W = different question; the judge sees only the two questions.
Round-1 pairs keep their labels; a new judge labelled 600 new pairs plus the 143 round-1 pairs used here, plus 60 blind round-1 pairs
for calibration (= single-judge view). Calibration: R agrees 13/14; P is far more generous (22 of 38 round-1 W became P).
**R is comparable across rounds; P and W are not.** Tables use the single-judge view (`eval_v2.py --single`); the mixed view gives
almost the same R.

## Coverage at T = 0.80 / 0.85
| bank | T | answered | R | P | W | off-question | R+P | R | v3 R+P | fresh R+P |
|---|---|---|---|---|---|---|---|---|---|---|
| round-1 report, 1,182 | 0.80 | 86 | 55 | 19 | 12 | 14% | 51% | 38% | 60% | 40% |
| round-1 report, 1,182 | 0.85 | 67 | 52 | 12 | 3 | 4.5% | 44% | 36% | 55% | 31% |
| old 1,182, single judge | 0.80 | 86 | 54 | 29 | 3 | 3.5% | 57% | 37% | 65% | 48% |
| old 1,182, single judge | 0.85 | 67 | 51 | 13 | 3 | 4.5% | 44% | 35% | 56% | 29% |
| **v2 5,090, single judge** | **0.80** | 137 | 106 | 28 | 3 | **2.2%** | **92%** | **73%** | 92% | 92% |
| **v2 5,090, single judge** | **0.85** | 121 | 102 | 16 | 3 | **2.5%** | **81%** | **70%** | 86% | 75% |

## Always-answer coverage by bank size (top-1, no threshold)
| bank | items | R+P (single) | R | R+P (mixed) |
|---|---|---|---|---|
| round-1 bank | 1,182 | 88% | 39% | 61% |
| round 1 + 1,318 random new | 2,500 | 91% | 50% | 80% |
| full v2 | 5,090 | 97% | 74% | 97% |
| random v2 subset (topic-proportional, seed 1) | 1,182 | 69% | 17% | 65% |
| random v2 subset | 2,500 | 88% | 34% | 77% |

R grows 39% -> 50% -> 74% (v3 46 -> 52 -> 75%, fresh 31 -> 46 -> 72%). Random v2 subsets do worse at the same size because the classic
questions are in the round-1 bank. Round 1's extrapolation was ~75-80% at 5k on v3-like questions; measured at T=0.80: R+P 92%, R 74%.

## Off-question share (W / answered, single judge)
| setting | old bank | v2 |
|---|---|---|
| T=0.80 | 3.5% | 2.2% |
| T=0.85 | 4.5% | 2.5% |
| always answer | 12% (18 W) | 2.8% (4 W) |

(Round 1's 14% at T=0.80 reflects that judge's stricter W and is not comparable.)

## Prototype selection step
A separate judge saw the question and the 5 v2 candidate questions (random order) and picked one or "none" (124 picks, 21 "none").
| score floor | without: R/P/W (answered) | with selector | W removed | R+P lost | R lost |
|---|---|---|---|---|---|
| none | 107/34/4 (145) | 116/8/0 (124) | 4/4 | 17 (all P) | 0 |
| 0.80 | 106/28/3 (137) | 110/7/0 (117) | 3/3 | 17 | 2 |
| 0.85 | 102/16/3 (121) | 104/6/0 (110) | 3/3 | 8 | 2 |

Removes every off-question answer and raises R in 9 cases (right item at ranks 2-5); costs P answers (says "none" when only a
same-topic item exists): R+P 97% -> 86%. Ceiling: top-5 holds an R for 119/145 (82%). The selector is bigger than the 1.5B device
model, so this is an upper bound.

## Latency
5,090 items (25,047 rows) on CPU: median 12.5 ms, p95 14.6 ms (old bank 11.4 / 13.6 ms in the same run); mostly the query embedding.
Index build at start-up 23 s; matrix about 38 MB float32.

## Still missing (26 questions with no R in the v2 top-5)
- True gaps: comets' tails, why planets have moons, voting, flags on buildings, sending letters, why Jupiter is so big, pink clouds,
  berries that make you sick, crayons breaking, points on drawn stars, why the ocean is deep.
- Same object, other aspect: zippers holding (bank: zipper stuck), keys opening locks, the oven getting hot, vacuum noise, clocks
  ticking, roots growing down, fruit colours, tall bamboo shoots, astronaut food in bags, a cold floor in the morning.
- Mismatched cause: hail in a storm, the moon moving the sea, oil staying on top of water.

## Failure types
1. Word sense: "runny nose when I have a cold" -> "nose runs when I am cold" (0.92), from a frozen old item's variants.
2. Same object, other aspect (most P cases): zipper hold vs stuck, keys vs lock, tired after lunch vs why we get tired.
3. General vs specific: bed at 10 -> bedtime (R); wearing glasses vs how glasses help you see (P).
4. Topic neighbours at low scores: skipping stone -> another lake item (0.69).

## Caveats
- **AI-written tests and bank share classic questions:** 11 of 145 test questions appear word for word (normalised) as a new item's
  question or variant, 20 in the old bank. No writer, checker or dedup reviewer opened the test sets. Real children's speech will score
  lower; guess_fresh is the closer stand-in.
- **Camera labels come from the knowledge base:** labels_openai.npz is built from knowledge/entries and principles labels (only the label
  strings were read). About 711 items were label-driven; if the held-out sets were written around knowledge-base objects, they favour them.
- **Single AI judge, single run:** trust R; switching judges moves the P/W line by about 20-40 questions. The selector also ran once.
- **AI fact checkers, not humans:** `review_sample.md` has 100 random new items with an empty column for the team's verdict.
- **Process incident:** checkers first shared a scratch folder; four briefly saw another chunk's items when a helper script was
  overwritten. All redid their work; ids and order of all 24 check files match the input, and corrected texts were embedding-tested
  against their own item (0 mismatches). Later agents used private folders.
- Frozen round-1 bank still has 26 questions in two groups (e.g. "Why do we dream?" as bod-013 and soc-132) and its wording flags.

## Files (eval/answer_bank/)
bank_en_v2.jsonl, FROZEN_v2, review_sample.md, report_v2.md; parts_v2/ (plan, camera_labels_en.txt, w01-w12 writer files, dedup_*,
new_dedup.jsonl, tocheck_*, check_{A,B,C}[_k].jsonl, check_merge.json, reconcile_in/out.jsonl, minority_fixes.jsonl, new_final.jsonl,
judge_* and selector_*); scripts *_v2.py (eval_v2 `--single` for the single-judge view); retrieval_top_v2.json, latency_v2.json,
eval_v2.json, eval_v2_single.json.
