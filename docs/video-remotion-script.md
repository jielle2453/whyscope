# Whyscope — Stage I demo video (Remotion), 2:55

Output: 1920×1080, 30 fps, MP4, English narration (local TTS, replaceable by a human voice-over), Chinese on-screen
only where the child speaks/types. Footage of the app is recorded automatically with Playwright at 390×844
(phone frame) against the running prototype; everything else is drawn by Remotion.

| # | Time | On screen | Narration (English) | 製作備註 |
|---|---|---|---|---|
| 1 | 0:00–0:08 | Pastel gradient, magnifying-glass logo draws itself, "Whyscope 好奇鏡" fades in, subtitle "A why-tool for kids aged 5–8, on-device". | A five-year-old asks about seventy-six questions an hour. Most of them start with "why". | Remotion 標題卡。 |
| 2 | 0:08–0:28 | Three big numbers animate up: **76** questions/hour, **36.7%** of "why" questions get a real explanation, **50%** fully answered by a voice assistant. Small source line. | Adults explain only about a third of them. And when a child turns to a smart speaker, only half of the questions get a complete answer, mostly because the speaker cannot see what the child is pointing at. | 數字卡，來源 Chouinard 2007、Frazier 2009、Lovato 2019。 |
| 3 | 0:28–0:45 | Three icons slide in: eye (sees), ear (listens), speech bubble with "?" (asks back). Then a phone frame appears with the kid page idle. | Whyscope is a small device that sees, listens, answers in a child's words, and asks one question back. Everything runs on the device. No audio or image ever leaves the home. | 三步驟圖示 + 手機框。 |
| 4 | 0:45–1:10 | **Clip A** (Playwright): kid page, text "為什麼蝸牛有殼" typed, first sentence appears immediately with the 🐌 disc, then explanation, then the orange "你猜猜看" ask-back. Caption overlay translates: "This is a snail! The shell is its home." / "Guess: does a snail come out in the rain, or hide in its shell?" | Here a child asks why a snail has a shell. The first sentence is spoken within a few milliseconds, straight from a curated kids' knowledge base. A small on-device language model adds one more sentence, and then Whyscope asks the child to guess. | 字幕用英文翻譯覆蓋，保留中文原畫面。 |
| 5 | 1:10–1:30 | **Clip B** (Playwright, fake mic): the mic button pressed, waveform moves, transcript "為什麼貓的眼睛晚上會發光" appears, answer card. Caption: "Why do cats' eyes glow at night?" | It also listens. The child holds the button and speaks. Speech recognition runs locally, and the answer uses only words a seven-year-old knows. Scientific terms are rewritten automatically: "reflect" becomes "bounce the light back". | 用 Chrome 假麥克風旗標餵 WAV；若失敗改用打字畫面並在旁白省略「holds the button」。 |
| 6 | 1:30–1:48 | **Clip C**: "為什麼人會死" typed → soft card "這個問題很重要，我們一起去問爸爸媽媽好嗎？" then "為什麼股票會跌" → "我不確定，我們一起去問爸爸媽媽好嗎？". Captions in English. | Some questions belong to parents. Death, violence, where babies come from: Whyscope gently hands them back to a grown-up. And when it does not know, it says so instead of guessing. | 兩段短片接在一起。 |
| 7 | 1:48–2:15 | **Clip D**: parent page, 本週 tab: big number, sparkline, emoji topic row, swipe through "可以聊聊看" cards; tap 小抄 tab showing the cheat sheet for the death question with the 5–6 / 7–8 toggle. Callout boxes in English: "This week: 22 whys", "Talk about: snail, rainbow", "Parent cheat sheet". | Parents get a weekly curiosity report: how many whys, which topics, and three questions to talk about at dinner. For the sensitive ones, a cheat sheet with age-appropriate talking points and sources. Only topic counts are stored. Never transcripts, never recordings. | 錄製時用 seed 的示範資料，數字才好看。 |
| 8 | 2:15–2:35 | Architecture diagram animates: camera + mic → Raspberry Pi 5 + ASUS UGen300 (Hailo-10H) box with four chips (YOLO detection + pose, Whisper, Qwen2.5-1.5B, CLIP) → speaker; a dotted line to "Parent web app on home Wi-Fi". Badge "Battlefield Lightning". | Today the prototype runs on a laptop. In Stage Two it moves to a Raspberry Pi 5 with the ASUS UGen300: vision, English speech and the language model on the Hailo-10H, Mandarin speech and retrieval on the CPU. Two and a half watts, battery-friendly, and it never bricks if a server goes away. | Remotion 畫的架構圖。 |
| 9 | 2:35–2:50 | Five metric tiles with targets: first word ≤ 2.5 s · child Mandarin CER ≤ 20 % · pointing ≥ 85 % · abstention error ≤ 10 % · energy per question. Under them: "Measured today on a laptop: first sentence 8 ms, abstention 91.7 %". | In four weeks we will measure five numbers on the real hardware: first-word latency, children's speech accuracy, pointing accuracy, how often it wrongly answers, and energy per question. Two of them we already measured today. | 已量數字來自 docs/benchmarks.md。 |
| 10 | 2:50–2:55 | Logo, "Whyscope — point at it, ask why.", GitHub URL, team name placeholder. | Point at it. Ask why. Whyscope. | 結尾卡。 |

## Narration word count

About 390 words → 2:40 at a calm pace, leaving room for the clips to breathe.

## Production plan

1. `video/record.ts` (Playwright): starts from the running server, seeds demo data into a throw-away DB, records
   Clips A–D as WebM at 390×844 (device scale 2), using `--use-fake-device-for-media-stream` and
   `--use-file-for-fake-audio-capture=<wav>` for Clip B.
2. `video/narration/`: one WAV per scene generated by local TTS (Kokoro, English voice; fallback Windows SAPI).
   Durations feed the Remotion timeline so scenes stretch to the narration.
3. `video/src/`: Remotion compositions — Title, Numbers, ThreeSteps, PhoneClip (phone frame + caption overlay),
   Architecture, Metrics, Closing; `Root.tsx` sequences them from `scenes.json`.
4. `npx remotion render` → `video/out/whyscope-stage1.mp4`. Upload to YouTube as unlisted.

## Things to decide

- Voice: synthetic English (ready today) vs. your own recording (replace `video/narration/*.wav`, timeline re-fits).
- Team name and GitHub URL on the closing card.
- Whether to show the laptop demo honestly as "laptop today" (recommended) or crop to the phone frame only.
