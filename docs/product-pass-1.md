# Product pass 1 — make it feel like a real product (spec)

Goal: the prototype works; now it must feel like Whyscope the product. Three themes:
(A) answers sound like a kind adult talking to a 5–8-year-old, (B) the first sentence is spoken almost
instantly, (C) the parent page is visual, mostly pictures and numbers, very few words, phone-first.
Keep everything on-device, no CDNs, no cloud, Traditional Chinese (Taiwan).

## A. Child-appropriate answers (hub/compose.py, hub/pipeline.py, knowledge entries untouched)

1. **Voice of Whyscope**: warm, curious, concrete, short. Rules enforced in code, not just in the prompt:
   - Every sentence ≤ 18 Chinese characters; explanation ≤ 2 sentences; total spoken text ≤ 60 characters.
   - Use everyday words only. Reject any explanation containing characters outside a "grade 1–2 friendly"
     filter: implement `hub/wording.py` with (a) a banned-term list (科學術語: 分子, 原子, 反射, 折射, 光譜, 細胞, 蛋白質,
     氧化, 電磁, 密度, 壓力, 蒸發, 凝結, 波長, 能量, 磁場, 細菌, 病毒, 神經, 器官, 酸鹼, 氣壓 …) with a
     replacement map to plain phrases (反射→彈回來, 蒸發→變成水氣飛走, 細菌→很小很小的小蟲蟲 …), and (b) a
     max of 2 characters per sentence not in a bundled list of ~1,500 common characters (`hub/data/common_chars.txt`,
     built from the entries themselves + the digits/punctuation; if a reliable 教育部 list is not available offline,
     build it from all text in knowledge/entries and a hand-written list of 300 everyday characters).
   - Tone: start with a short reaction only sometimes (每 3 題最多 1 次): 「好問題！」「哇，你有注意到耶！」; never flattery
     of the child ("你好聰明"); never "我覺得" / "我喜歡" / feelings of the device; never ask about the child's
     day, feelings, family or friends (block list in `safety.py`: 今天, 開心, 難過, 爸爸媽媽有沒有, 朋友, 學校 in ask_back).
   - Age adaptation from memory `child_age`: 5–6 → 1 explanation sentence, concrete comparison ("像你的雨衣");
     7–8 → 2 sentences, may include one "因為…所以…".
   - Bridges: if a bridge key exists in memory, prefer the entry's bridge as the ask-back (≤ 1 in 2 questions).
   - Ask-back must be guessable (yes/no or two choices) — enforce by pattern: contains 「嗎」「還是」「猜」 or 「你覺得」.
2. **Prompt**: rewrite the Qwen prompt with 3 few-shot examples in the Whyscope voice, JSON output, and the
   rules above. Grounding check stays strict; on any failure fall back to template text produced by a
   deterministic `template_explanation(entry, age)` that picks facts[0] (+ facts[1] for 7–8) and rewrites
   with the replacement map.
3. **Speech**: in kid.html pick a zh-TW voice (prefer names containing "HsiaoChen", "HsiaoYu", "Hanhan", "Yating",
   "Taiwan"), rate 0.9, pitch 1.05; split into sentences and speak sequentially; highlight the sentence being
   spoken.

## B. First sentence instantly (API change, keep backward compatible)

- `POST /api/ask` returns as soon as recall/safety is done: `{..., "first_sentence", "status", "pending_id"}`
  with `explanation`/`ask_back` possibly empty and `"pending": true`. The compose step runs in a background task.
- `GET /api/ask/{pending_id}` returns the completed fields (`"pending": false`) or 202-style `{"pending": true}`.
- kid.html: speak `first_sentence` immediately, poll every 300 ms up to 8 s for the rest, then speak explanation
  and ask_back. The event row is written at the first phase and updated in the second.
- Latency fields: add `first_sentence_ms` (time from request start to first-phase response). Update
  `eval/run_latency.py` to report it. Target ≤ 300 ms for text, ≤ 1,000 ms for voice.

## C. Kid page (hub/static/kid.html) — product feel

- Full-screen, phone and tablet first (portrait), min touch target 72 px. Palette: deep navy #1F2A44, warm cream
  #FBF8F2, orange #F28C28, sky #2E86AB; rounded 24 px; Noto Sans TC via local system font fallback (no CDN).
