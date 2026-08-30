#!/usr/bin/env node
/**
 * measure_layout.mjs: where the console puts the three things a punch-in is centred on.
 *
 * The punch-ins in video/assemble.py move the frame towards the element that just changed, so the
 * centre of each one is a measurement and not a guess: this opens the live console at the take's
 * own viewport (1920x1080), reads the bounding box of the verdict card, of the checks list and of
 * the stage, and writes video/out/layout.json. assemble.py carries the same numbers in PUNCH_AT
 * and prints the file when it disagrees with them.
 *
 *   node video/measure_layout.mjs
 *   node video/measure_layout.mjs --url http://127.0.0.1:3111 --out video/out
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONSOLE = "https://airlock-console-771466810465.us-central1.run.app";

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i === -1 ? fallback : process.argv[i + 1];
}

const URL_ = (arg("--url", DEFAULT_CONSOLE) || DEFAULT_CONSOLE).replace(/\/$/, "");
const OUT = path.resolve(arg("--out", path.join(HERE, "out")));

const browser = await chromium.launch({ headless: true, args: ["--hide-scrollbars"] });
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
await page.goto(URL_, { waitUntil: "domcontentloaded", timeout: 90_000 });
await page.waitForSelector('button[aria-controls^="check-"]', { timeout: 60_000 });
await page.waitForTimeout(2_000);

const boxes = await page.evaluate(() => {
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x),
      y: Math.round(r.y),
      w: Math.round(r.width),
      h: Math.round(r.height),
      cx: Math.round(r.x + r.width / 2),
      cy: Math.round(r.y + r.height / 2),
    };
  };
  const rows = Array.from(document.querySelectorAll('button[aria-controls^="check-"]'));
  const first = rows[0]?.getBoundingClientRect();
  const last = rows[rows.length - 1]?.getBoundingClientRect();
  const checks =
    first && last
      ? {
          x: Math.round(first.x),
          y: Math.round(first.y),
          w: Math.round(first.width),
          h: Math.round(last.bottom - first.y),
          cx: Math.round(first.x + first.width / 2),
          cy: Math.round((first.y + last.bottom) / 2),
        }
      : null;
  return {
    verdict: box(document.querySelector('section[aria-label="Verdict"]')),
    checks,
    check_rows: rows.length,
    stage: box(document.querySelector("#stage")),
    viewport: { w: window.innerWidth, h: window.innerHeight },
  };
});

fs.mkdirSync(OUT, { recursive: true });
const payload = { measured_at: new Date().toISOString(), console: URL_, ...boxes };
fs.writeFileSync(path.join(OUT, "layout.json"), `${JSON.stringify(payload, null, 2)}\n`);
console.log(JSON.stringify(payload, null, 2));

await context.close();
await browser.close();
