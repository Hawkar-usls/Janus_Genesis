# Janus Cristal × FractalGPT sandbox

This experiment uses **Janus Genesis only as an isolated creative-technology sandbox**. It does not alter the authoritative Genesis gameplay runtime.

## Recovered FractalGPT

The user's prior `FractalGPT(12).py` was recovered from the file library. Original raw-file SHA-256:

`11e6c97ae7169a0fae4e0ad17f2fb7fb23b10265b04b4b057e3c968d6d0a3662`

The connector-serialized CI mirror is stored as `recovered/FractalGPT.py`; executed-mirror SHA-256:

`1dfc5bb1dabcb256d569de30dbe4431f6901c8dcddbe15fb76634fd57d9146e8`

The recovered source is a small autoregressive model over fractal-state sequences, approximately `[x, y, angle, scale, iteration]`, with native Koch, Sierpinski and fractal-Brownian generators.

```text
FractalGPT / fractal planner = WHERE / AT WHAT SCALE TO LOOK
fixed detector/field         = WHAT IS MEASURED
matched nulls                = WHETHER THE EFFECT SURVIVES A NULL MODEL
admission gate               = WHETHER A RESULT MAY BE ESCALATED
```

FractalGPT has no semantic authority.

## v0.3 — semantic/null hardening

Five crystal images and six planners were tested against block-shuffle and Fourier phase-scramble nulls. No word, formula, code or algorithm was admitted. An earlier mirror-symmetry lead was falsified as quartz-specific because calcite and fluorite controls produced comparable or stronger behavior.

## v0.4 — registered Alatay visible ↔ UV405 difference

The same petroleum-quartz specimen was registered before defining any difference region. Frozen nonsemantic field:

```text
0.40 × CLAHE luminance absolute difference
+ 0.40 × RGB chromaticity distance / sqrt(2)
+ 0.20 × normalized edge absolute difference
```

The registered pair produced a composite median near `0.23847`; fixed gamma=0.72 self-control near `0.03823`, ratio near `6.24`. Six planners were then compared with 2048 matched random trajectories each, familywise α=0.01. No planner was enriched.

## v0.5 — provenance and validator hardening

The frozen protocol produced a strong registered image-level visible/LWUVR difference on a LucasFassari quartz pair, but public metadata did not explicitly establish identical physical-specimen identity. It remained provenance-limited.

An AKAZE/RANSAC identity heuristic returned `INSUFFICIENT_MATCHES` on Lucas **and on the confirmed same-specimen Alatay positive control**, so it was invalidated as a necessary identity gate:

```text
A_VALIDATOR_THAT_FAILS_THE_POSITIVE_CONTROL
= NOT_ADMISSIBLE_AS_A_NECESSARY_GATE
```

## v0.6 — formal independent same-specimen replication

FMDB specimen 1226 describes one 26 mm petroleum-included quartz specimen and provides normal-light, 365 nm longwave and 254 nm shortwave photographs within the same record.

The **primary normal ↔ LW365 pair was frozen before outcome inspection**. Existing protocol, no pair-specific retuning:

```text
registration                             = USABLE_IMAGE_REGISTRATION
composite median                         = 0.25711361
gamma self-control median                = 0.04156784
pair / gamma-control median ratio        = 6.18539741
FractalGPT/baseline planner enrichment   = 0 / 6
final admission                          = FORMAL_INDEPENDENT_SAME_SPECIMEN_IMAGE_LEVEL_REPLICATION
```

Authoritative receipt:

```text
workflow run     = 31392997858
measurement head = 4d50e06e1c6df2f33abe02fac0a8c3b05893ed57
artifact id      = 9064508226
artifact sha256  = b2d62365fb93f330413a4ed8e60ec95c0604edbc98464c8ff7221d7284fd8cb2
conclusion       = SUCCESS
```

So the narrow image-level material branch reached:

```text
FORMAL_INDEPENDENT_REPLICATIONS = 1
CROSS_SPECIMEN_REPLICATION_GATE = PASS
SEMANTIC_CONTENT_ADMITTED       = 0
```

This is not a universal quartz law and not chemistry inferred from pixels.

## v0.6c — Sierpinski/SW254 single-pair candidate

The same FMS 1226 specimen had its 254 nm mode preregistered as **confirmatory**, so it could not count as a second independent specimen. Five planners were null; recovered FractalGPT Sierpinski produced:

