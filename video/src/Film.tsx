import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import tl from "./timeline.json";

const Placeholder: React.FC<{ id: number; title: string }> = ({ id, title }) => (
  <AbsoluteFill style={{ background: "#2B2A4A", color: "#fff", justifyContent: "center", alignItems: "center", fontSize: 90, fontFamily: "sans-serif" }}>
    {id}. {title}
  </AbsoluteFill>
);

export const Film: React.FC = () => (
  <AbsoluteFill>
    {tl.beats.map((b) => (
      <Sequence key={b.id} from={b.start} durationInFrames={b.frames} name={`${b.id} ${b.title}`}>
        <Placeholder id={b.id} title={b.title} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
