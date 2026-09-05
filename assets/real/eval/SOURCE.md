# Real inputs, eval set

Ten more Prelinger Archives commercials, public domain, none of them CrestToothpa (the demo asset
in `assets/real/SOURCE.md`). Selected from the archive.org advanced search used by the task:

```
https://archive.org/advancedsearch.php?q=collection%3Aprelinger+AND+mediatype%3Amovies+AND+(title%3Acommercial+OR+subject%3Acommercials)&fl[]=identifier&fl[]=title&fl[]=licenseurl&rows=100&output=json
```

Each row: title, archive.org URL, licence as stated on the item, the excerpt cut with
`ffmpeg -ss <start> -t 30 -c copy` (stream copy, no re-encode), its sha256, and the brand the rights
gate is expected to find. None of these brands are in `rights-registry.yaml`, so every one of them
is ground truth for BLOCK on rights (unknown brand) and BLOCK on provenance (no C2PA manifest: a
1950s to 1960s film predates the C2PA specification, same as CrestToothpa). The claim and brand
gates have no ground truth beyond "a mid-century commercial makes claims"; what they find on these
ten is reported in `eval/EVAL.md` without being scored.

Nothing under `assets/` is committed (`.gitignore`: `assets/real/**/*.mp4`). `scripts/fetch_assets.sh`
downloads the ten full source files (640x480, as archive.org serves them) into `assets/real/eval/src/`,
cuts the excerpts with the command above and checks every sha256 against the values below; the
hashes were recorded with ffmpeg 8.0, and a different ffmpeg build can write a different container
header for the same frames (then record the new hash here and say which build produced it).
Verified from an empty `assets/` on 2026-09-04 (18 files OK, about 4 minutes) and again on 2026-09-05
(18 files OK).

## Cheerios1960-0-30.mp4

- Title: Cheerios/V-8 (Prelinger Archives)
- Source: https://archive.org/details/Cheerios1960 (file `Cheerios1960.mp4`, 640x480, 60.93 s, h264/aac)
- License: Public Domain (http://creativecommons.org/licenses/publicdomain/), as stated on the item
- Excerpt: seconds 0 to 30
- sha256: f2ec973ae8267248fb37f3c0a8187d437af9984e410a35a39c94656dd66151a5
- Expected brand: Cheerios (General Mills). A boy and a girl hold up a Cheerios box and a V-8 can
  to the camera at 5 s and again close up at 20 s; a "FREE OFFER for a Cheerios boxtop" title card
  follows at 25 s.

## chevrolet-31-61.mp4

- Title: Chevrolet Commercial (Prelinger Archives)
- Source: https://archive.org/details/chevrolet (file `chevrolet.mp4`, 640x480, 61.06 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 31 to 61 (the last 30 s of the spot)
- sha256: 61ac27bd121b844873b558d93fdd3fbee926696eaba36d926ff84d6315ebf972
- Expected brand: Chevrolet. A Saul Bass style line-drawing ad; the wordmark "CHEVROLET" is spelled
  out over a repeating pattern of model names (Chevy II, Corvair, Corvette, Chevrolet) from about
  50 s to the end.

## ivory_soap-25-55.mp4

- Title: Ivory Soap Commercial (Prelinger Archives)
- Source: https://archive.org/details/ivory_soap (file `ivory_soap.mp4`, 640x480, 60.05 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 25 to 55
- sha256: 506ba0e184a31f61904e0161a40b5fcd056095b89397295302cd650ed0395f49
- Expected brand: Ivory (Procter and Gamble). A close-up bar of soap with "IVORY" printed on the
  wrapper at about 40 s, then a mother bathing a baby.

## kodak_instamatic-31-60.mp4

- Title: Kodak Instamatic Commercial (Prelinger Archives)
- Source: https://archive.org/details/kodak_instamatic (file `kodak_instamatic.mp4`, 640x480, 60.06 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 31 to 60 (29.06 s; the source is 60.06 s, so 31 plus 30 runs past the end)
- sha256: dea96bbcab247712e51e7d1d905be01437a383bc9dff330e2ce72639f57f817f
- Expected brand: Kodak. Hands operate an Instamatic camera at a party through the middle of the
  spot; the closing shot is the yellow "Instamatic" box with the camera and prints, "Less than $18,
  see your dealer."

## folgers-26-56.mp4

- Title: Folgers Coffee Commercial (Prelinger Archives)
- Source: https://archive.org/details/folgers (file `folgers.mp4`, 640x480, 60.53 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 26 to 56
- sha256: c6b7e6d90faa33d01079e5ac79fd943e338202ab9029ef9d47e4d484b12a3f9f
- Expected brand: Folgers. Mrs. Olson hands over a can labelled "coffee ... Mountain Grown, One
  pound net" at about 30 s; the can's full "MOUNTAIN GROWN Folgers coffee" label fills the frame at
  the end.

## labatts_beer-0-20.mp4

- Title: Labatts Beer Commercial (Prelinger Archives)
- Source: https://archive.org/details/labatts_beer (file `labatts_beer.mp4`, 640x480, 20.59 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: the full clip, seconds 0 to 20.59 (the source itself is only 20.59 s, shorter than the
  30 s the other nine excerpts use; `-ss 0 -t 30` on a 20.59 s source stream-copies to the end
  without error, which is what the excerpt is)
