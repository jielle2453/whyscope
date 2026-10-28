import React from "react";
import { AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F, Headline, PhoneStage, Sfx, eio, eout, PastelBg } from "./ui";

/* ---------------------------------------------------------------- Beats 1 + 2: cold open and the problem */
const QUESTIONS = [
  "為什麼蝸牛有殼？", "Why is the sky blue?", "為什麼月亮跟著我走？", "Why do cats' eyes glow?", "為什麼會打雷？",
  "Why is the ocean salty?", "Where does the sun go at night?", "為什麼狗狗會搖尾巴？", "How do birds know where to go?",
  "為什麼水是濕的？", "Why do I have a belly button?", "為什麼彩虹有七種顏色？", "Why can't I tickle myself?",
  "為什麼星星會閃？", "Why do onions make me cry?", "為什麼我會打嗝？", "Why is snow cold?", "為什麼夜晚會黑？",
  "Where do puddles go?", "為什麼蜜蜂會螫人？", "Why do we dream?", "How do fish breathe?", "為什麼氣球會飛？", "Why is fire hot?",
];
const T0 = 0.7; // first question starts (s)
const starts: number[] = [];
{
  let t = T0;
  QUESTIONS.forEach((_, i) => { starts.push(t); t += Math.max(0.17, 1.0 * Math.pow(0.84, i)); });
}
const isZh = (s: string) => /[一-鿿]/.test(s);

