#!/usr/bin/env node
/**
 * record.mjs: drives the live Airlock reviewer console (v3) through the beats of section 2 of
 * docs/VIDEO-SCRIPT.md while Playwright records the browser context at 1920x1080, and writes
 * video/out/cues.json so the narration can be placed where the picture actually is.
 *
 * Runs vary from 30 to 110 s, so nothing here is on a fixed clock: every beat waits on the DOM
 * and logs the wall time it landed at. Every wait is bounded and names the cue it gave up on.
 *
 *   node record.mjs                       # the real take against the live console
 *   node record.mjs --prep                # the recording day preparation, through the API
 *   node record.mjs --url http://127.0.0.1:3111 --mock --skip-asa
 *
 * Flags:
 *   --url <url>          console to drive (default: the hosted console)
 *   --mock               the url is a mock server: no telemetry age wait, fixed verdicts
 *   --skip-asa           skip the external ASA ruling page
 *   --prep               preparation only, no browser: one clean run, then one with rights muted
 *   --no-wait            do not wait for the rights telemetry to go stale before the take
 *   --min-mute-age <s>   how stale the rights telemetry must be before the take (default 990)
 *   --gap-min <m>        minutes between the two preparation runs (default 13)
 *   --out <dir>          output directory (default: video/out)
 *   --headed             show the browser
 *
 * The console v3 DOM this drives, so a future change to the console has one place to look:
 *   - the asset strip: one `button[aria-pressed]` per preset, matched on its visible name
 *   - the run: the `Run airlock` button in the top bar, disabled while a run is in flight
 *   - the checks: six `button[aria-controls="check-<name>"]` rows, each carrying a status line
 *     ("Waiting to run", "Checking: ...", "No issues found", "N issues found: ...") and a
 *     calibration line; the chevron expands the row and the rights row holds the mute switch
 *   - the verdict: `section[aria-label="Verdict"]`, its `p[aria-live="polite"]` summary reading
 *     "Checks complete: BLOCK, content, needs a human."
 *   - the segments: `[aria-label="What to read about this run"]` with Checks, Findings, Record;
 *     Findings carries the time chips that seek the clip, Record the "Open in Grafana" link
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONSOLE = "https://airlock-console-771466810465.us-central1.run.app";
const ASA_URL = "https://www.asa.org.uk/rulings/nutri-paw-ltd.html";
const GATES = ["rights", "claim", "brand", "provenance"];
const STEP_TIMEOUT_MS = 200_000;
const ASA_SCROLL_MS = 6_000;
const SEEK_HOLD_MS = 3_000;

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
  minMuteAge: Number(arg("--min-mute-age", "990")),
  gapMinutes: Number(arg("--gap-min", "13")),
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

/** A condition the poll below must not sit through, such as a run whose event stream died. */
class Fatal extends Error {}

/**
 * Poll a predicate every 250 ms. On a timeout it says which cue it was working towards, so a
 * failed take reads as "gave up on rights_done_2" and not as a stack trace. A Fatal thrown by
 * the predicate comes straight back out: waiting the full bound on it would only burn the one
 * telemetry window the take has.
 */
async function until(what, predicate, { timeoutMs = STEP_TIMEOUT_MS, cue: cueId = null } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    try {
      const value = await predicate();
      if (value) return value;
    } catch (error) {
      if (error instanceof Fatal) throw error;
      last = error;
    }
    await sleep(250);
  }
  const where = cueId ? `cue ${cueId}: ` : "";
  note(`TIMEOUT ${cueId ?? what} after ${Math.round(timeoutMs / 1000)} s`);
  throw new Error(
    `${where}timed out after ${Math.round(timeoutMs / 1000)} s waiting for: ${what}` +
      (last ? ` (last error: ${last.message})` : ""),
  );
}

/**
 * What the status line of a check row means. A row reads "Waiting to run" before its gate starts
 * and "Checking: ..." while it runs, so anything else is a landing.
 */
