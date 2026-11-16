# Principle library experiment (2026-11-14)

Question: questions are unbounded, principles are few. Can a library of about 50 child-level science principles
(buoyancy, gravity, germs, ...) answer the questions the hub missed, and what should the UGen300 do in it?

All verdicts are AI judgments (one judge, no human review). Questions are synthetic. The 52 principles
(`principles_draft.json`) are an AI draft, not human-reviewed. The list was not fully blind (the author had seen the
previous report), and the held-out set was written after the list, so the numbers are optimistic.

Files: `principles_draft.json`, `gold.json`, `failed_set.json` (54 questions the hub did not answer correctly in
`eval/coverage_report.md`), `heldout_questions.jsonl` (40 new questions), scripts, and `results/` (every raw UGen
choice and answer).

## A. Coverage by 52 principles

| | full | partly | none |
|---|---|---|---|
| failed set (54) | 29 (54%) | 13 (24%) | 12 (22%) |
| held-out (40) | 22 (55%) | 10 (25%) | 8 (20%) |

Strong: water/physics (8/8 full), earth/rocks (8/10), everyday objects. Weak: animals (one-off facts), food/taste,
people/society (money, jobs, school), sky/space ("partly": the right area but not the real reason).

## B. Finding the principle (answerable = full or partly)

| | n | embedding top-1 | top-3 | top-5 | UGen picks gold |
|---|---|---|---|---|---|
| failed | 42 | 74% | 90% | 93% | 48% |
| failed, full only | 29 | 93% | | | 55% |
| held-out | 32 | 72% | 84% | 97% | 50% |
| held-out, full only | 22 | 86% | 95% | | 64% |

- The UGen is a worse chooser than the embedding and almost never says "none" (it picked a principle for 18 of 20
  questions with no fitting principle).
- A threshold on the embedding top-1 score separates "none" well (AUC 0.99 failed / 0.94 held-out). At 0.55: all 12
  failed-set "none" rejected, 9 of 42 answerable lost.

## C. Answer quality of the UGen (1-2 sentences from the principle's facts)

| | answers | right | partly | wrong | false statement |
|---|---|---|---|---|---|
| as built (UGen chooses) | 84 | 21% | 33% | 45% | 49% |
| UGen chose the gold principle | 36 | 36% | 39% | 25% | 44% |
| forced gold principle, full only | 51 | 51% | 27% | 22% | 35% |

- Even with the right principle the model reverses facts ("因為船的重量比水重，所以會浮在水上"), invents ("magnets
  stick because they have the same magnetic field"), mixes in memory, and leaks the few-shot topic.
- Voice rules broken by 56% (zh) and 73% (en) of answers, mostly sentence length.
- Latency: choice 2.0 s, answer 5.1 s p50 (8.4 s p95), end to end 7.0 s p50 (10.3 s p95).

## D. Coverage, right answers only (projection, partly measured)

| variant | of 100 |
|---|---|
| hub only | 46 |
| + library, UGen chooses and answers | 51-53, with about 20 extra wrong answers delivered |
| + library, embedding top-1 picks, UGen answers | about 59 |
| + library, perfect mapping, UGen answers | about 61 |

## Recommendation (from the experiment)

- Build the library as **retrieval plus pre-written, human-checked child-voice answers**, not as a UGen task: 2-3
  answers per principle with an `{object}` slot, chosen by embedding plus a score threshold (about 0.55); below it,
  "ask a grown-up" / parent.
- About 65-70 principles (the 52 plus about 12-15 suggested: taste/acids, why planets are round, keeping cool, bees and
  honey, animal signals, wrinkly fingers, weightlessness, yeast/gas expansion, balance, plant ageing, thirst, snow,
  phones). Social topics stay as hub entries.
- The UGen (this ~1.5B model) should not choose principles, decide "none", or free-write explanations. At most it
  paraphrases one pre-written sentence behind the hub's validators.
- Next: human review of the principle facts, a second human gold mapping, the hub run on the held-out set for a real
  baseline.
