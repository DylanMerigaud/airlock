#!/usr/bin/env node
/**
 * record.mjs: drives the live Airlock reviewer console through the beats of section 2 of
 * docs/VIDEO-SCRIPT.md while Playwright records the browser context at 1920x1080, and writes
 * video/out/cues.json so the narration can be placed where the picture actually is.
 *
 * Runs vary from 30 to 110 s, so nothing here is on a fixed clock: every beat waits on the DOM
 * and logs the wall time it landed at.
 *
 *   node record.mjs                       # the real take against the live console
 *   node record.mjs --prep                # the recording day preparation (mute rights, one run)
 *   node record.mjs --url http://localhost:3000 --mock --skip-asa
 *
 * Flags:
 *   --url <url>          console to drive (default: the hosted console)
 *   --mock               the url is a mock server: no telemetry age wait
 *   --skip-asa           skip the external ASA ruling page
 *   --prep               preparation only, no video: mute rights and run the clean clip once
 *   --no-wait            do not wait for the rights telemetry to go stale before the take
 *   --min-mute-age <s>   how stale the rights telemetry must be before the take (default 960)
 *   --out <dir>          output directory (default: video/out)
 *   --headed             show the browser
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONSOLE = "https://airlock-console-771466810465.us-central1.run.app";
const ASA_URL = "https://www.asa.org.uk/rulings/nutri-paw-ltd.html";
const GATES = ["rights", "claim", "brand", "provenance"];
const TERMINAL = ["PASS", "BLOCK", "ERROR"];
const STEP_TIMEOUT_MS = 200_000;
const ASA_SCROLL_MS = 8_000;

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i === -1 ? fallback : process.argv[i + 1];
}
const has = (name) => process.argv.includes(name);

const OPTS = {
  url: (arg("--url", DEFAULT_CONSOLE) || DEFAULT_CONSOLE).replace(/\/$/, ""),
  mock: has("--mock"),
  skipAsa: has("--skip-asa"),
  prep: has("--prep"),
  wait: !has("--no-wait"),
  minMuteAge: Number(arg("--min-mute-age", "960")),
  out: path.resolve(arg("--out", path.join(HERE, "out"))),
  headed: has("--headed"),
};

const RAW_DIR = path.join(OPTS.out, "raw");
fs.mkdirSync(RAW_DIR, { recursive: true });

let t0 = Date.now();
const cues = [];
const notes = [];
const overlays = [];

const now = () => Number(((Date.now() - t0) / 1000).toFixed(3));
function log(msg) {
  const stamp = OPTS.prep ? new Date().toISOString().slice(11, 19) : `t+${now().toFixed(1).padStart(6)}s`;
  console.log(`[${stamp}] ${msg}`);
}
function cue(id, extra = {}) {
  const entry = { cue: id, t: now(), ...extra };
  cues.push(entry);
  log(`CUE ${id}${extra.detail ? `  ${extra.detail}` : ""}`);
  return entry;
}
function note(text) {
  notes.push({ t: now(), text });
  log(`NOTE ${text}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll a predicate every 250 ms, and say which beat gave up instead of hanging. */
async function until(what, predicate, timeoutMs = STEP_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    try {
      const value = await predicate();
      if (value) return value;
    } catch (error) {
      last = error;
    }
    await sleep(250);
  }
  throw new Error(
    `timed out after ${Math.round(timeoutMs / 1000)} s waiting for: ${what}` +
      (last ? ` (last error: ${last.message})` : ""),
  );
}

/**
 * One DOM read per poll: the four gate chips, the mute switches, the verdict headline and its
 * motive. The console renders the gate name lowercase in the markup and uppercases it in CSS, so
 * every match here is case insensitive; [data-gate] attributes do not exist.
 */
async function snapshot(page) {
  return page.evaluate(() => {
    const STATUSES = ["PENDING", "RUNNING", "PASS", "BLOCK", "ERROR"];
    const out = { gates: {}, mutes: {}, verdict: null, motive: null, busy: false, ready: false };
    const pipeline = document.querySelector("#pipeline");
    if (pipeline) {
      for (const card of pipeline.querySelectorAll("article")) {
        const heading = card.querySelector("h3");
        if (!heading) continue;
        const name = (heading.textContent || "").trim().toLowerCase();
        let status = null;
        for (const span of card.querySelectorAll("span")) {
          const text = (span.textContent || "").trim();
          if (STATUSES.includes(text)) {
            status = text;
            break;
          }
        }
        out.gates[name] = status;
        const sw = card.querySelector('[role="switch"]');
        if (sw) out.mutes[name] = sw.getAttribute("aria-checked") === "true";
        if (/injected defect/i.test(card.textContent || "")) out.ready = true;
      }
    }
    const decision = document.querySelector('section[aria-label="Verdict"]');
    if (decision) {
      const head = Array.from(decision.querySelectorAll("p")).find((p) =>
        ["PASS", "BLOCK", "ERROR"].includes((p.textContent || "").trim()),
      );
      out.verdict = head ? (head.textContent || "").trim() : null;
      const badge = Array.from(decision.querySelectorAll("span")).find((s) =>
        /^(content|control unavailable|uncalibrated control|instrument error)$/.test(
          (s.textContent || "").trim(),
        ),
      );
      out.motive = badge ? (badge.textContent || "").trim() : null;
      out.decisionText = (decision.textContent || "").replace(/\s+/g, " ").trim().slice(0, 400);
    }
    const run = Array.from(document.querySelectorAll("button")).find((b) =>
      /run airlock/i.test((b.textContent || "").trim()),
    );
    out.busy = Boolean(run && (run.disabled || run.getAttribute("aria-busy") === "true"));
    return out;
  });
}