function statusFromLine(line) {
  if (!line) return null;
  if (/^Waiting to run/i.test(line)) return null;
  if (/^Checking\b/i.test(line)) return null;
  if (/^No issues found/i.test(line)) return "PASS";
  if (/^Check failed/i.test(line)) return "ERROR";
  if (/^\d+ issues? found/i.test(line)) return "BLOCK";
  return null;
}

/**
 * One DOM read per poll: the six check rows with their status and calibration lines, the verdict
 * summary, the mute switch when the rights row is expanded, which segment is on screen, and
 * whether the clip is actually playing on the stage.
 */
async function snapshot(page) {
  return page.evaluate((gates) => {
    const clean = (node) => (node?.textContent || "").replace(/\s+/g, " ").trim();
    const out = {
      rows: {},
      rightsMute: null,
      verdict: null,
      motive: null,
      needsHuman: false,
      word: null,
      summary: null,
      incident: null,
      busy: false,
      lost: false,
      ready: false,
      segment: null,
      stageNote: null,
      playing: false,
      clipTime: null,
    };

    for (const button of document.querySelectorAll('button[aria-controls^="check-"]')) {
      const name = (button.getAttribute("aria-controls") || "").slice("check-".length);
      const box = button.children[1];
      if (!box) continue;
      const parts = Array.from(box.children).map(clean);
      out.rows[name] = {
        line: parts[1] || "",
        calibration: parts[2] || null,
        muted: /\bmuted\b/.test(parts[0] || ""),
        open: button.getAttribute("aria-expanded") === "true",
      };
    }
    out.ready = gates.every((gate) => {
      const row = out.rows[gate];
      return Boolean(row && row.calibration && !/^reading Grafana/i.test(row.calibration));
    });

    // Only in the DOM while the rights row is expanded, which is where the switch lives.
    const sw = document.querySelector('#check-rights [role="switch"]');
    out.rightsMute = sw ? sw.getAttribute("aria-checked") === "true" : null;

    const incident = /Incident (\S+) opened/.exec(out.rows.escalation?.line || "");
    out.incident = incident ? incident[1] : null;

    const verdict = document.querySelector('section[aria-label="Verdict"]');
    if (verdict) {
      out.word = clean(verdict.querySelector("p"));
      out.summary = clean(verdict.querySelector('p[aria-live="polite"]'));
      // The console says this, and only this, when the event stream died mid-run.
      out.lost = /did not produce a verdict/.test(out.summary);
      const match = /^Checks complete: (PASS|BLOCK|ERROR)(?:, (.+?))?\.$/.exec(out.summary);
      if (match) {
        out.verdict = match[1];
        let rest = match[2] || null;
        if (rest && /, needs a human$/.test(rest)) {
          out.needsHuman = true;
          rest = rest.replace(/, needs a human$/, "");
        }
        out.motive = match[1] === "PASS" ? null : rest;
      }
    }

    const list = document.querySelector('[aria-label="What to read about this run"]');
    if (list) {
      const active = Array.from(list.querySelectorAll('[role="tab"]')).find(
        (tab) => tab.getAttribute("data-state") === "active",
      );
      out.segment = active ? clean(active).toLowerCase().replace(/[^a-z]/g, "") : null;
    }

    const stage = document.querySelector("#stage");
    if (stage) {
      const status = stage.querySelector('p[role="status"]');
      out.stageNote = status ? clean(status) : null;
      const video = stage.querySelector("video");
      if (video) {
        out.clipTime = Number(video.currentTime.toFixed(2));
        out.playing = !video.paused && !video.ended && video.readyState >= 2;
      }
    }

    const run = Array.from(document.querySelectorAll("button")).find((b) =>
      /^run airlock$|^running the airlock$/i.test((b.textContent || "").trim()),
    );
    out.busy = Boolean(run && (run.disabled || run.getAttribute("aria-busy") === "true"));
    return out;
  }, GATES);
}

