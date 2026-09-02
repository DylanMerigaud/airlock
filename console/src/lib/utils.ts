import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Seconds since run start, mono formatted: 12.4s */
export function offset(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.round(value)} ms`;
}

/** A wall time in words: 2 ms, 3.4 s, 78 s. One decimal under 10 s, none above. */
export function duration(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 10000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value / 1000)} s`;
}

export function shortSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "never";
  if (value < 90) return `${Math.round(value)} s`;
  if (value < 5400) return `${Math.round(value / 60)} min`;
  if (value < 172800) return `${Math.round(value / 3600)} h`;
  return `${Math.round(value / 86400)} d`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.round(value * 100)} percent`;
}

/** A dollar figure at list price: $0 flat, two decimals normally, three under a cent. */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  if (value === 0) return "$0";
  const decimals = Math.abs(value) < 0.01 ? 3 : 2;
  return `$${value.toFixed(decimals)}`;
}
