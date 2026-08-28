import { NextResponse } from "next/server";
import { createHash } from "node:crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const MAX_BYTES = 50 * 1024 * 1024;

export async function POST(request: Request) {
  const bucketName = process.env.AIRLOCK_ASSETS_BUCKET;
  if (!bucketName) {
    return NextResponse.json(
      { error: "AIRLOCK_ASSETS_BUCKET is not set, so the console has nowhere to put the clip." },
      { status: 503 },
    );
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Send the clip as multipart form data." }, { status: 400 });
  }

  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file field in the upload." }, { status: 400 });
  }
  if (file.type && file.type !== "video/mp4") {
    return NextResponse.json(
      { error: `Airlock reads MP4 video. This file is ${file.type}.` },
      { status: 415 },
    );
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json(
      {
        error: `This clip is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 50 MB.`,
      },
      { status: 413 },
    );
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const digest = createHash("sha256").update(bytes).digest("hex").slice(0, 12);
  const safeName = (file.name || "clip.mp4").replace(/[^a-zA-Z0-9._-]/g, "-").slice(-80);
  const objectPath = `uploads/${digest}-${safeName}`;

  try {
    const { Storage } = await import("@google-cloud/storage");
    const storage = new Storage({ projectId: process.env.GOOGLE_CLOUD_PROJECT });
    await storage.bucket(bucketName).file(objectPath).save(bytes, {
      contentType: "video/mp4",
      resumable: false,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: `Cloud Storage refused the upload: ${message}` }, { status: 502 });
  }

  return NextResponse.json({ gcs_uri: `gs://${bucketName}/${objectPath}` });
}
