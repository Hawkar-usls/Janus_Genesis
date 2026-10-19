# JANUS CORPUS CALLOSUM v2 — sequential research gate

**Status: experimental, offline-only. No real external LLM calls; no automated production HOME writes or native model promotions.**

## Why

V1 runs native Demiurge and GOLEM free federation in parallel, recording two
separate answers but not a true exchange. V2 tests the stricter order:

1. Validate the read-only Beetle CONTEXT.json / CURSOR.json and capture
   SHA-256 of HOME STATE.json, CONTEXT.json, CURSOR.json.
2. Invoke the **real, SHA-pinned** Demiurge tiny Transformer on CPU using a
   bounded prompt. Its preliminary text remains an untrusted model observation.
3. Pass the original context binding and a bounded preliminary result into a
   **test-only external simulator**. It must return the exact initial native
   output SHA-256, context SHA-256 and legitimate context IDs.
4. Pass the simulated external text (explicitly marked REVIEW_UNTRUSTED)
   through a second native CPU inference using the **same checkpoint SHA**.
5. Validate the complete causal chain, save an exclusive append-only v2 JSON
   under corpus_callosum_v2/, and optionally test real **local bare-Git**
   commit/push/recovery via janus_corpus_v2_publisher.py.

The wrapper recognizes SUPPORTS, DISPUTES, and UNDETERMINED only as
**unverified claims made by the simulator**. DISPUTE_REPORTED_NOT_ADJUDICATED
is **not** a semantic contradiction detector. Its absence is **not** consensus.
quality=NOT_EVALUATED is mandatory, not a score of usefulness.

## Explicit boundaries

- Offline execution is allowed only when JANUS_BICAMERAL_V2_OFFLINE=1 and an
  explicit external simulator callback is supplied; no default network adapter
  or provider credentials exist.
- The CI worker checks out Janus-Demiurge at immutable commit
  8873e5121a67daac5c8afb8ff297d6565dc87c32, the already reviewed
  hardened checkpoint loader (Draft PR #301). The CPU test fails rather than
  silently skipping if the checkout is missing.
- **Two real CPU generations** in v2 are distinct in the test. Neither model
  output is authorized to issue shell commands, change Git code, write ACK,
  alter scientific authority or train the weights.
- The external answer is explicitly tagged OFFLINE_SIMULATED_EXTERNAL,
  FIXTURE_ONLY_NOT_A_REAL_PROVIDER. No evidence in this protocol claims a
  real provider request, real model agreement, or completed scientific review.
- We do **not** use a provider's outputs as training material, nor claim that
  the tiny native model is good at following textual instructions.
- The v1 production receipts and publisher are untouched. The v2 publisher
  is separate and stages **only one verified v2 receipt**. A non-force push to
  a disposable local Git remote demonstrates durable recovery. An operator
  must separately review and approve any future productive HOME deployment.
- Recovery distinguishes death **before** and **after** a confirmed remote
  push. No technique recovers data never durably stored.
- Git SHA-256 and same-branch compare-and-swap are integrity/concurrency
  guards, not independent anti-rollback guarantees: retain the external
  high-water witness.

## Running in CI

The existing JANUS Corpus Callosum (bicameral offline gate) PR workflow
runs both the v1 and new v2 unit suites in Python without external model API.
Its pinned-native job installs CPU-only PyTorch and runs
tests.test_janus_corpus_real_native_cpu, including the v2 true two-pass
integration with a fake external response. All Git recovery tests operate
against temporary local bare remotes. The workflow uses read-only credentials.

## Next research gates

1. Independent objective-specific oracle/benchmark, including blinded
   comparisons with native-only and external-only outputs. Do not infer
   semantic agreement from a simulator-supplied label.
2. A separately reviewed free-only external adapter that can accept the
   native challenge *as untrusted data* without broadening provider
   permissions, billing controls, context validation or secret exposure.
3. Versioned real-provider receipts with strict binding to both native input
   and actual provider response. Only then consider a supervised live trial.
4. Durable champion/previous-best checkpoint restoration, tested with an
   intentionally failed model rollout. Rejection of a corrupt *candidate* is
   weaker than rollback of an already-deployed version.
