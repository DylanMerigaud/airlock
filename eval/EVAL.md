# Gate evaluation: 10 real spots plus 6 synthetic assets

Reproduce (the excerpts are cut from archive.org by `scripts/fetch_assets.sh` and hash checked):

```
scripts/fetch_assets.sh
scripts/with_env.sh uv run python scripts/eval_gates.py
```

Run: 2026-09-05T09:30:56.310055+00:00 to 2026-09-05T09:59:40.472535+00:00 (UTC), code `4becdda`, ground truth `eval/manifest.yaml`. Bucket: `airlock-agentic-cinema-assets`.

Every percentage is printed beside the count it is made of. BLOCK is the positive class: a
gate exists to catch the case it should block. A rule fires when its gate BLOCKs citing it;
a forbidden rule that fires is a false positive even when the BLOCK itself was right.

## Results

| asset | kind | rights | claim | brand | provenance | wall | cost USD |
|---|---|---|---|---|---|---|---|
| Cheerios1960-0-30 | real | BLOCK (52263 ms) | BLOCK (29560 ms) | BLOCK (15649 ms) | BLOCK (86 ms) | 106.0 s | $0.5207 |
| chevrolet-31-61 | real | BLOCK (87814 ms) | PASS (24082 ms) | BLOCK (30772 ms) | BLOCK (8 ms) | 151.4 s | $0.5176 |
| ivory_soap-25-55 | real | BLOCK (44564 ms) | BLOCK (37121 ms) | BLOCK (18408 ms) | BLOCK (4 ms) | 109.4 s | $0.5216 |
| kodak_instamatic-31-60 | real | BLOCK (31171 ms) | BLOCK (22034 ms) | BLOCK (20482 ms) | BLOCK (16 ms) | 83.2 s | $0.5199 |
| folgers-26-56 | real | BLOCK (40798 ms) | BLOCK (29170 ms) | BLOCK (16797 ms) | BLOCK (5 ms) | 95.3 s | $0.5196 |
| labatts_beer-0-20 | real | BLOCK (28554 ms) | BLOCK (22012 ms) | BLOCK (25774 ms) | BLOCK (7 ms) | 84.8 s | $0.5161 |
| gilbert_slot_racers-0-30 | real | BLOCK (40408 ms) | BLOCK (18290 ms) | BLOCK (16490 ms) | BLOCK (4 ms) | 83.7 s | $0.5172 |
| MacleansToot-0-29 | real | BLOCK (42664 ms) | BLOCK (26951 ms) | BLOCK (16437 ms) | BLOCK (4 ms) | 94.8 s | $0.5197 |
| ScottiesTiss-0-30 | real | BLOCK (65827 ms) | BLOCK (26077 ms) | BLOCK (13268 ms) | BLOCK (5 ms) | 113.6 s | $0.5206 |
| GE_blender-0-30 | real | BLOCK (48022 ms) | ERROR (300500 ms) | BLOCK (15120 ms) | BLOCK (6 ms) | 372.4 s | $0.5031 |
| nimbus-test-clip | synthetic | PASS (35363 ms) | BLOCK (14595 ms) | PASS (10746 ms) | PASS (31 ms) | 70.0 s | $0.5063 |
| nimbus-clean-clip | synthetic | PASS (36887 ms) | PASS (13138 ms) | PASS (8875 ms) | PASS (10 ms) | 67.4 s | $0.5054 |
| nimbus-defect-brand-red | synthetic | PASS (40277 ms) | PASS (15738 ms) | BLOCK (19869 ms) | BLOCK (3 ms) | 84.3 s | $0.5065 |
| nimbus-defect-provenance-stripped | synthetic | PASS (22967 ms) | BLOCK (13145 ms) | PASS (12611 ms) | BLOCK (3 ms) | 56.6 s | $0.5061 |
| nimbus-defect-provenance-broken | synthetic | PASS (42834 ms) | BLOCK (15078 ms) | PASS (11415 ms) | BLOCK (12 ms) | 78.3 s | $0.5064 |
| veo-raw | synthetic | PASS (41620 ms) | PASS (10041 ms) | BLOCK (9304 ms) | BLOCK (21 ms) | 69.1 s | $0.5046 |

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
| gilbert_slot_racers-0-30 | Gilbert | Vauxhall Motors, Mitsubishi Fuso Truck and Bus Corporation | no |
| MacleansToot-0-29 | Macleans | no brand | no |
| ScottiesTiss-0-30 | Scotties | Lucid Motors, Green Bay Packers | no |
| GE_blender-0-30 | General Electric or GE | General Electric, Target Corporation | yes |

