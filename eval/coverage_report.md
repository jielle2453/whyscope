# Coverage experiment: curated entries vs. a Wikipedia reference corpus rewritten on the UGen300

Date 2026-11-14. Scripts: `eval/coverage_proto.py` (prototype), `eval/coverage_analyze.py` (tables).
Data: `eval/kid_questions.jsonl` (100 questions), `eval/coverage_results/hub_results.jsonl`,
`eval/coverage_results/proto_results.jsonl` (raw model output kept for every question),
`eval/coverage_judgments.json` (every verdict used below).

## Method in one paragraph

100 synthetic kid "why" questions (50 zh-TW, 50 en; 10 categories x 5 per language; about 5 odd ones per language) were
written **before** looking at `knowledge/entries`. (1) The running hub (hailo mode, UGen300 worker) was called with
`POST /api/ask?wait=1 {text, lang, age: 7}`. (2) For the prototype each question was turned into keywords, searched on
simple.wikipedia.org / zh.wikipedia.org (`variant=zh-tw` plus opencc s2twp), the intro extracts of the top 3 usable hits
were fetched (cached, about 1 request/s), the 3 most relevant sentences of the best hit were picked (multilingual
MiniLM cosine + keyword bonus), and the UGen300 (`POST /complete`, ChatML, zero-shot, `max_new` 80 en / 90 zh, stop after
3 sentences) was asked to answer "in at most 3 very short sentences using ONLY the passage". Checks from `hub/wording.py`
plus a grounding check were applied; raw output was always kept.

## Headline numbers

"Correct" = judged **right** for THIS question (partly-right answers are counted separately, never as correct).
Percentages are of all 50 questions in the language.

### Chinese (zh-TW, n = 50)

| | Current hub | Prototype (Wikipedia + UGen300) |
|---|---|---|
| Answered / produced an answer | 28 (56%) | 45 (90%) produced an answer, 5 were "I don't know" |
| Relevant passage found (extract really contained the answer) | n/a | 16 (32%) |
| Correct | 22 (44%); 79% of what it answered | 10 (20%); +11 partly right |
| Wrong / off-topic or false | 6 wrong; 2 flagged sensitive; 20 abstained | 24 wrong; 16 answers contain a false statement |
| Usable after the hub's voice checks | (by construction) | strict (hub rules, 18 chars/sentence, 60 total, rare chars, grounding ratio): **0 (0%)**; looser (no length caps, only the hub's "each sentence shares a content word with the passage"): 33 (66%), of which only 7 right, 9 partly, 17 wrong |
| Factual-error answers | 0 seen | 16 |
| Latency p50 / p95 | 4.2 s / 5.5 s (full answer, 12 of 28 composed by the LLM, rest template fallback); first sentence about 10 ms | model only 7.0 s / 15.3 s; with 2 Wikipedia requests 11.7 s / 19.4 s |

### English (n = 50)

| | Current hub | Prototype |
|---|---|---|
| Answered / produced an answer | 27 (54%) | 39 (78%) produced an answer, 9 were "I don't know", 2 had no passage at all |
| Relevant passage found | n/a | 11 (22%) |
| Correct | 24 (48%); 89% of answered; +2 partly | 13 (26%); +17 partly right |
| Wrong | 1 wrong; 1 sensitive-flagged; 22 abstained | 9 wrong; 11 answers contain a false statement |
| Usable after checks | | strict: **0 (0%)**; looser: 15 (30%), of which 9 right, 2 partly, 4 wrong |
| Latency p50 / p95 | 4.1 s / 5.6 s | model only 7.8 s / 12.1 s; with Wikipedia 10.3 s / 19.6 s (wiki fetch alone p50 1.8-2.9 s) |

### Both languages (100 questions)

