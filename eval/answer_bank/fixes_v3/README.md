# Answer bank fixes v3 (English)

Source: `knowledge/answer_bank_en.jsonl` (5,090 items, 83 sensitive). Nothing in the bank, the hub code or
`eval/answer_bank/bank_en_v2.jsonl` was edited; the main session merges these files.

## Outputs

| file | rows | content |
|---|---|---|
| `askback_fixes.jsonl` | 194 | `{id, old, new}`: a new ask_back for every non-sensitive item whose ask_back the hub drops |
| `wording_fixes.jsonl` | 21 rows, 16 items | `{id, field, old, new, word}`: a1/a2/ask_back sentences that used a banned science word |

The two sets do not overlap (`id`, field). After applying both, `build_outputs.py` confirms: 0 items with a banned word
in a1/a2/ask_back, and 0 non-sensitive ask_backs failing `askback_ok_en`.

## How targets were found (`list_targets.py`, hub functions, no reimplementation)

1. **Ask-backs**: `ask_back` non-empty, `hub.bank.sensitive_category(item) is None`, and
   `not hub.wording.askback_ok_en(ask_back)`. This is the drop condition in `hub/pipeline.py::_bank_answer`.
   It gives 194 items. The matches were: "do you like" 113, "you feel" 42, today 16, friend/friends 12, "your family" 4,
   school 2, "do you love" 2, and mommy, teacher, yesterday 1 each.
2. **Banned words**: `hub.wording.has_banned_en(text)`, i.e. the `_BANNED_EN` regex built from `wording.PLAIN_EN`
   (reflect, evaporate, condense, vibrate, absorb, bacteria/bacterium, molecule, atom, gravity, oxygen, reflex, nutrient,
   carbon dioxide, photosynthesis, organism, predator, with inflections). It ran on a1, a2 and ask_back of all items, and
   is the same check `check_text_en`, compose and guard use. The result is 21 hits in 16 items: gravity 16, oxygen 4,
   evaporating 1. (The brief estimated about 17 items. This check finds 16. `guard.BLOCK_EN` and `compose.BAD_ASKBACK_EN`
   are separate safety and ask-back lists, not science-word lists.)

## Ask-back rules (`check_askbacks.py`)

These checks are hard: every final line passes all of them, using the hub's real functions.
- `wording.askback_ok_en` (no day, feelings, family, friends, school, likes or "you feel")
- not `wording.has_banned_en`; not `wording.NOT_ALLOWED_EN`; not `guard.BLOCK_EN`; not `compose.BAD_ASKBACK_EN` (no "your")
- exactly one sentence ending in a single "?", at most 14 words (`wording.words_en`)
- not `compose.repeats_en(new, a1)`
- `wording.rare_score_en(new, allow=words of q/a1/a2) <= MAX_RARE_EN` (2)

These rules were judged by the writers and reviewers: about the object or phenomenon, not the child; invites a guess or an
observation; plain words; no facts beyond a1/a2; not yes/no-only where avoidable; varied openings.

The finals have a maximum of 14 words and a mean of about 10. First words: What 98 (mostly "What other / could / things",
with "What do you think" leading 14 times), Which 44, Where 19, How 17, Guess 10, Why 5, When 1. 25 lines keep a
soft "uncommon word" warning for everyday words outside the frozen common list, such as else, plate, feather, sock, kitten and teddy.

## Process and reviewer pass rate

- **Ask-backs.** Four writer subagents drafted 49/49/49/47 rows and got 0 hard checker failures. Two other reviewer
  subagents judged every draft against the rules and fixed the failures. Their fixes were re-checked to 0 hard failures.
  - Reviewer pass rate on drafts: **133 / 194 = 68.6 %** (batch 1: 31/49, batch 2: 35/49, batch 3: 34/49, batch 4: 33/47).
  - The main failure types:
    - the answer was already in a1/a2, so the question became a memory quiz;
    - "Can you find / spot ...?" yes/no forms;
    - odd or meaningless either/or choices;
    - a few false or unknown premises.
  - The coordinator then made 1 edit, pfd-141 ("How does a toaster know..." -> "How do you think a toaster knows when the
    bread is ready?"). Per-row verdicts are in `work/review_{1..4}.jsonl`.
- **Banned words.** The coordinator drafted the rewrites (`work/wording_draft.py`), changing only the offending sentence or
  question. A separate reviewer subagent checked facts and meaning.
  - Reviewer pass rate: **16 / 21 = 76.2 %**. Five rows were fixed:
    - sky-105 "to" -> "toward";
    - sky-154 a2 lost the empty "turns into water";
    - sky-198 ask_back went back to the original question's intent;
    - sky-082 and thg-002 ask_backs gained "do you think".
  - Every a1 is at most as long as before, in both words and characters. Verdicts are in `work/wording_review.jsonl`.

## Notes for merge

- When q is "What is gravity/oxygen?" (sky-081, sky-179, thg-002), the new a1 starts with "It is ...", which refers back
  to the child's word. The term itself is not spoken.
- sky-180 a1 (13 words) and thg-047 a1 (14 words) were already over the 12-word sentence rule before this change, and
  the rewrites keep the same length.
- The reviewer doubted three original facts but left them unchanged: sky-154 says "like a tiny mist" (vapour is
  invisible); sky-180 says "tiny plants in the sea" (many are not plants); and sky-105 a2 "squeezes ... from all sides"
  is loose.
- The reviewers judged "Guess which ..., A or B?" differently. Batches 3-4 rewrote them; batches 1-2 kept 10 of them.
- Some items are about social topics: soc-072 siblings, soc-073 grandparents, soc-064 rules. Their new ask_backs name
  these people in general terms ("brothers and sisters", "grandparents") and never ask about the child's own family.
  They pass `askback_ok_en`.

## Reproduce

```
set HF_HUB_OFFLINE=1
python eval/answer_bank/fixes_v3/list_targets.py      # -> work/askback_targets.jsonl, work/wording_targets.jsonl
python eval/answer_bank/fixes_v3/check_askbacks.py eval/answer_bank/fixes_v3/work/ab_final_1.jsonl
python eval/answer_bank/fixes_v3/build_outputs.py     # assembles + verifies the two output files
```
