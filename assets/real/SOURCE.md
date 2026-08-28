# Real inputs

Every file in this folder is a real, named asset. None was fabricated for the demo.

## CrestToothpa.mp4

- Title: Crest Toothpaste Commercial 1 (Prelinger Archives)
- Source: https://archive.org/details/CrestToothpa (file `CrestToothpa.mp4`, 640x480, 60.06 s, h264/aac)
- License: Public Domain (https://creativecommons.org/licenses/publicdomain/), as stated on the item
- Downloaded: 2026-08-28
- sha256: 6b4f9352b4127afaca15d9aab8325c93a147fdaa46e6d74adc76ac576f303903
- C2PA: none. `c2patool assets/real/CrestToothpa.mp4` answers `No claim found`, which is true of a
  film made decades before the C2PA specification existed. The provenance gate blocks on it honestly.
- Why this one: a real trademark (Crest, Procter and Gamble) on screen, and an on-air endorsement
  claim that maps onto 16 CFR 255.3 (expert endorsements) and 255.4 (endorsements by organizations).

The mp4 itself is not committed (see .gitignore); `scripts/fetch_assets.sh` downloads it and checks the hash.
