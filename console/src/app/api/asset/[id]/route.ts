import { NextResponse } from "next/server";
import { Readable } from "node:stream";
import { presetById } from "@/lib/assets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Streams a preloaded clip out of Cloud Storage with the server credentials. */
export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const preset = presetById(id);
  if (!preset) {
    return NextResponse.json({ error: `No preloaded asset called "${id}".` }, { status: 404 });
  }
  if (process.env.AIRLOCK_MOCK === "1") {
    return NextResponse.json(
      { error: "Mock mode has no Cloud Storage credentials, so the preview is unavailable." },
      { status: 503 },
    );
  }

  const match = /^gs:\/\/([^/]+)\/(.+)$/.exec(preset.gcs);
  if (!match) {
    return NextResponse.json({ error: "The asset URI is malformed." }, { status: 500 });
  }
  const [, bucketName, objectPath] = match;

  try {
    const { Storage } = await import("@google-cloud/storage");
    const storage = new Storage({ projectId: process.env.GOOGLE_CLOUD_PROJECT });
    const file = storage.bucket(bucketName).file(objectPath);
    const [metadata] = await file.getMetadata();
    const size = Number(metadata.size ?? 0);

    const range = request.headers.get("range");
    const parsed = range ? /bytes=(\d*)-(\d*)/.exec(range) : null;

    if (parsed && size > 0) {
      const start = parsed[1] ? Number(parsed[1]) : 0;
      const end = parsed[2] ? Number(parsed[2]) : size - 1;
      const nodeStream = file.createReadStream({ start, end });
      return new Response(Readable.toWeb(nodeStream) as ReadableStream, {
        status: 206,
        headers: {
          "Content-Type": "video/mp4",
          "Content-Length": String(end - start + 1),
          "Content-Range": `bytes ${start}-${end}/${size}`,
          "Accept-Ranges": "bytes",
          "Cache-Control": "private, max-age=300",
        },
      });
    }

    const nodeStream = file.createReadStream();
    return new Response(Readable.toWeb(nodeStream) as ReadableStream, {
      headers: {
        "Content-Type": "video/mp4",
        ...(size ? { "Content-Length": String(size) } : {}),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: `Cloud Storage refused the read: ${message}` }, { status: 502 });
  }
}