/** Pick a preset by the name printed on its card in the asset strip. */
async function clickAsset(page, label) {
  const card = page.locator("button[aria-pressed]").filter({ hasText: label }).first();
  await card.click({ timeout: 20_000 });
  await until(`the ${label} card to read selected`, async () =>
    (await card.getAttribute("aria-pressed")) === "true", { timeoutMs: 20_000 });
}

async function clickRun(page) {
  await page.getByRole("button", { name: /^run airlock$/i }).click({ timeout: 20_000 });
  // The console resets the run state on the click, so the watchers below must not read the
  // previous run's rows. Wait for the reset to be on screen before watching anything.
  await until(
    "the console to reset for a new run",
    async () => {
      const s = await snapshot(page);
      return s.verdict === null && s.busy;
    },
    { timeoutMs: 30_000 },
  );
}

/** Switch the right column between Checks, Findings and Record. */
async function segment(page, name) {
  const list = page.locator('[aria-label="What to read about this run"]');
  await list
    .locator('[role="tab"]')
    .filter({ hasText: new RegExp(`^${name}`, "i") })
    .first()
    .click({ timeout: 20_000 });
  await until(
    `the ${name} segment to be on screen`,
    async () => (await snapshot(page)).segment === name.toLowerCase(),
    { timeoutMs: 20_000 },
  );
}

async function setRightsRowOpen(page, open) {
  const header = page.locator('button[aria-controls="check-rights"]').first();
  const state = (await header.getAttribute("aria-expanded")) === "true";
  if (state === open) return;
  await header.click({ timeout: 20_000 });
  await until(
    `the rights row to be ${open ? "expanded" : "collapsed"}`,
    async () => Boolean((await snapshot(page)).rows.rights?.open) === open,
    { timeoutMs: 20_000 },
  );
}

/**
 * The mute switch lives inside the expanded rights row, so the row is opened, the switch thrown
 * and the row closed again: the reviewer's own gesture, and the row's "muted" badge is what stays
 * on screen afterwards.
 */
async function setMute(page, on) {
  await segment(page, "Checks");
  await setRightsRowOpen(page, true);
  const sw = page.locator('#check-rights [role="switch"]').first();
  const state = (await sw.getAttribute("aria-checked")) === "true";
  let toggled = false;
  if (state !== on) {
    await sw.click({ timeout: 20_000 });
    await until(
      `the rights mute switch to read ${on}`,
      async () => (await snapshot(page)).rightsMute === on,
      { timeoutMs: 20_000 },
    );
    toggled = true;
  }
  await sleep(500);
  await setRightsRowOpen(page, false);
  return toggled;
}

/**
 * Watch the four check rows and log each gate the moment its status line stops saying "Checking".
 * `onGate` can hold the camera somewhere else for a few seconds; the rows are gone from the DOM
 * while another segment is on screen, which the poll simply reads as "nothing new".
 */
async function watchGates(page, suffix, onGate = null) {
  const landed = new Map();
  let playedOnce = false;
  await until(
    `the four gates to settle${suffix ? ` (${suffix})` : ""}`,
    async () => {
      const s = await snapshot(page);
      if (s.lost) throw new Fatal(`the event stream was lost during the run${suffix}`);
      if (s.playing) playedOnce = true;
      for (const gate of GATES) {
        if (landed.has(gate)) continue;
        const status = statusFromLine(s.rows[gate]?.line);
        if (!status) continue;
        landed.set(gate, status);
        cue(`${gate}_done${suffix}`, { status, detail: status });
        if (onGate) await onGate(gate, status);
      }
      return landed.size === GATES.length;
    },
    { cue: `gates${suffix}` },
  );
  if (!playedOnce) {
    const s = await snapshot(page);
    note(
      `the clip never reported playing during the run${suffix}` +
        (s.stageNote ? `: ${s.stageNote}` : ""),
    );
  }
  return Object.fromEntries(landed);
}