```text
observed median composite        = 0.24602730
matched-random median composite  = 0.23252131
p(composite)                     = 0.00146413
observed hotspot fraction        = 0.11693349
matched-random hotspot fraction  = 0.05410556
p(hotspot)                       = 0.00048804
frozen per-planner threshold     = 0.00166667
single-pair status               = PASS_SINGLE_PAIR_CANDIDATE
```

The result was frozen as a **candidate only** because Sierpinski was not enriched on FMS 1226 LW365, Alatay UV405 or Lucas LWUVR.

## v0.7 — independent Sierpinski/SW254 replication: NEGATIVE

An independent specimen was chosen before its outcome: FMDB 1235, `Quartz - Cave-In-Rock, Illinois`, one record with normal, SW254 and LW365 views.

The initial preregistration accidentally said 48 windows. CI caught that **before image download or measurement** because the parent FractalGPT protocol actually uses 20. The manifest was corrected `48 → 20` before outcome acquisition; every statistical threshold and endpoint remained unchanged.

The first executable run after that correction was then invalidated because its resolver receipt proved a source-mapping bug: requested Normal was paired with an image whose own alt label said Shortwave, while requested Shortwave was paired with Longwave. That run is explicitly `INVALID_SOURCE_MAPPING_NOT_SCIENTIFIC_OUTCOME`.

The resolver was hardened to require an **exact image-own alt/title label**. No statistical rule was changed. The authoritative rerun resolved:

```text
Normal   = fmdb-1235-4627.jpg | alt = "Normal light."
SW254    = fmdb-1235-4626.jpg | alt = "Fluorescence under shortwave UV light."
```

Authoritative replication receipt:

```text
workflow run     = 31394703911
head             = 5c21b7e46596b4c31483c3e67650247a4db07a30
artifact id      = 9065114486
artifact sha256  = 2f343fc75672290c90bb034134ac466fc82ca42976ebb074b1cdcf9fa173e521
conclusion       = SUCCESS
```

The physical image-level modality difference **did** survive on the independent specimen:

```text
registration                         = USABLE_IMAGE_REGISTRATION
pair / gamma-control median ratio   = 1.90204387
registered modality difference      = OBSERVED
```

But the Sierpinski planner effect did not:

```text
observed median composite        = 0.08376963
matched-random median composite  = 0.08732847
p(composite)                     = 0.85846755
observed hotspot fraction        = 0.04310470
matched-random hotspot fraction  = 0.05351494
p(hotspot)                       = 0.91410444
replication alpha                = 0.00166667
replication gate                 = FAIL_TO_REPLICATE
```

Therefore:

```text
FRACTALGPT_SIERPINSKI_SW254_EFFECT = NOT_ESTABLISHED
CANDIDATE_STATUS                   = REJECTED_IN_TESTED_REPLICATION_SCOPE
INDEPENDENT_SW254_MODALITY_EFFECT  = OBSERVED
SEMANTIC_CONTENT                   = NOT_ADMITTED
```

This is exactly why the candidate/replication separation exists: the interesting single-pair Sierpinski signal was allowed to fail cleanly instead of being rescued by threshold or region tuning.

Frozen closeout:

- `GENESIS-JANUS-CRISTAL-FRACTALGPT-SIERPINSKI-SW254-CANDIDATE-v0.1.json`
- `GENESIS-JANUS-CRISTAL-FRACTALGPT-SIERPINSKI-SW254-REPLICATION-v0.1.json`

## Current direction

The FractalGPT planner-effect branch is **closed negative in this tested scope**. The stronger surviving branch is ordinary multispectral material imaging:

- confirmed Alatay visible↔UV405 difference;
- independent confirmed FMS 1226 normal↔LW365 replication;
- independent confirmed FMS 1235 normal↔SW254 modality difference;
- no admitted hidden message, formula, code or algorithm.

The next useful gate is wavelength-specific material replication on additional confirmed same-specimen quartz records, with FractalGPT retained as a controlled planner rather than promoted to a discovery mechanism.

## Claim ceiling

```text
FORMAL_IMAGE_LEVEL_REPLICATION != UNIVERSAL_QUARTZ_LAW
REGISTERED_MODALITY_DIFFERENCE != CHEMICAL_IDENTITY
REGISTERED_MODALITY_DIFFERENCE != HIDDEN_MESSAGE
FAILED_PLANNER_REPLICATION != FAILED_PHYSICAL_MODALITY_EFFECT
FRACTALGPT_TRAJECTORY != MATERIAL_DISCOVERY
NO_POST_HOC_REGION_OR_CIPHER_SEARCH
```
