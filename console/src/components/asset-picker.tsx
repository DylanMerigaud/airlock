"use client";

import * as React from "react";
import Image from "next/image";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogClose } from "@/components/ui/dialog";
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

function PresetChip({
  asset,
  selected,
  onSelect,
  onPreview,
}: {
  asset: PresetAsset;
  selected: boolean;
  onSelect: () => void;
  onPreview: () => void;
}) {
  return (
    <div
      className={cn(
        "group relative flex items-stretch rounded-[3px] border transition-colors",
        selected ? "border-amber/55 bg-panel-2" : "border-line bg-panel hover:border-[#39404b]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="flex items-center gap-2.5 py-1.5 pl-1.5 pr-2.5 text-left"
      >
        <span className="relative block h-[34px] w-[58px] shrink-0 overflow-hidden rounded-[2px] border border-line-soft bg-void">
          <Image
            src={asset.poster}
            alt=""
            fill
            sizes="58px"
            className={cn("object-cover", selected ? "opacity-100" : "opacity-70")}
          />
          {asset.origin === "synthetic" && (
            <span className="absolute inset-x-0 bottom-0 bg-void/85 px-1 py-[1px] font-mono text-[7px] uppercase leading-[1.3] tracking-[0.06em] text-amber">
              synthetic test asset
            </span>
          )}
        </span>
        <span className="flex min-w-0 flex-col gap-[3px]">
          <span
            className={cn(
              "truncate text-[12.5px] font-medium leading-none",
              selected ? "text-ink" : "text-ink-dim",
            )}
          >
            {asset.name}
          </span>
          <span className="truncate font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-faint">
            {asset.duration}, {asset.origin}
          </span>
        </span>
      </button>
      <button
        type="button"
        onClick={onPreview}
        title={`Preview ${asset.name}`}
        className="flex w-7 items-center justify-center border-l border-line-soft text-ink-faint transition-colors hover:bg-panel-2 hover:text-ink"
      >
        <span className="sr-only">Preview {asset.name}</span>
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path d="M3.5 2.4 9.4 6l-5.9 3.6z" fill="currentColor" />
        </svg>
      </button>
    </div>
  );
}

export function AssetPicker({
  target,
  onSelect,
  disabled,
}: {
  target: string;
  onSelect: (target: string) => void;
  disabled: boolean;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [uploadState, setUploadState] = React.useState<"idle" | "checking" | "uploading">("idle");
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [uploadedName, setUploadedName] = React.useState<string | null>(null);
  const [preview, setPreview] = React.useState<PresetAsset | null>(null);
  const [previewError, setPreviewError] = React.useState<string | null>(null);

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
      setUploadedName(file.name);
      onSelect(payload.gcs_uri);
    } catch (error) {
      setUploadError(
        `The upload did not reach Cloud Storage: ${error instanceof Error ? error.message : "unknown error"}.`,
      );
    } finally {
      setUploadState("idle");
    }
  };

  const uploadSelected = target.startsWith("gs://") && !PRESET_ASSETS.some((a) => a.gcs === target);

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
      <span className="label-micro text-ink-faint" id="asset-picker-label">
        Asset
      </span>
      <div
        role="group"
        aria-labelledby="asset-picker-label"
        className="flex flex-wrap items-center gap-2"
      >
          {PRESET_ASSETS.map((asset) => (
            <PresetChip
              key={asset.id}
              asset={asset}
              selected={target === asset.id}
              onSelect={() => onSelect(asset.id)}
              onPreview={() => {
                setPreviewError(null);
                setPreview(asset);
              }}
            />
          ))}

          <div
            className={cn(
              "flex items-center gap-2 rounded-[3px] border px-2.5 py-2 transition-colors",
              uploadSelected ? "border-amber/55 bg-panel-2" : "border-dashed border-line bg-panel",
            )}
          >
            <input
              ref={inputRef}
              id="clip-upload"
              type="file"
              accept="video/mp4"
              className="sr-only"
              disabled={disabled || uploadState !== "idle"}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void handleFile(file);
              }}
            />
            <label
              htmlFor="clip-upload"
              className={cn(
                "cursor-pointer font-mono text-[10.5px] uppercase tracking-[0.12em]",
                disabled || uploadState !== "idle"
                  ? "cursor-not-allowed text-ink-faint"
                  : "text-ink-dim hover:text-ink",
              )}
            >
              {uploadState === "checking"
                ? "Reading the clip duration"
                : uploadState === "uploading"
                  ? "Uploading to Cloud Storage"
                  : "Upload a clip"}
            </label>
            {uploadSelected && uploadedName && (
              <Badge tone="amber" size="xs" className="max-w-[140px] truncate normal-case">
                {uploadedName}
              </Badge>
            )}
        </div>
      </div>

      {uploadError ? (
        <p role="alert" className="max-w-[52ch] text-[11.5px] leading-[1.5] text-block">
          {uploadError}
        </p>
      ) : (
        <p className="font-mono text-[10px] leading-[1.5] text-ink-faint">
          MP4, 30 s and 50 MB at most
        </p>
      )}

      <Dialog
        open={preview !== null}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
      >
        <DialogContent aria-describedby={undefined}>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <DialogTitle>{preview?.name ?? "Preview"}</DialogTitle>
            <DialogClose asChild>
              <Button variant="ghost" size="sm">
                Close
              </Button>
            </DialogClose>
          </div>
          <div className="px-4 py-4">
            {preview && (
              <>
                <video
                  key={preview.id}
                  src={`/api/asset/${preview.id}`}
                  poster={preview.poster}
                  controls
                  playsInline
                  className="w-full rounded-[3px] border border-line bg-void"
                  onError={() =>
                    setPreviewError(
                      "The clip could not be streamed. The console needs Cloud Storage credentials for the preview; the poster still shows the asset.",
                    )
                  }
                />
                <p className="mt-3 font-mono text-[10.5px] leading-[1.6] text-ink-faint">
                  {preview.gcs}
                </p>
                <p className="mt-1.5 text-[12px] leading-[1.55] text-ink-dim">
                  {preview.provenance}. {preview.expectation}
                </p>
                {previewError && (
                  <p role="alert" className="mt-2 text-[11.5px] leading-[1.5] text-block">
                    {previewError}
                  </p>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