async function watchVerdict(page, suffix) {
  const settled = await until(
    `the verdict summary${suffix ? ` (${suffix})` : ""}`,
    async () => {
      const s = await snapshot(page);
      return s.verdict && !s.busy ? s : null;
    },
    { cue: `verdict${suffix}` },
  );
  return cue(`verdict${suffix}`, {
    status: settled.verdict,
    motive: settled.motive,
    needs_human: settled.needsHuman,
    incident: settled.incident,
    summary: settled.summary,
    detail: `${settled.verdict}${settled.motive ? ` (${settled.motive})` : ""}${
      settled.incident ? ` incident ${settled.incident}` : ""
    }`,
  });
}

/**
 * The claim beat: read the finding in the thread, click its time chip, watch the clip jump there.
 * The segment goes back to Checks afterwards, because the gates are still landing behind it.
 */
async function seekClaim(page) {
  const before = await snapshot(page);
  await segment(page, "Findings");
  const row = page
    .locator("li")
    .filter({ has: page.locator("span", { hasText: /^claim$/ }) })
    .filter({ has: page.locator("button") })
    .first();
  let detail = "no claim finding carried a time chip";
  if (await row.count()) {
    const chip = row.locator("button").first();
    const label = (await chip.innerText().catch(() => "")).replace(/\s+/g, " ").trim();
    await chip.click({ timeout: 20_000 });
    const after = await snapshot(page);
    detail = `clip seeked to ${label || "the claim"}${
      after.stageNote ? ` (stage note: ${after.stageNote})` : ""
    }`;
    if (after.stageNote) note(`seek_claim: the stage answered "${after.stageNote}"`);
  } else {
    note("seek_claim: no claim finding with a time chip, the thread is held instead");
  }
  cue("seek_claim", { detail, clip_time_before: before.clipTime });
  await sleep(SEEK_HOLD_MS);
  await segment(page, "Checks");
  // The assembler may only compress waiting, and the seek is not waiting, so it needs to know
  // when the beat is actually over rather than assuming a duration for it.
  cue("seek_done", { detail: "back on the Checks segment, the rights gate is still running" });
}

/** The Grafana link lives in the Record segment; the camera goes there and comes straight back. */
async function grafanaHref(page) {
  await segment(page, "Record");
  const link = page.locator("a").filter({ hasText: /^Open in Grafana$/ }).first();
  const href = await link.getAttribute("href", { timeout: 20_000 });
  await sleep(500);
  await segment(page, "Checks");
  return href;
}

/**
 * The console keeps the finished run in React state only, so navigating the recorded tab to
 * Grafana would throw the verdict away and the take could never come back to it. Grafana is
 * therefore visited on a second page of the same context, which Playwright records to its own
 * file; assemble.py lays that file over the console take.
 *
 * Playwright records that page from the moment it is created, so its first seconds are a blank
 * tab and then a dashboard drawing itself. None of that belongs in the video: the recorder logs
 * `<name>_ready` the moment the panels have drawn and writes the same instant into the overlay
 * entry as `ready_at`, and assemble.py starts the insert there. The console take, with the
 * verdict on it, keeps playing underneath until then.
 */
