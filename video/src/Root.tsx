import React from "react";
import { Composition } from "remotion";
import { Film } from "./Film";
import tl from "./timeline.json";

export const Root: React.FC = () => (
  <Composition
    id="Film"
    component={Film}
    durationInFrames={tl.total}
    fps={tl.fps}
    width={tl.width}
    height={tl.height}
  />
);
