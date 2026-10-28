# Visual pass 2 — soft pastel glass (spec)

Restyle `hub/static/kid.html` and `hub/static/parent.html` to the look of modern pastel wellness / smart-home
apps: airy pastel gradient backgrounds, frosted-glass cards, very round corners, generous white space, big
numbers with small labels, playful circular emoji, pill chips, a bottom navigation bar with a floating round
action button. **Only the visual layer changes.** Keep every feature, element, API call, state, Chinese string
and the information architecture from `docs/product-pass-1.md` (sections C and D). No CDNs, no web fonts over
the network (use `"Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, sans-serif`), no images except
inline SVG and emoji.

## Design tokens (both pages; define as CSS variables)

- Background: a fixed full-screen gradient, not flat colour.
  Parent: `linear-gradient(160deg, #F6EEFF 0%, #FDE9F1 35%, #FFF2E6 70%, #E9F3FF 100%)` plus two blurred
  radial blobs (lavender `#CDB8FF` and peach `#FFD3B6`, `filter: blur(80px)`, 40 % opacity) positioned
  top-left and bottom-right, `position: fixed`, behind content.
  Kid: `linear-gradient(170deg, #EAF2FF 0%, #F6F0FF 50%, #FFF6EC 100%)` with one sky-blue blob `#BFD9FF`.
- Glass card: `background: rgba(255,255,255,0.62); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  border: 1px solid rgba(255,255,255,0.8); border-radius: 28px; box-shadow: 0 10px 30px rgba(96, 80, 140, 0.10)`.
  Shadows are soft and neutral-lavender, never a coloured glow, never zero-offset halos.
- Accent set (pastel, each with a deeper text/ink partner for contrast):
  lavender `#C7B8FF` / ink `#5B4AB8`; sky `#BFE0FF` / ink `#2B6CB0`; peach `#FFD6C2` / ink `#C2410C`;
  mint `#CBF3E3` / ink `#1F7A5C`; lemon `#FFF1B8` / ink `#8A6D00`; rose `#FFD1E0` / ink `#B4306B`.
  Text: ink `#2B2A4A` headings, `#5A5878` body, `#8E8CA8` captions. Body text ≥ 4.5:1 on its card.
- Radii: cards 28 px, chips 999 px, buttons 20 px, mic button circle. Spacing scale 8/12/16/24/32.
- Type: numbers 56–72 px weight 800 with letter-spacing −1 px; section titles 18 px weight 700; body 16 px;
  captions 13 px. Chinese text never below 13 px.
- Motion: cards fade+rise 240 ms on first paint (staggered 40 ms); chips scale 0.96 on press; mic ring breathes.
  Respect `prefers-reduced-motion`.

## Parent page

- **Top**: avatar circle (emoji 🧒 on a pastel disc, 44 px) + child name + "好奇鏡" caption; right: status dot
  and a round glass gear button.
- **Segmented control** under the header: 日 / 週 / 月 (only 週 is functional now; others show a toast "即將推出").
- **Hero card** (glass): big number, small label "個為什麼", the 7-day sparkline redrawn as a smooth area with a
  lavender→sky gradient fill and a highlighted today dot; the "比上週" chip as a mint pill.
- **Mood-style topic row**: six circular pastel discs in a row (like the reference's emoji row), each with the
  topic emoji and the count underneath; tapping filters 紀錄. Keep the donut below it but make it a thin ring
  (stroke 14) with the total inside.
- **可以聊聊看**: horizontal cards with a soft pastel header band per topic colour, emoji 40 px, object name
  22 px bold, the ask-back line, and a round "聊過了 ✓" button bottom-right.
- **我答不出來** and **用過的例子**: glass list rows / pill chips.
- **Bottom nav**: glass bar with 4 icons (本週 / 紀錄 / 小抄 / 孩子) and a centred floating round button (56 px,
  lavender ink gradient `linear-gradient(135deg,#7C6CFF,#5B4AB8)`, white "＋" that opens the 孩子 tab's add-chip
  sheet). Active icon in lavender ink with a small dot.
- **紀錄**: day headers as pills; rows as glass cards with emoji disc, object, status icon, time.
- **小抄**: cards with pastel header per category; segmented 5–6 / 7–8 as pills; urgent card uses rose header
  with a red ink border, helpline buttons as rose pills with `tel:` links.
- **孩子**: toggle chips become pastel pills with emoji that fill with the ink colour when on; age picker as
  four round discs; name field as a glass input.
- **Empty states**: a big soft emoji on a pastel disc + one line.

## Kid page

- **Header**: small glass pill "好奇鏡" with the magnifying-glass SVG, status dot right.
- **Prompt card**: glass, centered, "有什麼想知道的嗎？" 22 px; below it an SVG waveform (like the reference)
  that is flat when idle and animates with the mic level while listening.
- **Answer card**: glass; emoji on a pastel disc 72 px; first sentence 34 px weight 800 ink; explanation 20 px;
  ask-back inside a peach pill-shaped block with a "你猜猜看" lemon chip; two buttons as pastel pills.
- **Mic**: a 112 px circle in sky→lavender gradient with a white mic SVG, resting on a larger translucent disc
  (the "listening" ring breathes by scaling the disc 1.0→1.08, no glow). Thinking state: three pastel dots.
- **Text input**: glass pill with the "問問題" button inside it on the right.
- **Camera toggle**: a small glass pill with 📷.

## Verification

1. Start the server, open both pages in the built-in browser at 390×844, take screenshots
   `docs/screens/v2-kid-idle.png`, `v2-kid-answer.png`, `v2-parent-week.png`, `v2-parent-log.png`,
   `v2-parent-cheats.png`, `v2-parent-child.png`; replace the images referenced in README.md with the v2 set.
2. Run `eval/check_answers.py` (or the equivalent script) once to prove nothing in the answer path changed.
3. Check with a quick script that no `box-shadow` with zero x/y offset and a non-neutral colour remains, and
   no `#FBF8F2`/`#F3EDE2` cream backgrounds remain.
