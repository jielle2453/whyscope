# On-device selector over the answer bank (Qwen2.5-1.5B on the UGen300), 2026-11-18

Can the device LLM look at a child's question and the top-k retrieved bank items, and pick the one that answers it or say "none"?
Labels: the single-judge R/P/W labels of report_v2.md (R = answers the exact question, P = same topic other aspect, W = different
question). One run at temperature 0.1 with a fixed seed. All calls used `priority: "low"`, ran sequentially, and were preempted 0 times.

**Candidates:** the earlier v2 bank (5,090 items, `bank_en_v2.jsonl`, `retrieval_top_v2.json`). The labels and the big-AI prototype
refer to that bank, so they stay comparable. The hub now runs bank v3 (5,139 items), so its live top-5 can differ slightly.

## Setup
- **Worker:** LLM `sha256_0856a10c…` (Qwen2.5-1.5B hailo-ollama blob), plus Whisper-Small, yolov8s and CLIP image.
- **Prompt (variant C, frozen on dev):**
  - The system prefix is fixed: a short instruction ("pick the list question that means the same; same topic is not enough; else 0")
    plus 3 invented few-shot turns. The worker saves it once as a device context.
  - The turn is `Child: <q>` followed by the k candidate questions, numbered, in retrieval order.
  - One generated token, a digit; 0 = none. There were 0 invalid outputs.
- **Dev slice (tuning only; none of it is in the test set):** 32 questions from `eval/heldout_en_v2.jsonl`, labelled by hand, plus 10
  synthetic no-fit cases.
  - A (longer instruction): answered "1" 29 of 42 times. That is position bias.
  - B (+ the first 9 words of a1): +0.5 s per call, and mostly answered "0".
  - C: 16/27 right picks, 9/15 right "none".
- **Test set:** the 145 labelled questions (heldout_en_v3 + guess_fresh_en). This is also the routing set of `eval/run_bank_order.py`.
  Through the hub pipeline on CPU they route to kb 22, bank 116 (R 90 / P 23 / W 3), ai_guess 7, and all checks pass.

## Results on 145 questions
| policy | answered | R | P | W | R share of all | off-question share (W / answered) | selector calls |
|---|---|---|---|---|---|---|---|
| (a) threshold only, T = 0.80 (today) | 137 (94%) | 106 | 28 | 3 | 73.1% | **2.2%** | 0 |
| threshold only, T = 0.85 | 121 (83%) | 102 | 16 | 3 | 70.3% | 2.5% | 0 |
| threshold only, T = 0.88 | 106 (73%) | 93 | 12 | 1 | 64.1% | 0.9% | 0 |
| always top-1 | 145 | 107 | 34 | 4 | 73.8% | 2.8% | 0 |
| device selector, k=5, every question | 107 (74%) | 93 | 13 | 1 | 64.1% | 0.9% | 145 |
| device selector, k=5, when top-1 ≥ 0.80 | 105 (72%) | 92 | 12 | 1 | 63.4% | 1.0% | 137 |
| **(b) gray zone, k=5: top-1 ≥ 0.88 answered, 0.70–0.88 → selector** | **120 (83%)** | **103** | **16** | **1** | **71.0%** | **0.8%** | 38 (26%) |
| (b) gray zone, k=3 (same split) | 120 (83%) | 103 | 16 | 1 | 71.0% | 0.8% | 38 |
| (b) gray zone, k=5: ≥ 0.92 answered, 0.70–0.92 → selector | 114 (79%) | 100 | 13 | 1 | 69.0% | 0.9% | 64 |
| (c) big-AI prototype, every question | 124 (86%) | 116 | 8 | 0 | 80.0% | 0.0% | 145 |
| (c) big-AI prototype, when top-1 ≥ 0.80 | 120 (83%) | 113 | 7 | 0 | 77.9% | 0.0% | 145 |
| (c) big-AI prototype, same gray zone 0.70–0.88 | 128 (88%) | 113 | 14 | 1 | 77.9% | 0.8% | 38 |

### Selector outcomes, k=5, no threshold (145 questions; 119 have an R somewhere in the top 5)
| | device (C) | big-AI prototype |
|---|---|---|
| correct pick (R) | 93 | 116 |
| wrong pick: off-question (W) | 1 (no R in the top 5) | 0 |
| wrong pick: same topic (P) | 13 (7 with no R in the top 5) | 8 (7 with no R) |
| correct "none" (no R in the top 5) | 18 | 19 |
| missed answer ("none" although an R is in the top 5) | **20** | 2 |
| picked rank 1 / 2–5 / none | 95 / 12 / 38 | – |

Agreement with the prototype: 108 of 145. k=3 gives almost the same picks: R 93, P 14, W 1, 20 missed.

### What the gray zone does (38 questions with top-1 between 0.70 and 0.88; k=5 and k=3 identical)
| top-1 label in the zone | count | selector result |
|---|---|---|
| W (f-040 moon/sea 0.854, f-058 letters 0.856) | 2 | **both vetoed** |
| R | 14 | 8 kept, **6 lost** ("none") |
| P | 20 | 16 "none", 2 **upgraded to R** (rank 2–5), 2 kept as P |

