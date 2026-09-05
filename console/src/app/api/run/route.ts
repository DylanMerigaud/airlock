import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { assetIdFor, ASSETS_BUCKET, PRESET_ASSETS, resolveAsset } from "@/lib/assets";
import { callerKey, RUN_LIMIT_PER_HOUR, takeRunToken } from "@/lib/run-limit";
import { GATE_ORDER, type FaultKind, type FaultMap, type GateName } from "@/lib/events";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 900;

const UPSTREAM_TIMEOUT_MS = 15 * 60 * 1000;

const encoder = new TextEncoder();

function sse(event: string | null, data: unknown): Uint8Array {
  const head = event ? `event: ${event}\n` : "";
  return encoder.encode(`${head}data: ${JSON.stringify(data)}\n\n`);
}

type Relay = {
  push: (author: string, text: string) => void;
  fail: (message: string) => void;
};

function sleep(msValue: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, msValue);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

/**
 * Mock mode replays a run recorded against the real pipeline. Each preloaded
 * asset has its own recording; anything else replays the instrument-error run,
 * which is the state a reviewer most needs the console to get right.
 */
const MOCK_FIXTURES: Record<string, string> = {
  crest: "run-crest-incident.jsonl",
  nimbus: "run-nimbus-block.jsonl",
  substantiated: "run-substantiated-pass.jsonl",
  clean: "run-clean-pass.jsonl",
};
const DEFAULT_FIXTURE = "run-nimbus-instrument-error.jsonl";

function fixtureFor(asset: string): string {
  if (MOCK_FIXTURES[asset]) return MOCK_FIXTURES[asset];
  const preset = PRESET_ASSETS.find((a) => a.gcs === asset);
  if (preset && MOCK_FIXTURES[preset.id]) return MOCK_FIXTURES[preset.id];
  return DEFAULT_FIXTURE;
}

async function replayFixture(fixture: string, relay: Relay, signal: AbortSignal) {
  const file = path.join(process.cwd(), "fixtures", fixture);
  let raw: string;
  try {
    raw = await readFile(file, "utf8");
  } catch {
    relay.fail(`Mock fixture not found at ${file}`);
    return;
  }
  const lines = raw.split("\n").filter((line) => line.trim().length > 0);
  for (const line of lines) {
    if (signal.aborted) return;
    await sleep(400 + Math.random() * 1100, signal);
    if (signal.aborted) return;
    try {
      const parsed = JSON.parse(line) as { author?: string; text?: string };
      if (parsed.author && typeof parsed.text === "string") {
        relay.push(parsed.author, parsed.text);
      }
    } catch {
      // A malformed fixture line is skipped rather than killing the run.
    }
  }
}

function locationOf(resource: string): string {
  const match = /locations\/([^/]+)/.exec(resource);
  return match ? match[1] : "us-central1";
}

/** The faults the pipeline knows how to inject; anything else in the body is dropped. */
const FAULT_KINDS: FaultKind[] = ["timeout"];

/** Only known gates and known fault kinds travel; the pipeline never sees a free-form value. */
function faultsFrom(value: unknown): FaultMap {
  const faults: FaultMap = {};
  if (typeof value !== "object" || value === null || Array.isArray(value)) return faults;
  for (const gate of GATE_ORDER) {
    const kind = (value as Record<string, unknown>)[gate];
    if (typeof kind === "string" && (FAULT_KINDS as string[]).includes(kind)) faults[gate] = kind as FaultKind;
  }
  return faults;
}

/**
 * What the pipeline receives. A bare URI when nothing is muted and no fault is
 * injected, so a plain run stays exactly what it was; a JSON message when the
 * reviewer asked one or more gates to run without pushing anything to Grafana
 * (`mute`) or to fail on purpose before spending anything (`fault`).
 */
function messageFor(gcsUri: string, mute: GateName[], faults: FaultMap = {}): string {
  const injected = Object.keys(faults).length > 0;
  if (mute.length === 0 && !injected) return gcsUri;
  return JSON.stringify({
    gcs_uri: gcsUri,
    asset_id: assetIdFor(gcsUri),
    mute,
    ...(injected ? { fault: faults } : {}),
  });
}

