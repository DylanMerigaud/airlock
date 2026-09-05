import "server-only";

/**
 * The duration of an MP4 read from its movie header (the `mvhd` box inside `moov`), in seconds, or
 * null when the file carries none (a fragmented or truncated file). The browser refuses a clip over
 * 30 s before uploading; this is the same rule read on the server from the bytes, so a caller who skips
 * the browser cannot hand the pipeline an hour of video at Video Intelligence prices.
 */
export function mp4DurationSeconds(bytes: Buffer): number | null {
  const found = findBox(bytes, 0, bytes.length, "moov");
  if (!found) return null;
  const mvhd = findBox(bytes, found.start, found.end, "mvhd");
  if (!mvhd) return null;
  const version = bytes[mvhd.start];
  if (version === 1) {
    if (mvhd.end - mvhd.start < 32) return null;
    const timescale = bytes.readUInt32BE(mvhd.start + 20);
    const duration = Number(bytes.readBigUInt64BE(mvhd.start + 24));
    return timescale ? duration / timescale : null;
  }
  if (mvhd.end - mvhd.start < 20) return null;
  const timescale = bytes.readUInt32BE(mvhd.start + 12);
  const duration = bytes.readUInt32BE(mvhd.start + 16);
  return timescale ? duration / timescale : null;
}

/** Scans the boxes between `from` and `to` for one of `type`; returns the payload bounds (after the header). */
function findBox(bytes: Buffer, from: number, to: number, type: string): { start: number; end: number } | null {
  let offset = from;
  while (offset + 8 <= to) {
    let size = bytes.readUInt32BE(offset);
    const boxType = bytes.toString("latin1", offset + 4, offset + 8);
    let header = 8;
    if (size === 1) {
      if (offset + 16 > to) return null;
      size = Number(bytes.readBigUInt64BE(offset + 8));
      header = 16;
    } else if (size === 0) {
      size = to - offset;
    }
    if (size < header) return null;
    if (boxType === type) return { start: offset + header, end: Math.min(offset + size, to) };
    offset += size;
  }
  return null;
}
