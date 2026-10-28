import React from "react";
import {
  AbsoluteFill, Audio, Easing, Img, OffthreadVideo, Sequence, interpolate, random, spring,
  staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";
import { loadFont as loadNunito } from "@remotion/google-fonts/Nunito";
import { loadFont as loadFredoka } from "@remotion/google-fonts/Fredoka";
import { loadFont as loadHand } from "@remotion/google-fonts/PatrickHand";

const nunito = loadNunito("normal", { weights: ["400", "700", "800"], subsets: ["latin"] });
const fredoka = loadFredoka("normal", { weights: ["500", "600", "700"], subsets: ["latin"] });
const hand = loadHand("normal", { weights: ["400"], subsets: ["latin"] });

export const C = {
  ink: "#2B2A4A", lav: "#5B4AB8", sky: "#2B6CB0", peach: "#C2410C", mint: "#1F7A5C",
  dark: "#15132B", gradient: "linear-gradient(160deg,#F6EEFF,#FDE9F1,#FFF2E6,#E9F3FF)",
};
export const F = {
  text: `${nunito.fontFamily}, "Microsoft JhengHei", sans-serif`,
  display: `${fredoka.fontFamily}, "Microsoft JhengHei", sans-serif`,
  hand: `${hand.fontFamily}, "Microsoft JhengHei", "Segoe Print", cursive`,
};
export const eio = Easing.inOut(Easing.cubic);
export const eout = Easing.out(Easing.cubic);

/** Short sound effect at a local frame. */
export const Sfx: React.FC<{ name: "tick" | "tick2" | "pop" | "stamp" | "bloom"; at: number; volume?: number }> = ({ name, at, volume = 0.6 }) => (
  <Sequence from={Math.max(0, Math.round(at))} layout="none">
    <Audio src={staticFile(`audio/${name}.wav`)} volume={volume} />
  </Sequence>
);

/** Slowly drifting pastel blobs. */
export const Blobs: React.FC<{ speed?: number; opacity?: number }> = ({ speed = 1, opacity = 0.75 }) => {
  const f = useCurrentFrame();
  const cols = ["#E6D9FF", "#FFD9E6", "#FFE7CC", "#D6E8FF", "#E3F6EA"];
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {cols.map((c, i) => {
        const x = 200 + i * 380 + Math.sin((f * speed) / (90 + i * 23) + i * 2) * 140;
        const y = 150 + ((i * 337) % 800) + Math.cos((f * speed) / (110 + i * 17) + i) * 110;
        const s = 420 + (i % 3) * 120 + Math.sin(f / 70 + i) * 25;
        return <div key={i} style={{ position: "absolute", left: x - s / 2, top: y - s / 2, width: s, height: s, borderRadius: "50%", background: c, filter: "blur(70px)", opacity }} />;
      })}
    </AbsoluteFill>
  );
};

export const PastelBg: React.FC = () => (
  <AbsoluteFill style={{ background: C.gradient }}>
    <Blobs />
  </AbsoluteFill>
);

