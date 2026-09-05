/**
 * The payloads the ADK agents emit inside `content.parts[].text`, and the
 * shapes the console derives from them. Anything that does not parse, or that
 * carries no `stage`, is ignored: workflow agents emit state events too.
 */

import { formatUsd } from "@/lib/utils";

export type GateName = "rights" | "claim" | "brand" | "provenance";
export type Terminal = "PASS" | "BLOCK" | "ERROR";
export type ChipStatus = "PENDING" | "RUNNING" | Terminal;

export const GATE_ORDER: GateName[] = ["rights", "claim", "brand", "provenance"];

export const GATE_SOURCE_OF_TRUTH: Record<GateName, string> = {
  rights: "Video Intelligence against the rights registry",
  claim: "16 CFR 255 and ASA rulings, read by gemini-2.5-pro",
  brand: "Brand charter, read by gemini-2.5-flash",
  provenance: "C2PA manifest, cryptographic check against the trust list",
};

/** What the console says it is waiting on while a gate runs. */
export const GATE_STEP: Record<GateName, string> = {
  rights: "Video Intelligence: logos, faces, text",
  claim: "gemini-2.5-pro reading claims",
  brand: "gemini-2.5-flash reading the charter",
  provenance: "c2pa-python verifying the manifest",
};

/** The instrument a running gate is waiting on, for the elapsed counter. */
export const GATE_INSTRUMENT: Record<GateName, string> = {
  rights: "Video Intelligence",
  claim: "gemini-2.5-pro",
  brand: "gemini-2.5-flash",
  provenance: "c2pa-python",
};

/**
 * How long the instrument took when it was measured, so a reviewer watching
 * the counter knows what is normal. Rights: airlock/gates/rights.py, annotate()
 * docstring, 2026-08-28: an 8 s clip 30 to 90 s, the 30 s excerpt 59 s alone
 * and 598 s when three jobs ran at once; a hosted run of the 8 s clean clip on
 * 2026-09-02 waited 220 s, so the upper bound is said too.
 */
export const GATE_MEASURED: Partial<Record<GateName, string>> = {
  rights: "30 to 90 s usual, up to 600 s measured",
};


/**
 * The one fault a reviewer can inject for now: the gate raises a TimeoutError
 * before it calls its instrument, so nothing is spent and the ERROR lands in
 * Loki and Influx like a real one. The verdict has to notice through Grafana.
 */
export type FaultKind = "timeout";
export type FaultMap = Partial<Record<GateName, FaultKind>>;

export type GateRunningPayload = {
  gate: GateName;
  stage: "running";
  asset_id?: string;
  /** The ADK invocation id: the run the verdict asks Loki about. */
  run_id?: string;
  source_of_truth?: string;
  telemetry_muted?: boolean;
  /** Set when the reviewer injected a fault into this gate for this run. */
  fault?: string;
};

/** What a single gate spent to produce its answer, at list price. */
export type GateUsage = {
  tokens_in?: number;
  tokens_out?: number;
  video_minutes?: number;
  features?: number;
  cost_usd?: number;
  basis?: string;
};

export type GateDonePayload = {
  gate: GateName;
  stage: "done";
  status: Terminal;
  reasons?: string[];
  evidence?: unknown[];
  rule_ids?: string[];
  elapsed_ms?: number;
  run_id?: string;
  source_of_truth?: string;
  telemetry_muted?: boolean;
  fault?: string;
  usage?: GateUsage;
};

export type GrafanaAnswer = { expr: string; value: number | null };

export type ProbePayload = {
  stage: "grafana";
  gate: GateName;
  answers: Record<string, GrafanaAnswer>;
  health: string;
  calibrated: boolean;
  /** The sentence the verdict agent read out of Grafana, when it sent one. */
  calibration?: string;
  /** Whether Loki holds this run's event for the gate; absent on older recordings. */
  seen_this_run?: boolean | null;
  /** The R1 fact as the verdict computed it (not seen, unreadable, or the error ratio at the block line). */
  unavailable?: boolean;
  /** A remark the verdict attached to this probe, when it sent one. */
  note?: string;
};

/**
 * A remark from the verdict agent about Grafana itself, not about a gate: for
 * now "Grafana Cloud was starting, waited N s" when a paused free stack had to
 * wake before it answered.
 */
export type GrafanaNotePayload = {
  stage: "grafana";
  note: string;
  waited_s?: number;
};

export type VerdictGate = {
  gate: GateName;
  status: Terminal;
  reason?: string;
  health?: string;
  calibrated?: boolean;
  calibration?: string;
  calibration_catches_7d?: number | null;
  seen_this_run?: boolean | null;
  unavailable?: boolean;
  rule_ids?: string[];
};

/** What a gate reported about its own instrument, probe first, verdict last. */
export type ReportedInstrument = {
  health?: string;
  calibrated?: boolean;
  /** The verdict's own R1 boolean; when present the console keys its tone on it, never on the prose. */
  unavailable?: boolean;
  calibration?: string;
  /** The verdict's own PromQL answers for this gate, when the probe stage sent them: the real numbers
   *  the decision rested on, never the console's own independent background poll. */
  answers?: Record<string, GrafanaAnswer>;
};

