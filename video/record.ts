// Records the four phone clips against the running prototype (http://localhost:8000).
// Usage: node record.ts [A|B|C|D ...]   (default: all)   Needs: npm i playwright; uses installed Edge/Chrome.
import { chromium, type Browser, type BrowserContext, type Page } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE ?? "http://localhost:8000";
const ROOT = import.meta.dirname;
const OUT = path.join(ROOT, "public", "clips");
const TMP = path.join(ROOT, ".tmp", "rec");
const W = 390, H = 844;
const QWAV = path.join(ROOT, "audio", "question.wav");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(TMP, { recursive: true });

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const channel = process.env.CHANNEL ?? "msedge";

async function launch(extra: string[] = []): Promise<Browser> {
  try {
    return await chromium.launch({ channel, headless: true, args: extra });
  } catch (e) {
    console.log("channel", channel, "failed, trying bundled chromium");
    return await chromium.launch({ headless: true, args: extra });
  }
}

async function clip(name: string, extraArgs: string[], body: (p: Page, ctx: BrowserContext) => Promise<void>) {
  const dir = path.join(TMP, name);
  fs.rmSync(dir, { recursive: true, force: true });
  const browser = await launch(extraArgs);
  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    permissions: ["microphone", "camera"],
    recordVideo: { dir, size: { width: W * 2, height: H * 2 } },
  });
  const page = await ctx.newPage();
  const t0 = Date.now();
  try {
    await body(page, ctx);
  } finally {
    const v = page.video();
    await ctx.close();
    await browser.close();
    if (v) {
      const src = await v.path();
      const dst = path.join(OUT, `${name}.webm`);
      fs.copyFileSync(src, dst);
      console.log(`clip ${name}: ${((Date.now() - t0) / 1000).toFixed(1)}s, ${(fs.statSync(dst).size / 1e6).toFixed(1)} MB`);
    }
  }
}

async function typeSlow(p: Page, sel: string, text: string, delay = 85) {
  await p.click(sel);
  await p.type(sel, text, { delay });
}

async function waitAnswer(p: Page, full = true) {
  await p.waitForFunction(() => document.body.classList.contains("has-answer"), null, { timeout: 20000 }).catch(() => {});
  // text appears at reading pace: wait until the ask-back sentence has started to show
  if (full) await p.waitForFunction(() => !!document.querySelector("#askb .s.in"), null, { timeout: 30000 }).catch(() => {});
}

const clips: Record<string, () => Promise<void>> = {
  // A: typed snail question, two-phase answer (first sentence now, explanation + ask-back after)
  A: () =>
    clip("clipA-text", [], async (p) => {
      await p.goto(`${BASE}/kid?lang=en`);
      await sleep(1800);
      await typeSlow(p, "#text", "why does a snail have a shell");
      await sleep(500);
      await p.click("#send");
      await waitAnswer(p, true);
      await sleep(5500);
    }),

  // B: voice question with Chrome's fake microphone fed by an SAPI WAV
  B: async () => {
    const args = [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      `--use-file-for-fake-audio-capture=${QWAV}`,
    ];
    let ok = false;
    try {
      await clip("clipB-voice", args, async (p) => {
        await p.goto(`${BASE}/kid?lang=en`);
        await sleep(1800);
        const box = (await p.locator("#talk").boundingBox())!;
        await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await p.mouse.down();
        await sleep(3600); // WAV is ~2.7 s; hold a little longer
        await p.mouse.up();
        await waitAnswer(p, true);
        const q = (await p.locator("#q").textContent())?.toLowerCase() ?? "";
        console.log("B transcript:", q.slice(0, 80));
        ok = /cat|glow|eye/.test(q) || (await p.locator("#first").textContent())?.toLowerCase().includes("cat") === true;
        await sleep(3500);
      });
    } catch (e) {
      console.log("B failed:", String(e).slice(0, 200));
    }
    if (!ok) {
      console.log("B: voice not transcribed as expected; falling back to a typed question");
      await clip("clipB-voice", [], async (p) => {
        await p.goto(`${BASE}/kid?lang=en`);
        await sleep(1500);
        await typeSlow(p, "#text", "why do cats eyes glow at night");
        await p.click("#send");
        await waitAnswer(p, true);
        await sleep(3500);
      });
      fs.writeFileSync(path.join(OUT, "clipB-FALLBACK.txt"), "voice clip is a typed fallback");
    }
  },

  // C: sensitive deflection, then out-of-base abstain
  C: () =>
    clip("clipC-sensitive", [], async (p) => {
      await p.goto(`${BASE}/kid?lang=en`);
      await sleep(1500);
      await typeSlow(p, "#text", "why do people die", 80);
      await p.click("#send");
      await waitAnswer(p, false);
      await sleep(4500);
      await p.click("#another").catch(() => {});
      await sleep(600);
      await typeSlow(p, "#text", "how does the stock market work", 70);
      await p.click("#send");
      await sleep(5500);
    }),

  // D: parent app Home -> Moments -> Cheats
  D: () =>
    clip("clipD-parent", [], async (p) => {
      await p.goto(`${BASE}/parent?lang=en`);
      await sleep(2500);
      await p.mouse.wheel(0, 350);
      await sleep(1800);
      await p.mouse.wheel(0, -350);
      await sleep(900);
      await p.click('nav .tab[data-tab="moments"]');
      await sleep(3200);
      await p.mouse.wheel(0, 300);
      await sleep(1800);
      await p.click('nav .tab[data-tab="cheats"]');
      await sleep(3000);
      await p.mouse.wheel(0, 250);
      await sleep(2200);
    }),
};

const want = process.argv.slice(2).map((s) => s.toUpperCase());
for (const k of Object.keys(clips)) {
  if (want.length && !want.includes(k)) continue;
  console.log("recording", k);
  await clips[k]();
}
