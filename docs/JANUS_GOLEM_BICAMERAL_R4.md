# JANUS GOLEM BICAMERAL R4A — actual native CPU pilot

**Scope:** A genuine, pinned native-model measurement. External and bicameral
arms are **NOT EXECUTED**: no real free-provider credential/receipt is available
from the currently authorized development context. This is NOT a completed
three-way R4 experiment, NOT a blinded independent holdout, and NOT proof that
two models are better than one.

## What the measurement does

- The prior R3 calibration uses long questions that cannot fairly fit inside
  Demiurge's promoted tiny byte-level context. R4A freezes **12 short English
  cases** (three each: gateway, memory, evidence, authority) of at most 80
  characters per task. Every actual inference prompt is limited to 96 UTF-8
  bytes. This is a **new PUBLIC native CPU pilot**, not the R3 test and not
  the preregistered independent 40+ sample study.
- Actual native code and weights are pinned to Janus-Demiurge commit
  8873e5121a67daac5c8afb8ff297d6565dc87c32 (Draft PR #301). The
  existing trusted native adapter rejects dirty or mismatched checkouts,
  validates the model checkpoint, strips credential environment variables,
  and invokes the local Transformer via CPU only.
- Every test asks for an exact first token ALLOW, DENY or UNKNOWN. Any
  nonconforming response is marked ABSTAIN; no post hoc semantic
  interpretation or answer laundering is permitted. Gold labels are read
  by the scorer AFTER inference, not included in the model prompt.
- Public pack/key hashes, native commit, native checkpoint SHA-256, each
  prompt SHA-256 and generated-response SHA-256 are recorded. A missing
  model execution is INCOMPLETE, not an artificial score of 0. A changed
  checkpoint SHA mid-run fails closed.
- The report stores 12 response labels/hashes and fixed-denominator
  accuracy, but deliberately not raw generated model text to avoid
  accidental prompt-injection propagation. This pilot is not training data.
- No external free-model API is called. External and bicameral score fields
  are explicitly null and statuses NOT_EXECUTED. No improvement claim, no
  model promotion, no training, no HOME push, no ACK changes.
- Stubbed native inference in unit tests has source_type
  TEST_FIXTURE__NOT_REAL_NATIVE and never qualifies as a real CPU baseline.
  The GitHub CI job calls the actual pinned native adapter and publishes an
  Actions artifact retained for 14 days with observed scores and hashes.

## Artifacts

- benchmarks/golem_r4_native_cpu_pilot.json
- benchmarks/golem_r4_native_cpu_pilot_key.json
- tools/golem_bicameral_r4_native_probe.py
- tests/test_golem_bicameral_r4_native_probe.py
- GitHub Actions artifact: golem-r4-native-public-pilot.

The workflow is on a read-only PR run; the CPU PyTorch installation may
use GitHub Actions minutes and download open-source Python packages. The
work itself performs no model API calls, paid GPU allocation or training.

## What R4B needs before a scientifically admissible comparison

1. Confirm a truly nonbillable provider account with a user-controlled
   GitHub secret and explicit free-only opt-in. API account limits, billing
   settings and provider terms must be verified before any call. The
   unavailable secret is not a license to scrape a chat UI or evade quotas.
2. Run the exact SAME frozen tasks through independently authenticated
   EXTERNAL and BICAMERAL modes using a real external inference protocol,
   not the R2 simulator. Store provider identity, tokens, context and
   immutable request/response receipts. No label is a proof/authority grant.
3. Evaluate fairness: native context must actually contain the whole
   question, and record that prompt truncation/byte tokenizer limitations
   may materially affect performance. Report output length, timeout,
   abstention, availability and latency per mode.
4. Freeze a separate independently authored *hidden* 40+ task holdout and
   reference answers before responses, with preregistered rules for paired
   effect sizes, uncertainty, critical violations and replication.
5. Do not train Demiurge on external outputs unless license/terms, dataset
   independence and user approval explicitly allow it. Native promoted
   checkpoint remains unchanged.

**R4A cannot claim bicameral superiority regardless of its native score.**
