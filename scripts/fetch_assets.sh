#!/usr/bin/env bash
# Downloads every demo and eval asset and verifies its hash.
#   real: Prelinger commercials from archive.org (public domain); the full film is downloaded, then the
#         excerpt is cut locally with ffmpeg (stream copy, no re-encode). CrestToothpa is the demo asset
#         (assets/real/SOURCE.md); the ten under assets/real/eval/ are the evaluation set
#         (assets/real/eval/SOURCE.md, run by scripts/eval_gates.py).
#   synthetic: the labelled clips from the GitHub release assets-2026-08-28 (see SYNTHETIC.md)
# Nothing under assets/ is committed (.gitignore: assets/real/**/*.mp4, assets/synthetic/**/*.mp4);
# this script is how a judge gets the same bytes. Re-running it is idempotent: a file that exists is
# not fetched or cut again.
#
# The excerpt hashes were recorded with ffmpeg 8.0 (2026-08-28 and 2026-08-29, the same cut command);
# a different ffmpeg can write a different container header for the same frames, in which case the
# eval excerpts fail the sha256 check below while still being the same 30 seconds. Say so in
# assets/real/eval/SOURCE.md rather than treating them as corrupt.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REL="https://github.com/DylanMerigaud/airlock/releases/download/assets-2026-08-28"
EVAL="$ROOT/assets/real/eval"
mkdir -p "$ROOT/assets/real" "$EVAL/src" "$ROOT/assets/synthetic/calibration"

fetch() { [[ -f "$2" ]] || curl -sL "$1" -o "$2"; }
# cut <source> <start_s> <length_s> <out>: -ss before -i seeks the input, -c copy keeps the streams as they are
cut() { [[ -f "$4" ]] || ffmpeg -v error -y -ss "$2" -t "$3" -i "$1" -c copy "$4"; }

# The demo asset (assets/real/SOURCE.md)
fetch "https://archive.org/download/CrestToothpa/CrestToothpa.mp4" "$ROOT/assets/real/CrestToothpa.mp4"
cut "$ROOT/assets/real/CrestToothpa.mp4" 18 30 "$ROOT/assets/real/CrestToothpa-18-48.mp4"

# The eval set (assets/real/eval/SOURCE.md): archive.org identifier, start second, excerpt name.
# Every excerpt is 30 s from the start second; on labatts_beer (20.59 s) and MacleansToot (29.5 s)
# the source is shorter than 30 s and the cut runs to the end.
while read -r id start name; do
  fetch "https://archive.org/download/$id/$id.mp4" "$EVAL/src/$id.mp4"
  cut "$EVAL/src/$id.mp4" "$start" 30 "$EVAL/$name.mp4"
done <<'CUTS'
Cheerios1960 0 Cheerios1960-0-30
chevrolet 31 chevrolet-31-61
ivory_soap 25 ivory_soap-25-55
kodak_instamatic 31 kodak_instamatic-31-60
folgers 26 folgers-26-56
labatts_beer 0 labatts_beer-0-20
gilbert_slot_racers 0 gilbert_slot_racers-0-30
MacleansToot 0 MacleansToot-0-29
ScottiesTiss 0 ScottiesTiss-0-30
GE_blender 0 GE_blender-0-30
CUTS

# The synthetic assets (SYNTHETIC.md)
fetch "$REL/nimbus-test-clip.mp4" "$ROOT/assets/synthetic/nimbus-test-clip.mp4"
fetch "$REL/veo-raw.mp4" "$ROOT/assets/synthetic/veo-raw.mp4"
for f in nimbus-clean-clip nimbus-defect-brand-red nimbus-defect-provenance-stripped nimbus-defect-provenance-broken; do
  fetch "$REL/$f.mp4" "$ROOT/assets/synthetic/calibration/$f.mp4"
done

cd "$ROOT" && shasum -a 256 -c - <<'SUMS'
6b4f9352b4127afaca15d9aab8325c93a147fdaa46e6d74adc76ac576f303903  assets/real/CrestToothpa.mp4
97ccbcdc8316277909b25591b79a5a307c463089e6558ed1a14ddd2f0114edd4  assets/real/CrestToothpa-18-48.mp4
f2ec973ae8267248fb37f3c0a8187d437af9984e410a35a39c94656dd66151a5  assets/real/eval/Cheerios1960-0-30.mp4
61ac27bd121b844873b558d93fdd3fbee926696eaba36d926ff84d6315ebf972  assets/real/eval/chevrolet-31-61.mp4
506ba0e184a31f61904e0161a40b5fcd056095b89397295302cd650ed0395f49  assets/real/eval/ivory_soap-25-55.mp4
dea96bbcab247712e51e7d1d905be01437a383bc9dff330e2ce72639f57f817f  assets/real/eval/kodak_instamatic-31-60.mp4
c6b7e6d90faa33d01079e5ac79fd943e338202ab9029ef9d47e4d484b12a3f9f  assets/real/eval/folgers-26-56.mp4
7cd92971774eecc698afdb3dd12128cbf966531f0166f680aa7adebdb59e38f9  assets/real/eval/labatts_beer-0-20.mp4
8eaffb36f71a06c37231010e19515ea8af9b27dcb9427156c445eb5c105ef542  assets/real/eval/gilbert_slot_racers-0-30.mp4
3cbaa5c577eb47663a724aebfb629bef5bcb018cc741a4c10026c6ceba7fe07c  assets/real/eval/MacleansToot-0-29.mp4
68308f685676f0f02800d6fe19a463d3e0a134dbabc8cba8764021c0f2a02008  assets/real/eval/ScottiesTiss-0-30.mp4
018d8000b5ec93b0bc7568cbced49073bf3f61d54702b539edc978821df04c6a  assets/real/eval/GE_blender-0-30.mp4
cf5e05c2665181b92f81ac3c80a02ed99b85e066d4fd72a7ef4f3b54e5efe343  assets/synthetic/nimbus-test-clip.mp4
a6667d0f35851828cc9dad4813394a3df4f99bed7fef4fe97b394616ae6c5f6f  assets/synthetic/veo-raw.mp4
89dcb1549e9d8d95d0b9f5c6c99917b7d3c1430c999ede7af67076dfc5a7b732  assets/synthetic/calibration/nimbus-clean-clip.mp4
1fe1669e96283f80dc1500c850fdd4044790ca777046684ce7aaebfd6716975d  assets/synthetic/calibration/nimbus-defect-brand-red.mp4
1d2e45090802ccbd1f2bd2832898807c24150d8324a84e799791fa266f3d905d  assets/synthetic/calibration/nimbus-defect-provenance-stripped.mp4
42a4d31850d07f8671ce415ac52c01edbb7112bf1a819940a8954e30364306b5  assets/synthetic/calibration/nimbus-defect-provenance-broken.mp4
SUMS
