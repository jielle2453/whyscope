# Whyscope product film (Remotion)

1920x1080, 30 fps, 12 beats, about 2:55. Script: `../docs/video-remotion-script.md`.
Everything (music, sound effects, narration, phone clips) is generated locally; nothing is downloaded except the npm packages, Google Fonts (Nunito, Fredoka, Patrick Hand) and Remotion's headless Chrome.

## Re-render

```bash
cd video
npm install
npm run render            # -> out/whyscope-film.mp4 (h264, CRF 18)
npm run studio            # live preview
```

Windows note: if the repo path is very long, Remotion cannot spawn its bundled browser. Copy
`node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64` to `C:\whyscope-chrome`;
`remotion.config.ts` picks it up automatically.

## Rebuild the assets (all optional; generated files are git-ignored)

| Step | Command |
|---|---|
| Narration, one WAV per beat (Windows SAPI) | `powershell -File audio/make_narration.ps1` |
| Timeline (beat lengths stretch to narration length + padding) | `npm run timeline` |
| Music + UI ticks/bloom/pop/stamp | `C:\whyscope-venv\Scripts\python.exe audio/make_music.py` (needs numpy; length follows the timeline) |
| Spoken-question WAV for the voice clip | `powershell -File audio/make_question_wav.ps1` |
| Phone clips (server must run on :8000) | `node --no-warnings record.ts [A\|B\|C\|D]` |

`scenes.json` holds beat names, nominal seconds, narration text and the narration start offset (`narrDelay`) inside each beat.
Run order after changing text or voice: narration, timeline, music, render.

## Replace the narration with a human voice

1. Record each beat as a mono or stereo WAV (44.1 or 48 kHz) and save it over `public/audio/narr-01.wav` ... `narr-12.wav` (same names).
2. Edit `narrDelay` in `scenes.json` if a take should start earlier or later in its beat, then run `npm run timeline`.
   Beats grow automatically when a take is longer than the nominal beat; the music is then regenerated to the new length (`audio/make_music.py`).
3. `npm run render`.

Music sits at -14 dB (volume 0.2) under narration and rises to 0.32 in the gaps (`musicVolume` in `src/Film.tsx`).
To use your own music instead, drop a WAV named `public/audio/music.wav` and skip `make_music.py` (the SFX WAVs are still needed).

## Layout

- `src/ui.tsx`: fonts, colours, `PhoneScene` (3D tilt phone, Ken Burns, springy entrance, headline words, callouts with drawn connectors), `Sfx`.
- `src/scenes1.tsx`: cold open + problem (`DarkOpen`), logo draw, bloom reveal.
- `src/scenes2.tsx`: "stays home" studio, proof tiles, close.
- `src/Film.tsx`: sequencing, per-beat phone configuration, audio mix.
- `scripts/stills.mjs <frames>` + `scripts/sheet.py`: quick still frames and a contact sheet for visual checks.

## Known simplifications

- Clips are recorded at the phone's 390x844 CSS size (1x): Playwright pads larger video sizes with grey.
- The camera "toy snail in frame" shot is replaced by the typed snail question (no real camera in the recorder).
- Team name in the close is a placeholder (`jielle2453`); edit `src/scenes2.tsx` (`Close`).
- The prototype UI is recorded in English (`?lang=en`), so Chinese text appears only in the cold open.
