# Writer brief: zh pilot layer (Whyscope)

Audience: bilingual Taiwanese children aged 5-8. They mostly ask in Mandarin and often mix in English words
("為什麼 zebra 有條紋？"). The voice is a warm Taiwanese preschool teacher (台灣幼兒園老師), not a mainland
textbook and not a translation. Traditional Chinese, Taiwan usage.

Input row (English, fact-checked 3 times): id, topic, q, variants, a1, a2, ask_back.
Output row (one JSON object per line, UTF-8, no BOM), keys in this order:
`id, q_zh, variants_zh, a1_zh, a2_zh, ask_back_zh, key_en, tw_note`

## Fields

**q_zh**: the question as a Taiwanese 5-8-year-old would naturally say it. Kid words are fine (狗狗、肚子、便便、
放屁、尿尿、哈啾). Usually 為什麼…？ / …怎麼…的？ / …是什麼？

**variants_zh**: 4-6 strings, all different from q_zh and from each other, with varied wording (different verbs and
sentence frames; this feeds retrieval). Include:
- spoken forms / reduplication (狗狗、車車、一條一條的);
- at least one fragment ("為什麼彩虹", "斑馬的條紋");
- at least one mixed zh+English variant using a simple English noun or verb a kindergartener knows
  ("為什麼 zebra 有條紋", "rocket 怎麼飛上去"); English words lowercase, a space on each side;
- optional: one likely speech-recognition slip (homophone or near-homophone, e.g. 噴嚏→噴涕, 斑馬→班馬).
No question marks needed in variants.

**a1_zh**: exactly ONE sentence, ending with 。, at most 18 spoken characters (punctuation, digits and Latin letters do
not count; the hub enforces 18). For why / how-come questions it gives the cause with 因為…; for what-is questions a
plain definition. Re-say it the way a teacher would; do NOT translate word for word. Everyday words a 注音-stage child
knows. If the English a1 has two parts, put the core cause in a1_zh and move the rest to a2_zh (or drop it).

**a2_zh**: the answer to the child's follow-up "為什麼？/然後呢？": 1-2 short sentences, each at most 18 spoken
characters. Faithful to the English a2 (plus anything moved from a1). a1_zh + a2_zh at most 60 characters.

