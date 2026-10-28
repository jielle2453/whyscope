# Whyscope — product film (Remotion), 2:55

Style: a product launch film, not a walkthrough. Dark, quiet cold open → light floods in at the reveal → pastel
world. Kinetic typography, slow parallax on a phone mockup, one big idea per beat, music-driven cuts, soft UI
ticks. English narration (calm, warm, few words). Chinese appears only inside the phone (what the child
says) with small English captions. 1920×1080, 30 fps, MP4.

| # | Time | Beat | On screen | Narration |
|---|---|---|---|---|
| 1 | 0:00–0:14 | **Cold open** | Near-black indigo. A cursor blinks. Questions type themselves and stack up, faster and faster, in a child's handwriting-style font, mixing 中文 and English: 「為什麼蝸牛有殼？」 "Why is the sky blue?" 「為什麼月亮跟著我走？」 "Why do cats' eyes glow?" … Soft tick on each. They fill the screen. | *(silence, then)* Seventy-six questions an hour. |
| 2 | 0:14–0:26 | **The problem** | All questions dim except one: "Why?" It hangs alone. Three lines fade in beneath, one at a time: "Most get a shrug." "Smart speakers can't see what she's pointing at." "Curiosity fades." | Most of them get a shrug. The speaker in the kitchen can't see what she's pointing at. And little by little, the questions stop. |
| 3 | 0:26–0:40 | **Reveal** | A warm light blooms from the centre; the dark dissolves into the pastel gradient. The magnifying-glass logo draws itself, then the word **Whyscope** settles under it. A phone rises from below with parallax, idle kid screen glowing. Tagline fades: **Point at it. Ask why.** | Meet Whyscope. A small companion for the biggest word in a child's vocabulary. |
| 4 | 0:40–0:58 | **It sees.** | Headline "It sees." slides in from the left; the phone tilts 8°. Inside: camera toggle on, a toy snail in frame, the 🐌 disc pops, "你問：為什麼蝸牛有殼". Caption: "Why does the snail have a shell?" | Point at anything. Whyscope looks with you. |
| 5 | 0:58–1:16 | **It answers like a kind grown-up.** | Headline. Inside the phone the first sentence lands instantly in big type: 「這是蝸牛！殼是牠的家。」 then the explanation. Floating callouts: "First words in 8 ms", "Words a 6-year-old knows", "Facts from a curated kids' knowledge base". Caption translation. | It answers in seconds, in words a six-year-old already knows. Every fact comes from a knowledge base built for children. |
| 6 | 1:16–1:32 | **Then it asks you to guess.** | The peach "你猜猜看" block glows; the ask-back appears line by line: 「猜猜看，你家的狗狗有毛，蝸牛為什麼沒有毛呢？」 Caption. A small chip "uses what parents told it: 🐶 has a dog". | And then it turns the question around. Guess first. Because the thinking is the point. |
| 7 | 1:32–1:48 | **It listens.** | Headline. Phone: the mic disc breathes, waveform swells with a spoken question, transcript 「為什麼貓的眼睛晚上會發光」, answer card with 🐱. Caption "Why do cats' eyes glow at night?" Callout: "Speech recognition on the device". | Hold the button and just ask. The listening happens right here, on the device. |
| 8 | 1:48–2:04 | **It knows what's for grown-ups.** | Phone: 「為什麼人會死」 → the soft card 「這個問題很重要，我們一起去問爸爸媽媽好嗎？」 Cut to the parent phone receiving a cheat-sheet notification with the 5–6 / 7–8 toggle. Caption. | Some questions belong to you. Whyscope hands them back gently, and gives you a few words to start with. |
| 9 | 2:04–2:24 | **For parents: a week of wonder.** | Second phone slides in beside the first: the parent home with the big number, sparkline, emoji topic discs; cards swipe: 🐌 蝸牛 → "Talk about: does a snail come out in the rain?". Callouts: "22 whys this week", "3 things to talk about at dinner", "Only topics are stored. Never recordings." | Every week, a curiosity report. What she wondered about. Three things to talk about at dinner. Only the topics are kept. Never her voice, never her face. |
| 10 | 2:24–2:40 | **Everything stays home.** | Pastel fades to a clean white studio. The ASUS UGen300 module and a Raspberry Pi 5 appear as flat illustrations, assembling into a small device; a badge "Hailo-10H · 2.5 W". Three lines: "On-device. No cloud." "No subscription needed." "Never bricks." Small footer: "Prototype on a laptop today · UGen300 in Stage II". | It runs on a two-and-a-half-watt chip, at home, without the cloud. No subscription. Nothing to switch off when a company disappears. |
| 11 | 2:40–2:50 | **Proof** | Five tiles flip in: first word ≤ 2.5 s · child speech CER ≤ 20 % · pointing ≥ 85 % · wrong answers ≤ 10 % · energy per question. Two tiles stamp "measured today: 8 ms", "91.7 %". | Five numbers we will measure on the real hardware. Two of them, we already have. |
| 12 | 2:50–2:55 | **Close** | Logo, **Point at it. Ask why.**, "Whyscope 好奇鏡", GitHub URL, team name. Music resolves. | Whyscope. |

Narration ≈ 210 words. Music carries the rest.

## Sound

- Music: one calm, hopeful piano/ambient track, 3 minutes, building at the reveal (0:26) and resolving at the end.
  Needs a licence-free file (CC0 or CC BY with credit in the description). **I need your OK before downloading any
  track; or drop an MP3 you own into `video/music/`.**
- UI ticks and the "bloom" whoosh: synthesised locally with a small Python script (sine/noise envelopes), no downloads.
- Narration: local TTS (Kokoro, warm English voice) at −6 dB under the music; replaceable with your own recording.

## Production

1. `video/record.ts` (Playwright): records the four phone clips against the running prototype with seeded demo data;
   Clip 7 uses Chrome's fake-microphone flag fed with a WAV of the question.
2. `video/src/`: Remotion compositions — ColdOpen, Problem, Reveal, FeatureBeat (headline + phone mockup + clip +
   callouts, reused for beats 4–9), StaysHome, Proof, Close. Phone mockup is an SVG frame with rounded corners,
   subtle reflection and parallax.
3. `scenes.json` holds timings; narration WAV durations stretch each beat.
4. `npx remotion render` → `video/out/whyscope-film.mp4`; upload unlisted.

## Decisions needed

1. Music: let me download a CC0 track (I will name it and credit it), or you supply one.
2. Narration: synthetic English voice now; you can replace it later.
3. Team name + GitHub URL for the close (repo must be public first).
