# Answer bank round 3: gap items and borderline variants (2026-11-18)

Proposed additions to the English answer bank (`knowledge/answer_bank_en.jsonl`, 5,090 items). Nothing here has been merged:
the bank, `bank_en_v2.jsonl`, hub code and configs are unchanged. Every number below was measured on a **temporary copy** of the bank
(bank + new items + added variants) with the hub's own model and normalisation.

**Read this first: the gaps were found from the evaluation sets.** The 145 test questions (heldout_en_v3 + guess_fresh_en) were
used to find the missing topics and the borderline items, so the "after" numbers on those 145 questions are **in-sample and
optimistic**. The fairer number is the fresh probe set (111 questions written by a separate agent that never saw the bank or the new
items; see "Fresh probes").

## Files
| file | content |
|---|---|
| `new_items.jsonl` | 49 new items, full round-2 schema (id, topic, q, variants, a1, a2, ask_back, confidence, notes, check) |
| `variant_additions.jsonl` | 15 existing items, 37 new variants: `{"id", "add": [...]}` |
| `gaps_report.md` | this report |
| `gaps_v3_work/` | inputs and outputs of the 3 fact checks, merge decisions, blind judge sheet/key/labels, probes, retrieval and routing dumps, safety logs, scripts (scratch copies, paths inside point to the scratchpad) |

Ids use a new prefix `v3-<group>-NNN` (e.g. `v3-sky-005`). None of these ids is used in the bank. The ids are not in the eval
sets' `v3-NNN` format, but scripts that group items by `id[:3]` (`retrieve.subsets`, `validate_v2.IDRX`) will put all of them in a
group called "v3-". `hub/bank.py` only uses the id prefix for `topic == "ocean"`. Ocean items with a `v3-sky-` id map to "earth",
which is correct.

## 1. What was missing
Sources: the 26 questions with no R in the v2 top-5 (`report_v2.md`, `eval_v2.py --single`), the W answers at top-1, and a routing
run of the 145-question set through the real pipeline (`run_bank_order.make`, temporary bank and cache). Before this round, that run
gave bank 116 / kb 22 / ai_guess 7, with these questions at or near the threshold:
- **ai_guess (7):** kittens and string (0.794), skipping stone (0.69), ocean deep (0.799), doctors and shots (R item at 0.782),
  berries that make you sick (0.768), rockets need fire (0.762), star points in drawings (0.745).
- **True gaps or wrong aspect (no right item):** runny nose with a cold, so many stars, planets with moons, comet tails, hail in a
  storm, roots growing down, fruit colours, bamboo tall, zippers holding, clocks ticking, oil on water, ocean deep, voting, pink
  clouds, poisonous berries, Jupiter's size, star points, astronaut food bags, the moon moving the sea, vacuum noise, cold floor,
  oven heat, keys and locks, crayons breaking, flags on buildings, sending letters.
- **Right item at 0.75–0.84, or a right item losing to a P item:** kittens pounce `ani-n03338` (0.78), dew `sky-019` (0.79),
  sea breeze `sky-n07173` (0.84), straw `thg-n08275` (0.83 < P 0.84), vaccines `bod-123` (0.78), dry skin `bod-n01125`
  (0.83 < P 0.94), mouth watering `bod-045` (0.82), pan handles `thg-n08187` (0.75 < P 0.84), sharing `soc-025` (0.83 < P 0.84),
  black hair `bod-063` (0.83), bedtime `soc-029` (**0.800**), long head hair `bod-n01151` (0.80). Also ice melting `thg-022` (0.85)
  and wet clothes `thg-n08217` (0.87), which are just outside the band but lose to a P item, and the rocket R item `thg-136` (0.72).

## 2. What was added
**49 new items** (26 for gap topics + 23 nearby questions children ask about the same topics). Confidence: 44 high, 5 medium. No item
is sensitive (all three checkers agreed).
- Space: so many stars, new stars still being made; how planets get moons, Jupiter's moon count (medium: the count changes);
  comet tails, comets coming back; Jupiter's size, what Jupiter is made of; astronauts eating from bags, drinking in space.
