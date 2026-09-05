# Gate evaluation: 10 real spots plus 6 synthetic assets

Reproduce (the excerpts are cut from archive.org by `scripts/fetch_assets.sh` and hash checked):

```
scripts/fetch_assets.sh
scripts/with_env.sh uv run python scripts/eval_gates.py
```

Run: 2026-09-05T06:20:15.751853+00:00 to 2026-09-05T06:45:18.083892+00:00 (UTC), code `c3bc502`, ground truth `eval/manifest.yaml`. Bucket: `airlock-agentic-cinema-assets`.

Every percentage is printed beside the count it is made of. BLOCK is the positive class: a
gate exists to catch the case it should block. A rule fires when its gate BLOCKs citing it;
a forbidden rule that fires is a false positive even when the BLOCK itself was right.

## Results

| asset | kind | rights | claim | brand | provenance | wall | cost USD |
|---|---|---|---|---|---|---|---|
| Cheerios1960-0-30 | real | BLOCK (78169 ms) | BLOCK (20966 ms) | BLOCK (13607 ms) | BLOCK (52 ms) | 122.2 s | $0.5190 |
| chevrolet-31-61 | real | BLOCK (58662 ms) | BLOCK (40599 ms) | BLOCK (22014 ms) | BLOCK (3 ms) | 132.1 s | $0.5206 |
| ivory_soap-25-55 | real | BLOCK (58967 ms) | BLOCK (35822 ms) | BLOCK (14446 ms) | BLOCK (4 ms) | 119.0 s | $0.5208 |
| kodak_instamatic-31-60 | real | BLOCK (26505 ms) | BLOCK (22388 ms) | BLOCK (15966 ms) | BLOCK (2 ms) | 74.6 s | $0.5192 |
| folgers-26-56 | real | BLOCK (36082 ms) | BLOCK (20578 ms) | BLOCK (15849 ms) | BLOCK (4 ms) | 81.9 s | $0.5191 |
| labatts_beer-0-20 | real | BLOCK (42554 ms) | BLOCK (35627 ms) | BLOCK (9256 ms) | BLOCK (2 ms) | 96.5 s | $0.5171 |
| gilbert_slot_racers-0-30 | real | BLOCK (35271 ms) | BLOCK (20801 ms) | BLOCK (20953 ms) | BLOCK (2 ms) | 86.2 s | $0.5177 |
| MacleansToot-0-29 | real | BLOCK (39673 ms) | BLOCK (22480 ms) | BLOCK (16247 ms) | BLOCK (2 ms) | 87.8 s | $0.5200 |
| ScottiesTiss-0-30 | real | BLOCK (58010 ms) | BLOCK (25755 ms) | BLOCK (12782 ms) | BLOCK (2 ms) | 106.3 s | $0.5197 |
| GE_blender-0-30 | real | BLOCK (47545 ms) | BLOCK (19615 ms) | BLOCK (14904 ms) | BLOCK (2 ms) | 91.5 s | $0.5189 |
| nimbus-test-clip | synthetic | PASS (34299 ms) | BLOCK (12943 ms) | PASS (11399 ms) | PASS (33 ms) | 68.4 s | $0.5060 |
| nimbus-clean-clip | synthetic | PASS (38224 ms) | PASS (13092 ms) | PASS (8476 ms) | PASS (8 ms) | 70.3 s | $0.5050 |
| nimbus-defect-brand-red | synthetic | PASS (36811 ms) | PASS (14160 ms) | BLOCK (20367 ms) | BLOCK (2 ms) | 80.7 s | $0.5064 |
| nimbus-defect-provenance-stripped | synthetic | PASS (94528 ms) | BLOCK (15666 ms) | PASS (11173 ms) | BLOCK (2 ms) | 130.8 s | $0.5059 |
| nimbus-defect-provenance-broken | synthetic | PASS (34502 ms) | BLOCK (14435 ms) | PASS (9947 ms) | BLOCK (10 ms) | 68.2 s | $0.5059 |
| veo-raw | synthetic | PASS (50047 ms) | PASS (9604 ms) | BLOCK (15662 ms) | BLOCK (17 ms) | 85.2 s | $0.5044 |

## Per gate: the status against the expected status

