# Whyscope 好奇鏡 示範影片腳本

ASUS UGen AI League Stage I 提交用，3:00。

- 錄製方式：一人出境，筆電網路攝影機（畫面角落小窗）＋螢幕錄影
- 口說語言：英文（短句）；示範的中文問題請慢慢念
- 備註欄為中文，列出需要事先準備的項目

## 腳本

| time (mm:ss) | What is on screen | Spoken line | 備註 |
|---|---|---|---|
| 0:00–0:08 | Webcam full frame. Title card: "Whyscope (好奇鏡)". | "Kids ask a lot of 'why' questions. Here are three numbers." | 直視鏡頭，語氣輕快。 |
| 0:08–0:20 | Three number cards, one at a time, each held for about 3 seconds. | "Preschoolers ask about 76 information-seeking questions per hour. Adults explain only 36.7% of causal questions. And a voice assistant fully answered only 50% of 5-to-8-year-olds' questions." | 三個數字需與提案書一致，來源要列在提案附註。每張卡停留約 3 秒。 |
| 0:20–0:30 | Slide: "Whyscope: see, listen, answer like a friend." | "Whyscope is a curious little lens for children. It sees, it listens, and it answers in a child's words." | 準備投影片 1 張（標題＋一行說明）。 |
| 0:30–0:40 | Slide with four icons: ask back, weekly report, on-device. | "It asks one question back, to keep the thinking going. Parents get a weekly curiosity report. And everything runs on the device." | 四個圖示要與口說順序一致。可在這裡點出「不上傳語音與影像」。 |
| 0:40–0:52 | Browser on the kid page (zoom 125%). Type 為什麼蝸牛有殼 and press Enter. | "Let's try a real question. A child asks, in Chinese: 'Why does a snail have a shell?'" | 中文問題慢慢念，念完再按 Enter。先錄一次試音確認麥克風。 |
| 0:52–1:02 | The first sentence appears and is spoken aloud. | "The first sentence comes back in seconds, and it is read aloud." | 這一段是 Fallback 的關鍵，即使後面慢也要保留。計時從按下 Enter 開始。 |
| 1:02–1:10 | Full short explanation on screen, then the ask-back question. | "Here is the full answer in simple words. Then Whyscope asks one question back." | 解釋保持 2 到 3 句。反問句要是孩子能回答的小問題。 |
| 1:10–1:20 | Click the mic button. Ask the same question aloud. | "Now the same question by voice. I click the mic and ask out loud." | 事先測試麥克風權限與音量，避免彈出授權視窗錄進影片。 |
| 1:20–1:30 | Type 為什麼人會死. The deflection message appears. | "A harder topic, like death, is not answered by the app alone. Whyscope kindly sends the child to a grown-up." | 只示範一次，不要停留太久。實際文字以目前版本為準。 |
| 1:30–1:50 | Type 恐龍為什麼不見了. The screen shows "I'm not sure, let's ask a grown-up." | "Finally, a question outside what Whyscope knows. It says, 'I'm not sure, let's ask a grown-up.' It does not make things up." | 這是「不確定就交給大人」的示範，語氣要肯定。 |
| 1:50–2:02 | Parent page: this week's summary card. | "On the parent page, this week's summary shows what the child was curious about." | 先登入家長帳號並切到本週摘要，避免現場載入。 |
| 2:02–2:10 | Question log: questions with answered and handed-back status. | "The question log shows every question, and whether it was answered or handed back to a grown-up." | 準備 5 到 6 筆示範資料，其中要有一筆「交給大人」。 |
| 2:10–2:15 | Cheat sheet for the sensitive question. | "For sensitive questions, a short cheat sheet helps parents answer at home." | 家長備忘卡內容要先定稿。 |
| 2:15–2:20 | "Child's world" memory card. | "And a child's world memory keeps the topics they love, stored on the device." | 小卡片列出 3 個孩子感興趣的主題。 |
| 2:20–2:32 | Architecture diagram: laptop today; Raspberry Pi 5 plus ASUS UGen300 Hailo-10H in Stage II. | "Today it runs on a laptop. In Stage Two, it moves to a Raspberry Pi 5 with the ASUS UGen300 Hailo-10H." | 架構圖需先畫好，兩個階段用箭頭分開。 |
| 2:32–2:40 | Split diagram: NPU block and CPU block. | "The NPU runs speech and the language model. The CPU runs retrieval and the safety rules." | 注意：NPU/CPU 分工是暫定寫法，錄前請對照技術規格確認。 |
| 2:40–2:45 | Icon: microphone and camera with a crossed-out disk. | "We do not store audio or images." | 這句要與實際儲存行為一致，錄前再確認。 |
| 2:45–2:55 | Stage II slide: timeline and five numbers. | "In Stage Two, we will measure five numbers on real hardware: answer accuracy, correct abstention, time to first sentence, power use, and parent usefulness." | 五個指標是建議版本，請與提案的 Stage II 章節核對後再錄。 |
| 2:55–3:00 | Closing slide: Whyscope logo and "Every 'why' deserves an answer." | "Every 'why' deserves a good answer. And some deserve a grown-up. Thank you." | 結束時停在 logo 畫面 2 秒。 |

## 錄製檢查表（Recording checklist）

- 工具：OBS 或 Windows Game Bar（Win + G），輸出 1080p。
- 麥克風：錄 10 秒試音，確認中文問題清楚；必要時改用外接麥克風。
- 瀏覽器：縮放 125%，關閉書籤列與通知，桌面整理乾淨。
- 網路：示範時可先斷網，證明確實在裝置上運作（錄前確認功能可離線）。
- 道具：準備玩具蝸牛或蝸牛圖片，給選用的鏡頭特寫（0:40 前後）。
- 中文問題：每句慢慢念，每句念完停一拍。
- 家長頁與架構圖：事先開好分頁，避免現場找頁面。
- 備份：先完整錄一次，再錄正式版本；保留成功的那一段。

## Fallback

若 LLM 解釋太慢，第一句仍會先播放。這段 take 要保留，不要為了等完整解釋而重錄；剪輯時可用旁白補上說明。
