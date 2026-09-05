"use client";

import { GATE_ORDER, type GateDonePayload, type GateName, type Terminal } from "@/lib/events";
import { splitTimecodes, stamp } from "@/lib/timecodes";
import type { GateCardState } from "@/lib/use-run";

/**
 * A gate writes `reasons` as sentences, and some gates also put one record per
 * thing they read in `evidence`: the claim gate one per claim, the rights gate
 * one per brand or face track, the brand gate one per exclusion hit. When those
 * records exist the thread gets one row per record, anchored on that record's
 * own second, so the scrubber shows one marker per claim; the sentence that only
 * summarised them ("9 regulated claim(s) ...; first at 7.0s") stays the gate's
 * headline in the Checks row. A gate whose evidence has no per-item structure
 * (provenance, a gate in error) keeps one row per reason.
 */
export type FindingItem = {
  /** What the gate calls it: "consumer testimonial", "brand not cleared", "exclusion violated". */
  kind: string;
  /** Where in the clip it was read: spoken, on-screen text, logo, faces. */
  channel: string | null;
  /** The rules the gate cited for this item. */
  rules: string[];
  /** The gate's one-line reason for this item, or what lifted it; null when the sentence already says it. */
  why: string | null;
  /** Where the item ends, when the record says. */
  endSeconds: number | null;
};

