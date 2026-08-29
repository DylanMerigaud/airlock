export type PresetId = "crest" | "nimbus" | "clean";

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
    gcs: "gs://airlock-agentic-cinema-assets/real/CrestToothpa-18-48.mp4",
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
    gcs: "gs://airlock-agentic-cinema-assets/synthetic/nimbus-test-clip.mp4",
    poster: "/posters/nimbus.jpg",
    expectation:
      "Expected: rights pass, claim block on 16 CFR 255.3, brand pass, provenance pass.",
  },
  {
    id: "clean",
    name: "Nimbus clean clip",
    origin: "synthetic",
    provenance: "Veo 3.1 on Vertex AI, C2PA signed",
    duration: "8 s",
    gcs: "gs://airlock-agentic-cinema-assets/calibration/nimbus-clean-clip.mp4",
    poster: "/posters/clean.jpg",
    expectation:
      "Expected: four PASS and a PASS verdict, every gate healthy and calibrated. The one that should pass.",
  },
];

export function presetById(id: string): PresetAsset | undefined {
  return PRESET_ASSETS.find((a) => a.id === id);
}

export function resolveAsset(input: string): string | null {
  if (input.startsWith("gs://")) return input;
  const preset = presetById(input);
  return preset ? preset.gcs : null;
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