- Sea and weather: how the moon pulls the sea, two high tides a day (medium); how the ocean got so deep (medium), how deep it is;
  hail in thunderstorms; pink clouds at sunset.
- Plants: roots growing down, root hairs; fruit colours; bamboo tall, bamboo hollow; poisonous berries, how to tell safe berries
  (a grown-up), why birds can eat them (medium).
- Home and things: zipper staying closed; clock tick, clocks that don't tick; vacuum noise, hair-dryer noise; cold floor in the
  morning; how an oven heats up, the oven light; how a key opens a lock; crayons breaking, crayon tips going flat; rocket launch
  cloud (medium).
- People: why grown-ups vote, how votes are counted, what an election is; flags on buildings, stars on flags; why people write
  letters, how a letter finds the house.
- Other: runny nose when sick; a flat stone skipping, the stone-skipping record; cats chasing string, cats chasing a laser dot.

**37 variants on 15 existing items:** bod-123, ani-n03338, sky-019, sky-n07173, thg-n08275, thg-022, thg-n08217, bod-n01125,
bod-045, thg-n08187, soc-025, bod-063, soc-029, bod-n01151, thg-136 (2–4 each). Oil on water (`thg-029`) was not touched: its
variants and a2 already answer it, and the P label comes from the judge seeing only the two questions.

### Anti-overfitting rules used while writing
- No new q or variant is equal, after normalisation, to any of the 145 test questions. One draft variant ("why do rockets need fire")
  and four draft q's were equal to a test question and were rewritten.
- No new row has cosine ≥ 0.95 to any test question. The highest are 0.949 (fruit colours), 0.947 (cats and string) and 0.946
  (crayons): these are the item's own natural q. The core gap items still score 0.87–0.95 against their test question, as any
  natural phrasing of the same question would.
- Collisions (round-2 dedup rule): a new row scoring ≥ 0.90 against a row of a different existing item was removed. Two remain, and
  both are the item's own q: `v3-sky-005` "Why does a comet have a tail?" vs `sky-059`'s variant "what is a comet tail" (0.917), and
  `v3-thg-002` "Why does a clock go tick tock?" vs `thg-062`'s variant "why clock tick" (0.918).
- Wording: all 49 items pass `voice_v2.py` (sentence length, rare words, ask-back pattern): 0 flags.

## 3. Fact check (3 independent checkers, each covering all 50 drafted items and all 15 variant sets)
Checkers worked in private folders and read only the two input files. The merge used the `merge_checks_v2.py` rules.

| drafted items (50) | items | share |
|---|---|---|
| true (≥ 2 of 3) | 26 | 52% |
| simplified (acceptable) | 22 | 44% |
| fixed (≥ 2 of 3; texts reconciled) | 2 | 4% |
| dropped by the checks | 0 | 0% |

The 49 items that remain after the guard (section 4) are 26 true, 21 simplified and 2 fixed, and this label is the `check` field in
`new_items.jsonl`.

- Per checker: A 28 true / 20 simplified / 2 fix; B 23 / 24 / 3; C 22 / 26 / 2. Unanimous on 33 items; all three found 47 acceptable.
- **Fixed by 3 of 3:**
  - `v3-sky-003` (how planets get moons): a1 only defined a moon. It now gives the two ways planets get moons.
  - `v3-pfd-003` (fruit colours): a1 restated the question. It now says colours help animals find ripe fruit and spread the seeds.
- **One minority fix (B):** `v3-thg-008` (oven door hot). A2 said the door "stays cooler", which could sound safe to touch, and C
  raised the same concern in a note. The safety line was added, then the item was **removed by the guard** (section 4).
- **Changed after the check (wording only):** `v3-sky-003` a2, from the reconciled "likely formed after a huge rock crashed into
  Earth" to "was probably made when a huge rock hit Earth" (a rare-word flag). Same meaning.
