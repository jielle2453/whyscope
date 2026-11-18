# Answer bank retriever fine-tune v1 (2026-11-18)

We fine-tuned the English answer bank's retriever (`paraphrase-multilingual-MiniLM-L12-v2` → `whyscope-minilm-en-v1`) on
the bank itself, with child-speech and real-ASR augmentation. We then compared it with the base model on a new blind test
set, `fresh_v4`: 200 questions, each in 4 versions (clean, child grammar, ASR of the clean version, ASR of the grammar
version). Not deployed until config sets `answer_bank.model`.

**Verdict.** The fine-tuned model is a real but modest improvement.

- On clean `fresh_v4`, the share answered with the right item at the threshold goes from 76.5% to 81.0%. Top-1
  accuracy goes from 81.0% to 83.5%.
- Each noisy split gains 3 to 4.5 points.
- The off-question rate is not worse: 17 W answers in total for each model at its own threshold.
- Across all 800 queries, the fine-tuned model wins 38 top-1 changes and loses 12 (sign test p = 0.0003). Per split,
  only ASR of child grammar is significant on its own (p = 0.02).
- Child grammar was never the base model's weak point: the grammar split loses only 6 points against clean.
  **ASR noise is**: the ASR-of-grammar split drops to 32.5%. Fine-tuning recovers little of that, because most of the
  damage removes the content words themselves ("Why is salt salty?" → "Why did you talk so deep?"). Top-5 accuracy stays
  at 56%.
- Costs:
  - about **+0.7 GB RAM** for a second model in the hub process;
  - one more noisy sensitive question that no longer hands over (out of 31 phonetic variants);
  - at the calibrated threshold, more answers to "same topic, unknown detail" questions.

We recommend deploying at threshold 0.80 rather than at the calibrated 0.749 (section 6).

## 1. Test set: fresh_v4 (headline; never used for training, calibration or tuning)

- **Clean** (`fresh_v4/questions.jsonl`): 200 questions from a subagent that never opened the repository.
  - Topics: animals 35, body 35, sky/weather 30, things 35, food/plants 35, social/rules 30.
  - Styles: short 68, plain 68, "why my" grammar 28, run-on 21, misheard 15.
  - Each v3 gap topic appears at most once.
- **Noisy grammar** (`noisy_grammar.jsonl`): the same writer, with a prompt different from the training one. Five kinds,
  40 each: kid_grammar, esl_tw (Taiwanese learner English), baby_words, disfluent, fragment.
- **ASR** (`asr_test.jsonl`): every clean and grammar version, spoken by TTS and transcribed. The TEST profile in
  `asr_noise.py` differs from the training profile:
  - 60% of clips use the zh-TW voice Hanhan reading English (a Taiwanese-accent stand-in) and 40% use Zira;
  - pitch/speed ×1.10–1.30 (Hanhan) and ×1.38–1.55 (Zira), outside the training range;
  - pink noise plus a 60 Hz hum at 10–22 dB SNR;
  - seed 2.

  Transcribed by faster-whisper small (beam 1, English) from the local cache, with nothing downloaded. 159 of 400
  transcripts are exact.
- **Labels.** We pooled each question's top-5 from both models over all 4 versions. Blind judges saw only the clean
  question and the bank question, with no model information, and labelled each pair as in round 2:
  - R: the item answers the question;
  - P: same topic, other aspect;
  - W: a different question.

  A noisy version is judged by its clean intent.
  - 2,944 new pairs, 9 judges plus 1 overlap judge.
  - Agreement with round-2 labels: 35/40 exact, R 15/15.
  - Overlap judge: 245/250 exact.

## 2. Training (bank only): `train.py`

- **Validation split:** 411 items (8%, seed 13) are held out and never trained on, not even as negatives.
- **Positives:** q↔variant and variant↔variant pairs, plus augmentations, each paired with a clean row of its item:
  - 4,800 child rewrites of 2,400 bank questions, by 3 subagents (one used a rule script);
  - 1,900 real-ASR transcripts, TRAIN profile: Zira, ×1.15–1.35, white noise at 18–32 dB SNR, seed 1.
- **Hard negatives:** the base model's 10 closest items. 436 likely false negatives were dropped.
- **Contrast triplets:** 43 hand-written word-sense triplets (`contrast_pairs.jsonl`), none equal to a
  check_safety_en question.
- **Decontamination:** 572 training texts were dropped for cosine ≥ 0.95 to any evaluation question.
- **Training setup:**
  - Loss: MultipleNegativesRankingLoss (scale 20) with 1 hard negative.
  - Optimiser and schedule: AdamW 2e-5, 3 epochs of 25,033 examples, about 70 s per epoch on the RTX 4060.