/** What the whole run spent, at list price, and how it splits across gates. */
export type VerdictCost = {
  cost_usd: number;
  per_gate?: Partial<Record<GateName, number>>;
  tokens_in?: number;
  tokens_out?: number;
  video_minutes?: number;
  basis?: string;
};

export type VerdictPayload = {
  stage: "verdict";
  status: Terminal;
  motive?: string;
  needs_human?: boolean;
  reasons?: string[];
  gates?: VerdictGate[];
  rule_ids?: string[];
  asset_id?: string;
  annotation_id?: number | null;
  /** The run's trace in Tempo (airlock.tracing): the 32-hex id and the Grafana Explore URL that opens it. */
  trace_id?: string;
  trace_url?: string;
  elapsed_ms?: number;
  cost?: VerdictCost;
};

export type EscalationPayload = {
  stage: "escalation";
  opened: boolean;
  /** This run joined the open incident of the same asset and motive instead of opening a new one. */
  attached?: boolean;
  /** Who the incident is routed to: "clearance" (paperwork) or "platform" (a control). */
  owner?: string;
  reason?: string;
  incident_id?: string;
  incident_url?: string;
  incident_title?: string;
  activity_id?: string;
  fallback?: string;
  fallback_annotation_id?: number;
  incident_raw?: string;
  elapsed_ms?: number;
};

/** One Loki line the investigator read, compact: what the incident and the record show. */
export type LokiLine = {
  time_utc?: string | null;
  gate?: string;
  status?: string;
  run_id?: string;
  asset_id?: string;
  reason?: string;
  fault?: string;
};

/** One tool call or one tool answer of the investigator, streamed while it works. */
export type InvestigationStepPayload = {
  stage: "investigation";
  step: "tool_call" | "tool_result";
  tool: string;
  run_id?: string;
  args?: Record<string, unknown>;
  chars?: number;
  preview?: string;
  lines?: number;
};

/**
 * The investigator's note: an LlmAgent on gemini-2.5-flash read this run's Loki
 * lines, the counters and the alert rules through mcp-grafana and named the
 * cause. ROOT CAUSE on a control motive, DECISION NOTE on a content verdict or
 * a PASS. The verdict never depends on it.
 */
export type InvestigationPayload = {
  stage: "investigation";
  kind: "ROOT CAUSE" | "DECISION NOTE" | string;
  note: string;
  conclusion?: string | null;
  run_id?: string;
  asset_id?: string | null;
  model?: string;
  tool_calls?: number;
  model_turns?: number;
  steps?: Array<Omit<InvestigationStepPayload, "stage">>;
  loki_lines?: LokiLine[];
  cited?: LokiLine[];
  elapsed_ms?: number;
  /** The investigator could not run; the note is the verdict's own reason, said as such. */
  fallback?: boolean;
  error?: string | null;
  stopped?: string;
};

export type ParsedPayload =
  | { kind: "gate-running"; gate: GateName; payload: GateRunningPayload }
  | { kind: "gate-done"; gate: GateName; payload: GateDonePayload }
  | { kind: "probe"; payload: ProbePayload }
  | { kind: "grafana-note"; payload: GrafanaNotePayload }
  | { kind: "verdict"; payload: VerdictPayload }
  | { kind: "investigation-step"; payload: InvestigationStepPayload }
  | { kind: "investigation"; payload: InvestigationPayload }
  | { kind: "escalation"; payload: EscalationPayload };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isGate(value: unknown): value is GateName {
  return typeof value === "string" && (GATE_ORDER as string[]).includes(value);
}

