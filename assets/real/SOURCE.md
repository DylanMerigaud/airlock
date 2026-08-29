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

## CrestToothpa-18-48.mp4 (the demo asset)

- The same film, seconds 18 to 48, cut with `ffmpeg -ss 18 -t 30 -c copy` (stream copy, no re-encode),
  because the Video Intelligence API takes about 4 minutes on the full 60 s and about 1 minute on
  30 s (measured 2026-08-28), and the demo video is one take of 180 s.
- The excerpt holds the brand on screen, the 21 percent testimonial, the "more dentists recommend"
  line and the American Dental Association seal.
- sha256: 97ccbcdc8316277909b25591b79a5a307c463089e6558ed1a14ddd2f0114edd4

## CrestToothpa-33-48.mp4 (the video's asset)

- The same film, seconds 33 to 48, cut with `ffmpeg -ss 33 -t 15 -c copy` (stream copy): the
  "more dentists recommend" line, the Crest box on screen, the American Dental Association seal.
  Cut to test whether a shorter input makes the rights gate faster. Measured 2026-08-29: rights 47 s
  on 15 s against 43 to 72 s on 30 s; the Video Intelligence API has a fixed cost of 30 to 45 s
  whatever the length, so the 30 s excerpt stays the demo asset. Kept for the record.
- sha256: ccd690bdc933ed4f67faffdebbb327302be87c0ae576a10b11344697c8ad5f1e