async function clickAsset(page, label) {
  const chip = page.locator("button[aria-pressed]").filter({ hasText: label }).first();
  await chip.click({ timeout: 20_000 });
}

async function clickRun(page) {
  await page.getByRole("button", { name: /run airlock/i }).click({ timeout: 20_000 });
  // The console resets the run state on the click, so the watchers below must not read the
  // previous run's chips. Wait for the reset to be on screen before watching anything.
  await until("the console to reset for a new run", async () => {
    const s = await snapshot(page);
    return s.verdict === null && s.busy;
  }, 30_000);
}

async function setMute(page, gate, on) {
  const card = page
    .locator("#pipeline article")
    .filter({ has: page.locator("h3", { hasText: new RegExp(`^${gate}$`, "i") }) })
    .first();
  const sw = card.locator('[role="switch"]').first();
  const state = (await sw.getAttribute("aria-checked")) === "true";
  if (state === on) return false;
  await sw.click({ timeout: 20_000 });
  await until(`the ${gate} mute switch to read ${on}`, async () => {
    const s = await snapshot(page);
    return s.mutes[gate] === on;
  }, 20_000);
  return true;
}

/** Watch the four gate chips and log each terminal status the moment it lands. */
async function watchGates(page, suffix) {
  const landed = new Map();
  await until(`the four gates to settle${suffix}`, async () => {
    const s = await snapshot(page);
    for (const gate of GATES) {
      const status = s.gates[gate];
      if (!landed.has(gate) && TERMINAL.includes(status)) {
        landed.set(gate, status);
        cue(`${gate}_done${suffix}`, { status, detail: status });
      }
    }
    return landed.size === GATES.length;
  });
  return Object.fromEntries(landed);
}

async function watchVerdict(page, suffix) {
  const settled = await until(`the verdict card${suffix}`, async () => {
    const s = await snapshot(page);
    return s.verdict && !s.busy ? s : null;
  });
  return cue(`verdict${suffix}`, {
    status: settled.verdict,
    motive: settled.motive,
    detail: `${settled.verdict}${settled.motive ? ` (${settled.motive})` : ""}`,
  });
}

async function grafanaHref(page) {
  const link = page
    .locator('section[aria-label="Verdict"] a')
    .filter({ hasText: /open in grafana/i })
    .first();
  return link.getAttribute("href", { timeout: 20_000 });
}

/**
 * The console keeps the finished run in React state only, so navigating the recorded tab to
 * Grafana would throw the verdict card away and the take could never come back to it. Grafana is
 * therefore visited on a second page of the same context, which Playwright records to its own
 * file; assemble.py lays that file over the console take for the window it was open.
 */
async function visitGrafana(context, url, waitForText, holdMs, cueId) {
  const openedAt = now();
  const page = await context.newPage();
  let ok = true;
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90_000 });
    // The panel titles render about 1.5 s before the queries come back, so waiting on the title
    // alone puts an empty dashboard on camera. Measured on this stack: the eight panels draw 21
    // canvases once their data lands, and none before.
    await until(
      `the Grafana panel "${waitForText}" and its data`,
      async () =>
        page.evaluate(
          (title) =>
            (document.body.innerText || "").includes(title) &&
            document.querySelectorAll("canvas").length >= 8,
          waitForText,
        ),
      90_000,
    );
  } catch (error) {
    ok = false;
    note(`${cueId}: ${error.message}; holding on whatever Grafana rendered`);
  }
  cue(cueId, { url, detail: ok ? "panel visible" : "panel title not seen" });
  await sleep(holdMs);
  const video = page.video();
  await page.close();
  const file = `${cueId}.webm`;
  overlays.push({
    cue: cueId,
    file,
    page_opened_at: openedAt,
    closed_at: now(),
    panel_seen: ok,
  });
  return { video, file };
}

