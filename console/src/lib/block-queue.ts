"use client";

export type BlockEntry = {
  id: string;
  asset: string;
  assetLabel: string;
  motive: string;
  reason: string;
  at: string;
  needsHuman: boolean;
};

const KEY = "airlock.console.block-queue.v1";

export function loadQueue(): BlockEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as BlockEntry[]) : [];
  } catch {
    return [];
  }
}

export function saveQueue(entries: BlockEntry[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(entries.slice(0, 50)));
  } catch {
    // A full or blocked localStorage costs the session history, nothing else.
  }
}