* Current hub: 55 answered, **46 correct**, 2 partly, 7 wrong, 3 "sensitive" deflections (2 of them false positives, see below), 42 abstained.
* Prototype on its own: 23 correct, 28 partly right, 33 wrong, 14 "I don't know", 2 no passage. Zero of 100 pass the hub's voice rules.
* **Hub first, prototype as fallback** (only for questions the hub did not answer): the hub's 46 correct become 59 (zh 27, en 32 of 50 in the
  union, i.e. +5 zh, +8 en). 10 of the 13 added answers came from questions whose retrieved passage did not contain the
  answer, i.e. the 1.5B model answered from its own memory. Those 13 would have to be accepted without grounding.
  If only answers backed by a relevant passage are accepted, the gain is +4 zh and +6 en (about 10 questions) and every one would still
  need the child-voice rewrite to pass the voice rules.

## Reading the numbers

The hub is better than the "most questions are abstained" suspicion in this set: it answers 55% and is right 84% of the time it answers
(46/55; the 7 mistakes are listed below). The questions were written independently of the 93 entries and the entries clearly cluster on
weather, sky, body and food (4 to 5 of 5 answered in most of those), almost zero in earth/rocks (0/10 answered), and thin in water/physics,
animals and people/society (1 to 3 of 5). The abstained list is full of the most classic kid questions: why is the sea salty, why do boats float,
why does a ball come down, what is a volcano, why brush teeth, why is the Earth round.

The reference-corpus path as prototyped is **not** a drop-in fix: 22-32% of questions got a passage that actually contains the answer, and a
1.5B quantized model rewrote only about half of those correctly and not within the hub's voice limits.

## Breakdown by category

Counts out of 5 per language (zh / en). "passage" = relevant passage retrieved, "proto right" = prototype answer judged right
(ignoring voice checks). Strict voice checks passed 0 everywhere, so they are not shown.

| category | hub answered zh/en | hub right zh/en | passage ok zh/en | proto right zh/en | proto partly zh/en |
|---|---|---|---|---|---|
| animals | 3 / 2 | 1 / 1 | 1 / 0 | 0 / 0 | 1 / 3 |
| human body | 3 / 4 | 3 / 4 | 3 / 1 | 0 / 1 | 4 / 1 |
| sky/space | 4 / 3 | 2 / 3 | 1 / 1 | 0 / 2 | 1 / 2 |
| weather/nature | 5 / 5 | 5 / 5 | 3 / 1 | 3 / 0 | 0 / 1 |
| plants | 4 / 3 | 3 / 3 | 0 / 1 | 0 / 2 | 1 / 1 |
| food | 4 / 4 | 3 / 4 | 1 / 1 | 1 / 1 | 1 / 2 |
| everyday objects/machines | 3 / 3 | 3 / 2 | 0 / 1 | 0 / 1 | 2 / 4 |
| water/physics | 1 / 2 | 1 / 1 | 0 / 1 | 1 / 2 | 0 / 1 |
| earth/rocks | 0 / 0 | 0 / 0 | 4 / 1 | 3 / 1 | 0 / 1 |
| people/society | 1 / 1 | 1 / 1 | 3 / 3 | 2 / 3 | 1 / 1 |

The two approaches are complementary: the hub is strong where entries exist (weather, body, food), the corpus finds passages for
earth/rocks and people/society (everyday facts such as sea water, earthquakes, sand, brushing teeth, washing hands, money) where the hub has nothing.

## Failure types (counts across the 100 prototype answers; one answer can have several)

1. **Retrieval missed (no relevant passage): 73 of 100** (zh 34, en 39). Sub-causes seen:
   * Keyword search lands on a *proper noun or title that contains the words*, not the concept: zh 風吹純 (actress) for 風會一直吹, 草莓姐姐 (TV host)
     for 爆米花, 《來自星星的事》 (TV show) for 星星, ONE PIECE角色列表 for 球/石頭, 《錢在路上跑》 (film) for 錢; en *Plague doctor costume* for
     flowers smell, *Behind the Sun* (song) for the sun, *Chantico* (goddess) for cactus spikes, *Mony Mony* (song) for mirror, *L Taraval* (train line) for light switch.
   * Right article, **but the lead does not explain the "why"**: it defines the thing (Rain, Thunder, Wind, Sky blue, 天空藍, 冰箱, 向日葵, 檸檬).
     Wikipedia intros are definitions; kid "why" answers usually live in a later section or a different article (Rayleigh scattering, Why is the sea salty).
   * Zero hits at all: en "tummy growl", "wrinkly fingers" (no passage, nothing generated).
