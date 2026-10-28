import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F, Headline, Sfx, eio, eout, PastelBg } from "./ui";
import { Logo } from "./scenes1";

const fadeIO = (f: number, frames: number, a = 14, b = 14) =>
  Math.min(interpolate(f, [0, a], [0, 1], { extrapolateRight: "clamp" }), interpolate(f, [frames - b, frames], [1, 0], { extrapolateLeft: "clamp" }));

/* ---------------------------------------------------------------- flat illustrations */
const PiBoard: React.FC = () => (
  <svg width="560" height="360" viewBox="0 0 560 360">
    <rect x="4" y="4" width="552" height="352" rx="26" fill="#2E9F6F" stroke="#1F7A5C" strokeWidth="8" />
    {[[30, 30], [530, 30], [30, 330], [530, 330]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="9" fill="#E9F7EF" stroke="#1F7A5C" strokeWidth="3" />)}
    {/* GPIO header */}
    <rect x="70" y="26" width="300" height="38" rx="4" fill="#1d1b3a" />
    {Array.from({ length: 20 }).map((_, i) => (<React.Fragment key={i}><circle cx={84 + i * 14.5} cy="38" r="3.4" fill="#F2C94C" /><circle cx={84 + i * 14.5} cy="52" r="3.4" fill="#F2C94C" /></React.Fragment>))}
    {/* SoC */}
    <rect x="150" y="130" width="120" height="120" rx="10" fill="#C9CCD8" stroke="#8F93AA" strokeWidth="4" />
    <rect x="172" y="152" width="76" height="76" rx="6" fill="#B2B6C8" />
    <text x="210" y="198" textAnchor="middle" fontFamily="Nunito, sans-serif" fontWeight="800" fontSize="15" fill="#5a5e78">BCM</text>
    {/* USB + ethernet on the right */}
    {[110, 195].map((y, i) => (<g key={i}><rect x="430" y={y} width="122" height="72" rx="6" fill="#B9BDCC" stroke="#8F93AA" strokeWidth="3" /><rect x="444" y={y + 14} width="94" height="16" fill="#2b2a4a" /><rect x="444" y={y + 42} width="94" height="16" fill="#2b2a4a" /></g>))}
    <rect x="430" y="285" width="122" height="62" rx="6" fill="#B9BDCC" stroke="#8F93AA" strokeWidth="3" />
    <rect x="446" y="298" width="90" height="34" fill="#2b2a4a" />
    {/* micro-HDMI + USB-C power */}
    {[60, 128, 196].map((x, i) => <rect key={i} x={x} y="318" width={i === 0 ? 50 : 52} height="30" rx="5" fill="#C9CCD8" stroke="#8F93AA" strokeWidth="3" />)}
    <text x="320" y="320" fontFamily="Nunito, sans-serif" fontWeight="800" fontSize="17" fill="#E9F7EF" opacity=".85">Raspberry Pi 5</text>
  </svg>
);

const UGen: React.FC = () => (
  <svg width="430" height="170" viewBox="0 0 430 170">
    <rect x="30" y="8" width="380" height="154" rx="16" fill="#1d1b3a" stroke="#5B4AB8" strokeWidth="6" />
    <rect x="6" y="58" width="26" height="54" rx="4" fill="#F2C94C" />
    {Array.from({ length: 8 }).map((_, i) => <rect key={i} x="8" y={62 + i * 6.2} width="22" height="3" fill="#B8860B" />)}
    {Array.from({ length: 9 }).map((_, i) => <rect key={i} x={74 + i * 26} y="28" width="12" height="112" rx="5" fill="#2f2c5a" />)}
    <rect x="60" y="62" width="150" height="46" rx="10" fill="#5B4AB8" opacity=".9" />
    <text x="135" y="93" textAnchor="middle" fontFamily="Nunito, sans-serif" fontWeight="800" fontSize="26" fill="#fff">UGen300</text>
    <rect x="344" y="52" width="58" height="22" rx="5" fill="#C9CCD8" /><rect x="344" y="92" width="58" height="22" rx="5" fill="#C9CCD8" />
    <circle cx="48" cy="26" r="6" fill="#0e0d1f" /><circle cx="48" cy="144" r="6" fill="#0e0d1f" />
  </svg>
);

