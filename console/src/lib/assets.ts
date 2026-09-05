export type PresetId = "crest" | "nimbus" | "substantiated" | "clean";

/** The one bucket a run may read: presets, uploads and the calibration set all live there. A gs:// URI
 *  elsewhere is refused, so the public run route cannot be pointed at someone else's object. */
export const ASSETS_BUCKET = process.env.AIRLOCK_ASSETS_BUCKET || "airlock-agentic-cinema-assets";

export type PresetAsset = {
  id: PresetId;
  name: string;
  origin: "real" | "synthetic";
  provenance: string;
  duration: string;
  gcs: string;
  poster: string;
  expectation: string;
};

export const PRESET_ASSETS: PresetAsset[] = [
  {
    id: "crest",
    name: "Crest Toothpaste Commercial",
    origin: "real",
    provenance: "Prelinger Archives, public domain",
    duration: "30 s excerpt",
    gcs: `gs://${ASSETS_BUCKET}/real/CrestToothpa-18-48.mp4`,
    poster: "/posters/crest.jpg",
    expectation:
      "Expected: four blocks. Real trademark not cleared, unsubstantiated claims, off charter, no C2PA manifest.",
  },
  {
    id: "nimbus",
    name: "Nimbus test clip",
    origin: "synthetic",
    provenance: "Veo 3.1 on Vertex AI, C2PA signed",
    duration: "8 s",
    gcs: `gs://${ASSETS_BUCKET}/synthetic/nimbus-test-clip.mp4`,
    poster: "/posters/nimbus.jpg",
    expectation:
      "Expected: rights pass, claim block on 16 CFR 255.3, brand pass, provenance pass.",
  },
  {
    id: "substantiated",
    name: "Nimbus test clip, study on file",
    origin: "synthetic",
    provenance: "Veo 3.1 on Vertex AI, C2PA signed; a substantiation file beside it",
    duration: "8 s",
    gcs: `gs://${ASSETS_BUCKET}/synthetic/nimbus-test-clip-substantiated.mp4`,
    poster: "/posters/nimbus.jpg",
    expectation:
      "Expected: the same clip as the test clip, with the sommelier study on file beside it in the bucket: claim PASS naming the study.",
  },
  {
    id: "clean",
    name: "Nimbus clean clip",
    origin: "synthetic",
    provenance: "Veo 3.1 on Vertex AI, C2PA signed",
    duration: "8 s",
    gcs: `gs://${ASSETS_BUCKET}/calibration/nimbus-clean-clip.mp4`,
    poster: "/posters/clean.jpg",
    expectation:
      "Expected: four PASS and a PASS verdict, every gate healthy and calibrated. The one that should pass.",
  },
];

export function presetById(id: string): PresetAsset | undefined {
  return PRESET_ASSETS.find((a) => a.id === id);
}

function inAssetsBucket(uri: string): boolean {
  return uri.startsWith(`gs://${ASSETS_BUCKET}/`) && !uri.includes("..");
}

export function resolveAsset(input: string): string | null {
  const uri = input.startsWith("gs://") ? input : presetById(input)?.gcs;
  return uri && inAssetsBucket(uri) ? uri : null;
}

/** The name the pipeline uses for an asset: the object name without its suffix. */
export function assetIdFor(gcsUri: string): string {
  const tail = gcsUri.split("/").pop() ?? gcsUri;
  return tail.replace(/\.[^.]+$/, "");
}

export function labelForTarget(target: string): string {
  const preset = presetById(target);
  if (preset) return preset.name;
  if (target.startsWith("gs://")) {
    const tail = target.split("/").pop() ?? target;
    return tail;
  }
  return target;
}
