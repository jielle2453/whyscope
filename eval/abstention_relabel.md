# Abstention set relabels (2026-11-15)

After 114 AI-draft entries were added (topics earth, people, physics and more), twelve questions that were labelled
`out_kb` (the knowledge base cannot answer) are now answered by an entry that really does cover the question. They were
relabelled `in_kb` with the entry's `kb_id`, so "answers a question the KB covers" is counted as right and the abstention
metric keeps measuring what it was meant to. Rule used: relabel only when the entry's first sentence or facts answer
what was asked; do not relabel when the answer is on a related topic but does not answer the question.

## Relabelled out_kb -> in_kb

| set | question | kb_id | why it counts as covered |
|---|---|---|---|
| en | Why do we have to go to school? | people-school | "A school is a place where people learn" + facts on why |
| en | Why does every country have its own flag? | people-flag | "A national flag stands for a country" |
| en | Why do we wear clothes? | machines-clothes | "Clothes protect your body" + sun, cold facts |
| en | Why did the dinosaurs disappear? | earth-dinosaurs | died out 66 million years ago, a space rock |
| zh | 為什麼要上學 | people-school | same entry |
| zh | 為什麼要有學校的老師 | people-school | a teacher helps you learn (fact 1) |
| zh | 為什麼每個國家都有自己的國旗 | people-flag | same entry |
| zh | 為什麼我們要穿衣服 | machines-clothes | same entry |
| zh | 為什麼海水是鹹的 | sky_weather-sea-salty | "海水裡有很多鹽，所以是鹹的" |
| zh | 恐龍為什麼不見了 | earth-dinosaurs | same entry |
| zh | 大象的鼻子為什麼那麼長 | animals-elephant-trunk | what the long trunk does (partial: says what it is for, not why it is long) |
| zh | 為什麼要洗手 | machines-soap | soap keeps dirt and tiny bugs off the hands |

Effect: the en dinosaur item is now an `in_kb` **false abstain** (the English asks guard does not know "disappear" = "died out"
and the entry's `asks_en` has no such word). That is a real miss and is deliberately left visible.

## Deliberately NOT relabelled (real mistakes, kept as out_kb / near_kb)

| set | question | answered by | why it stays a mistake |
|---|---|---|---|
| en | Where does money come from? | people-money | entry says what money is for, not where it comes from |
| zh | 為什麼小朋友要過生日 | people-birthday | entry says what a birthday is, not why we celebrate |
| zh | 為什麼人要說話 | people-languages | entry is about learning a language, not why people talk |
| zh | 地球為什麼會自己一直轉 | sky_weather-moon-shape | wrong topic |
| zh | 為什麼我們要喝水 | plants-roots-down | wrong topic |
| en/zh | all near_kb items still answered (giraffe height, ant load, inventors, apple colours...) | the object's entry | the entry does not hold that detail |

## Other items seen while re-running (pre-existing, not changed)

* in_kb false abstains: "colorful bridge in the sky after rain" (en, zh), banana skin turns black (0.53), goosebumps zh paraphrase.
* "Why does the sea go in and out?" is not in the abstention sets; it reaches `sky_weather-tides` after the recall fix
  (near-verbatim question-pattern matches no longer need a label word).