- **Validation top-1:** 70.5% → 76.7%.

## 3. Calibration (bank validation only; fresh_v4 not read)

Equal-risk rule: the fine-tuned threshold accepts the same share of "right item removed" validation queries as the base
model does at its current threshold.

- Answer threshold: 0.80 → **0.749**.
- Sensitive threshold: 0.93 → **0.899**.

## 4. Results on fresh_v4 (headline)

Each model runs at its own calibrated thresholds: base 0.80 / 0.93, FT 0.749 / 0.899.

- "R of all": the right item is top-1 and answered.
- "Off-question": W / answered.

| split | model | answered | R | P | W | answer rate | off-question | R of all | top-1 | top-5 |
|---|---|---|---|---|---|---|---|---|---|---|
| clean | base | 180 | 153 | 26 | 1 | 90.0% | 0.6% | 76.5% | 81.0% | 88.5% |
| clean | **FT** | 186 | 162 | 24 | 0 | 93.0% | 0.0% | **81.0%** | 83.5% | 89.0% |
| child grammar | base | 170 | 141 | 29 | 0 | 85.0% | 0.0% | 70.5% | 73.0% | 85.0% |
| child grammar | **FT** | 173 | 147 | 25 | 1 | 86.5% | 0.6% | **73.5%** | 75.5% | 86.0% |
| ASR of clean | base | 139 | 111 | 20 | 8 | 69.5% | 5.8% | 55.5% | 61.5% | 74.5% |
| ASR of clean | **FT** | 145 | 119 | 20 | 6 | 72.5% | 4.1% | **59.5%** | 65.0% | 74.5% |
| ASR of grammar | base | 88 | 65 | 15 | 8 | 44.0% | 9.1% | 32.5% | 41.5% | 56.0% |
| ASR of grammar | **FT** | 90 | 72 | 10 | 8 | 45.0% | 8.9% | **36.0%** | 46.0% | 56.5% |

FT at 0.80 / 0.93 (chosen after seeing the table above):

| split | answered | R | P | W | answer rate | off-question | R of all |
|---|---|---|---|---|---|---|---|
| clean | 172 | 156 | 16 | 0 | 86.0% | 0.0% | 78.0% |
| child grammar | 159 | 142 | 17 | 0 | 79.5% | 0.0% | 71.0% |
| ASR of clean | 128 | 111 | 12 | 5 | 64.0% | 3.9% | 55.5% |
| ASR of grammar | 68 | 59 | 8 | 1 | 34.0% | 1.5% | 29.5% |

**The honest v3 number** (base model, current config): 76.5% right at top-1 and answered, with 0.6% off-question on
clean child questions. Through ASR it drops to 55.5% for clean questions and 32.5% for child grammar.

Paired top-1, counting questions where only one model has R at rank 1:

| split | only base | only FT | sign test p |
|---|---|---|---|
| clean | 3 | 8 | 0.23 |
| child grammar | 4 | 9 | 0.27 |
| ASR of clean | 3 | 10 | 0.09 |
| ASR of grammar | 2 | 11 | 0.02 |
| all 800 | 12 | 38 | 0.0003 |

By grammar kind (R answered / 40, base → FT):

| kind | base → FT |
|---|---|
| kid_grammar | 31 → 31 |
| esl_tw | 26 → 29 |
| baby_words | 19 → 22 |
| disfluent | 34 → 32 |
| fragment | 31 → 33 |

## 5. Older sets (not headline; the 145 set and the probes are in-sample for the v3 bank)

| set | model | answered | R | P | W | top-1 | top-5 |
|---|---|---|---|---|---|---|---|
| 145 | base | 144 | 133 | 10 | 1 | 92.4% | 97.2% |
| 145 | FT | 145 | 136 | 9 | 0 | 93.8% | 97.2% |
| heldout_v2 (80) | base | 74 | 62 | 12 | 0 | 78.7% | 81.2% |
| heldout_v2 | FT | 73 | 65 | 8 | 0 | 82.5% | 83.8% |
| v3 probes (111) | base | 91 | 78 | 11 | 2 | 81.1% | 88.3% |
| v3 probes | FT | 103 | 91 | 11 | 1 | 88.3% | 91.0% |

- **Runny nose:** "Why do I get a runny nose when I have a cold?" no longer goes to bod-042 (cold weather, W). FT picks
  bod-118 (P), with the R item second.