2. **Passage not kid-relevant / different sense**: Dead Sea for "Why is the sea salty", Open-wheel car for wheels, 躉船 (pontoon) for 船會浮, Kulfi for ice-cream melting,
   Kebab for bread rising, 熱橋 for winter/summer.
3. **Model wrong or invented even with a related passage**: reversed density (zh 船會浮: "船的密度大於水所以會浮", zh/en rock sinks: "water has higher density than rock"),
   fridge "cold on the outside and warm on the inside", bees "don't actually make honey", volcano "angry/tired of sleeping", zebra stripes "to look bigger".
   The model also answers from its own memory when the passage is useless (7 of the 23 right answers had an irrelevant passage).
4. **Model broke format/language rules** (visible in raw outputs): numbered lists "1. 2. 3." in zh (14 of 50), simplified characters in raw zh output, English answer with a
   Chinese translation appended (en-019), meta leakage ("The passage does not answer the question", "I don't know." appended after an answer, an echoed "Child's question: ...", "我說"),
   duplicated sentences (zh-017), 3 long sentences/lists up to 16.9 s of generation for one answer. Copying the passage verbatim (zh-019 rainbow, en-007 hiccups) is also common.
5. **Voice checks rejected a good answer**: strict checks pass 0/100. Of the 23 right answers, only 4 meet the 18-char / 12-word sentence limit,
   and 7 meet the rare-word/char limit. The grounding-ratio check (>= 60% of answer content words in the passage) rejects 88 of 100 and is itself questionable: right
   answers from the model's memory fail it correctly, but paraphrases of a relevant passage also fail it. So "checks rejected a good answer" is mostly the sentence-length rule
   (the model does not obey "at most 12 words / 18 characters"), plus a rewriter pass would be needed.

Check failure counts (zh / en of 50): sentence too long 36 / 32, rare chars/words 25 / 30, grounding 42 / 46, total over 60 chars / 45 words 14 / 6, too many sentences 3 / 0, language 0 / 1.

## Hub: what went wrong in the 7 wrong answers and 3 safety flags

* Wrong because the matched entry is only "related": zh 貓咪呼嚕 -> cat-eyes-glow; zh 狗狗吐舌頭 -> dog wags tail; zh 晚上有星星 -> stars twinkle; zh 太陽熱 -> sunflower;
  zh 樹葉秋天變黃 -> leaf-green; zh 吃辣流眼淚 -> tears; en "things fall down when I drop them" -> rain (confidence 0.657). Confidences were 0.56-0.72, all above the threshold,
  so tuning the threshold alone would also drop right answers (zh 夏天熱冬天冷 0.83 and en bread 0.66 are right at similar levels).
* Partly: en bees "make honey" (entry explains how, not why), en magnets "stick together" (answers "it has a pull").
* Safety false positives: zh 為什麼會有地震 and en "Why do earthquakes happen?" and zh 流血的地方會結痂 were deflected as `sensitive`. Earthquake science is a normal kid question; these are lost coverage.
* Chinese answers: 16 of 28 were the template fallback (`template(grounding)`), not the LLM (en 11 of 27), so the LLM's contribution is smaller than assumed.

## Examples (verbatim, answers as spoken or as raw model output)

### Chinese, good

