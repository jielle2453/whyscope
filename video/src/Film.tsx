import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from "remotion";
import tl from "./timeline.json";
import { C, PastelBg, PhoneScene } from "./ui";
import { DarkOpen, Reveal } from "./scenes1";
import { Close, Home, Proof } from "./scenes2";

const B = (key: string) => tl.beats.find((b) => b.key === key)!;
const S = (b: { start: number; frames: number }, name: string, children: React.ReactNode) => (
  <Sequence from={b.start} durationInFrames={b.frames} name={name}>{children}</Sequence>
);

// Narration windows (global frames) for ducking the music
const windows = tl.beats.filter((b) => b.hasNarr).map((b) => {
  const s = b.start + Math.round(b.narrDelay * tl.fps);
  return [s, s + Math.round(b.narrSec * tl.fps)] as const;
});
const musicVolume = (f: number) => {
  let pres = 0;
  for (const [s, e] of windows) pres = Math.max(pres, interpolate(f, [s - 12, s + 6, e - 4, e + 24], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return 0.2 + 0.12 * (1 - pres); // -14 dB under narration, a little more air in the gaps
};

export const Film: React.FC = () => {
  const b4 = B("sees"), b5 = B("answers"), b6 = B("asks"), b7 = B("listens"), b8 = B("grownups"), b9 = B("parents");
  const b1 = B("cold"), b2 = B("problem"), b3 = B("reveal");
  const R = 1380; // phone x when it sits on the right
  const pillW = 520;
  return (
    <AbsoluteFill style={{ background: C.dark }}>
      {/* persistent pastel world from the reveal onwards */}
      <Sequence from={b3.start} durationInFrames={tl.total - b3.start} name="pastel world"><PastelBg /></Sequence>

      <Sequence from={0} durationInFrames={b1.frames + b2.frames} name="1-2 cold open + problem"><DarkOpen f1={b1.frames} f2={b2.frames} /></Sequence>
      {S(b3, "3 Reveal", <Reveal frames={b3.frames} />)}

      {S(b4, "4 It sees", (
        <PhoneScene frames={b4.frames} headline={["It", "sees."]} accent={[1]} accentColor={C.sky}
          caption={{ text: "You ask: “Why does the snail have a shell?”", at: 150, y: 400 }}
          callouts={[
            { text: "Camera on: it looks with you", x: 560, y: 840, tx: 1262, ty: 884, at: 80, color: C.sky, width: pillW },
            { text: "The snail pops up", x: 560, y: 650, tx: 1230, ty: 300, at: 240, color: C.peach, width: pillW },
          ]}
          phones={[{ clip: "clipA-text.webm", from: 1.0, rate: 0.75, x: R, enterAt: 4, enter: "bottom", dir: 1 }]} />
      ))}
      {S(b5, "5 It answers", (
        <PhoneScene frames={b5.frames} headline={["It answers like", "a kind grown-up."]} accent={[4, 5]} accentColor={C.peach} headSize={100}
          callouts={[
            { text: "First words in 8 ms", x: 560, y: 590, tx: 1215, ty: 330, at: 50, color: C.peach, width: pillW },
            { text: "Words a 6-year-old knows", x: 560, y: 730, tx: 1230, ty: 480, at: 170, color: C.mint, width: pillW },
            { text: "Facts from a curated kids' knowledge base", x: 560, y: 870, tx: 1230, ty: 640, at: 300, color: C.sky, width: pillW + 60, size: 30 },
          ]}
          phones={[{ clip: "clipA-text.webm", from: 5.5, rate: 0.8, x: R, dir: -1 }]} />
      ))}
      {S(b6, "6 It asks you to guess", (
        <PhoneScene frames={b6.frames} headline={["Then it asks", "you to guess."]} accent={[5]} accentColor={C.peach} headSize={104}
          caption={{ text: "“Do you think a snail comes out in the rain, or hides in its shell?”", at: 140, y: 400 }}
          callouts={[
            { text: "Uses what parents told it: has a dog", x: 560, y: 720, tx: 1240, ty: 690, at: 60, color: C.lav, width: pillW + 40, size: 30 },
            { text: "Guess first. The thinking is the point.", x: 560, y: 860, tx: 1250, ty: 770, at: 260, color: C.peach, width: pillW + 60, size: 30 },
          ]}
          phones={[{ clip: "clipA-text.webm", from: 15, rate: 0.55, x: R, dir: 1 }]} />
      ))}
      {S(b7, "7 It listens", (
        <PhoneScene frames={b7.frames} headline={["It", "listens."]} accent={[1]} accentColor={C.sky} textX={1000}
          caption={{ text: "“Why do cats' eyes glow at night?”", at: 150, y: 400 }}
          callouts={[
            { text: "Hold the button and just ask", x: 1420, y: 860, tx: 700, ty: 880, at: 50, color: C.lav, width: pillW },
            { text: "Speech recognition on the device", x: 1420, y: 700, tx: 740, ty: 560, at: 200, color: C.sky, width: pillW + 40, size: 31 },
          ]}
          phones={[{ clip: "clipB-voice.webm", from: 2.0, rate: 1, x: 560, enterAt: 0, enter: "bottom", dir: -1 }]} />
      ))}
      {S(b8, "8 For grown-ups", (
        <PhoneScene frames={b8.frames} headline={["It knows what's", "for grown-ups."]} accent={[3, 4]} accentColor={C.lav} headSize={92}
          callouts={[
            { text: "A soft card, never a scare", x: 470, y: 560, tx: 960, ty: 420, at: 130, color: C.lav, width: 600 },
            { text: "Cheat sheet for parents: ages 5–6 / 7–8", x: 470, y: 760, tx: 1420, ty: 330, at: 330, color: C.mint, width: 640, size: 31 },
          ]}
          phones={[
            { clip: "clipC-sensitive.webm", from: 0.5, rate: 1, x: R, enterAt: 0, enter: "bottom", dir: 1 },
            { clip: "clipD-parent.webm", from: 9.5, rate: 1, x: R + 480, enterAt: 250, enter: "right", dir: -1 },
          ]}
          pan={[[0, 0], [250, 0], [330, -240]]} />
      ))}
      {S(b9, "9 For parents", (
        <PhoneScene frames={b9.frames} headline={["A week", "of wonder."]} accent={[2, 3]} accentColor={C.mint} headSize={104}
          callouts={[
            { text: "Whys this week, at a glance", x: 470, y: 520, tx: 1190, ty: 330, at: 60, color: C.lav, width: 600 },
            { text: "3 things to talk about at dinner", x: 470, y: 690, tx: 960, ty: 700, at: 260, color: C.peach, width: 600 },
            { text: "Only topics are stored. Never recordings.", x: 470, y: 860, tx: 960, ty: 850, at: 420, color: C.mint, width: 650, size: 31 },
          ]}
          phones={[
            { clip: "clipD-parent.webm", from: 0.5, rate: 0.85, x: R, enterAt: 0, enter: "bottom", dir: 1 },
            { clip: "clipB-voice.webm", from: 9, rate: 1, x: R + 480, enterAt: 180, enter: "right", dir: -1 },
          ]}
          pan={[[0, 0], [180, 0], [250, -240]]} />
      ))}

      {S(B("home"), "10 Everything stays home", <Home frames={B("home").frames} />)}
      {S(B("proof"), "11 Proof", <Proof frames={B("proof").frames} />)}
      {S(B("close"), "12 Close", <Close frames={B("close").frames} />)}

      {/* audio: music bed, ducked under narration; one narration WAV per beat */}
      <Audio src={staticFile("audio/music.wav")} volume={musicVolume} />
      {tl.beats.filter((b) => b.hasNarr).map((b) => (
        <Sequence key={b.id} from={b.start + Math.round(b.narrDelay * tl.fps)} durationInFrames={Math.ceil(b.narrSec * tl.fps) + 2} name={`narration ${b.id}`}>
          <Audio src={staticFile(`audio/narr-${String(b.id).padStart(2, "0")}.wav`)} volume={1} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