async function visitGrafana(context, url, waitForText, holdMs, cueId, readyCueId) {
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
      { timeoutMs: 90_000, cue: readyCueId },
    );
  } catch (error) {
    ok = false;
    note(`${readyCueId}: ${error.message}; holding on whatever Grafana rendered`);
  }
  // Two cues at the same instant, and they are not the same thing: the ready one is where the
  // insert starts on the picture, the named one is the anchor the script's voice line sits on.
  const readyAt = ok ? now() : null;
  cue(readyCueId, {
    url,
    detail: ok
      ? `panels drawn ${(now() - openedAt).toFixed(1)} s after the page opened, the insert starts here`
      : "the panels never drew, the insert falls back to skipping its black head",
  });
  cue(cueId, { url, detail: ok ? "panel visible" : "panel title not seen" });
  await sleep(holdMs);
  const video = page.video();
  await page.close();
  const file = `${cueId}.webm`;
  overlays.push({
    cue: cueId,
    file,
    page_opened_at: openedAt,
    ready_cue: readyCueId,
    ready_at: readyAt,
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
  const deadline = Date.now() + 40 * 60_000;
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
      log(`rights telemetry ${Math.round(age)} s old, waiting for ${minAge} s`);
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
  await until(
    "the console to render its six check rows",
    async () => Object.keys((await snapshot(page)).rows).length >= 6,
    { cue: "console_open" },
  );
  await until("the calibration lines read from Grafana", async () => (await snapshot(page)).ready, {
    cue: "console_open",
  });
  return page;
}

/**
 * The preparation, through the API and with no browser: one clean run with nothing muted, so
 * every gate has a fresh success, then a second one 13 minutes later with the rights telemetry
 * muted. The take then waits until the rights gate is past `--min-mute-age` and starts, which is
 * the only moment the console reads "17 min ago" on rights and healthy on the other three.
 */
async function apiRun(asset, mute) {
  const started = Date.now();
  const response = await fetch(`${OPTS.url}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mute.length ? { asset, mute } : { asset }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`/api/run answered ${response.status}`);
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let verdict = null;
  let motive = null;
  let failure = null;
  for await (const chunk of response.body) {
    buffer += decoder.decode(chunk, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("");
      if (!data) continue;
      let event;
      try {
        event = JSON.parse(data);
      } catch {
        continue;
      }
      if (event.message) failure = event.message;
      if (typeof event.text !== "string") continue;
      try {
        const payload = JSON.parse(event.text);
        if (payload.stage === "verdict" || (payload.status && payload.motive !== undefined)) {
          verdict = payload.status ?? verdict;
          motive = payload.motive ?? motive;
        }
      } catch {
        // Not every relayed event is a JSON payload; the ones that are not say nothing here.
      }
    }
  }
  const seconds = Number(((Date.now() - started) / 1000).toFixed(1));
  if (failure) throw new Error(`the run failed: ${failure}`);
  return { asset, mute, seconds, verdict, motive, at: new Date(started).toISOString() };
}

async function runPrep() {
  log(`preparation against ${OPTS.url}`);
  log("run 1 of 2: the clean clip, nothing muted, so every gate gets a fresh success");
  const first = await apiRun("clean", []);
  log(`run 1 done in ${first.seconds} s: ${first.verdict ?? "no verdict parsed"}`);

  const gapMs = OPTS.gapMinutes * 60_000;
  log(`waiting ${OPTS.gapMinutes} minutes before the muted run`);
  await sleep(gapMs);

  log("run 2 of 2: the clean clip with the rights telemetry muted");
  const second = await apiRun("clean", ["rights"]);
  log(`run 2 done in ${second.seconds} s: ${second.verdict ?? "no verdict parsed"}`);

  const payload = {
    at: new Date().toISOString(),
    console: OPTS.url,
    gap_minutes: OPTS.gapMinutes,
    min_mute_age_s: OPTS.minMuteAge,
    runs: [first, second],
  };
  fs.writeFileSync(path.join(OPTS.out, "prep.json"), `${JSON.stringify(payload, null, 2)}\n`);
  log(`preparation written to ${path.join(OPTS.out, "prep.json")}`);
  log(`now: node video/record.mjs (it waits until the rights gate is past ${OPTS.minMuteAge} s)`);
}

async function runTake() {
  await waitForStaleTelemetry(OPTS.minMuteAge);

  const browser = await chromium.launch({ headless: !OPTS.headed, args: ["--hide-scrollbars"] });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: RAW_DIR, size: { width: 1920, height: 1080 } },
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
    cue("stake", { detail: "console idle, the clip on the stage, six check rows" });
    await sleep(8_000);

    // 2. The reviewer's job today: a real ASA ruling, scrolled for 6 s.
    if (OPTS.skipAsa) {
      note("ASA page skipped (--skip-asa); the stake beat holds on the console instead");
      cue("asa", { detail: "skipped" });
      await sleep(ASA_SCROLL_MS);
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
        // beat is short and the assembler never cuts here, so the picture lasts exactly as long
        // as the beat is worth. Small steps, so the page glides instead of jumping.
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
      await until("the console to come back up", async () => (await snapshot(page)).ready, {
        cue: "console_idle",
      });
    }

    // 3. The console idle, with the rights telemetry muted for the whole take. The mute is on
    //    from here so the Crest run does not refresh the control the script wants dark.
    const toggled = await setMute(page, true);
    cue("mute_on", { detail: toggled ? "switched on by the recorder" : "already on" });
    await clickAsset(page, "Crest Toothpaste Commercial");
    cue("console_idle", { detail: "the Crest clip on the stage, the rights row amber" });
    await sleep(9_000);

    // 4. The Crest commercial: four blocks on the asset itself, and the claim beat seeks the clip.
    await clickRun(page);
    cue("crest_click", { detail: "Run airlock on the Crest commercial" });
    await watchGates(page, "", async (gate) => {
      if (gate === "claim") await seekClaim(page);
    });
    const verdict1 = await watchVerdict(page, "");
    if (!OPTS.mock && (verdict1.status !== "BLOCK" || verdict1.motive !== "content")) {
      note(`verdict expected BLOCK (content), got ${verdict1.status} (${verdict1.motive})`);
    }
    await sleep(2_500);

    // 5. Grafana, on a second page so the console keeps the verdict on screen.
    const href = await grafanaHref(page);
    log(`open in Grafana: ${href}`);
    grafanaVideos.push(
      await visitGrafana(context, href, "Verdicts (7d)", 5_000, "grafana_open", "grafana_ready"),
    );
    await sleep(1_000);

    // 6. The clean clip with the rights control still dark.
    await clickAsset(page, "Nimbus clean clip");
    await sleep(700);
    await clickRun(page);
    cue("clean_muted_click", { detail: "Run airlock on the clean clip, rights telemetry muted" });
    await watchGates(page, "_2");
    const verdict2 = await watchVerdict(page, "_2");
    if (!OPTS.mock && (verdict2.status !== "BLOCK" || verdict2.motive !== "control unavailable")) {
      note(`verdict_2 expected BLOCK (control unavailable), got ${verdict2.status} (${verdict2.motive})`);
    }
    await sleep(3_500);

    // 7. The control back on, the same clip again.
    const off = await setMute(page, false);
    cue("unmute", { detail: off ? "rights mute telemetry switched off" : "already off" });
    await sleep(1_000);
    await clickRun(page);
    cue("clean_click_2", { detail: "Run airlock on the clean clip again" });
    await watchGates(page, "_3");
    const verdict3 = await watchVerdict(page, "_3");
    if (!OPTS.mock && verdict3.status !== "PASS") {
      note(`verdict_3 expected PASS, got ${verdict3.status} (${verdict3.motive})`);
    }
    await sleep(2_500);

    // 8. The public dashboard, then the PASS verdict held.
    const dashboard = new URL(href);
    dashboard.searchParams.set("from", "now-1h");
    dashboard.searchParams.set("to", "now");
    grafanaVideos.push(
      await visitGrafana(context, dashboard.toString(), "Verdicts (7d)", 9_000, "dashboard",
        "dashboard_ready"),
    );
    const landed = await snapshot(page);
    if (landed.verdict !== "PASS") {
      note(`landing: the console no longer shows the PASS verdict (verdict=${landed.verdict})`);
    }
    cue("landing", { detail: `holding on the ${landed.verdict ?? "idle"} verdict` });
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