| gate | n | tp | fp | tn | fn | precision | recall |
|---|---|---|---|---|---|---|---|
| rights | 16 | 10 | 0 | 6 | 0 | 100% (10 of 10) | 100% (10 of 10) |
| claim | 5 | 3 | 0 | 2 | 0 | 100% (3 of 3) | 100% (3 of 3) |
| brand | 6 | 2 | 0 | 4 | 0 | 100% (2 of 2) | 100% (2 of 2) |
| provenance | 16 | 14 | 0 | 2 | 0 | 100% (14 of 14) | 100% (14 of 14) |

No status miss against the manifest.

## Per rule: did the rule fire where it must, and stay silent where it must not

n is the number of assets the manifest says something about for that rule (expected or
forbidden). tp: expected and fired. fn: expected and silent. fp: forbidden and fired. tn:
forbidden and silent. A rule with no forbidden case has no precision denominator beyond its
own true positives; a rule with no expected case has no recall.

| rule | gate | n | tp | fp | tn | fn | precision | recall |
|---|---|---|---|---|---|---|---|---|
| `registry:brands:not_cleared` | rights | 6 | 0 | 0 | 6 | 0 | n/a (0 of 0) | n/a (0 of 0) |
| `registry:brands:unknown` | rights | 16 | 9 | 0 | 6 | 1 | 100% (9 of 9) | 90% (9 of 10) |
| `registry:explicit_content` | rights | 16 | 0 | 1 | 15 | 0 | 0% (0 of 1) | n/a (0 of 0) |
| `registry:faces:no_release` | rights | 16 | 7 | 0 | 9 | 0 | 100% (7 of 7) | 100% (7 of 7) |
| `16 CFR 255.3` | claim | 4 | 3 | 0 | 1 | 0 | 100% (3 of 3) | 100% (3 of 3) |
| `charter:exclusions` | brand | 5 | 1 | 0 | 4 | 0 | 100% (1 of 1) | 100% (1 of 1) |
| `charter:mandatory_mentions` | brand | 6 | 1 | 0 | 5 | 0 | 100% (1 of 1) | 100% (1 of 1) |
| `charter:palette` | brand | 5 | 1 | 0 | 4 | 0 | 100% (1 of 1) | 100% (1 of 1) |
| `charter:tone` | brand | 4 | 0 | 0 | 4 | 0 | n/a (0 of 0) | n/a (0 of 0) |
| `charter:typography` | brand | 4 | 0 | 0 | 4 | 0 | n/a (0 of 0) | n/a (0 of 0) |
| `airlock:provenance:manifest-required` | provenance | 16 | 12 | 0 | 4 | 0 | 100% (12 of 12) | 100% (12 of 12) |
| `airlock:provenance:signature-valid` | provenance | 4 | 1 | 0 | 3 | 0 | 100% (1 of 1) | 100% (1 of 1) |
| `airlock:provenance:signer-trusted` | provenance | 3 | 1 | 0 | 2 | 0 | 100% (1 of 1) | 100% (1 of 1) |

- miss: `registry:brands:unknown` did not fire on `MacleansToot-0-29` (gate status BLOCK)
- false positive: `registry:explicit_content` fired on `kodak_instamatic-31-60`: "explicit content likelihood at or above LIKELY on 1 frame(s)"

## Brand identification on the real spots, scored apart from the BLOCK

The BLOCK on a real spot does not depend on the name (any brand the registry does not know
blocks); a rights desk needs the name. Named means one name the gate reported carries every
token of the brand on screen, as hand-labelled in the manifest.

Brand named: 40% (4 of 10).

| asset | brand on screen | what the rights gate reported | named |
|---|---|---|---|
| Cheerios1960-0-30 | Cheerios | Hootsuite, HTC, Honey Nut Cheerios | yes |
| chevrolet-31-61 | Chevrolet or Chevy | DeLorean Motor Company | no |
| ivory_soap-25-55 | Ivory | Ivory | yes |
| kodak_instamatic-31-60 | Kodak or Instamatic | Stanley Steemer, JanSport, Ichiran | no |
| folgers-26-56 | Folgers | Folgers | yes |
| labatts_beer-0-20 | Labatt | Peugeot | no |
| gilbert_slot_racers-0-30 | Gilbert | Mitsubishi Fuso Truck and Bus Corporation, Vauxhall Motors | no |
| MacleansToot-0-29 | Macleans | no brand | no |
| ScottiesTiss-0-30 | Scotties | Lucid Motors, Green Bay Packers | no |
| GE_blender-0-30 | General Electric or GE | General Electric, Target Corporation | yes |

