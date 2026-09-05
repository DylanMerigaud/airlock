import "server-only";

/** A per-caller token bucket for the public run route. One Cloud Run instance keeps its own bucket in
 *  memory (the service runs with few instances and a run holds a stream open for minutes, so the
 *  bucket is per instance by design and stated in RUNS); a restart empties it, which errs on the
 *  side of the judge, not the abuser. */
export const RUN_LIMIT_PER_HOUR = Number(process.env.AIRLOCK_RUN_LIMIT_PER_HOUR || 12);
const WINDOW_MS = 60 * 60 * 1000;

type Bucket = { tokens: number; refilledAt: number };
const buckets = new Map<string, Bucket>();

export function callerKey(request: Request): string {
  const fwd = request.headers.get("x-forwarded-for");
  if (fwd) return fwd.split(",")[0].trim();
  return request.headers.get("x-real-ip") || "unknown";
}

export function takeRunToken(key: string, now = Date.now()): { ok: true } | { ok: false; retryAfterS: number } {
  const bucket = buckets.get(key) ?? { tokens: RUN_LIMIT_PER_HOUR, refilledAt: now };
  const refill = ((now - bucket.refilledAt) / WINDOW_MS) * RUN_LIMIT_PER_HOUR;
  bucket.tokens = Math.min(RUN_LIMIT_PER_HOUR, bucket.tokens + refill);
  bucket.refilledAt = now;
  if (bucket.tokens < 1) {
    buckets.set(key, bucket);
    const retryAfterS = Math.ceil(((1 - bucket.tokens) / RUN_LIMIT_PER_HOUR) * (WINDOW_MS / 1000));
    return { ok: false, retryAfterS };
  }
  bucket.tokens -= 1;
  buckets.set(key, bucket);
  return { ok: true };
}

/** For tests and for a restart: forget every caller. */
export function resetRunLimits(): void {
  buckets.clear();
}
