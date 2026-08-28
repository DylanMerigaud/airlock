import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { resolveAsset } from "@/lib/assets";

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

/** Mock mode: replay the recorded run, one line at a time, with real pauses. */
async function replayFixture(relay: Relay, signal: AbortSignal) {
  const file = path.join(process.cwd(), "fixtures", "run-nimbus-instrument-error.jsonl");
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

/** Live mode: Vertex AI Agent Engine streamQuery, relayed event by event. */
async function relayAgentEngine(gcsUri: string, relay: Relay, signal: AbortSignal) {
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
          message: gcsUri,
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
  try {
    const body = (await request.json()) as { asset?: string };
    asset = String(body.asset ?? "");
  } catch {
    return NextResponse.json({ error: "Send a JSON body with an asset field." }, { status: 400 });
  }

  const gcsUri = resolveAsset(asset);
  if (!gcsUri) {
    return NextResponse.json(
      { error: `Unknown asset "${asset}". Use crest, nimbus, or a gs:// URI.` },
      { status: 400 },
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

      write(sse("open", { asset: gcsUri, mock, ts: 0 }));

      try {
        if (mock) {
          await replayFixture(relay, request.signal);
        } else {
          await relayAgentEngine(gcsUri, relay, request.signal);
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