| question | answer | verdict |
|---|---|---|
| 為什麼海水是鹹的？ | 海水鹹的原因是因為它含有大量的鹽分。這些鹽分在水中溶解，使海水的水份濃度增加，所以海水就變鹹了。 | right (passage said 35 g salt per litre; "鹽分濃度" fluff) |
| 為什麼沙子是一粒一粒的？ | 因為沙子是從大岩石中被分割出來的，所以它會分成一粒一粒的小粒子。 | right, grounded |
| 為什麼要刷牙？ | 1. 刷牙可以清除掉牙齿表面的细菌，保持口腔清洁。 2. 保持口腔卫生是维持身体健康的重要因素。 3. 每天刷牙可以帮助预防疾病。 | right but simplified chars and list format |
| 為什麼會下雨？ | 因為大氣中的水蒸紮凝結成液態的水珠，並受到重力和風力的作用而落向地表。 | right, but jargon and a garbled character (水蒸紮) |
| 為什麼紅燈要停綠燈才能走？ | 紅燈代表停止，綠燈代表通行。這是為了讓行人和車輛有秩序地通行，避免造成不必要的傷害。 | right, long sentences |

### Chinese, bad

| question | answer | verdict |
|---|---|---|
| 為什麼貓咪會呼嚕呼嚕叫？ | 因為貓咪在唱歌。 | wrong (passage was the lyrics of a TV show, 《軟軟貓咪》) |
| 為什麼船會浮在水上？ | 因為船的密度大於水，所以會浮在水上。 | wrong, factual error (reversed) |
| 為什麼冬天會冷夏天會熱？ | 因為地球的表面和地下是冷的，而天空是熱的。… | wrong, invented (passage was 熱橋, thermal bridge) |
| 為什麼流血的地方會結痂？ | 癌症和良性腫瘤是不同的。癌細胞分裂失控，侵犯正常組織，並轉移到其他部位。… | wrong and unsuitable for a child (retrieved 癌症); the hub flagged this question as sensitive |
| 為什麼錢可以買東西？ | 1. 《錢在路上跑》是天山電影製片廠攝製的輕喜劇電影。… | wrong (a film) |

### English, good

| question | answer | verdict |
|---|---|---|
| Why do we wash our hands? | Washing hands helps keep germs away. It's important to wash before touching food or cooking. Germs can make you sick if they get on your hands and then touch something else. | right, grounded; 3 sentences, passes loose checks |
| Why do plants need sunlight? | Plants need light to make food. Without it, they can't grow or survive. Sunlight is the most important thing for them. | right, short, kid-like |
| Why do things fall down when I drop them? | Because of gravity. When you drop something, it's pulled towards the ground by Earth's gravity. This is what makes objects fall down. | right (passage was about "drop"; model used its own knowledge) |
| Why do boats float? | Boats float because of the force called "buoyancy". … Boats are made to be lighter than water, so when you put them in water, they don't sink and stay afloat. | right (slightly imprecise, "lighter than water") |
| Why do I have to brush my teeth? | To keep your teeth clean. To help them stay healthy and strong. Because germs can make you sick. | right |

### English, bad

| question | answer | verdict |
|---|---|---|
| Why do bees make honey? | Bees don't actually make honey. They make something called nectar, which they turn into honey … I don't know. | wrong, factual error and leaked "I don't know." (passage joke about the scientific name) |
| Why does a rock sink in water? | Because water has a higher density than rock. … | wrong, reversed |
| Why does a cactus have spikes? | Chantico wore a crown of cacti spikes. She was the 'Lady of the chili pepper'. … | wrong, off-topic (Aztec goddess article) |
| Why do volcanoes erupt? | I don't know. Volcanoes are like big, angry volcanoes that erupt when they're upset or tired of sleeping. … | wrong, invents emotions |
| Why is the fridge cold inside? | A fridge is a machine that cools things. It has a heat pump which takes heat away from the air inside it, making it cold on the outside and warm on the inside. The passage directly answers this question. | partly: right passage, one false clause, meta leak |

## Caveats (please read)

* **Correctness was judged by me, an AI, not by a human expert or by children.** I judged each answer against my own world knowledge and
  the retrieved passage; borderline calls (right vs partly) are in `coverage_judgments.json` and can be flipped. No children were asked or tested.