export type Finding = {
  key: string;
  gate: GateName;
  /** What the gate concluded about this row: PASS for something it read and let through. */
  status: Terminal;
  /** The sentence: the gate's reason, or the quote the record carries. */
  text: string;
  /** The second the row is anchored on: the record's own, or the first second the sentence names. */
  seconds: number | null;
  /** Set when the row was built from one evidence record. */
  item: FindingItem | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function records(value: unknown): Record<string, unknown>[] | null {
  return Array.isArray(value) ? value.filter(isRecord) : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

/** snake_case from the gate schema to words: consumer_testimonial, not_cleared. */
function words(value: string): string {
  return value.replace(/_/g, " ");
}

function firstSecond(text: string): number | null {
  for (const part of splitTimecodes(text)) {
    if (part.kind === "time") return part.seconds;
  }
  return null;
}

function plainRow(gate: GateName, done: GateDonePayload, text: string, key: string): Finding {
  return { key, gate, status: done.status, text, seconds: firstSecond(text), item: null };
}

/** The existing behaviour: one row per reason sentence. */
function plainRows(gate: GateName, done: GateDonePayload): Finding[] {
  const reasons = done.reasons?.length ? done.reasons : [`${gate} ${done.status}`];
  return reasons.map((text, index) => plainRow(gate, done, text, `${gate}-${index}`));
}

/**
 * Hands out the gate's reasons one at a time to the record that describes them,
 * so a sentence is never shown twice; what no record claimed stays a plain row.
 */
function reasonPool(done: GateDonePayload) {
  const reasons = done.reasons ?? [];
  const used = new Set<number>();
  return {
    take(predicate: (reason: string) => boolean): string | null {
      const index = reasons.findIndex((reason, i) => !used.has(i) && predicate(reason));
      if (index === -1) return null;
      used.add(index);
      return reasons[index];
    },
    rest(gate: GateName): Finding[] {
      return reasons
        .map((text, index) => ({ text, index }))
        .filter(({ index }) => !used.has(index))
        .map(({ text, index }) => plainRow(gate, done, text, `${gate}-reason-${index}`));
    },
  };
}

const CLAIM_CHANNEL: Record<string, string> = { spoken: "spoken", on_screen_text: "on-screen text" };

/**
 * One row per claim: `blocking_claims` as issues, `advisory_claims` (puffery, or
 * a claim with its study on file) as what the gate let through. On a BLOCK the
 * gate's single reason is a summary of the blocking rows and stays out of the
 * thread; on a PASS the reason names the study and stays.
 */
function claimRows(gate: GateName, done: GateDonePayload, first: Record<string, unknown>): Finding[] | null {
  const blocking = records(first.blocking_claims);
  if (blocking === null) return null;
  const advisory = records(first.advisory_claims) ?? [];

  const row = (claim: Record<string, unknown>, status: Terminal, key: string): Finding => {
    const quote = (str(claim.quote) ?? "(no quote)").replace(/\s+/g, " ");
    const kind = words(str(claim.kind) ?? "claim");
    const rawChannel = str(claim.channel);
    const channel = rawChannel ? (CLAIM_CHANNEL[rawChannel] ?? words(rawChannel)) : null;
    const lifted = isRecord(claim.substantiated_by) ? str(claim.substantiated_by.study) : str(claim.substantiated_by);
    // The full row keeps the (SYNTHETIC: ...) disclosure the study carries: this is the detailed evidence
    // view, and a fictional study must stay visibly fictional here even where the short headline
    // (checks-panel.tsx) trims it for space. Found live, 2026-09-05.
    const why = lifted ? `substantiation on file: ${lifted}` : str(claim.why);
    const seconds = num(claim.start_s);
    return {
      key,
      gate,
      status,
      text: `"${quote}"`,
      seconds: seconds ?? firstSecond(quote),
      item: { kind, channel, rules: strings(claim.rules), why, endSeconds: num(claim.end_s) },
    };
  };

  const rows = blocking.map((claim, index) => row(claim, done.status, `${gate}-claim-${index}`));
  advisory.forEach((claim, index) => rows.push(row(claim, "PASS", `${gate}-advisory-${index}`)));
  if (done.status !== "PASS" && blocking.length > 0) return rows;
  return [...plainRows(gate, done), ...rows];
}

/**
 * One row per element the rights gate read: a brand (logo or on-screen text),
 * the face tracks, explicit content. The gate's sentence for that element is
 * kept as the row's text, since it carries the registry note and the confidence.
 */
function rightsRows(gate: GateName, done: GateDonePayload, first: Record<string, unknown>): Finding[] | null {
  const elements = records(first.findings);
  if (elements === null) return null;
  const pool = reasonPool(done);
  const rows: Finding[] = [];

  elements.forEach((record, index) => {
    const element = str(record.element);
    const seconds = num(record.first_seen_s);
    const at = seconds === null ? "" : ` at ${stamp(seconds)}`;
    const key = `${gate}-${element ?? "element"}-${index}`;

    if (element === "brand") {
      const name = str(record.name) ?? "unknown brand";
      const status = str(record.status) ?? "unknown";
      const how = str(record.how);
      const channel =
        how === "logo"
          ? "logo"
          : how === "on_screen_text"
            ? record.across_lines === true
              ? "on-screen text across lines"
              : "on-screen text"
            : how;
      const reason = pool.take((r) => r.includes(`brand ${name} (`) || r.includes(`guess: ${name},`));
      const cleared = status === "cleared";
      const rule = cleared ? "registry:brands" : `registry:brands:${status}`;
      rows.push({
        key,
        gate,
        status: cleared ? "PASS" : done.status,
        text: reason ?? `brand ${name} (${words(status)}${channel ? `, ${channel}` : ""}${at})`,
        seconds: seconds ?? (reason ? firstSecond(reason) : null),
        item: { kind: `brand ${words(status)}`, channel, rules: [rule], why: null, endSeconds: null },
      });
      return;
    }

    if (element === "faces") {
      const tracks = num(record.tracks) ?? 0;
      const released = Array.isArray(record.released_by) || str(record.status) === "released";
      const reason = pool.take((r) => /face track/.test(r));
      rows.push({
        key,
        gate,
        status: released ? "PASS" : done.status,
        text:
          reason ??
          `${tracks} face track${tracks === 1 ? "" : "s"} ${released ? "released" : "with no release on file for this asset"}${at ? ` (first${at})` : ""}`,
        seconds: seconds ?? (reason ? firstSecond(reason) : null),
        item: {
          kind: released ? "faces released" : "faces, no release",
          channel: null,
          rules: [released ? "registry:faces" : "registry:faces:no_release"],
          why: null,
          endSeconds: null,
        },
      });
      return;
    }

    if (element === "explicit") {
      const reason = pool.take((r) => /explicit content/.test(r));
      rows.push({
        key,
        gate,
        status: done.status,
        text: reason ?? "explicit content at or above the block line",
        seconds: reason ? firstSecond(reason) : null,
        item: { kind: "explicit content", channel: null, rules: ["registry:explicit_content"], why: null, endSeconds: null },
      });
    }
  });

  return [...pool.rest(gate), ...rows];
}

/**
 * One row per exclusion hit the brand gate read, quoting what it saw; the other
 * charter reasons (a missing wordmark, palette, tone, typography) stay sentences.
 */
function brandRows(gate: GateName, done: GateDonePayload, first: Record<string, unknown>): Finding[] | null {
  const violations = records(first.exclusion_violations);
  if (violations === null) return null;
  const pool = reasonPool(done);
  const rows: Finding[] = [];

  violations.forEach((record, index) => {
    const exclusion = str(record.exclusion) ?? "an exclusion";
    const quote = str(record.evidence) ?? "(no quote)";
    // The gate's sentence for this hit repeats the quote and the second: consumed, not shown twice.
    pool.take((r) => r.startsWith(`exclusion violated: ${exclusion} (${quote}`));
    rows.push({
      key: `${gate}-exclusion-${index}`,
      gate,
      status: done.status,
      text: `"${quote}"`,
      seconds: num(record.start_s),
      item: { kind: "exclusion violated", channel: null, rules: ["charter:exclusions"], why: `the charter excludes: ${exclusion}`, endSeconds: null },
    });
  });

  return [...pool.rest(gate), ...rows];
}

/** What one gate contributes to the thread and the scrubber. */
export function gateFindings(gate: GateName, done: GateDonePayload): Finding[] {
  const first = Array.isArray(done.evidence) ? done.evidence.find(isRecord) : undefined;
  let rows: Finding[] | null = null;
  if (first) {
    if (gate === "claim") rows = claimRows(gate, done, first);
    else if (gate === "rights") rows = rightsRows(gate, done, first);
    else if (gate === "brand") rows = brandRows(gate, done, first);
  }
  return rows ?? plainRows(gate, done);
}

/** Claim first (the regulatory substance a reviewer reads for), then rights, then the charter's own
 *  exclusions, then provenance last (rarely has more than one row). Fixed rather than sorted by which
 *  gate happened to land first: on Crest, brand settles before claim and its twelve exclusion rows
 *  buried the eight claim rows at the top of the thread every time (found live, 2026-09-05). */
const FINDINGS_GATE_PRIORITY: GateName[] = ["claim", "rights", "brand", "provenance"];

/** The gates' rows in a fixed, reviewer-priority order, not the order the gates happened to settle in. */
export function buildFindings(gates: Record<GateName, GateCardState>): Finding[] {
  const settled = FINDINGS_GATE_PRIORITY.filter((gate) => gates[gate].done !== null);
  const findings: Finding[] = [];
  for (const gate of settled) {
    const done = gates[gate].done;
    if (done) findings.push(...gateFindings(gate, done));
  }
  return findings;
}

/** How many rows a gate's answer puts in the thread as issues (a PASS row is an attestation). */
export function issueCount(gate: GateName, done: GateDonePayload): number {
  return gateFindings(gate, done).filter((finding) => finding.status !== "PASS").length;
}

/**
 * A verdict reason that no gate already said. The gate sentences live in the
 * thread (or as a Checks headline); what is left here is what the verdict itself
 * added, such as a control that Grafana says is unavailable.
 */
export function verdictNotes(reasons: string[], gates: Record<GateName, GateCardState>): string[] {
  const said = GATE_ORDER.flatMap((gate) => gates[gate].done?.reasons ?? []);
  return reasons.filter((reason) => !said.some((sentence) => reason.includes(sentence)));
}
