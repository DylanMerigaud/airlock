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