* The 100 questions are **synthetic** (written by an AI, informed by the usual kind of public "kid why" lists), 50 per language, 5 per category per language;
  one-question differences move a category by 20 points. Differences of a few questions between hub and prototype are within noise.
* Prototype retrieval is the crudest reasonable version: keyword extraction + the Wikipedia search API + lead sections only.
  A prepared local corpus with better chunking and dense retrieval would do better; this is a lower bound for retrieval, not a ceiling.
* The prompt is zero-shot, one try per question (temperature 0.1 as in the worker config). A few-shot prompt, a JSON prefill (as the hub does) or a second
  pass for format would change the format failures. The first run had 3 HTTP 429 errors from Wikipedia (rate limit) which were rerun; the cached
  responses are what produced the final numbers.
* Wikipedia was **fetched online** for the prototype (generic User-Agent, no personal data, about 1 request/s, cached). A real product would use a local snapshot, and its license (CC BY-SA) needs the same attribution handling as the entries.
* The hub run called the live server, so the 100 test questions are now **logged as events** in the hub's database (the parent page will show them, and
  `memory.note_asked` was updated). The `age` field is not read by `/api/ask` (the server uses the memory's child age), so the "age 7" parameter had no effect.
  Latency of the hub includes whichever queue position the UGen300 had; the prototype ran sequentially after the hub run, with nothing else hitting the worker.
* Hub numbers use the question's whole text; the hub's behavior on spoken/ASR questions is not measured here.

## Recommendation

**The corpus approach is worth continuing, but not as "retrieve a Wikipedia lead and let the 1.5B model rewrite it" on its own.** With the current
setup only 22-32% of questions got a passage that contains the answer, only 4/100 of the answers meet the hub's own voice limits, and 27 of 100 answers contain a false statement
(three of them reversing a physical fact): that cannot be shown to a child without a human-checked layer. What the experiment does show:

1. **Growing the curated set is the cheaper way to coverage.** Most missing questions are classic and repeat across kids (sea salt, boats, gravity, volcanoes, tooth brushing, round Earth, Why leaves change color).
   The hub's 84% precision when it answers is a real asset. 20 to 30 more entries across earth/rocks, water/physics and people/society would raise hub coverage by roughly 15 points in this set.
   Use the corpus as an **authoring aid** (retrieve, draft in child language, a human reviews and signs off), not as a run-time answerer.
2. **If a run-time corpus path is wanted, change what is retrieved and what the model does:**
   * retrieve with a question-aware dense retriever over a prepared corpus of passages that **explain** (a "why/how" subset, kids' encyclopedias, Simple English Wikipedia body sections,
     not only the intros), chunked by section; keep only answers whose passage cosine to the question is high (best_cos values of the relevant passages here were mostly above 0.6,
     the irrelevant ones mostly below, with exceptions such as 0.861 for the song lyrics);
   * constrain generation harder: JSON/sentence prefill as in the hub, 1-2 few-shot examples, no lists, single short sentence, Traditional output enforced, and
     refuse ("ask a parent") when the passage does not name a cause. The model already says "I don't know" 14 times; the checks should treat that as an abstain, which is correct behavior;
   * reuse the hub's novelty and no-new-knowledge checks (which exist for the entries) instead of the loose grounding ratio, and treat the 12-word / 18-character rules as a hard
     truncate-and-re-ask loop rather than a post-filter;
   * cost: this adds 7-8 s of generation per answer (p50) on the UGen300 versus 4 s for the current hub answer, so the first sentence must be spoken immediately from the passage or be a template.
3. **Fix the hub's own near-miss problem at the same time**: all 7 of its mistakes were related-but-wrong-entry matches at confidence 0.56-0.72 (one at 0.657 for gravity vs rain); a "does the entry's labels/facts actually mention the question's key noun"
   check, and un-flagging common science topics such as earthquakes in the sensitive rules, are cheap improvements.
4. **Next measurement to run**: a human-reviewed pass (a parent or teacher) on the same 100 answers, and a rerun with a few-shot prompt plus section-level retrieval, before deciding on any corpus work.