async function waitForStaleTelemetry(minAge) {
  if (!OPTS.wait || OPTS.mock) {
    log(`skipping the telemetry age wait (${OPTS.mock ? "mock" : "--no-wait"})`);
    return null;
  }
  const deadline = Date.now() + 30 * 60_000;
  let age = null;
  while (Date.now() < deadline) {
    try {
      const health = await fetch(`${OPTS.url}/api/health`, { cache: "no-store" }).then((r) => r.json());
      const rights = (health.gates || []).find((g) => g.gate === "rights");
      age = rights ? rights.seconds_since_success : null;
      if (age === null || age >= minAge) {
        log(`rights telemetry is ${age === null ? "not visible at all" : `${Math.round(age)} s`} old, the take can start`);
        return age;
      }
      log(`rights telemetry ${Math.round(age)} s old, waiting for ${minAge} s (${Math.round((minAge - age) / 60)} min left)`);
    } catch (error) {
      log(`health read failed: ${error.message}`);
    }
    await sleep(20_000);
  }
  throw new Error(`the rights telemetry never got older than ${minAge} s`);
}

async function openConsole(context) {
  const page = await context.newPage();
  await page.goto(OPTS.url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await until("the console to render its gate cards", async () => {
    const s = await snapshot(page);
    return Object.keys(s.gates).length >= 4;
  });
  await until("the calibration lines read from Grafana", async () => (await snapshot(page)).ready);
  return page;
}

async function runPrep() {
  log("preparation: mute the rights telemetry and run the clean clip once");
  const browser = await chromium.launch({ headless: !OPTS.headed });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  try {
    const page = await openConsole(context);
    const toggled = await setMute(page, "rights", true);
    log(`rights mute telemetry: ${toggled ? "switched on" : "already on"}`);
    await clickAsset(page, "Nimbus clean clip");
    await clickRun(page);
    const started = Date.now();
    await watchGates(page, "_prep");
    const verdict = await watchVerdict(page, "_prep");
    const payload = {
      at: new Date().toISOString(),
      console: OPTS.url,
      muted: ["rights"],
      asset: "Nimbus clean clip",
      run_seconds: Number(((Date.now() - started) / 1000).toFixed(1)),
      verdict: verdict.status,
      motive: verdict.motive,
    };
    fs.writeFileSync(path.join(OPTS.out, "prep.json"), `${JSON.stringify(payload, null, 2)}\n`);
    log(`preparation done in ${payload.run_seconds} s: ${payload.verdict} (${payload.motive})`);
    log(`wait at least 16 minutes from now, then: node record.mjs`);
  } finally {
    await context.close();
    await browser.close();
  }
}

async function runTake() {
  await waitForStaleTelemetry(OPTS.minMuteAge);

  const browser = await chromium.launch({ headless: !OPTS.headed, args: ["--hide-scrollbars"] });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: RAW_DIR, size: { width: 1920, height: 1080 } },
    colorScheme: "dark",
    deviceScaleFactor: 1,
  });

  let consoleVideo = null;
  const grafanaVideos = [];
  let failure = null;

  try {
    t0 = Date.now();
    const page = await openConsole(context);
    consoleVideo = page.video();
    cue("record_start", { t: 0, detail: "the context video starts here" });

    // 1. The stake. The Article 50 overlay is laid over these seconds in assemble.py.
    cue("stake", { detail: "console idle, gate cards up" });
    await sleep(8_000);

    // 2. The reviewer's job today: a real ASA ruling, scrolled.
    if (OPTS.skipAsa) {
      note("ASA page skipped (--skip-asa); the stake beat holds on the console instead");
      cue("asa", { detail: "skipped" });
      await sleep(8_000);
    } else {
      try {
      await page.goto(ASA_URL, { waitUntil: "domcontentloaded", timeout: 90_000 });
      for (const label of [/accept all/i, /accept/i, /agree/i]) {
        const button = page.getByRole("button", { name: label }).first();
        if (await button.count().catch(() => 0)) {
          await button.click({ timeout: 3_000 }).catch(() => {});
          break;
        }
      }
      await page
        .getByText(/assessment/i)
        .first()
        .scrollIntoViewIfNeeded({ timeout: 10_000 })
        .catch(() => note("ASA: no Assessment heading found, scrolling from the top"));
      cue("asa", { url: ASA_URL, detail: "scrolling the assessment" });
      // The scroll is bounded by the wall clock, not by a step count: the voice line for this
      // beat is short, and the assembler never cuts here, so the picture has to last exactly as
      // long as the beat is worth. Small steps, so the page glides instead of jumping.
      const scrollUntil = Date.now() + ASA_SCROLL_MS;
      while (Date.now() < scrollUntil) {
        await page.evaluate(() => window.scrollBy(0, 16));
        await sleep(90);
      }
      } catch (error) {
        note(`ASA beat failed: ${error.message}`);
        cue("asa", { detail: "failed" });
      }
      await page.goto(OPTS.url, { waitUntil: "domcontentloaded", timeout: 90_000 });
      await until("the console to come back up", async () => (await snapshot(page)).ready);
    }

    // 3. The console idle, with the rights telemetry muted for the whole take. The mute is on
    //    from here so the crest run does not refresh the control the script wants dark.
    const toggled = await setMute(page, "rights", true);
    cue("mute_on", { detail: toggled ? "switched on by the recorder" : "already on" });
    cue("console_idle", { detail: "gate cards with their calibration lines" });
    await sleep(9_000);

    // 4. The Crest commercial: four blocks on the asset itself.
    await clickAsset(page, "Crest Toothpaste Commercial");
    await sleep(700);
    await clickRun(page);
    cue("crest_click", { detail: "RUN AIRLOCK on the Crest commercial" });
    await watchGates(page, "");
    const verdict1 = await watchVerdict(page, "");
    if (verdict1.status !== "BLOCK" || verdict1.motive !== "content") {
      note(`verdict expected BLOCK (content), got ${verdict1.status} (${verdict1.motive})`);
    }
    await sleep(4_000);

    // 5. Grafana, on a second page so the console keeps the verdict card.
    const href = await grafanaHref(page);
    log(`open in Grafana: ${href}`);
    grafanaVideos.push(await visitGrafana(context, href, "Verdicts (7d)", 6_000, "grafana_open"));
    await sleep(1_500);

    // 6. The clean clip with the rights control still dark.
    await clickAsset(page, "Nimbus clean clip");
    await sleep(700);
    await clickRun(page);
    cue("clean_muted_click", { detail: "RUN AIRLOCK on the clean clip, rights telemetry muted" });
    await watchGates(page, "_2");
    const verdict2 = await watchVerdict(page, "_2");
    if (verdict2.status !== "BLOCK" || verdict2.motive !== "control unavailable") {
      note(`verdict_2 expected BLOCK (control unavailable), got ${verdict2.status} (${verdict2.motive})`);
    }
    await sleep(5_000);

    // 7. The control back on, the same clip again.
    await setMute(page, "rights", false);
    cue("unmute", { detail: "rights MUTE TELEMETRY switched off" });
    await sleep(2_000);
    await clickRun(page);
    cue("clean_click_2", { detail: "RUN AIRLOCK on the clean clip again" });
    await watchGates(page, "_3");
    const verdict3 = await watchVerdict(page, "_3");
    if (verdict3.status !== "PASS") {
      note(`verdict_3 expected PASS, got ${verdict3.status} (${verdict3.motive})`);
    }
    await sleep(4_000);

    // 8. The public dashboard, then the PASS card held.
    const dashboard = new URL(href);
    dashboard.searchParams.set("from", "now-1h");
    dashboard.searchParams.set("to", "now");
    grafanaVideos.push(
      await visitGrafana(context, dashboard.toString(), "Verdicts (7d)", 10_000, "dashboard"),
    );
    const landed = await snapshot(page);
    if (landed.verdict !== "PASS") {
      note(`landing: the console no longer shows the PASS card (verdict=${landed.verdict})`);
    }
    cue("landing", { detail: `holding on the ${landed.verdict ?? "idle"} verdict card` });
    await sleep(12_000);
    cue("end", { detail: "take finished" });
  } catch (error) {
    failure = error;
    note(`TAKE FAILED: ${error.message}`);
    console.error(error);
  } finally {
    // The videos are finalised by context.close(); video.saveAs() only works while the browser
    // is still alive, so the browser is closed after the files have been written.
    await context.close();
  }

  const files = {};
  if (consoleVideo) {
    const dest = path.join(RAW_DIR, "console.webm");
    await consoleVideo.saveAs(dest);
    files.console = dest;
  }
  for (const { video, file } of grafanaVideos) {
    const dest = path.join(RAW_DIR, file);
    await video.saveAs(dest);
    files[file] = dest;
  }
  await browser.close();

  const payload = {
    recorded_at: new Date(t0).toISOString(),
    console: OPTS.url,
    mock: OPTS.mock,
    duration_s: now(),
    video: path.relative(OPTS.out, files.console ?? ""),
    overlays,
    notes,
    cues,
    failed: failure ? failure.message : null,
  };
  const cuesPath = path.join(OPTS.out, "cues.json");
  fs.writeFileSync(cuesPath, `${JSON.stringify(payload, null, 2)}\n`);

  console.log("");
  console.log(`cues:  ${cuesPath}`);
  for (const [name, file] of Object.entries(files)) console.log(`video: ${name} -> ${file}`);
  console.log(`take:  ${payload.duration_s.toFixed(1)} s, ${cues.length} cues, ${notes.length} note(s)`);
  if (failure) process.exitCode = 1;
}

await (OPTS.prep ? runPrep() : runTake());