- sha256: 7cd92971774eecc698afdb3dd12128cbf966531f0166f680aa7adebdb59e38f9
- Expected brand: Labatt's. A couple at a restaurant table pours and drinks from bottles bearing
  the Labatt's label throughout the spot.

## gilbert_slot_racers-0-30.mp4

- Title: Gilbert Slot Car Racers Commercial (Prelinger Archives)
- Source: https://archive.org/details/gilbert_slot_racers (file `gilbert_slot_racers.mp4`, 640x480, 61.76 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 0 to 30
- sha256: 8eaffb36f71a06c37231010e19515ea8af9b27dcb9427156c445eb5c105ef542
- Expected brand: Gilbert (A.C. Gilbert Company). The "GILBERT" wordmark in a circle overlays the
  slot car track at 5 s, then boys racing the set through the rest of the excerpt.

## MacleansToot-0-29.mp4

- Title: Macleans Toothpaste Commercial (Prelinger Archives)
- Source: https://archive.org/details/MacleansToot (file `MacleansToot.mp4`, 640x480, 29.5 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: the full clip, seconds 0 to 29.5 (the source is 29.5 s, under 30 s, so `-ss 0 -t 30`
  stream-copies the whole thing)
- sha256: 3cbaa5c577eb47663a724aebfb629bef5bcb018cc741a4c10026c6ceba7fe07c
- Expected brand: Macleans (a toothpaste other than Crest). Two skiers in the snow, then a tube of
  "Macleans TOOTH PASTE" fills the frame twice, at about 15 s and again at the very end.

## ScottiesTiss-0-30.mp4

- Title: Scotties Tissue Commercial (Prelinger Archives)
- Source: https://archive.org/details/ScottiesTiss (file `ScottiesTiss.mp4`, 640x480, 60.55 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 0 to 30
- sha256: 68308f685676f0f02800d6fe19a463d3e0a134dbabc8cba8764021c0f2a02008
- Expected brand: Scotties. A tissue box with the oval "Scotties" logo is on screen through nearly
  the whole excerpt (a tissue pulled from the box at 0 s, the box shown face on at 10 s).

## GE_blender-0-30.mp4

- Title: GE Blender Commercial (Prelinger Archives)
- Source: https://archive.org/details/GE_blender (file `GE_blender.mp4`, 640x480, 72.07 s, h264/aac)
- License: Public Domain, as stated on the item
- Excerpt: seconds 0 to 30
- sha256: 018d8000b5ec93b0bc7568cbced49073bf3f61d54702b539edc978821df04c6a
- Expected brand: General Electric (GE). The cursive "General Electric" script logo opens the spot
  at 5 s; "GENERAL ELECTRIC" is printed on the blender's base at 25 s.

## Ground truth summary

| identifier | expected brand | rights | provenance |
|---|---|---|---|
| Cheerios1960-0-30 | Cheerios | BLOCK, unknown brand | BLOCK, no manifest |
| chevrolet-31-61 | Chevrolet | BLOCK, unknown brand | BLOCK, no manifest |
| ivory_soap-25-55 | Ivory | BLOCK, unknown brand | BLOCK, no manifest |
| kodak_instamatic-31-60 | Kodak | BLOCK, unknown brand | BLOCK, no manifest |
| folgers-26-56 | Folgers | BLOCK, unknown brand | BLOCK, no manifest |
| labatts_beer-0-20 | Labatt's | BLOCK, unknown brand | BLOCK, no manifest |
| gilbert_slot_racers-0-30 | Gilbert | BLOCK, unknown brand | BLOCK, no manifest |
| MacleansToot-0-29 | Macleans | BLOCK, unknown brand | BLOCK, no manifest |
| ScottiesTiss-0-30 | Scotties | BLOCK, unknown brand | BLOCK, no manifest |
| GE_blender-0-30 | General Electric | BLOCK, unknown brand | BLOCK, no manifest |

The rights gate's policy (`rights-registry.yaml`, `policy.unknown_brand: BLOCK`) blocks a brand it
has never heard of exactly the same way it blocks one it has heard of and not cleared: none of
these ten names appear in the registry at all, so every one is a BLOCK, not because the gate
recognizes and refuses the brand but because it cannot clear what it cannot find. The claim and
brand gates (Nimbus charter, 16 CFR claims) have no ground truth on a real, unrelated commercial;
`eval/EVAL.md` reports what they find without scoring it right or wrong.