/** Live mode: Vertex AI Agent Engine streamQuery, relayed event by event. */
async function relayAgentEngine(message: string, relay: Relay, signal: AbortSignal) {
  const resource = process.env.AGENT_ENGINE_RESOURCE;
  if (!resource) {
    relay.fail("AGENT_ENGINE_RESOURCE is not set. Start the console with AIRLOCK_MOCK=1 to replay a recorded run.");
    return;
  }

  const { GoogleAuth } = await import("google-auth-library");
  const auth = new GoogleAuth({ scopes: ["https://www.googleapis.com/auth/cloud-platform"] });

  let accessToken: string | null | undefined;
  try {
    const client = await auth.getClient();
    accessToken = (await client.getAccessToken()).token;
  } catch (error) {
    relay.fail(
      `No Application Default Credentials: ${error instanceof Error ? error.message : String(error)}`,
    );
    return;
  }
  if (!accessToken) {
    relay.fail("Application Default Credentials returned no access token.");
    return;
  }

  const location = locationOf(resource);
  const url = `https://${location}-aiplatform.googleapis.com/v1/${resource}:streamQuery?alt=sse`;

  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), UPSTREAM_TIMEOUT_MS);
  signal.addEventListener("abort", () => timeout.abort(), { once: true });

  try {
    const upstream = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        class_method: "stream_query",
        input: {
          user_id: `console-${Math.random().toString(36).slice(2, 10)}`,
          message,
        },
      }),
      signal: timeout.signal,
    });

    if (!upstream.ok || !upstream.body) {
      const detail = upstream.body ? (await upstream.text()).slice(0, 300) : "empty response";
      relay.fail(`Agent Engine answered ${upstream.status}: ${detail}`);
      return;
    }

    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const consume = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith(":")) return;
      const payload = trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
      if (!payload || payload === "[DONE]") return;
      let event: unknown;
      try {
        event = JSON.parse(payload);
      } catch {
        return;
      }
      if (typeof event !== "object" || event === null) return;
      const record = event as {
        author?: string;
        content?: { parts?: Array<{ text?: string }> };
      };
      const author = record.author ?? "agent";
      const parts = record.content?.parts ?? [];
      for (const part of parts) {
        if (typeof part.text === "string" && part.text.trim().length > 0) {
          relay.push(author, part.text);
        }
      }
    };

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index = buffer.indexOf("\n");
      while (index !== -1) {
        consume(buffer.slice(0, index));
        buffer = buffer.slice(index + 1);
        index = buffer.indexOf("\n");
      }
    }
    if (buffer.trim()) consume(buffer);
  } catch (error) {
    if (signal.aborted) return;
    const message = error instanceof Error ? error.message : String(error);
    relay.fail(
      timeout.signal.aborted && !signal.aborted
        ? "Agent Engine did not answer within 15 minutes. The run was cut off."
        : `Agent Engine stream failed: ${message}`,
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  let asset: string;
  let mute: GateName[];
  let faults: FaultMap;
  try {
    const body = (await request.json()) as { asset?: string; mute?: unknown; fault?: unknown };
    asset = String(body.asset ?? "");
    const asked = Array.isArray(body.mute) ? body.mute : [];
    mute = GATE_ORDER.filter((gate) => asked.includes(gate));
    faults = faultsFrom(body.fault);
  } catch {
    return NextResponse.json({ error: "Send a JSON body with an asset field." }, { status: 400 });
  }

  const gcsUri = resolveAsset(asset);
  if (!gcsUri) {
    const names = PRESET_ASSETS.map((a) => a.id).join(", ");
    return NextResponse.json(
      { error: `Unknown asset "${asset}". Use ${names}, or a gs:// URI in the ${ASSETS_BUCKET} bucket.` },
      { status: 400 },
    );
  }

  // Every run spends real quota (about half a dollar at list price, one to three minutes of Video
  // Intelligence), and the route is public: a caller gets a few runs per hour, not a firehose.
  const caller = callerKey(request);
  const allowed = takeRunToken(caller);
  if (!allowed.ok) {
    return NextResponse.json(
      { error: `Too many runs from this address: ${RUN_LIMIT_PER_HOUR} per hour. Try again in ${allowed.retryAfterS} s.` },
      { status: 429, headers: { "Retry-After": String(allowed.retryAfterS) } },
    );
  }

  const mock = process.env.AIRLOCK_MOCK === "1";
  const startedAt = Date.now();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let closed = false;
      const close = () => {
        if (closed) return;
        closed = true;
        try {
          controller.close();
        } catch {
          // The client already went away.
        }
      };
      const write = (chunk: Uint8Array) => {
        if (closed) return;
        try {
          controller.enqueue(chunk);
        } catch {
          closed = true;
        }
      };

      const relay: Relay = {
        push: (author, text) =>
          write(sse(null, { author, text, ts: Date.now() - startedAt })),
        fail: (message) => write(sse("failed", { message, ts: Date.now() - startedAt })),
      };

      write(sse("open", { asset: gcsUri, mock, mute, fault: faults, ts: 0 }));

      try {
        if (mock) {
          await replayFixture(fixtureFor(asset), relay, request.signal);
        } else {
          await relayAgentEngine(messageFor(gcsUri, mute, faults), relay, request.signal);
        }
      } catch (error) {
        relay.fail(error instanceof Error ? error.message : String(error));
      }

      write(sse("done", { elapsed_ms: Date.now() - startedAt }));
      close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