## Latency per gate

| gate | n | median | max |
|---|---|---|---|
| rights | 16 | 41209 ms | 87814 ms |
| claim | 16 | 22023 ms | 300500 ms |
| brand | 16 | 16043 ms | 30772 ms |
| provenance | 16 | 6 ms | 86 ms |

## Cost, at list price

From `pricing.yaml`, read from the Cloud Billing Catalog on 2026-08-29; the free
monthly quotas are not netted out.

Median cost per asset: $0.5167 (n=16). Maximum cost per asset: $0.5216.
Total cost of the whole evaluation: $8.2115, 16 Video Intelligence minute(s), 31 Gemini call(s).

## Surprises

What the status-level score would hide. This run:

- `registry:brands:unknown` did not fire on `MacleansToot-0-29` where it must (gate status BLOCK)
- `registry:explicit_content` fired on `kodak_instamatic-31-60` where it must not: "explicit content likelihood at or above LIKELY on 1 frame(s)"
- Video Intelligence did not name the brand on 6 of 10 real spots: `chevrolet-31-61` expected Chevrolet or Chevy, got DeLorean Motor Company; `kodak_instamatic-31-60` expected Kodak or Instamatic, got Stanley Steemer, JanSport, Ichiran; `labatts_beer-0-20` expected Labatt, got Peugeot; `gilbert_slot_racers-0-30` expected Gilbert, got Vauxhall Motors, Mitsubishi Fuso Truck and Bus Corporation; `MacleansToot-0-29` expected Macleans, got no brand; `ScottiesTiss-0-30` expected Scotties, got Lucid Motors, Green Bay Packers
- `claim` on `GE_blender-0-30` ended in ERROR: "ReadTimeout: The read operation timed out"

Seen in earlier runs of this eval, kept for the record:

- 2026-08-29, `kodak_instamatic-31-60`: the rights gate cited registry:explicit_content on a 1963 family party scene (a false positive the status-level score of that day counted as a correct BLOCK)
- 2026-08-29, `6 of 10 real spots`: Video Intelligence named the wrong company at high confidence (a 1955 Chevrolet read as DeLorean Motor Company; Ichiran, Peugeot, Vauxhall, Lucid and Target on five others); the BLOCK held because the policy blocks any brand the registry does not know, so the status-level score hid it

## What claim and brand found on the real spots, unscored

These ten are real, unrelated commercials: there is no charter or substantiation
file for them, so claim and brand cannot be right or wrong here, only informative.

- `Cheerios1960-0-30` (brand on screen Cheerios): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 10s: "that teams up V8 juice and Cheerios for flavor and energy." (health, FTC Act section 5 (15 U"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `chevrolet-31-61` (brand on screen Chevrolet): claim PASS, "no regulated claim without substantiation (3 claim(s) read, 3 advisory)"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `ivory_soap-25-55` (brand on screen Ivory): claim BLOCK, "7 regulated claim(s) with no substantiation on file; first at 8.6s: "We use Ivory around this house." (consumer_testimonial, 16 CFR 255.2(a)): a testimonial mus"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `kodak_instamatic-31-60` (brand on screen Kodak): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 6.4s: "Drop in the film." (efficacy, FTC Act section 5 (15 U.S.C. 45)): an efficacy claim needs a "; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `folgers-26-56` (brand on screen Folgers): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 2.0s: "You just need the coffee with better flavor." (comparative, FTC Act section 5 (15 U.S.C. 45"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `labatts_beer-0-20` (brand on screen Labatt's): claim BLOCK, "1 regulated claim(s) with no substantiation on file; first at 13.213s: "Enjoy import quality at USA prices." (comparative, FTC Act section 5 (15 U.S.C. 45)): a "; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `gilbert_slot_racers-0-30` (brand on screen Gilbert): claim BLOCK, "2 regulated claim(s) with no substantiation on file; first at 20.5s: "Gilbert makes cars rugged enough to take this kind of punishment." (efficacy, FTC Act sect"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `MacleansToot-0-29` (brand on screen Macleans): claim BLOCK, "6 regulated claim(s) with no substantiation on file; first at 9.8s: "This is the security clean white teeth give." (efficacy, FTC Act section 5 (15 U.S.C. 45)):"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `ScottiesTiss-0-30` (brand on screen Scotties): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 5.4s: "There's no other box of facial tissues like this." (comparative, FTC Act section 5 (15 U.S."; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `GE_blender-0-30` (brand on screen General Electric): claim ERROR, "ReadTimeout: The read operation timed out"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"