/* ---------------------------------------------------------------- Beat 10: everything stays home */
export const Home: React.FC<{ frames: number }> = ({ frames }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const op = fadeIO(f, frames, 24, 22);
  const pi = spring({ frame: f - 16, fps, config: { damping: 14, stiffness: 80, mass: 1 } });
  const ug = spring({ frame: f - 58, fps, config: { damping: 8, stiffness: 110, mass: 0.9 } });
  const click = spring({ frame: f - 82, fps, config: { damping: 6, stiffness: 240 } });
  const stamp = spring({ frame: f - 118, fps, config: { damping: 7, stiffness: 150, mass: 0.8 } });
  const push = interpolate(f, [0, frames], [1, 1.05], { easing: eio });
  const items = ["On-device. No cloud.", "No subscription needed.", "Never bricks."];
  const foot = interpolate(f, [frames - 120, frames - 90], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ opacity: op, background: "radial-gradient(ellipse at 50% 40%, #ffffff 0%, #f4f2fb 70%, #ebe8f6 100%)" }}>
      <Sfx name="pop" at={20} volume={0.4} />
      <Sfx name="stamp" at={82} volume={0.45} />
      <Sfx name="stamp" at={118} volume={0.7} />
      <Headline lines={["Everything", "stays home."]} x={120} y={110} size={112} accent={[2]} accentColor={C.mint} />
      {items.map((s, i) => {
        const p = spring({ frame: f - (150 + i * 36), fps, config: { damping: 16, stiffness: 110 } });
        return (
          <div key={i} style={{ position: "absolute", left: 120, top: 470 + i * 96, display: "flex", alignItems: "center", gap: 22, opacity: p, transform: `translateX(${(1 - p) * -60}px)`, fontFamily: F.text, fontWeight: 800, fontSize: 48, color: C.ink }}>
            <svg width="46" height="46" viewBox="0 0 46 46"><circle cx="23" cy="23" r="22" fill={C.mint} /><path d="M12 24l8 8 15-17" stroke="#fff" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
            {s}
          </div>
        );
      })}
      <Sfx name="tick" at={150} volume={0.3} /><Sfx name="tick" at={186} volume={0.3} /><Sfx name="tick" at={222} volume={0.3} />
      {/* studio device */}
      <div style={{ position: "absolute", left: 0, top: 0, width: 1920, height: 1080, transform: `scale(${push})`, transformOrigin: "1330px 560px" }}>
        <div style={{ position: "absolute", left: 1330 - 360, top: 770, width: 720, height: 70, borderRadius: "50%", background: "rgba(43,42,74,.18)", filter: "blur(26px)", opacity: pi }} />
        <div style={{ position: "absolute", left: 1330 - 280 + (1 - pi) * -900, top: 470 + Math.sin(f / 30) * 3, transform: `rotate(${(1 - pi) * -12}deg)` }}><PiBoard /></div>
        <div style={{ position: "absolute", left: 1330 - 205, top: 360 - (1 - ug) * 700, opacity: Math.min(1, ug * 3), transform: `scale(${1 + 0.05 * (1 - click)})`, filter: "drop-shadow(0 18px 22px rgba(43,42,74,.3))" }}><UGen /></div>
        <div style={{ position: "absolute", left: 1330 - 40, top: 240, transform: `rotate(-9deg) scale(${stamp * (1.0)})`, opacity: Math.min(1, stamp * 2),
          border: `7px solid ${C.peach}`, color: C.peach, borderRadius: 22, padding: "12px 30px", fontFamily: F.display, fontWeight: 700, fontSize: 50, background: "rgba(255,255,255,.92)", whiteSpace: "nowrap", boxShadow: "0 10px 30px rgba(194,65,12,.22)" }}>
          Hailo-10H · 2.5 W
        </div>
      </div>
      <div style={{ position: "absolute", left: 0, width: 1920, top: 985, textAlign: "center", fontFamily: F.text, fontWeight: 700, fontSize: 30, color: "#6b6a8a", opacity: foot }}>
        Prototype on a laptop today · UGen300 in Stage II
      </div>
    </AbsoluteFill>
  );
};

