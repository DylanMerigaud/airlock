#!/usr/bin/env bash
# Builds the synthetic test asset from the raw Veo clip: text overlays, then a C2PA manifest signed
# with a self-issued test certificate. Everything it produces is listed in SYNTHETIC.md.
#   scripts/make_synthetic_asset.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYN="$ROOT/assets/synthetic"
RAW="$SYN/veo-raw.mp4"
OVERLAID="$SYN/nimbus-test-clip-unsigned.mp4"
SIGNED="$SYN/nimbus-test-clip.mp4"
SIGNER="$SYN/signer"
FONT="${AIRLOCK_FONT:-/System/Library/Fonts/Supplemental/Arial Bold.ttf}"
[[ -f "$RAW" ]] || { echo "missing $RAW: run scripts/generate_synthetic_clip.py and download the clip" >&2; exit 1; }
[[ -f "$FONT" ]] || { echo "missing font $FONT (set AIRLOCK_FONT)" >&2; exit 1; }

# 1. Overlays: wordmark (charter primary blue on a white box), tagline, and the claim from 3 s on.
ffmpeg -v error -y -i "$RAW" -vf "\
drawbox=x=60:y=ih-230:w=560:h=170:color=white@0.85:t=fill,\
drawtext=fontfile='$FONT':text='Nimbus':fontcolor=0x1F4E79:fontsize=64:x=90:y=ih-210,\
drawtext=fontfile='$FONT':text='Clear as morning.':fontcolor=0x1F4E79:fontsize=30:x=92:y=ih-130,\
drawtext=fontfile='$FONT':text='Recommended by 9 out of 10 sommeliers.':fontcolor=white:fontsize=40:box=1:boxcolor=0x1F4E79@0.9:boxborderw=18:x=(w-text_w)/2:y=80:enable='gte(t,3)'" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -an "$OVERLAID"

# 2. Self-issued test signing certificate (ES256, emailProtection EKU as C2PA expects), never committed.
mkdir -p "$SIGNER"
if [[ ! -f "$SIGNER/key.pem" ]]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -sha256 -days 400 \
    -keyout "$SIGNER/key.pem" -out "$SIGNER/cert.pem" \
    -subj "/CN=Airlock self-issued test signer/O=Airlock (hackathon test)/C=US" \
    -addext "keyUsage=digitalSignature" -addext "extendedKeyUsage=emailProtection" -addext "basicConstraints=CA:FALSE" 2>/dev/null
fi

# 3. Manifest: created by a trained algorithmic model (Veo), then edited (overlay). Signed by the test cert.
cat > "$SIGNER/manifest.json" <<JSON
{
  "alg": "es256",
  "private_key": "$SIGNER/key.pem",
  "sign_cert": "$SIGNER/cert.pem",
  "claim_generator_info": [{"name": "airlock-synthetic-asset", "version": "0.1.0"}],
  "title": "Nimbus test clip (synthetic, labelled)",
  "assertions": [
    {"label": "c2pa.actions", "data": {"actions": [
      {"action": "c2pa.created", "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia", "softwareAgent": {"name": "Veo 3.1 on Vertex AI", "version": "veo-3.1-generate-001"}},
      {"action": "c2pa.edited", "softwareAgent": {"name": "ffmpeg drawtext overlay"}}
    ]}}
  ]
}
JSON
rm -f "$SIGNED"
c2patool "$OVERLAID" -m "$SIGNER/manifest.json" -o "$SIGNED" >/dev/null
echo "signed: $SIGNED"
c2patool "$SIGNED" | head -40
shasum -a 256 "$SIGNED"