- Header: a simple inline-SVG magnifying-glass logo + "好奇鏡"; a small green dot "已連線" from /healthz.
- One big mic button with three states and animation: idle (soft pulse), listening (ring expands with level
  meter from the mic stream), thinking (three bouncing dots). Text box stays below, smaller.
- Answer card: object emoji (map topic/labels → emoji: 蝸牛🐌 貓🐱 狗🐶 彩虹🌈 … default by topic 🐾🌱🌤️🧒⚙️🍎),
  first sentence in 40 px bold, explanation 28 px, ask-back in orange with a "你猜猜看" badge, two big buttons
  「再說一次」「換一個問題」. Sentences fade in as they are spoken.
- Abstained state: friendly illustration (inline SVG shrug or question mark) + "我們一起去問大人". Sensitive state:
  same look, softer colour, no details.
- Camera toggle keeps working; show a 120 px thumbnail of the captured frame for 2 s then discard (never persist).

## D. Parent page (hub/static/parent.html) — visual, few words, phone-first

Design rule: every screen must be understandable in 5 seconds with the text hidden. Numbers big, words small.
No CDNs; charts are inline SVG drawn by JS.

- **Top bar**: logo, child name (from memory; "我的孩子" if unset), device status dot.
- **Bottom tab bar** with 4 icons + 1-word labels: 本週 / 紀錄 / 小抄 / 孩子（孩子的世界）; 設定 behind a gear icon top-right.
- **本週**:
  1. Hero: one big number "23" with "個為什麼" and a 7-day sparkline (SVG) of questions per day; a tiny
     "比上週 +5" chip only if last week has data.
  2. Topic donut (SVG) with emoji legend (🐾 動物 9 · 🌤️ 天氣 6 …); tap a slice to filter 紀錄.
  3. "可以聊聊看" as a horizontal swipe of 3 cards: emoji, the object name big, the ask-back line, a one-tap
     「聊過了 ✓」 that marks the event (new `POST /api/events/{id}/talked`).
  4. "我答不出來" as a short list with emoji ❓ and the question, each with 「聊過了 ✓」.
  5. "用過的例子" as chips (🐶 用你家的狗解釋了蝸牛).
- **紀錄**: a timeline grouped by day; each row = emoji + object + status icon (✅ 答了 / ❓ 不確定 / 🛡️ 轉給家長) +
  time; tap expands to show the question, answer and ask-back. Filter chips by topic at top.
- **小抄**: cards with category emoji and a coloured header; segmented control 5–6 / 7–8 switches talking points;
  "不要說" in a muted box; sources as small link chips; 「聊過了 ✓」. Urgent (self_harm) card is red with the
  helplines 1925 / 1995 as tap-to-call `tel:` links.
- **孩子**: chips that toggle on/off with emoji (🐶 有養狗, 🐱 有養貓, 👧 有兄弟姊妹, 🦖 喜歡恐龍, 🚗 喜歡車車,
  🌿 家裡有植物, 🚲 會騎腳踏車), an age picker 5/6/7/8 as big buttons, name field; a line "Whyscope 只用這些來舉例，
  不會對孩子說出名字". Auto "最近常問" shown as emoji chips.
- **設定** (gear): retention slider 7/30/90 天, 雲端後備 toggle disabled with "Stage II", 匯出, 清除 (with confirm),
  version and mode line.
- Empty states: friendly SVG + one line (e.g. "還沒有問題，去問問好奇鏡吧").
- Accessibility: contrast ≥ 4.5:1 for body text; 16 px minimum; all icons have aria-labels.

## E. Verification (must actually run)

1. Start server; run `eval/run_latency.py`; first_sentence_ms for text must be ≤ 300 ms.
2. Ask 10 questions from `eval/abstention_set.jsonl` (in_kb) through `/api/ask` + polling; print the final spoken
   text for each and assert all sentences ≤ 18 chars, total ≤ 60 chars, no banned term, ask-back matches pattern.
3. Open /kid and /parent in the built-in browser at a 390×844 viewport; take screenshots to `docs/screens/`
   (kid-idle, kid-answer, parent-week, parent-log, parent-cheats, parent-child); embed them in README.
4. `eval/run_abstention.py` still ≥ 90 % at threshold 0.55.
5. Update docs/benchmarks.md with the new numbers; list deviations.
