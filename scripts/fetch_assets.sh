#!/usr/bin/env bash
# Downloads every demo asset and verifies its hash.
#   real: the Prelinger commercial from archive.org (public domain), then the 30 s excerpt is cut locally
#   synthetic: the labelled clips from the GitHub release assets-2026-08-28 (see SYNTHETIC.md)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REL="https://github.com/DylanMerigaud/airlock/releases/download/assets-2026-08-28"
mkdir -p "$ROOT/assets/real" "$ROOT/assets/synthetic/calibration"

fetch() { [[ -f "$2" ]] || curl -sL "$1" -o "$2"; }

fetch "https://archive.org/download/CrestToothpa/CrestToothpa.mp4" "$ROOT/assets/real/CrestToothpa.mp4"
[[ -f "$ROOT/assets/real/CrestToothpa-18-48.mp4" ]] || ffmpeg -v error -y -ss 18 -t 30 -i "$ROOT/assets/real/CrestToothpa.mp4" -c copy "$ROOT/assets/real/CrestToothpa-18-48.mp4"

fetch "$REL/nimbus-test-clip.mp4" "$ROOT/assets/synthetic/nimbus-test-clip.mp4"
fetch "$REL/veo-raw.mp4" "$ROOT/assets/synthetic/veo-raw.mp4"
for f in nimbus-clean-clip nimbus-defect-brand-red nimbus-defect-provenance-stripped nimbus-defect-provenance-broken; do
  fetch "$REL/$f.mp4" "$ROOT/assets/synthetic/calibration/$f.mp4"
done

cd "$ROOT" && shasum -a 256 -c - <<'SUMS'
6b4f9352b4127afaca15d9aab8325c93a147fdaa46e6d74adc76ac576f303903  assets/real/CrestToothpa.mp4
97ccbcdc8316277909b25591b79a5a307c463089e6558ed1a14ddd2f0114edd4  assets/real/CrestToothpa-18-48.mp4
cf5e05c2665181b92f81ac3c80a02ed99b85e066d4fd72a7ef4f3b54e5efe343  assets/synthetic/nimbus-test-clip.mp4
a6667d0f35851828cc9dad4813394a3df4f99bed7fef4fe97b394616ae6c5f6f  assets/synthetic/veo-raw.mp4
89dcb1549e9d8d95d0b9f5c6c99917b7d3c1430c999ede7af67076dfc5a7b732  assets/synthetic/calibration/nimbus-clean-clip.mp4
1fe1669e96283f80dc1500c850fdd4044790ca777046684ce7aaebfd6716975d  assets/synthetic/calibration/nimbus-defect-brand-red.mp4
1d2e45090802ccbd1f2bd2832898807c24150d8324a84e799791fa266f3d905d  assets/synthetic/calibration/nimbus-defect-provenance-stripped.mp4
42a4d31850d07f8671ce415ac52c01edbb7112bf1a819940a8954e30364306b5  assets/synthetic/calibration/nimbus-defect-provenance-broken.mp4
SUMS
