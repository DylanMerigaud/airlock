#!/usr/bin/env bash
# Downloads the real demo asset and verifies its hash against assets/real/SOURCE.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/assets/real"
curl -sL "https://archive.org/download/CrestToothpa/CrestToothpa.mp4" -o "$ROOT/assets/real/CrestToothpa.mp4"
echo "6b4f9352b4127afaca15d9aab8325c93a147fdaa46e6d74adc76ac576f303903  $ROOT/assets/real/CrestToothpa.mp4" | shasum -a 256 -c -