/** Returns null for anything the console does not model, without throwing. */
export function parsePayload(text: string): ParsedPayload | null {
  const trimmed = text?.trim();
  if (!trimmed || trimmed[0] !== "{") return null;

  let value: unknown;
  try {
    value = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;

  const stage = value.stage;

  if (stage === "running" && isGate(value.gate)) {
    return { kind: "gate-running", gate: value.gate, payload: value as unknown as GateRunningPayload };
  }
  if (stage === "done" && isGate(value.gate)) {
    return { kind: "gate-done", gate: value.gate, payload: value as unknown as GateDonePayload };
  }
  if (stage === "grafana" && isGate(value.gate)) {
    return { kind: "probe", payload: value as unknown as ProbePayload };
  }
  if (stage === "grafana" && typeof value.note === "string" && value.note.trim()) {
    return { kind: "grafana-note", payload: value as unknown as GrafanaNotePayload };
  }
  if (stage === "verdict") {
    return { kind: "verdict", payload: value as unknown as VerdictPayload };
  }
  if (stage === "investigation" && (value.step === "tool_call" || value.step === "tool_result") && typeof value.tool === "string") {
    return { kind: "investigation-step", payload: value as unknown as InvestigationStepPayload };
  }
  if (stage === "investigation" && typeof value.note === "string") {
    return { kind: "investigation", payload: value as unknown as InvestigationPayload };
  }
  if (stage === "escalation") {
    return { kind: "escalation", payload: value as unknown as EscalationPayload };
  }
  return null;
}

export type RuleGroup = { source: string; ids: string[] };

/** Rule ids grouped by the authority that issued them. */
export function groupRuleIds(ids: string[]): RuleGroup[] {
  const groups = new Map<string, string[]>();
  const order = [
    "16 CFR 255",
    "ASA rulings",
    "Brand charter",
    "Rights registry",
    "Airlock policy",
    "Other references",
  ];
  for (const id of ids) {
    let source = "Other references";
    if (/^16\s*CFR/i.test(id)) source = "16 CFR 255";
    else if (/^ASA/i.test(id) || /^[AG]\d{2}-\d+/.test(id)) source = "ASA rulings";
    else if (id.startsWith("charter:")) source = "Brand charter";
    else if (id.startsWith("registry:")) source = "Rights registry";
    else if (id.startsWith("airlock:")) source = "Airlock policy";
    const bucket = groups.get(source) ?? [];
    if (!bucket.includes(id)) bucket.push(id);
    groups.set(source, bucket);
  }
  return order
    .filter((source) => groups.has(source))
    .map((source) => ({ source, ids: groups.get(source) as string[] }));
}

export type C2paReading = {
  state: string;
  line: string;
  ok: boolean;
};

/** The C2PA status line, read out of the provenance gate evidence. */
export function readC2pa(done: GateDonePayload | null): C2paReading | null {
  if (!done) return null;
  const evidence = Array.isArray(done.evidence) ? done.evidence : [];
  const manifest = evidence.find(
    (item) => isRecord(item) && ("validation_state" in item || "active_manifest" in item),
  );
  if (!isRecord(manifest)) {
    if (done.status === "BLOCK") {
      return {
        state: "absent",
        ok: false,
        line: "C2PA: no manifest on the asset, provenance cannot be established.",
      };
    }
    return null;
  }
  const state = typeof manifest.validation_state === "string" ? manifest.validation_state : "unknown";
  const issuer = typeof manifest.issuer === "string" ? manifest.issuer : null;
  const generator = typeof manifest.claim_generator === "string" ? manifest.claim_generator : null;
  const parts = [`C2PA: ${state}`];
  if (issuer) parts.push(`signed by ${issuer}`);
  if (generator) parts.push(`created by ${generator}`);
  return { state, ok: state.toLowerCase() === "trusted", line: `${parts.join(", ")}.` };
}

export const MOTIVE_COPY: Record<string, string> = {
  content: "The asset itself breaks a rule.",
  "control unavailable": "A control could not be reached, so nothing can be cleared.",
  "uncalibrated control": "A control has never caught a defect, so its pass means nothing.",
  "instrument error": "A control failed while running. A failed control is never a pass.",
};

/** Amber for a control problem, red for the content or a broken instrument. */
export function motiveTone(motive: string | undefined): "block" | "degraded" {
  if (motive === "control unavailable" || motive === "uncalibrated control") return "degraded";
  return "block";
}

function formatMinutes(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** One small mono line for a single gate's usage, video-shaped or token-shaped. */
export function formatGateUsage(usage: GateUsage): string {
  const parts: string[] = [];
  if (usage.video_minutes !== undefined && usage.features !== undefined) {
    parts.push(
      `${formatMinutes(usage.video_minutes)} min x ${usage.features} feature${usage.features === 1 ? "" : "s"}`,
    );
  } else if (usage.tokens_in !== undefined || usage.tokens_out !== undefined) {
    const segments: string[] = [];
    if (usage.tokens_in !== undefined) segments.push(`${usage.tokens_in.toLocaleString("en-US")} tokens in`);
    if (usage.tokens_out !== undefined) segments.push(`${usage.tokens_out.toLocaleString("en-US")} out`);
    parts.push(segments.join(", "));
  }
  if (usage.cost_usd !== undefined) parts.push(formatUsd(usage.cost_usd));
  return parts.join(", ");
}

/** The compact "this check cost" line the Record segment shows for a settled run. */
export function formatVerdictCostLine(cost: VerdictCost): string {
  const perGate = cost.per_gate ?? {};
  const gateParts = GATE_ORDER.filter((gate) => perGate[gate] !== undefined).map(
    (gate) => `${gate} ${formatUsd(perGate[gate] as number)}`,
  );
  if (cost.cost_usd === null || cost.cost_usd === undefined) {
    return `This check: cost not measured${cost.basis ? ` (${cost.basis})` : ""}`;
  }
  let head = `This check: ${formatUsd(cost.cost_usd)} at list price`;
  if (gateParts.length > 0) head += ` (${gateParts.join(", ")})`;

  const tail: string[] = [];
  if (cost.tokens_in !== undefined) tail.push(`${cost.tokens_in.toLocaleString("en-US")} tokens in`);
  if (cost.tokens_out !== undefined) tail.push(`${cost.tokens_out.toLocaleString("en-US")} out`);
  if (cost.video_minutes !== undefined) {
    tail.push(
      `${formatMinutes(cost.video_minutes)} min of video (Video Intelligence bills per started minute)`,
    );
  }

  return tail.length > 0 ? `${head}, ${tail.join(", ")}` : head;
}