**Against T = 0.85** (about the same number of answers): R is +1, W goes from 3 to 1, and P is the same.

**Against T = 0.80:** 17 fewer answers, R −3, P −12, W from 3 to 1. Off-question share falls from 2.2% to 0.8%.

The remaining W is v3-009, "runny nose when I have a cold", which matches "nose runs when I am cold" at 0.918. It sits above the gray
zone, and the selector kept it there too: it is a word-sense error in a variant of a frozen item, best fixed in the bank.

## Latency (test calls, worker ms, including the queue and the per-call context load)
| | mean | median | p90 | max | turn |
|---|---|---|---|---|---|
| k=5 | 1,260 ms | 1,221 ms | 1,395 ms | 3,225 ms (first call: prefix prefill) | ~270 chars |
| k=3 | 1,261 ms | 1,229 ms | 1,402 ms | 1,543 ms | ~197 chars |
| dev B (k=5 + a1) | – | 1,679 ms | 1,698 ms | – | ~554 chars |

- **What the time is made of:**
  - The worker loads the saved prefix context on every call: about 0.8 s (/info load_s 0.75–0.99 s).
  - Prefill of a ~70-token turn plus one token is about 0.4 s.
  - k=3 saves nothing measurable. Adding a1 text costs +0.5 s.
- **The next child call pays no extra reload.** The hub's own calls also load their context per call, so the ~0.8 s reload is already
  inside each selector call and is not added after it.
- **Child path:** a bank answer today takes about 10 ms. In the gray-zone design, 26% of questions (38 of 145) get **+1.2 s median,
  +1.4 s p90**, more when a child request is already queued. The other 74% are unchanged.

## Recommendation
- **Prompting is good enough for one narrow job:** a veto in a gray zone (0.70–0.88).
  - It vetoed both in-zone W, upgraded 2 P to R, and lost 6 R.
  - Net, it matches a T = 0.85 threshold on R with a third of the off-question answers (0.8% vs 2.5%).
  - Cost: +1.2 s on about a quarter of bank questions.
  - The gain is small (2 W on 145) and rests on one run, so ship it only if 2% off-question answers is judged a real problem. A
    threshold of 0.85–0.88 alone gets most of the way at zero latency.
- **As a re-ranker or a general selector, prompting is not good enough.**
  - It misses 20 of the 119 available R answers, against 2 for the prototype.
  - It mostly picks rank 1: dev variant A picked rank 1 29 of 42 times, and C with k=5 on test picked it 95 of 145 times.
  - It found rank-2–5 answers in only a handful of cases.
- **Fine-tuning has measurable headroom.**
  - The prototype reaches R 116 with W 0, against the device's 93 / 1 and today's 106 / 3. The ceiling is 119 R in the top 5.
  - A fine-tuned 1.5B selector that got near the prototype would raise R from 73% to about 78–80% while removing off-question answers.
  - That is the only path to the re-ranking gain, but every call would still cost about 1.2 s.
  - It is worth a small trial (the training pairs exist: judge labels on question × top-5) if the team wants coverage above 73% R.
  - Otherwise, more bank items (the 26 gaps in report_v2.md) are the cheaper lever.

## Soak test (USB failure)
- **First run (earlier today):** 146 calls were fine. Then, from 15:01:41, every `/complete` failed with HAILO_LIBUSB_FAILURE (98), and
  the run stopped after 20 of 290 test calls. hailort.log shows LIBUSB errors at 15:01–15:04, 15:26–15:27 and 15:53, all before this
  run.
- **This run:**
  - Started 2026-11-18 15:55:07 and ended 16:00:51 (5 min 44 s).
  - **270 selector calls**: the k=5 calls not already made plus all 145 k=3 calls. 416 calls in all, counting the earlier run.
  - **503s: 0.** Preemptions: 0.
  - **health.recoveries: 1 before, 1 after.** The 1 is the POST /recover at about 15:54. State was ok at the start and at the end.
  - **No LIBUSB or COMMUNICATION_CLOSED line in `repo/hailort.log` after 15:55:07.** The last one is at 15:53:08.
    `%LOCALAPPDATA%\Hailo\HailoRT\hailort.log` has none since 2026-11-15.
  - No real USB failure recurred, so the self-recovery was not exercised by this run.
- Health snapshots and any 503s are logged in `selector_ondevice_soak.jsonl`.

## Caveats
- One AI judge and one run. The P/W line moves between judges, so trust R and W counts more than P.
- The test questions are AI-written. Some appear nearly verbatim in the bank (report_v2.md caveats).
- The dev slice is small (42 cases) and was labelled by the evaluator. Only 3 variants were tried, and none were tuned on test.
- The prototype saw the candidates in random order; the device saw them in retrieval order. That is realistic for the hub, but the
  order helps the device's rank-1 bias.

## Files (eval/answer_bank/)
- `selector_ondevice.py`: stages dev / test / report; resumable call cache; low priority; 503 handling.
- `selector_ondevice.json`: all tables, the confusion matrix, latency, prompts, /info and per-question picks.
- `selector_ondevice_calls.jsonl`: 416 raw calls.
- `selector_ondevice_dev.json`: dev top-5.
- `selector_ondevice_soak.jsonl`.
