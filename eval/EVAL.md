# Gate evaluation: 10 real spots plus 6 synthetic assets

Reproduce:

```
scripts/with_env.sh uv run python scripts/eval_gates.py
```

Run: 2026-08-29T23:03:27.544937+00:00 to 2026-08-29T23:37:29.156820+00:00 (UTC). Bucket: `airlock-agentic-cinema-assets`.

## Results

| asset | kind | rights | claim | brand | provenance | wall | cost USD |
|---|---|---|---|---|---|---|---|
| Cheerios1960-0-30 | real | BLOCK (83130 ms) | BLOCK (23165 ms) | BLOCK (21784 ms) | BLOCK (34 ms) | 137.7 s | $0.5202 |
| chevrolet-31-61 | real | BLOCK (142739 ms) | BLOCK (39892 ms) | BLOCK (31106 ms) | BLOCK (1 ms) | 223.7 s | $0.5213 |
| ivory_soap-25-55 | real | BLOCK (28564 ms) | BLOCK (21561 ms) | BLOCK (19562 ms) | BLOCK (2 ms) | 78.6 s | $0.5202 |
| kodak_instamatic-31-60 | real | BLOCK (47139 ms) | BLOCK (18242 ms) | BLOCK (18530 ms) | BLOCK (2 ms) | 92.9 s | $0.5184 |
| folgers-26-56 | real | BLOCK (85380 ms) | BLOCK (20113 ms) | BLOCK (18925 ms) | BLOCK (1 ms) | 133.4 s | $0.5194 |
| labatts_beer-0-20 | real | BLOCK (48356 ms) | BLOCK (33577 ms) | BLOCK (16865 ms) | BLOCK (2 ms) | 107.8 s | $0.5174 |
| gilbert_slot_racers-0-30 | real | BLOCK (457941 ms) | BLOCK (17414 ms) | BLOCK (19968 ms) | BLOCK (2 ms) | 504.3 s | $0.5181 |
| MacleansToot-0-29 | real | BLOCK (39884 ms) | BLOCK (22377 ms) | BLOCK (17208 ms) | BLOCK (2 ms) | 88.7 s | $0.5198 |
| ScottiesTiss-0-30 | real | BLOCK (60011 ms) | BLOCK (23671 ms) | BLOCK (15175 ms) | BLOCK (1 ms) | 109.2 s | $0.5189 |
| GE_blender-0-30 | real | BLOCK (51776 ms) | BLOCK (19521 ms) | BLOCK (15710 ms) | BLOCK (2 ms) | 99.5 s | $0.5188 |
| nimbus-test-clip | synthetic | PASS (32387 ms) | BLOCK (16666 ms) | PASS (12573 ms) | PASS (23 ms) | 70.6 s | $0.5059 |
| nimbus-clean-clip | synthetic | PASS (33966 ms) | PASS (12100 ms) | PASS (8614 ms) | PASS (7 ms) | 63.6 s | $0.5052 |
| nimbus-defect-brand-red | synthetic | PASS (33757 ms) | PASS (13711 ms) | BLOCK (22305 ms) | BLOCK (2 ms) | 78.7 s | $0.5064 |
| nimbus-defect-provenance-stripped | synthetic | PASS (37344 ms) | BLOCK (16113 ms) | PASS (10827 ms) | BLOCK (1 ms) | 73.0 s | $0.5059 |
| nimbus-defect-provenance-broken | synthetic | PASS (46145 ms) | BLOCK (10031 ms) | PASS (13917 ms) | BLOCK (7 ms) | 79.2 s | $0.5060 |
| veo-raw | synthetic | PASS (66285 ms) | PASS (11168 ms) | BLOCK (14399 ms) | BLOCK (12 ms) | 100.8 s | $0.5044 |

## Precision and recall, where a ground truth exists

BLOCK is the positive class: a gate exists to catch the case it should block.

| gate | n | tp | fp | tn | fn | precision | recall |
|---|---|---|---|---|---|---|---|
| rights | 13 | 10 | 0 | 3 | 0 | 100% | 100% |
| claim | 3 | 1 | 0 | 2 | 0 | 100% | 100% |
| brand | 4 | 2 | 0 | 2 | 0 | 100% | 100% |
| provenance | 15 | 13 | 0 | 2 | 0 | 100% | 100% |

No misses against the stated ground truth.

## Latency per gate

| gate | n | median | max |
|---|---|---|---|
| rights | 16 | 47747 ms | 457941 ms |
| claim | 16 | 18881 ms | 39892 ms |
| brand | 16 | 17036 ms | 31106 ms |
| provenance | 16 | 2 ms | 34 ms |

## Cost, at list price

From `pricing.yaml`, read from the Cloud Billing Catalog on 2026-08-29; the free
monthly quotas are not netted out.

Median cost per asset: $0.5182. Maximum cost per asset: $0.5213.
Total cost of the whole evaluation: $8.2262, 16 Video Intelligence minute(s), 32 Gemini call(s).

## What claim and brand found on the real spots, unscored

These ten are real, unrelated commercials: there is no charter or substantiation
file for them, so claim and brand cannot be right or wrong here, only informative.

- `Cheerios1960-0-30` (expected brand Cheerios): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 7.8s: "an out-of-this-world breakfast." (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `chevrolet-31-61` (expected brand Chevrolet): claim BLOCK, "2 regulated claim(s) with no substantiation on file; first at 11.5s: "I'm going to see the 1963 Chevrolets." (consumer_testimonial, 16 CFR 255.2(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `ivory_soap-25-55` (expected brand Ivory): claim BLOCK, "5 regulated claim(s) with no substantiation on file; first at 10.5s: "Ivory's natural soap" (health, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `kodak_instamatic-31-60` (expected brand Kodak): claim BLOCK, "2 regulated claim(s) with no substantiation on file; first at 19.59s: "Take four flash pictures without changing bulbs." (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `folgers-26-56` (expected brand Folgers): claim BLOCK, "7 regulated claim(s) with no substantiation on file; first at 1.8s: "You just need the coffee with better flavor." (comparative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `labatts_beer-0-20` (expected brand Labatt's): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 10.5s: "It's a great new taste in beer." (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `gilbert_slot_racers-0-30` (expected brand Gilbert): claim BLOCK, "3 regulated claim(s) with no substantiation on file; first at 11.578s: "featuring the exclusive new Gilbert flyover chicane." (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `MacleansToot-0-29` (expected brand Macleans): claim BLOCK, "7 regulated claim(s) with no substantiation on file; first at 9.8s: "This is the security clean white teeth give." (efficacy, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `ScottiesTiss-0-30` (expected brand Scotties): claim BLOCK, "4 regulated claim(s) with no substantiation on file; first at 5.59s: "There's no other box of facial tissues like this." (comparative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"
- `GE_blender-0-30` (expected brand General Electric): claim BLOCK, "6 regulated claim(s) with no substantiation on file; first at 3.8s: "It's the newest, most exciting sound in town." (superlative, 16 CFR 255.1(a))"; brand BLOCK, "mandatory mention missing: the Nimbus wordmark is never seen"

