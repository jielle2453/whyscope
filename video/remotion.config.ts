import { Config } from "@remotion/cli/config";
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
Config.setOverwriteOutput(true);
Config.setPublicDir("public");
import fs from "node:fs";
// Long Windows paths break spawning the bundled browser; use a short-path copy when present.
if (fs.existsSync("C:/whyscope-chrome/chrome-headless-shell.exe")) {
  Config.setBrowserExecutable("C:/whyscope-chrome/chrome-headless-shell.exe");
}
