# Answer bank vs on-device generation (2026-11-16)

Question: does a large kid-level answer bank, written and fact-checked offline by big models and only *retrieved* on the device, beat
letting the 1.5B UGen LLM answer by itself? All verdicts are AI judgments (one judge, single run, one subset seed): expect several points of noise.

## Bank
- `bank_en.jsonl`: 1,182 items in 6 topic groups, each with the question, 3-5 child-style variants, a1 (direct cause), a2, ask_back.
- Written by 6 writer subagents; each item was checked by one of 3 checker subagents (check_A/B/C each cover a third of the bank:
  419/382/381; corrected in round 2, see report_v2.md). FROZEN 2026-11-16 (`FROZEN`, items=1182).

| fact check | items | share |
|---|---|---|
| true | 1,028 | 87.0% |
| simplified (acceptable) | 137 | 11.6% |
| fixed (all applied) | 17 | 1.4% |
| dropped | 0 | 0% |

The checkers are AI passes, not humans, so residual error is not zero.

## Hygiene
The test sets (heldout_en_v3/v2, guess_fresh_en, kid_questions, chat_set_en, abstention_set_en, chat_results, principles, coverage_results) and
knowledge/entries were not opened by the writer, checkers or evaluator before the freeze. After the freeze only heldout_en_v3 and guess_fresh_en
were used. Caveat: an LLM-written bank and LLM-written tests share "classic" questions, so coverage is probably higher than on real children's speech.

## Method
- Retrieval (`retrieve.py`): the hub's embedding model (paraphrase-multilingual-MiniLM-L12-v2, CPU); score = max cosine over q + variants.
  The hub's label/ask guards are not applied.
- Test: heldout_en_v3 (80) + guess_fresh_en (65) = 145 questions. R = answers the exact question, P = same topic, other aspect, W = different question.

## Coverage by bank size (always answer with the best match; R+P share)
| bank size | v3 | fresh | all |
|---|---|---|---|
| 250 | 24% | 11% | 18% |
| 500 | 39% | 25% | 32% |
| 1,182 | 72% | 48% | 61% |

## Threshold sweep (full bank)
| T | answered | R | P | W | off-question share of answers | coverage R+P | v3 | fresh |
|---|---|---|---|---|---|---|---|---|
| 0.60 | 140 | 56 | 33 | 51 | 36% | 61% | 72% | 48% |
| 0.70 | 121 | 56 | 30 | 35 | 29% | 59% | 70% | 46% |
| 0.75 | 109 | 56 | 26 | 27 | 25% | 57% | 68% | 43% |
| 0.80 | 86 | 55 | 19 | 12 | 14% | 51% | 60% | 40% |
| 0.85 | 67 | 52 | 12 | 3 | 4.5% | 44% | 55% | 31% |
| 0.90 | 46 | 40 | 5 | 1 | 2% | 31% | 40% | 20% |

## Compared with the current system
| system | right or partly | notes |
|---|---|---|
| KB (207) + principles, v3 | 30/80 = 38% | 18 R, 12 P, 0 false (earlier run) |
| bank T=0.85, v3 | 44/80 = 55% | 35 R, 9 P, 3 off-question |
| bank T=0.80, v3 | 48/80 = 60% | 35 R, 13 P, 6 off-question |
| bank T=0.85, guess_fresh | 20/65 = 31% | 17 R, 3 P, 0 off-question |
| bank T=0.80, guess_fresh | 26/65 = 40% | 20 R, 6 P, 6 off-question |
| AI guess (Qwen2.5), guess_fresh | 23 of 41 guesses | 11 R, 12 P, 10 weak, **8 false (19.5%)** |

Bank answers contain no invented facts (every text shown was fact-checked); the failure mode is answering a *different* question.
User utterances: "Why my hair is black? I want a blonded hair" -> "Why is my hair black?" (0.83); "why i need to go to bed at 10" ->
"Why do we have bedtime?" (0.80). Both answered at T=0.80, abstained at T=0.85.

## Arm C (LLM adapts a near match) — not measured
The UGen worker was down during the run. Ceiling from the judgments: the 0.60-0.85 band holds 73 questions (4 R, 21 P, 48 W), so the LLM
could add at most ~25 questions (17%) and would have to refuse 48 mismatches. `armc.py` is ready.

## Latency
Retrieval on CPU over 1,182 items: median 11.9 ms, p95 14.8 ms.

## Failure examples (off-question top-1)
"Runny nose when I have a cold" -> "nose run when I am cold" (0.92); "Why does a refrigerator hum?" -> "What is a fridge for?" (0.86);
"Lights come on when I flip the switch" -> "Why do we turn off lights?" (0.82); "Ducks walk in a line" -> "birds fly in a V" (0.80).
Gaps with no item: stale bread, tomatoes turning red, icicles, window frost, pine cones, holes in cheese, handshakes, clapping.

## Takeaways
- Retrieval over a fact-checked bank beats generation: more coverage than the current KB with no invented facts, at ~12 ms.
- Coverage grows steeply with bank size (18% -> 32% -> 61% at 250/500/1,182, always-answer). Extrapolation (not measured): ~60-70% at 2k and
  ~75-80% at 5k items at T=0.80 on v3-like questions; lower on guess_fresh-like and real speech.
- Off-question matches below ~0.85 cannot be separated by cosine alone; the hub's label/ask guards (or a selection step) are needed.

Files: bank_en.jsonl, FROZEN, parts/ (writer files + check_A/B/C.jsonl), retrieve.py, retrieval_top.json, sheet.txt, judg.py, sweep.py, band.py, armc.py.