/** Words slide in from the left, staggered, with a spring. */
export const Headline: React.FC<{ lines: string[]; x: number; y: number; size?: number; accent?: number[]; accentColor?: string; delay?: number; color?: string; font?: string; stagger?: number }> = ({
  lines, x, y, size = 124, accent = [], accentColor = C.lav, delay = 0, color = C.ink, font = F.display, stagger = 5,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  let k = 0;
  return (
    <div style={{ position: "absolute", left: x, top: y, fontFamily: font, fontWeight: 600, fontSize: size, lineHeight: 1.08, color, letterSpacing: -1 }}>
      {lines.map((line, li) => (
        <div key={li} style={{ display: "flex", gap: size * 0.26, whiteSpace: "nowrap" }}>
          {line.split(" ").map((w) => {
            const idx = k++;
            const p = spring({ frame: f - delay - idx * stagger, fps, config: { damping: 15, stiffness: 120, mass: 0.8 } });
            return (
              <span key={idx} style={{ display: "inline-block", transform: `translateX(${(1 - p) * -170}px)`, opacity: Math.min(1, p * 1.6), color: accent.includes(idx) ? accentColor : color }}>
                {w}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
};

/** Caption (translation / quote). */
export const Caption: React.FC<{ text: string; x: number; y: number; at: number; width?: number; size?: number }> = ({ text, x, y, at, width = 760, size = 38 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - at, fps, config: { damping: 18, stiffness: 110 } });
  return (
    <div style={{ position: "absolute", left: x, top: y, width, transform: `translateY(${(1 - p) * 30}px)`, opacity: p, fontFamily: F.text, fontWeight: 700, fontSize: size, color: C.ink, lineHeight: 1.25, borderLeft: `8px solid ${C.lav}`, padding: "6px 0 6px 22px" }}>
      {text}
    </div>
  );
};

/** Pop-in pill with a connector line that draws toward (tx, ty). Centre of the pill at (x, y). */
export const Callout: React.FC<{ text: string; x: number; y: number; tx: number; ty: number; at: number; color?: string; width?: number; size?: number }> = ({
  text, x, y, tx, ty, at, color = C.lav, width = 460, size = 34,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: f - at, fps, config: { damping: 9, stiffness: 190, mass: 0.7 } });
  const line = interpolate(f - at - 6, [0, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: eout });
  const len = Math.hypot(tx - x, ty - y);
  return (
    <>
      <Sfx name="pop" at={at} volume={0.35} />
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}>
        <line x1={x} y1={y} x2={tx} y2={ty} stroke={color} strokeWidth={4} strokeLinecap="round" strokeDasharray={len} strokeDashoffset={len * (1 - line)} opacity={0.85} />
        <circle cx={tx} cy={ty} r={9 * line} fill={color} />
      </svg>
      <div style={{
        position: "absolute", left: x - width / 2, top: y - size, width, minHeight: size * 2, display: "flex", alignItems: "center", justifyContent: "center",
        transform: `scale(${Math.max(0, pop)})`, opacity: Math.min(1, pop * 2), padding: "10px 26px", boxSizing: "border-box",
        background: "#fff", border: `3px solid ${color}`, borderRadius: 999, color, fontFamily: F.text, fontWeight: 800, fontSize: size, textAlign: "center",
        lineHeight: 1.15, boxShadow: "0 14px 34px rgba(43,42,74,.16)",
      }}>
        {text}
      </div>
    </>
  );
};

/** Phone mockup: bezel, island, clip/image inside, glass reflection. */
export const PhoneMock: React.FC<{ clip?: string; img?: string; from?: number; rate?: number; reflect?: number; glow?: boolean }> = ({ clip, img, from = 0, rate = 1, reflect = 0, glow }) => {
  const w = 400, h = 866;
  return (
    <div style={{ width: w + 28, height: h + 28, borderRadius: 64, padding: 14, boxSizing: "border-box", position: "relative",
      background: "linear-gradient(145deg,#4a4870,#1d1b3a 40%,#2b2a4a)", boxShadow: `inset 0 0 0 2px rgba(255,255,255,.18), inset 0 0 14px rgba(0,0,0,.5)${glow ? ", 0 0 120px rgba(91,74,184,.45)" : ""}` }}>
      <div style={{ width: w, height: h, borderRadius: 50, overflow: "hidden", position: "relative", background: "#fff" }}>
        {clip && <OffthreadVideo src={staticFile(`clips/${clip}`)} startFrom={Math.round(from * 30)} playbackRate={rate} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
        {img && <Img src={staticFile(`img/${img}`)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
        <div style={{ position: "absolute", left: "50%", top: 12, width: 112, height: 30, marginLeft: -56, borderRadius: 20, background: "#0e0d1f" }} />
        <div style={{ position: "absolute", inset: 0, background: `linear-gradient(${115 + reflect * 2}deg, rgba(255,255,255,.30) 0%, rgba(255,255,255,0) 28%, rgba(255,255,255,0) 72%, rgba(255,255,255,.14) 100%)`, mixBlendMode: "screen", pointerEvents: "none" }} />
      </div>
      <div style={{ position: "absolute", right: -4, top: 210, width: 5, height: 90, borderRadius: 3, background: "#34325a" }} />
    </div>
  );
};

export type PhoneCfg = {
  clip?: string; img?: string; from?: number; rate?: number;
  x: number;              // centre x on the 1920 canvas (before camera pan)
  enterAt?: number;       // local frame the phone starts entering (omit: already on screen)
  enter?: "bottom" | "right";
  dir?: 1 | -1;           // tilt direction: 1 = -8 -> +8, -1 = +8 -> -8
  glow?: boolean;
};

/** Reusable phone: 3D perspective tilt -8..+8 over the beat, Ken Burns drift, parallax drop shadow, spring entrance. */
export const PhoneStage: React.FC<{ cfg: PhoneCfg; dur: number }> = ({ cfg, dur }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const u0 = interpolate(f, [0, dur], [0, 1], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.sin) });
  const u = cfg.dir === -1 ? 1 - u0 : u0;
  const tilt = -8 + 16 * u;
  const kb = 1 + 0.06 * u;
  const driftX = -18 + 36 * u, driftY = 14 - 28 * u;
  let ex = 0, ey = 0, es = 1, eo = 1;
  if (cfg.enterAt !== undefined) {
    const p = spring({ frame: f - cfg.enterAt, fps, config: { damping: 11, stiffness: 70, mass: 0.95 } });
    eo = Math.min(1, p * 3);
    if (cfg.enter === "right") { ex = (1 - p) * 900; es = 0.9 + 0.1 * p; } else { ey = (1 - p) * 1250; }
  }
  const baseY = 540;
  return (
    <div style={{ position: "absolute", left: cfg.x - 214, top: baseY - 447, width: 428, height: 894, perspective: 2200, opacity: eo }}>
      <div style={{ position: "absolute", left: 20 - tilt * 7, top: 70 + Math.abs(tilt) * 2, width: 390, height: 840, borderRadius: 70, background: "rgba(43,42,74,.5)", filter: "blur(46px)", transform: `translate(${ex}px, ${ey}px)`, opacity: 0.5 }} />
      <div style={{ width: "100%", height: "100%", transformStyle: "preserve-3d", transform: `translate(${ex + driftX}px, ${ey + driftY}px) scale(${es * kb}) rotateY(${tilt}deg) rotateX(${3 - u * 3}deg)` }}>
        <PhoneMock clip={cfg.clip} img={cfg.img} from={cfg.from} rate={cfg.rate} reflect={tilt} glow={cfg.glow} />
      </div>
    </div>
  );
};

export type CalloutCfg = { text: string; x: number; y: number; tx: number; ty: number; at: number; color?: string; width?: number; size?: number };

/** Feature beat: headline + caption + callouts on one side, phone(s) on the other, optional camera pan. */
export const PhoneScene: React.FC<{
  frames: number;
  headline: string[]; accent?: number[]; accentColor?: string;
  textX?: number; headSize?: number;
  caption?: { text: string; at: number; y?: number };
  callouts?: CalloutCfg[];
  phones: PhoneCfg[];
  pan?: [number, number][];   // [localFrame, offsetX] keyframes for the phone group
}> = ({ frames, headline, accent, accentColor, textX = 120, headSize = 112, caption, callouts = [], phones, pan }) => {
  const f = useCurrentFrame();
  const fade = Math.min(interpolate(f, [0, 10], [0, 1], { extrapolateRight: "clamp" }), interpolate(f, [frames - 10, frames], [1, 0], { extrapolateLeft: "clamp" }));
  const panX = pan ? interpolate(f, pan.map((k) => k[0]), pan.map((k) => k[1]), { easing: eio, extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div style={{ position: "absolute", inset: 0, transform: `translateX(${panX * 0.35}px)` }}><Blobs speed={1.4} opacity={0.35} /></div>
      <Headline lines={headline} x={textX} y={130} size={headSize} accent={accent} accentColor={accentColor} />
      {caption && <Caption text={caption.text} x={textX} y={caption.y ?? 410} at={caption.at} />}
      {callouts.map((c, i) => <Callout key={i} {...c} />)}
      <div style={{ position: "absolute", inset: 0, transform: `translateX(${panX}px)` }}>
        {phones.map((p, i) => <PhoneStage key={i} cfg={p} dur={frames} />)}
      </div>
    </AbsoluteFill>
  );
};
export { random };