- **Variants removed (flagged by ≥ 2 checkers):** 8 from 6 new items. Examples: "which planet has the most moons" (that is Saturn),
  "how deep is the deepest sea" (a1 gives the average depth), "how far can a stone skip", "what is jupiter". One single-flagged
  variant was kept ("why do we have elections" on `v3-soc-003`). After the removals, `v3-sky-002` has 2 variants and `v3-sky-009`
  has 1 (round 2 also left a few items below 3).
- **Variant additions removed (3 of 3):** 4 of 41. "why does a pan have a long handle" asks about length, not cool handles.
  "why is my hair a different colour from my brothers" is not answered by "families pass it down". "why do i have a bedtime and
  grown-ups dont" and "why do rockets burn so much fuel" are also not answered by the item.
- **Checker notes to review:**
  - The skipping record (88 skips, Kurt Steiner, 2013) and "nearly a hundred" Jupiter moons were confirmed from memory, not from a
    live source. The moon count will go out of date.
  - `v3-sky-006`'s ask-back (how old you will be when Halley's Comet returns) needs the year 2061, which the answer does not give.
  - `v3-thg-004`'s ask-back implies a bigger fan is louder.

## 4. Guard pass (re-embedded, temporary bank)
- **Stealing a labelled question from its right item (top-1 ≥ 0.80 by a different item):** two drafts did, and both were fixed.
  - `v3-thg-013`'s variant "why do rockets make smoke" took "Why do rockets need fire?" (0.834) from its R items `thg-136` and
    `sky-086`. The variant was removed. The question now has R `thg-136` at top-1 (0.788), still below the threshold, so it still goes
    to an AI guess.
  - `v3-thg-008` (oven door hot) took "Why does the oven get hot?" (0.902 vs 0.892 for `v3-thg-007`) and the v2 held-out question
    "Why does food burn in the oven?". The whole item was removed (49 items remain).
  - `v3-007` (kittens and string) moved from its labelled R `ani-n03338` to the new `v3-ani-001`. The blind judge labels the new
    pair R as well (two right items), so it is not a steal. Same for `v3-064` (skipping stone): the earlier "R" `sky-n07273` (stone
    ripples) is a doubtful label, and the new pair is R.
- **Other eval sets** (abstention_set_en, chat_set_en, heldout_en_v2): no question has a new or changed item as top-1 ≥ 0.80. The
  two chat-set rows that reach the bank (`bod-063`, `soc-029`) did so before as well, at the same scores.
- **Sensitive questions:** `eval/check_safety_en.py` was run for real on both banks: 35 sensitive + 38 harmless, 0 failures, and the
  output is identical before and after. All 410 q/variant rows of the 83 sensitive items still have a non-new item as top-1. The
  highest score of a sensitive row against any new or changed item is 0.678.
- `run_bank_order.py`'s fixed checks (child utterances, chat stays chat, safety first, Chinese mode, a2 on "why?", family beats
  bank) all pass on the temporary bank.

## 5. Before / after
Labels: round-2 single-judge labels where the pair was judged. For the 24 new (question, item) top-1 pairs, a new blind judge saw
only the two questions (round-2 method), mixed with 30 round-2 pairs as calibration: 28/30 exact agreement, 28/30 on R+P vs W
(the 12 R pairs: 12/12). **R is comparable; P and W less so.**

### Retrieval on the 145 questions (in-sample)
| bank | T | answered | R | P | W | off-question | R share | R+P share |
|---|---|---|---|---|---|---|---|---|
| v2 (5,090) | 0.80 | 137 | 106 | 28 | 3 | 2.2% | 73% | 92% |
| + round 3 (5,139) | 0.80 | 144 | 133 | 10 | 1 | **0.7%** | **92%** | 99% |
| v2 | 0.85 | 121 | 102 | 16 | 3 | 2.5% | 70% | 81% |
| + round 3 | 0.85 | 139 | 129 | 9 | 1 | 0.7% | 89% | 95% |
| v2 | always answer | 145 | 107 | 34 | 4 | 2.8% | 74% | 97% |
| + round 3 | always answer | 145 | 134 | 10 | 1 | 0.7% | 92% | 99% |