**ask_back_zh**: ONE question about the object (not about the child's life) that invites a guess. Must:
- contain 嗎 / 還是 / 猜 / 你覺得 (an either-or "你猜…是A，還是B？" works best);
- be at most 30 characters and end with ？;
- NOT contain any of: 今天 開心 難過 傷心 生氣 害怕 朋友 同學 學校 老師 你喜歡 你愛 你家 你的 你今天
  爸爸 媽媽 哥哥 姐姐 弟弟 妹妹 爸爸媽媽有沒有 你的家人 (the hub blocks these: hub/safety.py askback_ok,
  hub/compose.py BAD_ASKBACK). Note "你的" is blocked: write "家裡的狗狗" / "狗狗", not "你的狗狗".
- no feelings/flattery of the device or child (我覺得 我喜歡 我愛 你好棒 你真聰明 …).
Rewrite the English ask_back when it breaks these rules (e.g. "What is your favorite dinner?" →
"你猜晚餐是在早上吃，還是晚上吃？").

**key_en**: 1-2 items `{"en": "stripes", "zh": "條紋"}`. Simple concrete English words a bilingual kindergarten teaches:
nouns, colours, body parts, actions (rain, nose, yellow, jump). No abstract or science words (gas, energy, protein,
reflect, muscle is borderline: avoid). Prefer words that appear in the English a1 (else a2 or q). Lowercase, base form
as it appears or its simple singular ("stripes" ok, "flies" → "fly" only if fly is in the text; prefer a word that
literally appears). zh = the Taiwan word for it.

**tw_note**: "" normally.
- `"not_for_tw: <reason>"` when the English item does not fit Taiwan (snow days, Thanksgiving, Fahrenheit, US-only
  things like quarters, 911, US states). Still fill all fields faithfully so the team can decide.
- `"adapted: <what changed>"` when you localized content (°F→°C, miles→km, 911→119, school bus→娃娃車). Only adapt
  when the fact stays true for Taiwan; never invent Taiwan facts you are not sure of.
Use Taiwan context where natural and true: 颱風、地震、捷運、機車、垃圾車、夜市、便利商店、°C、km.

## Faithfulness (most important)
The English facts were checked 3 times. Simplifying is OK; adding a new fact, number, cause, animal, or example is NOT.
Keep hedges ("scientists think" → 科學家猜/可能; "nobody knows for sure" → 沒有人確定). Don't turn "often" into
"always".

## Taiwan wording
- Taiwan words: 馬鈴薯(not 土豆) 影片(視頻) 品質(質量) 計程車(出租車) 公車(公交) 捷運(地鐵) 腳踏車(自行車)
  機車(摩托車) 冷氣(空調) 塑膠(塑料) 鳳梨(菠蘿) 奇異果(獼猴桃) 優格(酸奶) 泡麵(方便面) 廁所/洗手間(衛生間)
  資料(數據) 網路(網絡) 番茄(西紅柿) 冰棒(冰棍) 垃圾桶 雷射(激光) 螢幕(屏幕).
- No 兒化 (玩兒、一點兒、哪兒、一會兒), no 啥/咋/唄/搞. Use 牠/牠們 for animals. Use 裡 (not 裏), 著 (not 着).
- Sentence-final 喔/耶/呢 are fine, sparingly. Don't start answers with 好問題 (the hub adds reactions itself).
- Hub-banned jargon (use the plain phrase instead): 反射→彈回來, 折射→拐彎, 光譜→彩色的光, 蛋白質→一種營養,
  氧化→變質, 細胞→小小的小格子, 分子/原子→很小的小東西, 電磁/磁場→磁鐵的力量, 密度→有多擠,
  氣壓→空氣的力量, 壓力→擠的力氣, 蒸發→變成水氣飛走, 凝結→聚在一起, 波長→長短, 能量→力氣,
  病毒/細菌→很小很小的小蟲蟲 (or 髒東西 if faithful), 神經→感覺的線, 器官→身體的小幫手, 酸鹼.
- The hub also allows at most 2 "uncommon" characters per sentence (hub/data/common_chars.txt); characters that
  appear in your q_zh/variants_zh are exempt. The validator checks this.

## Examples (not pilot items)
```
{"id": "ani-071", "q_zh": "斑馬為什麼有條紋？", "variants_zh": ["為什麼斑馬身上一條一條的", "斑馬的條紋", "為什麼 zebra 有條紋", "斑馬為什麼是黑白的", "為什麼班馬有條紋"], "a1_zh": "因為科學家猜，條紋可以趕走蒼蠅。", "a2_zh": "每隻斑馬的條紋都不一樣，就像指紋。", "ask_back_zh": "如果幫斑馬換顏色，你覺得要塗什麼顏色？", "key_en": [{"en": "stripes", "zh": "條紋"}, {"en": "zebra", "zh": "斑馬"}], "tw_note": ""}
{"id": "bod-002", "q_zh": "為什麼會打噴嚏？", "variants_zh": ["為什麼我一直哈啾", "打噴嚏", "為什麼鼻子癢癢就會哈啾", "為什麼會 sneeze", "為什麼會打噴涕"], "a1_zh": "因為鼻子要把癢癢的灰塵噴出去。", "a2_zh": "身體會很快噴出一大口氣，把鼻子清乾淨。", "ask_back_zh": "你猜胡椒粉會讓人打噴嚏嗎？", "key_en": [{"en": "nose", "zh": "鼻子"}, {"en": "dust", "zh": "灰塵"}], "tw_note": ""}
{"id": "soc-n11191", "q_zh": "為什麼要過感恩節？", "variants_zh": ["感恩節是什麼", "感恩節", "為什麼有 Thanksgiving", "感恩節為什麼要吃大餐"], "a1_zh": "因為大家要一起吃大餐，說謝謝。", "a2_zh": "它一開始是收成以後的大餐。", "ask_back_zh": "你猜感恩節的大餐，是在收成前還是收成後？", "key_en": [{"en": "meal", "zh": "大餐"}, {"en": "thanks", "zh": "謝謝"}], "tw_note": "not_for_tw: Thanksgiving is a US/Canada holiday, not celebrated in Taiwan"}
```

## Check your work
Run (from any directory; PowerShell):
```
$env:HF_HUB_OFFLINE=1; $env:PYTHONIOENCODING="utf-8"; & C:\whyscope-venv\Scripts\python.exe C:\Users\Jie\Desktop\whyscope\repo\eval\answer_bank\zh_pilot\scripts\validate_zh.py <your out file>
```
Fix every ERROR. Read every warning and fix it unless you have a reason (e.g. a what-is question needs no 因為).
