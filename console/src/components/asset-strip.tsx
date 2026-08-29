"use client";

import * as React from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { PRESET_ASSETS, type PresetAsset } from "@/lib/assets";

const MAX_BYTES = 50 * 1024 * 1024;
const MAX_SECONDS = 30;

function readDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(video.duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("the browser could not read this file as video"));
    };
    video.src = url;
  });
}

function PresetCard({
  asset,
  selected,
  onSelect,
  disabled,
}: {
  asset: PresetAsset;
  selected: boolean;
  onSelect: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      disabled={disabled}
      className={cn(
        "flex min-w-0 flex-1 items-center gap-2.5 rounded-[4px] border p-1.5 text-left transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        selected
          ? "border-ember bg-ember-wash"
          : "border-line bg-card hover:border-ink-soft hover:bg-card-sunk",
      )}
    >
      <span className="relative block h-[42px] w-[74px] shrink-0 overflow-hidden rounded-[2px] border border-line bg-[#171510]">
        <Image
          src={asset.poster}
          alt=""
          fill
          sizes="74px"
          className={cn("object-cover", selected ? "opacity-100" : "opacity-85")}
        />
        {asset.origin === "synthetic" && (
          <span className="absolute inset-x-0 bottom-0 bg-[#171510]/85 px-1 py-[1px] text-center font-mono text-[7px] uppercase leading-[1.3] tracking-[0.06em] text-[#f3e4d4]">
            synthetic
          </span>
        )}
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span
          className={cn(
            "truncate text-[12.5px] font-medium leading-tight",
            selected ? "text-ink" : "text-ink-mid",
          )}
        >
          {asset.name}
        </span>
        <span className="truncate font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-soft">
          {asset.duration}, {asset.origin}
        </span>
      </span>
    </button>
  );
}

export function AssetStrip({
  target,
  onSelect,
  disabled,
}: {
  target: string;
  onSelect: (target: string, upload?: { name: string; objectUrl: string }) => void;
  disabled: boolean;
}) {
  const [uploadState, setUploadState] = React.useState<"idle" | "checking" | "uploading">("idle");
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [uploadedName, setUploadedName] = React.useState<string | null>(null);
  const objectUrl = React.useRef<string | null>(null);

  const handleFile = async (file: File) => {
    setUploadError(null);
    if (file.type && file.type !== "video/mp4") {
      setUploadError(`Airlock reads MP4 video. This file is ${file.type || "of an unknown type"}.`);
      return;
    }
    if (file.size > MAX_BYTES) {
      setUploadError(`This clip is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 50 MB.`);
      return;
    }

    setUploadState("checking");
    let duration: number;
    try {
      duration = await readDuration(file);
    } catch (error) {
      setUploadState("idle");
      setUploadError(
        `Rejected: ${error instanceof Error ? error.message : "the file could not be read"}.`,
      );
      return;
    }
    if (Number.isFinite(duration) && duration > MAX_SECONDS) {
      setUploadState("idle");
      setUploadError(`This clip runs ${duration.toFixed(1)} s. The limit is 30 s.`);
      return;
    }

    setUploadState("uploading");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/upload", { method: "POST", body: form });
      const payload = (await response.json()) as { gcs_uri?: string; error?: string };
      if (!response.ok || !payload.gcs_uri) {
        setUploadError(payload.error ?? `The upload route answered ${response.status}.`);
        setUploadState("idle");
        return;
      }
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = URL.createObjectURL(file);
      setUploadedName(file.name);
      onSelect(payload.gcs_uri, { name: file.name, objectUrl: objectUrl.current });
    } catch (error) {
      setUploadError(
        `The upload did not reach Cloud Storage: ${error instanceof Error ? error.message : "unknown error"}.`,
      );
    } finally {
      setUploadState("idle");
    }
  };

  const uploadSelected = target.startsWith("gs://") && !PRESET_ASSETS.some((a) => a.gcs === target);
  const busy = uploadState !== "idle";

  return (
    <section aria-labelledby="asset-strip-heading" className="mt-3">
      <h2 id="asset-strip-heading" className="label-micro text-ink-soft">
        Clip under review
      </h2>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-stretch">
        {PRESET_ASSETS.map((asset) => (
          <PresetCard
            key={asset.id}
            asset={asset}
            selected={target === asset.id}
            onSelect={() => onSelect(asset.id)}
            disabled={disabled}
          />
        ))}

        <div
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2.5 rounded-[4px] border border-dashed p-1.5 transition-colors",
            uploadSelected ? "border-ember bg-ember-wash" : "border-line bg-card",
          )}
        >
          <input
            id="clip-upload"
            type="file"
            accept="video/mp4"
            className="sr-only"
            disabled={disabled || busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void handleFile(file);
            }}
          />
          <label
            htmlFor="clip-upload"
            className={cn(
              "flex min-w-0 flex-col gap-1",
              disabled || busy ? "cursor-not-allowed" : "cursor-pointer",
            )}
          >
            <span
              className={cn(
                "text-[12.5px] font-medium leading-tight",
                disabled || busy ? "text-ink-soft" : "text-ink-mid",
              )}
            >
              {uploadState === "checking"
                ? "Reading the clip duration"
                : uploadState === "uploading"
                  ? "Uploading to Cloud Storage"
                  : uploadSelected && uploadedName
                    ? uploadedName
                    : "Upload a clip"}
            </span>
            <span className="truncate font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-soft">
              MP4, 30 s and 50 MB at most
            </span>
          </label>
        </div>
      </div>

      {uploadError && (
        <p role="alert" className="mt-2 text-[12px] leading-[1.5] text-block">
          {uploadError}
        </p>
      )}
    </section>
  );
}