The "before" row reproduces report_v2 exactly (137 / 106 / 28 / 3). 27 questions change top-1: 24 P→R and 3 W→R (letters vs
alphabet, the moon and the sea, the skipping stone). No R or P became W.

### Routing through the hub pipeline (145 questions, temporary bank and cache)
| | bank | kb | ai_guess | bank answers R / P / W |
|---|---|---|---|---|
| before | 116 | 22 | 7 | 90 / 23 / 3 |
| after | 124 | 20 | 1 | 116 / 7 / 1 |

6 AI guesses became bank answers, all R: kittens and string, skipping stone, ocean deep, doctors and shots, berries, star points.
2 KB answers moved to the bank (hail in a storm, zippers holding), both R by the KB-margin rule. The only AI guess left is
"Why do rockets need fire?" (`thg-136` R at 0.788). The one W is still `bod-042` (cold nose) for the runny-nose-with-a-cold question.

### Fresh probes (fairer check: 111 questions, 3 per topic, from a writer who saw neither the bank nor the new items)
| | answered at 0.80 | R | P | W | off-question | R at top-1 (always answer) |
|---|---|---|---|---|---|---|
| before | 62 | 12 | 48 | 2 | 3.2% | 19 / 111 |
| after | 91 | 76 | 14 | 1 | 1.1% | 88 / 111 |

- **Gap topics (78 probes):** R at 0.80 went 2 → 58. Before, the bank mostly answered these with a P item (45 P).
- **Borderline-item topics (33 probes):** R at 0.80 went 10 → 18.
- The 1 W after is unchanged from before: "why share toy" → `thg-081` (0.817).
- The probes are AI-written, and their topic list was derived from the same gaps. They test paraphrase coverage, not new topics.

## 6. Still open (for the merge session / team)
- **"Why do I get a runny nose when I have a cold?"** still goes to `bod-042` (cold weather, W, 0.918). The embedding cannot tell
  "a cold" from "cold", and any new row close to the test question also scores ~0.98 against `bod-042`'s q. The new item
  `v3-bod-001` catches "sick" phrasings only. This needs a rule outside retrieval (or a selector step).
- **Clocks ticking:** the new `v3-thg-002` loses to `thg-062`'s variant "why clock tick" (0.952), whose answer (motor or spring)
  does not explain the tick. Suggestion for the merge: drop that variant from `thg-062` (it is frozen round-1 text, so this is the
  team's call).
- **Bedtime "why i need to go to bed at 10":** still exactly 0.800 against `soc-029`. It routes to the bank (R), but sits right on the
  threshold. The added general variants ("why do kids have to go to bed so early" …) do not move this particular phrasing. A closer
  variant was not added because it would mean tuning to the test sentence.
- **Unchanged P at top-1:**
  - Bamboo shoots tall (`pfd-n05251` 0.913, KB route).
  - Hair keeps growing (`bod-n12057` 0.935, KB).
  - Dew on the ground (`sky-n07098` 0.869).
  - Ice melting in the hand (`thg-n08190` 0.874).
  - Wet clothes in the sun (`thg-n08218` 0.889).
  - Dry lips in winter (`bod-n01092` 0.942).
  - Sticky mud (`sky-205` 0.992).
  - Sharing toys (`soc-164` 0.838).
  - Oil on water (`thg-029` 0.909).

  In each, the R item would need a near-copy of the test sentence to win.
- **Merging:** append `new_items.jsonl` to the bank, and extend each listed item's `variants` with `add`. The bank file hash changes,
  so the hub rebuilds `data/answer_bank_en.npz` on its next start (about 23 s). Re-run `eval/check_safety_en.py` and
  `eval/run_bank_order.py` after merging. The other agent's askback/wording fixes in this folder touch existing texts only, so no
  conflict is expected.
- **AI only:** all checks and labels are AI judgments (3 checkers, 1 judge, 1 run).
