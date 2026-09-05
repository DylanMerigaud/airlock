#!/usr/bin/env node
/**
 * record.mjs: drives the live Airlock reviewer console through the beats of docs/VIDEO-SCRIPT.md
 * (script v6) while Playwright records the browser context at 1920x1080, and writes
 * video/out/cues.json so the narration can be placed where the picture actually is.
 *
 * Runs vary from 30 to 110 s, so nothing here is on a fixed clock: every beat waits on the DOM
 * and logs the wall time it landed at. Every wait is bounded and names the cue it gave up on.
 *
 *   node record.mjs                       # the real take against the live console
 *   node record.mjs --url http://127.0.0.1:3111 --mock
 *
 * Flags:
 *   --url <url>          console to drive (default: the hosted console)
 *   --mock               the url is a mock server: fixed verdicts, no expectation notes
 *   --dashboard <url>    the Grafana page for the two inserts (default: the "Open in Grafana" href
 *                        read off the Record segment during the first run)
 *   --out <dir>          output directory (default: video/out)
 *   --headed             show the browser
 *
 * Script v6 needs no preparation: the control beat is a fault injected on camera (the "Inject a
 * fault" switch on the rights row), which fails the gate in a millisecond, so there is no muted run
 * before the take and no staleness to wait for. Three runs: the Crest commercial (BLOCK on its
 * content), the clean clip with the fault (BLOCK, control unavailable, the investigator names the
 * cause, a human resolves the incident from the console), the test clip with its study on file
 * (PASS).
 *
 * The console DOM this drives, so a future change to the console has one place to look:
 *   - the asset strip: one `button[aria-pressed]` per preset, matched on its visible name
 *   - the run: the `Run airlock` button in the top bar, disabled while a run is in flight
 *   - the checks: seven `button[aria-controls="check-<name>"]` rows (the four gates, verdict,
 *     investigation, escalation), each carrying a status line ("Waiting to run", "Checking: ...",
 *     "No issues found", "N issues found: ...", "Check failed: ...") and a calibration line; the
 *     chevron expands the row and the rights row holds the "Mute telemetry" and "Inject a fault"
 *     switches (`button[role="switch"]`, named by their text)
 *   - the verdict: `section[aria-label="Verdict"]`, its `p[aria-live="polite"]` summary reading
 *     "Checks complete: BLOCK, content, needs a human."
 *   - the segments: `[aria-label="What to read about this run"]` with Checks, Findings, Record;
 *     Findings carries the time chips that seek the clip, Record the "Open in Grafana" link, the
 *     annotation and incident ids, the Investigation section and the "Mark reviewed by a human"
 *     button under a "Signing as" select
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONSOLE = "https://airlock-console-771466810465.us-central1.run.app";
// The alert list (https://narrowsubmarine1895.grafana.net/alerting/list) redirects a fresh browser
// to /login, so the alert insert shows the public dashboard instead, on its "Gate errors" panel:
// the series the "Airlock gate errors" rule fires on.
const PUBLIC_DASHBOARD =
  "https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845";
const GATES = ["rights", "claim", "brand", "provenance"];
const STEP_TIMEOUT_MS = 200_000;
const SEEK_HOLD_MS = 3_000;
// The stake: the Article 50 overlay assemble.py burns over the open lasts 5 s, and the console
// is alone on the picture for the rest of this hold before the reviewer's first gesture.
const STAKE_HOLD_MS = 5_500;
// A beat is held for as long as the line spoken over it, which is measured and not assumed:
// video/out/narration.json from the previous narration carries every wav's duration. The
// fallbacks are for a first run, before any narration exists.
const LINE_MARGIN_MS = 1_000;
const HOLD_MAX_MS = 20_000;
const ALERT_INSERT_MS = 4_000;
// The dashboard insert lasts the dashboard line (10.8 s at 1.1x) and the landing the landing line
// plus the render's tail; the assembler trims either only when the render is over its maximum.
const DASHBOARD_INSERT_MS = 11_000;
const LANDING_HOLD_MS = 7_000;
const RECORD_HOLD_MIN_MS = 3_000;
// The resolved incident is held on camera for this long before the reviewer's next gesture (the
// fault switched off) plays under the rest of the resolve line.
const RESOLVED_HOLD_MS = 4_500;
// How long the run may keep working after the verdict (the investigator, then the escalation)
// before the recorder moves on without the incident id.
const SETTLE_TIMEOUT_MS = 120_000;
// An insert holds still while the line names what is on it, then glides down the panels for the
// rest of its window, so no insert is ever a still picture with nothing being said over it.
const DASHBOARD_STILL_MS = 2_000;
const DASHBOARD_GLIDE_STEP_MS = 60;
const REVIEWER_ROLE = "platform on-call";

/**
 * Every cue this recorder can write. narrate.py reads this list and refuses to synthesise a
 * script that names a cue which is not in it, so a renamed beat fails before a render and not
 * after one. A `<gate>_done<suffix>` entry is written by watchGates for each of the four gates.
 */