## Latency per gate

| gate | n | median | max |
|---|---|---|---|
| rights | 16 | 41113 ms | 94528 ms |
| claim | 16 | 20689 ms | 40599 ms |
| brand | 16 | 14675 ms | 22014 ms |
| provenance | 16 | 2 ms | 52 ms |

## Cost, at list price

From `pricing.yaml`, read from the Cloud Billing Catalog on 2026-08-29; the free
monthly quotas are not netted out.

Median cost per asset: $0.5183 (n=16). Maximum cost per asset: $0.5208.
Total cost of the whole evaluation: $8.2256, 16 Video Intelligence minute(s), 32 Gemini call(s).

## Surprises

What the status-level score would hide. This run:

- `registry:brands:unknown` did not fire on `MacleansToot-0-29` where it must (gate status BLOCK)
- `registry:explicit_content` fired on `kodak_instamatic-31-60` where it must not: "explicit content likelihood at or above LIKELY on 1 frame(s)"
- Video Intelligence did not name the brand on 6 of 10 real spots: `chevrolet-31-61` expected Chevrolet or Chevy, got DeLorean Motor Company; `kodak_instamatic-31-60` expected Kodak or Instamatic, got Stanley Steemer, JanSport, Ichiran; `labatts_beer-0-20` expected Labatt, got Peugeot; `gilbert_slot_racers-0-30` expected Gilbert, got Mitsubishi Fuso Truck and Bus Corporation, Vauxhall Motors; `MacleansToot-0-29` expected Macleans, got no brand; `ScottiesTiss-0-30` expected Scotties, got Lucid Motors, Green Bay Packers

Seen in earlier runs of this eval, kept for the record:

- 2026-08-29, `kodak_instamatic-31-60`: the rights gate cited registry:explicit_content on a 1963 family party scene (a false positive the status-level score of that day counted as a correct BLOCK)
- 2026-08-29, `6 of 10 real spots`: Video Intelligence named the wrong company at high confidence (a 1955 Chevrolet read as DeLorean Motor Company; Ichiran, Peugeot, Vauxhall, Lucid and Target on five others); the BLOCK held because the policy blocks any brand the registry does not know, so the status-level score hid it

## What claim and brand found on the real spots, unscored

These ten are real, unrelated commercials: there is no charter or substantiation
file for them, so claim and brand cannot be right or wrong here, only informative.

- `Cheerios1960-0-30` (brand on screen Cheerios): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 9.8s: "that teams up V8 juice and Cheerios for flavor and energy." (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `chevrolet-31-61` (brand on screen Chevrolet): claim BLOCK, "2 regulated claim(s) with no substantiation on file; first at 4.0s: "Oh, isn't it wonderful?" (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `ivory_soap-25-55` (brand on screen Ivory): claim BLOCK, "4 regulated claim(s) with no substantiation on file; first at 13.8s: "Ivory cleans gently" (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `kodak_instamatic-31-60` (brand on screen Kodak): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 6.4s: "Drop in the film." (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `folgers-26-56` (brand on screen Folgers): claim BLOCK, "6 regulated claim(s) with no substantiation on file; first at 1.8s: "You just need the coffee with better flavor." (comparative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `labatts_beer-0-20` (brand on screen Labatt's): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 10.5s: "It's a great new taste in beer." (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `gilbert_slot_racers-0-30` (brand on screen Gilbert): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 20.695s: "Gilbert makes cars rugged enough to take this kind of punishment." (efficacy, 16 CFR 255"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `MacleansToot-0-29` (brand on screen Macleans): claim BLOCK, "8 regulated claim(s) with no substantiation on file; first at 9.6s: "This is the security clean white teeth give." (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `ScottiesTiss-0-30` (brand on screen Scotties): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 5.5s: "There's no other box of facial tissues like this." (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `GE_blender-0-30` (brand on screen General Electric): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 3.7s: "Here's the newest, most exciting sound in town." (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"