export const DarkOpen: React.FC<{ f1: number; f2: number }> = ({ f1, f2 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = f1 + f2;
  const dimAt = 11 * fps;
  const push = interpolate(f, [0, dimAt + 30], [1, 1.08], { easing: eio, extrapolateRight: "clamp" });
  const dim = interpolate(f, [dimAt, dimAt + 40], [1, 0.1], { easing: eio, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // the lone "Why?"
  const whyIn = spring({ frame: f - dimAt - 8, fps, config: { damping: 20, stiffness: 40, mass: 1.4 } });
  const whyY = interpolate(f, [dimAt, f1 + 60], [560, 340], { easing: eio, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const breathe = 1 + 0.03 * Math.sin(f / 17);
  const endDim = interpolate(f, [total - 45, total - 4], [1, 0.4], { extrapolateLeft: "clamp" });
  const lines = [
    { t: f1 + 0.9 * fps, s: "Most get a shrug." },
    { t: f1 + 3.4 * fps, s: "Smart speakers can't see what she's pointing at." },
    { t: f1 + 7.4 * fps, s: "Curiosity fades." },
  ];
  const whyFade = interpolate(f, [f1 + 7.4 * fps, f1 + 9.2 * fps], [1, 0.28], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: C.dark }}>
      <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 45%, #25214a 0%, #15132B 62%)" }} />
      <AbsoluteFill style={{ transform: `scale(${push})`, opacity: dim, overflow: "hidden" }}>
        {QUESTIONS.map((q, i) => {
          const st = starts[i] * fps;
          if (f < st) return null;
          const size = 44 + Math.floor(random(`s${i}`) * 34);
          const zh = isZh(q);
          const estW = q.length * size * (zh ? 1.02 : 0.5);
          const x = 50 + random(`x${i}`) * Math.max(10, 1820 - estW);
          const y = 40 + random(`y${i}`) * 940;
          const rot = (random(`r${i}`) - 0.5) * 12;
          const sc = 0.92 + random(`c${i}`) * 0.3;
          const n = Math.min(q.length, Math.floor((f - st) * 1.4) + 1);
          const typing = n < q.length;
          const latest = i === QUESTIONS.length - 1 || f < starts[i + 1] * fps;
          const cursorOn = latest && Math.floor(f / 8) % 2 === 0;
          const pop = spring({ frame: f - st, fps, config: { damping: 14, stiffness: 160 } });
          const tint = ["#F4F1FF", "#FFE6D6", "#DCE9FF", "#E8DEFF"][i % 4];
          return (
            <div key={i} style={{ position: "absolute", left: x, top: y, transform: `rotate(${rot}deg) scale(${sc * (0.9 + 0.1 * pop)})`, transformOrigin: "left center", whiteSpace: "nowrap",
              fontFamily: F.hand, fontSize: size, color: tint, opacity: 0.55 + 0.45 * random(`o${i}`), textShadow: "0 0 24px rgba(160,140,255,.35)" }}>
              {q.slice(0, n)}
              {(typing || cursorOn) && <span style={{ display: "inline-block", width: size * 0.07, height: size * 0.85, background: "#fff", marginLeft: 6, verticalAlign: "middle", opacity: typing ? 1 : 0.9 }} />}
            </div>
          );
        })}
      </AbsoluteFill>
      {QUESTIONS.map((_, i) => <Sfx key={i} name={i % 3 === 1 ? "tick2" : "tick"} at={starts[i] * fps} volume={0.22 + Math.min(0.2, i * 0.01)} />)}
      {/* "Why?" breathes at centre, then rises to make room for the three lines */}
      <div style={{ position: "absolute", left: 0, right: 0, top: whyY - 150, textAlign: "center", fontFamily: F.display, fontWeight: 600, fontSize: 300, color: "#fff", opacity: Math.min(1, whyIn * 1.4) * whyFade * endDim,
        transform: `scale(${breathe * (0.92 + 0.08 * whyIn)})`, textShadow: "0 0 90px rgba(150,130,255,.55)" }}>
        Why?
      </div>
      {lines.map((l, i) => {
        const p = spring({ frame: f - l.t, fps, config: { damping: 20, stiffness: 70 } });
        return (
          <React.Fragment key={i}>
            <Sfx name="tick2" at={l.t} volume={0.3} />
            <div style={{ position: "absolute", left: 0, right: 0, top: 590 + i * 110, textAlign: "center", fontFamily: F.text, fontWeight: 700, fontSize: 56, color: i === 2 ? "#F6C7A8" : "#E8E3FF",
              opacity: p * endDim, transform: `translateY(${(1 - p) * 28}px)` }}>
              {l.s}
            </div>
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};

/* ---------------------------------------------------------------- Logo (draws itself) */
export const Logo: React.FC<{ p: number; size?: number }> = ({ p, size = 300 }) => {
  const seg = (a: number, b: number) => Math.min(1, Math.max(0, (p - a) / (b - a)));
  const draw = (v: number) => ({ pathLength: 1, strokeDasharray: 1, strokeDashoffset: 1 - eout(v) });
  return (
    <svg width={size} height={size} viewBox="0 0 140 140" fill="none" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="58" cy="58" r="40" stroke={C.lav} strokeWidth="9" {...draw(seg(0, 0.5))} />
      <path d="M88 88 L120 120" stroke={C.peach} strokeWidth="12" {...draw(seg(0.45, 0.7))} />
      <path d="M45 48a13 13 0 1 1 19 11c-5 3-7 6-7 11" stroke={C.sky} strokeWidth="8" {...draw(seg(0.6, 0.92))} />
      <circle cx="57" cy="83" r="4.5" fill={C.sky} opacity={seg(0.9, 1)} />
    </svg>
  );
};

/* ---------------------------------------------------------------- Beat 3: reveal */
export const Reveal: React.FC<{ frames: number }> = ({ frames }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const R = interpolate(f, [10, 90], [0, 1700], { easing: eio, extrapolateRight: "clamp" });
  const bloomS = interpolate(f, [6, 80], [0, 3000], { easing: eout, extrapolateRight: "clamp" });
  const bloomO = interpolate(f, [6, 34, 100], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const logoP = interpolate(f, [58, 128], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const wm = spring({ frame: f - 112, fps, config: { damping: 13, stiffness: 90 } });
  const move = spring({ frame: f - 165, fps, config: { damping: 16, stiffness: 70, mass: 1.1 } });
  const tag = interpolate(f, [270, 305], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: eout });
  const out = interpolate(f, [frames - 10, frames], [1, 0], { extrapolateLeft: "clamp" });
  const breath = 1 + 0.012 * Math.sin(f / 20);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Sfx name="bloom" at={4} volume={0.7} />
      {/* logo group: centred first, then slides left as the phone rises */}
      <div style={{ position: "absolute", left: 0, top: 0, width: 1920, height: 1080, transform: `translateX(${-400 * move}px) scale(${1 - 0.08 * move}) scale(${breath})`, transformOrigin: "960px 540px" }}>
        <div style={{ position: "absolute", left: 810, top: 190, filter: `drop-shadow(0 16px 24px rgba(91,74,184,.25))` }}><Logo p={logoP} size={300} /></div>
        <div style={{ position: "absolute", left: 0, width: 1920, top: 500, textAlign: "center", fontFamily: F.display, fontWeight: 700, fontSize: 168, color: C.ink, letterSpacing: -3,
          opacity: Math.min(1, wm * 1.5), transform: `translateY(${(1 - wm) * 50}px) scale(${0.9 + 0.1 * wm})` }}>
          Whyscope
        </div>
        <div style={{ position: "absolute", left: 0, width: 1920, top: 720, textAlign: "center", fontFamily: F.text, fontWeight: 800, fontSize: 60, color: C.lav, opacity: tag, transform: `translateY(${(1 - tag) * 18}px)` }}>
          Point at it. Ask why.
        </div>
      </div>
      <PhoneStage cfg={{ img: "kid-idle.png", x: 1420, enterAt: 165, enter: "bottom", glow: true }} dur={frames} />
      {/* the dark wipes away from the centre, a warm bloom leads it */}
      {R < 1690 && (
        <AbsoluteFill style={{ background: C.dark, WebkitMaskImage: `radial-gradient(circle at 50% 50%, transparent ${R}px, #000 ${R + 320}px)`, maskImage: `radial-gradient(circle at 50% 50%, transparent ${R}px, #000 ${R + 320}px)` }} />
      )}
      <div style={{ position: "absolute", left: 960 - bloomS / 2, top: 540 - bloomS / 2, width: bloomS, height: bloomS, borderRadius: "50%", opacity: bloomO, filter: "blur(40px)",
        background: "radial-gradient(circle, #ffffff 0%, rgba(255,250,240,.95) 30%, rgba(255,226,200,.55) 55%, rgba(255,255,255,0) 72%)" }} />
    </AbsoluteFill>
  );
};

export { PastelBg };