const CUE_NAMES = [
  "record_start",
  "stake",
  "console_idle",
  "crest_click",
  "rights_done", "claim_done", "brand_done", "provenance_done",
  "seek_claim",
  "seek_done",
  "verdict",
  "escalation_done",
  "record_open",
  "fault_on",
  "fault_click",
  "rights_error",
  "rights_done_2", "claim_done_2", "brand_done_2", "provenance_done_2",
  "gates_done_2",
  "verdict_2",
  "investigation",
  "escalation_done_2",
  "investigation_note",
  "alert_ready",
  "alert_insert",
  "resolve",
  "resolved",
  "fault_off",
  "study_click",
  "rights_done_3", "claim_done_3", "brand_done_3", "provenance_done_3",
  "verdict_3",
  "escalation_done_3",
  "dashboard_ready",
  "dashboard",
  "landing",
  "end",
];

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i === -1 ? fallback : process.argv[i + 1];
}
const has = (name) => process.argv.includes(name);

const OPTS = {
  url: (arg("--url", DEFAULT_CONSOLE) || DEFAULT_CONSOLE).replace(/\/$/, ""),
  mock: has("--mock"),
  dashboard: arg("--dashboard", null),
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
  console.log(`[t+${now().toFixed(1).padStart(6)}s] ${msg}`);
}
function cue(id, extra = {}) {
  if (!CUE_NAMES.includes(id)) throw new Error(`cue ${id} is not in CUE_NAMES; add it there first`);
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
/** Sleep until the recorder's clock reads `t` seconds, or not at all when it already does. */
async function holdUntil(t) {
  const ms = Math.round((t - now()) * 1000);
  if (ms > 0) await sleep(ms);
}

/** A condition the poll below must not sit through, such as a run whose event stream died. */
class Fatal extends Error {}

/**
 * Poll a predicate every 250 ms. On a timeout it says which cue it was working towards, so a
 * failed take reads as "gave up on rights_done_2" and not as a stack trace. A Fatal thrown by
 * the predicate comes straight back out.
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

/** The escalation row's line, once it has landed: which incident, opened or joined. */
function escalationFromLine(line) {
  if (!line) return null;
  let m = /^Incident ([^\s:,]+) opened/.exec(line);
  if (m) return { incident: m[1], attached: false };
  m = /^Joined open incident ([^\s:,]+)/.exec(line);
  if (m) return { incident: m[1], attached: true };
  if (/^no human needed/i.test(line)) return { incident: null, attached: false };
  return null;
}

/**
 * One DOM read per poll: the seven check rows with their status and calibration lines, the
 * verdict summary, the two switches when the rights row is expanded, which segment is on screen,
 * and whether the clip is actually playing on the stage.
 */
async function snapshot(page) {
  return page.evaluate((gates) => {
    const clean = (node) => (node?.textContent || "").replace(/\s+/g, " ").trim();
    const out = {
      rows: {},
      rightsMute: null,
      rightsFault: null,
      verdict: null,
      motive: null,
      needsHuman: false,
      word: null,
      summary: null,
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
        head: parts[0] || "",
        line: parts[1] || "",
        calibration: parts[2] || null,
        muted: /\bmuted\b/.test(parts[0] || ""),
        fault: /fault injected/.test(parts[0] || ""),
        open: button.getAttribute("aria-expanded") === "true",
      };
    }
    out.ready = gates.every((gate) => {
      const row = out.rows[gate];
      return Boolean(row && row.calibration && !/^reading Grafana/i.test(row.calibration));
    });

    // Only in the DOM while the rights row is expanded, which is where the switches live.
    for (const sw of document.querySelectorAll('#check-rights [role="switch"]')) {
      const label = clean(sw);
      const on = sw.getAttribute("aria-checked") === "true";
      if (/mute telemetry/i.test(label)) out.rightsMute = on;
      if (/inject a fault/i.test(label)) out.rightsFault = on;
    }

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

/**
 * What the Record segment shows, read only while it is on screen: the annotation and incident
 * ids, the cost line, the Investigation section and the review state.
 */
async function recordSnapshot(page) {
  return page.evaluate(() => {
    const clean = (node) => (node?.textContent || "").replace(/\s+/g, " ").trim();
    const paragraphs = Array.from(document.querySelectorAll("p, span, h3"));
    const find = (re) => {
      const node = paragraphs.find((p) => re.test(clean(p)));
      return node ? clean(node) : null;
    };
    const link = Array.from(document.querySelectorAll("a")).find((a) => /^Open in Grafana$/.test(clean(a)));
    const investigationHeader = paragraphs.find((p) => /^Investigation$/.test(clean(p)));
    const section = investigationHeader ? investigationHeader.closest("section") : null;
    const sectionText = section ? (section.innerText || section.textContent || "").replace(/\s+/g, " ").trim() : null;
    return {
      ids: find(/^(annotation \S+|no annotation id)(, incident \S+)?$/),
      cost: find(/^This check:/),
      href: link ? link.getAttribute("href") : null,
      investigation: sectionText,
      reviewed: find(/^Reviewed by a human/),
      reviewLine: find(/^(incident \S+ \S+|no incident to close)/),
    };
  });
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

async function setRowOpen(page, row, open) {
  const header = page.locator(`button[aria-controls="check-${row}"]`).first();
  const state = (await header.getAttribute("aria-expanded")) === "true";
  if (state === open) return;
  await header.click({ timeout: 20_000 });
  await until(
    `the ${row} row to be ${open ? "expanded" : "collapsed"}`,
    async () => Boolean((await snapshot(page)).rows[row]?.open) === open,
    { timeoutMs: 20_000 },
  );
}

/**
 * The "Inject a fault" switch lives inside the expanded rights row, so the row is opened, the
 * switch thrown, held a moment so the gesture reads, and the row closed again. The console keeps
 * the switch armed between runs, which is why the third run switches it off first.
 */
async function setFault(page, on) {
  await segment(page, "Checks");
  await setRowOpen(page, "rights", true);
  const sw = page.locator('#check-rights [role="switch"]').filter({ hasText: /inject a fault/i }).first();
  const state = (await sw.getAttribute("aria-checked")) === "true";
  let toggled = false;
  if (state !== on) {
    await sw.click({ timeout: 20_000 });
    await until(
      `the rights fault switch to read ${on}`,
      async () => (await snapshot(page)).rightsFault === on,
      { timeoutMs: 20_000 },
    );
    toggled = true;
  }
  return {
    toggled,
    close: async () => {
      await setRowOpen(page, "rights", false);
    },
  };
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
        cue(`${gate}_done${suffix}`, { status, detail: `${status}: ${s.rows[gate].line.slice(0, 120)}` });
        if (onGate) await onGate(gate, status, s);
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

/**
 * The verdict card fills when the summary reads "Checks complete"; the run keeps working after
 * it (the investigator, then the escalation), which waitSettled watches separately.
 */
async function watchVerdict(page, suffix) {
  const settled = await until(
    `the verdict summary${suffix ? ` (${suffix})` : ""}`,
    async () => {
      const s = await snapshot(page);
      return s.verdict ? s : null;
    },
    { cue: `verdict${suffix}` },
  );
  return cue(`verdict${suffix}`, {
    status: settled.verdict,
    motive: settled.motive,
    needs_human: settled.needsHuman,
    summary: settled.summary,
    detail: `${settled.verdict}${settled.motive ? ` (${settled.motive})` : ""}`,
  });
}

/**
 * The end of the run: the investigator has written its note and the escalation has opened or
 * joined an incident (or said no human is needed). The Run button is enabled again at that point.
 */
async function waitSettled(page, suffix) {
  let s = null;
  try {
    s = await until(
      `the run to settle${suffix ? ` (${suffix})` : ""}`,
      async () => {
        const snap = await snapshot(page);
        if (snap.lost) throw new Fatal(`the event stream was lost after the verdict${suffix}`);
        return snap.busy ? null : snap;
      },
      { timeoutMs: SETTLE_TIMEOUT_MS, cue: `escalation_done${suffix}` },
    );
  } catch (error) {
    if (error instanceof Fatal) throw error;
    note(`the run${suffix} did not settle in ${SETTLE_TIMEOUT_MS / 1000} s, moving on without the incident id`);
    s = await snapshot(page);
  }
  const escalation = escalationFromLine(s.rows.escalation?.line) || { incident: null, attached: false };
  const investigationLine = s.rows.investigation?.line || null;
  return cue(`escalation_done${suffix}`, {
    incident: escalation.incident,
    attached: escalation.attached,
    escalation: s.rows.escalation?.line || null,
    investigation: investigationLine,
    detail: escalation.incident
      ? `incident ${escalation.incident} ${escalation.attached ? "joined" : "opened"}`
      : `no incident (${(s.rows.escalation?.line || "no escalation line").slice(0, 80)})`,
  });
}

/**
 * The investigation row while it works: its line names the tool being called. The row is
 * expanded so the list of tool calls grows on camera under the verdict.
 */
async function watchInvestigation(page) {
  let s = null;
  try {
    s = await until(
      "the investigator's first tool call",
      async () => {
        const snap = await snapshot(page);
        const line = snap.rows.investigation?.line || "";
        return /Investigator calls|answered/.test(line) || !snap.busy ? snap : null;
      },
      { timeoutMs: 40_000, cue: "investigation" },
    );
  } catch {
    s = await snapshot(page);
  }
  await setRowOpen(page, "investigation", true).catch((error) =>
    note(`the investigation row did not expand: ${error.message}`),
  );
  return cue("investigation", { detail: (s.rows.investigation?.line || "no investigation line").slice(0, 140) });
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

/**
 * The Record segment on camera after the first verdict: the run's cost line ("This check: $0.50
 * at list price, ..."), the annotation and incident ids, and the Grafana href the inserts use.
 * The recorder reads the cost into the cue log so a take that says $0 says so there too.
 */
async function openRecord(page) {
  await segment(page, "Record");
  const record = await recordSnapshot(page).catch(() => ({}));
  cue("record_open", {
    ids: record.ids,
    cost: record.cost,
    detail: `Record segment: ${record.ids || "no ids"}; ${record.cost || "no cost line"}`,
  });
  if (!record.cost) note("the Record segment showed no cost line");
  return record;
}

/**
 * How long a line lasts: narration.json from the previous narration, synthesised from the same
 * script at the same speaking rate, carries every wav's duration. A missing file or a line the
 * narration does not have falls back to the number given.
 */
let narrationLines = null;
function lineSeconds(cueId, fallbackS) {
  if (narrationLines === null) {
    try {
      const narration = JSON.parse(fs.readFileSync(path.join(OPTS.out, "narration.json"), "utf8"));
      narrationLines = narration.lines || [];
    } catch {
      narrationLines = [];
    }
  }
  const line = narrationLines.find((entry) => entry.cue === cueId);
  if (line && line.duration_s) return line.duration_s;
  log(`no line for cue ${cueId} in narration.json, assuming ${fallbackS} s`);
  return fallbackS;
}

/** Hold the picture for the line spoken over `cueId`, from the moment that cue was written. */
async function holdForLine(cueId, fallbackS, minS = 0) {
  const from = cues.find((entry) => entry.cue === cueId)?.t ?? now();
  const seconds = Math.max(minS, lineSeconds(cueId, fallbackS) + LINE_MARGIN_MS / 1000);
  const end = from + Math.min(HOLD_MAX_MS / 1000, seconds);
  log(`holding for the ${cueId} line until t+${end.toFixed(1)}s`);
  await holdUntil(end);
}

/**
 * Hold on a drawn dashboard: still at first, so the annotation the voice is pointing at is read
 * where it landed, then a slow glide down the panels for the rest of the insert.
 *
 * The glide is not decoration. An insert is on screen longer than the line spoken over it, and a
 * still dashboard for those seconds is the one thing this cut is against: a stretch with no change
 * of picture. Grafana scrolls an inner element rather than the window, so the tallest scrollable
 * node is found and moved, and if nothing moves at all the recorder says so in the notes.
 */
async function holdOnDashboard(page, holdMs, cueId) {
  const still = Math.min(DASHBOARD_STILL_MS, holdMs / 2);
  await sleep(still);
  const glideFrom = now();
  const glideMs = holdMs - still;
  if (glideMs < 400) return null;
  const steps = Math.floor(glideMs / DASHBOARD_GLIDE_STEP_MS);
  let moved = 0;
  let movedAt = null;
  for (let i = 0; i < steps; i += 1) {
    const at = await page
      .evaluate(() => {
        const nodes = [document.scrollingElement, ...document.querySelectorAll("div")].filter(
          (node) => node && node.scrollHeight - node.clientHeight > 40,
        );
        const tallest = nodes.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
        if (!tallest) return 0;
        tallest.scrollTop += 4;
        return tallest.scrollTop;
      })
      .catch(() => moved);
    // A public dashboard is not always taller than the viewport. When it stops moving the picture
    // stops changing, and the pace measurement in assemble.py is told exactly when that was.
    if (at > moved) {
      moved = at;
      movedAt = now();
    }
    await sleep(DASHBOARD_GLIDE_STEP_MS);
  }
  if (!moved) {
    note(`${cueId}: the dashboard did not scroll, the insert holds still`);
    return null;
  }
  log(`${cueId}: the dashboard glided ${moved} px, moving until t+${movedAt.toFixed(1)}s`);
  return { from: glideFrom, to: movedAt, pixels: moved };
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
 * entry as `ready_at`, and assemble.py starts the insert there. The console take keeps playing
 * underneath until then.
 */
async function visitGrafana(context, url, waitForText, holdMs, cueId, readyCueId) {
  const openedAt = now();
  const page = await context.newPage();
  let ok = true;
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90_000 });
    // The panel titles render about 1.5 s before the queries come back, so waiting on the title
    // alone puts an empty dashboard on camera. Measured on this stack: the panels draw their
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
  const glide = await holdOnDashboard(page, holdMs, cueId);
  const video = page.video();
  await page.close();
  const file = `${cueId}.webm`;
  overlays.push({
    cue: cueId,
    file,
    page_opened_at: openedAt,
    ready_cue: readyCueId,
    ready_at: readyAt,
    glide_from: glide ? glide.from : null,
    glide_to: glide ? glide.to : null,
    glide_px: glide ? glide.pixels : 0,
    closed_at: now(),
    panel_seen: ok,
  });
  return { video, file };
}

/**
 * The reviewer closes the loop from the Record segment: signs as the platform on-call (a control
 * incident is the platform owner's), clicks "Mark reviewed by a human", and the console answers
 * with the incident's resolved status and the reviewed annotation id.
 */
async function markReviewed(page) {
  let select = page.getByLabel(/signing as/i).first();
  if (!(await select.count())) select = page.locator("select").first();
  if (await select.count()) {
    await select.selectOption({ label: REVIEWER_ROLE }).catch((error) =>
      note(`could not sign as ${REVIEWER_ROLE}: ${error.message}`),
    );
    await sleep(600);
  } else {
    note("no Signing as select on the Record segment");
  }
  const button = page.getByRole("button", { name: /^mark reviewed by a human$/i }).first();
  if (!(await button.count())) {
    note("no Mark reviewed by a human button on the Record segment");
    cue("resolve", { detail: "button not found" });
    return null;
  }
  await button.click({ timeout: 20_000 });
  cue("resolve", { detail: `Mark reviewed by a human, signing as ${REVIEWER_ROLE}` });
  let record = null;
  try {
    record = await until(
      "the review to be written",
      async () => {
        const r = await recordSnapshot(page);
        return r.reviewed ? r : null;
      },
      { timeoutMs: 30_000, cue: "resolved" },
    );
  } catch {
    record = await recordSnapshot(page).catch(() => ({}));
  }
  const line = record?.reviewLine || "no review line";
  const incident = /incident (\S+) (\S+)/.exec(line);
  const annotation = /annotation (\d+) written/.exec(line);
  cue("resolved", {
    reviewed: record?.reviewed || null,
    line,
    incident: incident ? incident[1] : null,
    incident_status: incident ? incident[2].replace(/,$/, "") : null,
    annotation: annotation ? Number(annotation[1]) : null,
    detail: `${record?.reviewed || "not reviewed"} ${line}`,
  });
  return record;
}

async function openConsole(context) {
  const page = await context.newPage();
  await page.goto(OPTS.url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await until(
    "the console to render its check rows",
    async () => Object.keys((await snapshot(page)).rows).length >= 6,
    { cue: "console_open" },
  );
  await until("the calibration lines read from Grafana", async () => (await snapshot(page)).ready, {
    cue: "console_open",
  });
  return page;
}

function dashboardUrl(href) {
  const base = OPTS.dashboard || href || PUBLIC_DASHBOARD;
  const url = new URL(base);
  url.searchParams.set("from", "now-1h");
  url.searchParams.set("to", "now");
  return url.toString();
}

async function runTake() {
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

    // 1. The stake. The Article 50 overlay is laid over the first 5 s of it in assemble.py.
    cue("stake", { detail: "console idle, the clip on the stage, seven check rows" });
    await sleep(STAKE_HOLD_MS);

    // 2. The console idle with the Crest clip on the stage, held until the stake line and the
    //    console line have both been said, so the first run starts on its own line.
    await clickAsset(page, "Crest Toothpaste Commercial");
    const idle = cue("console_idle", { detail: "the Crest clip on the stage, the gate rows read from Grafana" });
    const stakeAt = cues.find((entry) => entry.cue === "stake").t;
    const linesEnd = stakeAt + lineSeconds("stake", 11) + 0.4 + lineSeconds("console_idle", 7) + 0.4;
    await holdUntil(Math.min(idle.t + HOLD_MAX_MS / 1000, Math.max(linesEnd, idle.t + 4)));

    // 3. The Crest commercial: four blocks on the asset itself, and the claim beat seeks the clip.
    await clickRun(page);
    cue("crest_click", { detail: "Run airlock on the Crest commercial" });
    await watchGates(page, "", async (gate) => {
      if (gate === "claim") await seekClaim(page);
    });
    const verdict1 = await watchVerdict(page, "");
    if (!OPTS.mock && (verdict1.status !== "BLOCK" || verdict1.motive !== "content")) {
      note(`verdict expected BLOCK (content), got ${verdict1.status} (${verdict1.motive})`);
    }
    // The verdict line runs while the investigator and the escalation land under the card; the
    // Record segment then shows the cost line and the incident id for the end of that line.
    const settled1 = await waitSettled(page, "");
    const verdictLine = lineSeconds("verdict", 16);
    await holdUntil(verdict1.t + verdictLine * 0.55);
    const record = await openRecord(page);
    if (settled1.incident && record.ids && !record.ids.includes(settled1.incident)) {
      note(`the Record ids (${record.ids}) do not name incident ${settled1.incident}`);
    }
    await holdUntil(Math.max(verdict1.t + verdictLine + LINE_MARGIN_MS / 1000, now() + RECORD_HOLD_MIN_MS / 1000));
    const grafana = dashboardUrl(record.href);
    log(`Grafana inserts will show ${grafana}`);
    await segment(page, "Checks");

    // 4. The clean clip with a fault injected into the rights gate, on camera.
    await clickAsset(page, "Nimbus clean clip");
    await sleep(700);
    const fault = await setFault(page, true);
    cue("fault_on", { detail: fault.toggled ? "Inject a fault switched on for the rights gate" : "already on" });
    await sleep(1_800);
    await fault.close();
    await holdUntil(cues.find((entry) => entry.cue === "fault_on").t + Math.max(3, lineSeconds("fault_on", 7) * 0.5));
    await clickRun(page);
    cue("fault_click", { detail: "Run airlock on the clean clip, a timeout fault injected into rights" });
    const landed2 = new Set();
    await watchGates(page, "_2", async (gate, status, s) => {
      if (gate === "rights") {
        if (status === "ERROR") {
          cue("rights_error", { detail: (s.rows.rights?.line || "").slice(0, 140) });
        } else {
          note(`rights expected ERROR with the fault injected, got ${status}`);
          cue("rights_error", { detail: `rights landed ${status}, not ERROR` });
        }
        return;
      }
      landed2.add(gate);
      if (landed2.size === 3) {
        cue("gates_done_2", {
          detail: `brand, claim and provenance have landed: ${["provenance", "brand", "claim"]
            .map((g) => `${g} ${statusFromLine(s.rows[g]?.line) || "?"}`)
            .join(", ")}`,
        });
      }
    });
    const verdict2 = await watchVerdict(page, "_2");
    if (!OPTS.mock && (verdict2.status !== "BLOCK" || verdict2.motive !== "control unavailable")) {
      note(`verdict_2 expected BLOCK (control unavailable), got ${verdict2.status} (${verdict2.motive})`);
    }
    await watchInvestigation(page);
    const settled2 = await waitSettled(page, "_2");
    await holdForLine("verdict_2", 13);

    // 5. The Record: the investigator's note with the Loki line it cites, the incident id; then
    //    the Grafana insert on the gate errors panel, then the human resolves the incident.
    await segment(page, "Record");
    const record2 = await recordSnapshot(page).catch(() => ({}));
    cue("investigation_note", {
      ids: record2.ids,
      investigation: record2.investigation,
      incident: settled2.incident,
      detail: `${record2.ids || "no ids"}; ${(record2.investigation || "no investigation section").slice(0, 160)}`,
    });
    await sleep(2_500);
    grafanaVideos.push(
      await visitGrafana(context, grafana, "Gate errors (per 5 min)", ALERT_INSERT_MS, "alert_insert",
        "alert_ready"),
    );
    await sleep(500);
    await markReviewed(page);
    await sleep(RESOLVED_HOLD_MS);

    // 6. The test clip with its study on file: the fault off first (the console keeps the switch
    //    armed between runs), a gesture that plays under the end of the resolve line, then the
    //    fourth preset on its own line.
    const off = await setFault(page, false);
    cue("fault_off", { detail: off.toggled ? "Inject a fault switched off" : "already off" });
    await sleep(600);
    await off.close();
    await holdForLine("resolve", 8);
    await clickAsset(page, "Nimbus test clip, study on file");
    await sleep(700);
    await clickRun(page);
    cue("study_click", { detail: "Run airlock on the test clip with its study on file" });
    await watchGates(page, "_3");
    const verdict3 = await watchVerdict(page, "_3");
    if (!OPTS.mock && verdict3.status !== "PASS") {
      note(`verdict_3 expected PASS, got ${verdict3.status} (${verdict3.motive})`);
    }
    // The line about the PASS starts on the rights landing and runs over the card filling.
    const rightsAt = cues.find((entry) => entry.cue === "rights_done_3")?.t ?? verdict3.t;
    await holdUntil(Math.max(rightsAt + lineSeconds("rights_done_3", 15) + LINE_MARGIN_MS / 1000, verdict3.t + 3));

    // 7. The public dashboard, then the PASS verdict held.
    grafanaVideos.push(
      await visitGrafana(context, grafana, "Verdicts (7d)", DASHBOARD_INSERT_MS, "dashboard", "dashboard_ready"),
    );
    await waitSettled(page, "_3");
    const landed = await snapshot(page);
    if (landed.verdict !== "PASS") {
      note(`landing: the console no longer shows the PASS verdict (verdict=${landed.verdict})`);
    }
    cue("landing", { detail: `holding on the ${landed.verdict ?? "idle"} verdict` });
    await sleep(LANDING_HOLD_MS);
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
    script: "v6",
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

await runTake();