/* ---------------------------------------------------------------- Beat 11: proof */
const TILES = [
  { v: "≤ 2.5 s", l: "first word", c: C.lav, stamp: "measured today: 8 ms" },
  { v: "≤ 20 %", l: "child speech errors (CER)", c: C.sky },
  { v: "≥ 85 %", l: "pointing: right object", c: C.mint },
  { v: "≤ 10 %", l: "wrong answers", c: C.peach, stamp: "measured today: 91.7 %" },
  { v: "? J", l: "energy per question", c: C.ink },
];
export const Proof: React.FC<{ frames: number }> = ({ frames }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const op = fadeIO(f, frames, 12, 12);
  return (
    <AbsoluteFill style={{ opacity: op }}>
      <Headline lines={["Five numbers."]} x={120} y={90} size={110} accent={[1]} accentColor={C.lav} />
      <div style={{ position: "absolute", left: 124, top: 235, fontFamily: F.text, fontWeight: 700, fontSize: 38, color: "#5a5979", opacity: interpolate(f, [30, 50], [0, 1], { extrapolateRight: "clamp" }) }}>
        To be measured on the real hardware.
      </div>
      {TILES.map((t, i) => {
        const p = spring({ frame: f - (24 + i * 9), fps, config: { damping: 13, stiffness: 100, mass: 0.9 } });
        const sp = spring({ frame: f - (t.stamp ? (i === 0 ? 150 : 190) : 9999), fps, config: { damping: 6, stiffness: 160, mass: 0.7 } });
        const x = 90 + i * 360;
        return (
          <div key={i} style={{ position: "absolute", left: x, top: 340, width: 320, height: 470, perspective: 1400 }}>
            <div style={{ width: "100%", height: "100%", transform: `rotateX(${(1 - p) * 90}deg) translateY(${(1 - p) * 40}px)`, transformOrigin: "50% 100%", opacity: Math.min(1, p * 3),
              background: "#fff", borderRadius: 34, boxShadow: "0 24px 50px rgba(43,42,74,.16)", borderTop: `12px solid ${t.c}`, boxSizing: "border-box", padding: "48px 24px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 24, textAlign: "center" }}>
              <div style={{ fontFamily: F.display, fontWeight: 700, fontSize: 84, color: t.c, lineHeight: 1 }}>{t.v}</div>
              <div style={{ fontFamily: F.text, fontWeight: 800, fontSize: 32, color: C.ink, lineHeight: 1.2 }}>{t.l}</div>
              <div style={{ fontFamily: F.text, fontWeight: 700, fontSize: 24, color: "#8a89a8" }}>target</div>
            </div>
            {t.stamp && sp > 0.01 && (
              <>
                <Sfx name="stamp" at={i === 0 ? 150 : 190} volume={0.6} />
                <div style={{ position: "absolute", left: -18, right: -18, top: 300, transform: `rotate(-9deg) scale(${sp * 1})`, opacity: Math.min(1, sp * 2), textAlign: "center",
                  border: `6px solid ${C.mint}`, color: C.mint, background: "rgba(255,255,255,.95)", borderRadius: 18, padding: "10px 8px", fontFamily: F.display, fontWeight: 700, fontSize: 34, lineHeight: 1.1, boxShadow: "0 10px 26px rgba(31,122,92,.25)" }}>
                  <div style={{ fontSize: 26, letterSpacing: 1, textTransform: "uppercase" }}>{t.stamp.split(": ")[0]}</div>
                  <div style={{ fontSize: 52 }}>{t.stamp.split(": ")[1]}</div>
                </div>
              </>
            )}
          </div>
        );
      })}
      {TILES.map((_, i) => <Sfx key={i} name="tick" at={24 + i * 9 + 6} volume={0.25} />)}
    </AbsoluteFill>
  );
};

/* ---------------------------------------------------------------- Beat 12: close */
export const Close: React.FC<{ frames: number }> = ({ frames }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const logo = spring({ frame: f, fps, config: { damping: 9, stiffness: 90 } });
  const chars = spring({ frame: f - 6, fps, config: { damping: 8, stiffness: 85, mass: 1 } });
  const tagline = "Point at it. Ask why.";
  const sub = interpolate(f, [70, 95], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const out = interpolate(f, [frames - 20, frames], [1, 0.0], { extrapolateLeft: "clamp" });
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 820, top: 1080 - 640 + (1 - chars) * 700, width: 1100, height: 640 }}>
        <Img src={staticFile("img/characters-transparent.webp")} style={{ width: "100%", height: "100%", objectFit: "contain", objectPosition: "bottom" }} />
      </div>
      <div style={{ position: "absolute", left: 130, top: 120, transform: `scale(${0.6 + 0.4 * logo})`, transformOrigin: "left top", opacity: Math.min(1, logo * 2) }}><Logo p={1} size={190} /></div>
      <div style={{ position: "absolute", left: 120, top: 330, fontFamily: F.display, fontWeight: 700, fontSize: 150, color: C.ink, letterSpacing: -3, transform: `translateY(${(1 - logo) * 30}px)`, opacity: Math.min(1, logo * 2) }}>Whyscope</div>
      <div style={{ position: "absolute", left: 126, top: 520, display: "flex", fontFamily: F.text, fontWeight: 800, fontSize: 64, color: C.lav, whiteSpace: "pre" }}>
        {tagline.split("").map((ch, i) => <span key={i} style={{ opacity: interpolate(f, [14 + i * 2.2, 22 + i * 2.2], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>{ch}</span>)}
      </div>
      <div style={{ position: "absolute", left: 126, top: 640, opacity: sub, transform: `translateY(${(1 - sub) * 14}px)`, fontFamily: F.text, fontWeight: 700, color: C.ink }}>
        <div style={{ fontSize: 44 }}>Whyscope 好奇鏡</div>
        <div style={{ fontSize: 34, marginTop: 14, color: C.sky }}>github.com/jielle2453/whyscope</div>
        <div style={{ fontSize: 30, marginTop: 8, color: "#6b6a8a" }}>A home-first curiosity companion · jielle2453</div>
      </div>
      <AbsoluteFill style={{ background: "#fff", opacity: (1 - out) * 0.0 }} />
    </AbsoluteFill>
  );
};
export { PastelBg };