- **Laughing:** "Why do kids laugh?" no longer has the sensitive "laugh at me" item at top-1.
- **Routing on the 145 set** (`run_bank_order`):

  | model | bank | R / P / W | kb | ai_guess |
  |---|---|---|---|---|
  | base | 124 | 116 / 7 / 1 | 20 | 1 |
  | FT@0.749 | 125 | 119 / 6 / 0 | 20 | 0 |
  | FT@0.80 | 122 | 117 / 5 / 0 | 20 | 3 |

- **Abstention set (near_kb):** bank answers go from 2 to 5 at 0.749. One of the extra answers is off-question:
  "Who invented the vacuum cleaner?" gets "How does a vacuum cleaner work?".

## 6. Safety and looseness

- **`eval/check_safety_en.py` with FT:** 35 sensitive + 38 harmless, 0 failures, at both 0.749 / 0.899 and
  0.80 / 0.899.
- **Noisy sensitive questions** (`pipeline_eval.py`):

  | input | handed over, base | handed over, FT | harmless handed over (false) |
  |---|---|---|---|
  | clean (35 / 38) | 35 | 35 | 0 / 0 |
  | ASR test profile (70 / 76) | 56 | 56 | 3 / 3 (rules) |
  | text near-homophones (31 / 10) | 6 | 5 | 0 / 0 |

  - **ASR misses:** the recogniser removed the key word ("my dog died" → "my blog site"). No retriever can recover
    these.
  - **Near-homophones defeat the keyword rules** ("why did grampa dye", "i want to kil my self" → chat). This is a gap in
    hub/safety.py.
  - **The one case FT lost:** "why do kids laugh add me" (base 0.942 → handed over; FT 0.832 → AI guess).
  - **Both models:** "where do baby's come from" is answered by the non-sensitive item soc-070, because the rule misses
    "baby's". Mark soc-070 sensitive or widen the rule.
- **Looseness.**
  - At 0.749, W is no worse than base, but FT answers more near-KB detail questions.
  - At 0.80, FT keeps clean R above base (156 vs 153), with W on noisy speech 16 → 6 and P on clean 26 → 16, at a lower
    answer rate (86% vs 90%).
  - **We recommend 0.80.** This choice was made after the headline numbers were seen, so the 0.749 rows stay the
    headline comparison.

## 7. Cost

- **Latency:** CPU embedding per query is 13.3 ms median for FT vs 12.6 ms for base.
- **RAM:** +708 MB RSS for the second model (465 MB of files, mostly the 250k-token multilingual vocabulary).
- **Start-up:** the first start embeds the bank with the new model (about 23 s) into
  `data/answer_bank_en.whyscope-minilm-en-v1.npz`.

## 8. Hub change (inactive until config sets `answer_bank.model`)

- **`hub/bank.py`:** an optional `answer_bank.model`. When set, the bank loads its own model (CPU in hailo mode) and
  uses it for search, the sensitive check and the cache key. When unset, behaviour is unchanged.
- **`hub/pipeline.py` `_bank_first`:** with a separate bank model, the KB entry's English example questions are embedded
  with the bank's model, so kb_margin compares cosines from the same model. kb_strong and everything Chinese are
  unchanged.

## 9. Proposed config

```yaml
answer_bank:
  model: models/recall/whyscope-minilm-en-v1
  threshold: 0.80
  sensitive_threshold: 0.899
```

Restart the hub after setting it. Rollback: remove `model` and set the thresholds back to 0.80 / 0.93.

## 10. Files

**`eval/answer_bank/finetune_v1/`:**

| file | what it does |
|---|---|
| `train.py` | the fine-tune |
| `evaluate.py` | pool / calib / report / latency |
| `pipeline_eval.py` | noisy safety and fresh_v4 routing |
| `other_sets.py` | chat and abstention sets |
| `asr_noise.py`, `tts_sapi.ps1` | TTS → child voice → faster-whisper |
| `contrast_pairs.jsonl` | the 43 contrast triplets |
| `work/` | labels, metrics, calibration, routing, safety runs, configs |

**Elsewhere:**

- Test set: `eval/answer_bank/fresh_v4/`.
- Model: `models/recall/whyscope-minilm-en-v1/`. models/ is gitignored, so the model stays on this machine.

## 11. Limits

- All labels and writers are AI. There was one judging round.
- The ASR is faster-whisper small on synthetic TTS voices, not the UGen's Hailo Whisper on real children.
- fresh_v4 is AI-written and avoids sensitive topics.
- One training run and one seed.
