# JANUS GOLEM BICAMERAL R3 — preregistered calibration / measurement gate

**Scientific state: INSTRUMENT_READY, CLAIM_OF_BICAMERAL_SUPERIORITY_NOT_ADMITTED.**
The real external provider and independent blinded holdout have **not**
been evaluated. R3 in this PR is a *scoring-instrument validation*, not
a study demonstrating improvement by combining two models.

## Why the R2 v2 PASS is insufficient

In R2 the native Transformer ran twice, with a simulated external specialist
between passes. Correct hashing, git durability and a simulator's DISPUTES
label measure program behaviour. They do not establish that two working models
solved a task, resolved a genuine contradiction, or improved answer quality.

The earlier Genesis Top100 tool classifies a broader set of benchmarks and
provider readiness; it explicitly does not claim official benchmark scores
without frozen datasets and their independent graders. R3 addresses a
different question: paired per-task comparisons between NATIVE, EXTERNAL,
and BICAMERAL on the exact same set of cases.

## Frozen PUBLIC calibration

Input: benchmarks/golem_bicameral_r3_calibration.json

Answers: benchmarks/golem_bicameral_r3_calibration_key.json

Twelve **public** exact-label cases, balanced across four families:
gateway, memory, evidence, authority. Legal labels are ALLOW, DENY,
UNKNOWN; a responding system may abstain with ABSTAIN. This set is small,
public and written by the implementer. It is **not blinded**, independently
reviewed, representative of research questions, or sufficient for a valid
comparative inference. It tests the scoring tool's failure modes.

The gold key must NOT be included in any model prompt. Both files are
versioned in Git. The evaluator returns their canonical SHA-256 digests.
Changing the gold key changes its digest; there is no independent gold
signature yet.

## Submission and provenance contract

A JSON submission must contain:

- schema: janus.golem.bicameral.r3.responses.v1
- pack_sha256: the canonical digest of the exact public task pack
- records: objects with *exactly* mode, task_id, task_sha256, response,
  source_kind, source_receipt_sha256.

The mode is NATIVE, EXTERNAL or BICAMERAL. Source kind TEST_FIXTURE means
the record is synthetic and MUST have null receipt digest.
UNVERIFIED_CANDIDATE requires a 64-character receipt digest but **does not
make that provenance verified**. Future independent attestations must
reproduce a model reply from an immutable source checkout and a
contemporaneous signed provider trace; a self-reported digest is not proof.

Duplicate answers, out-of-set IDs, wrong task/pack SHA, source masquerading,
extra fields, invalid labels or answer-key size drift fail closed.

## Scoring and mandatory claim ceiling

For each mode, report correct, submitted, missing, abstained and fixed-
denominator exact accuracy. Missing and ABSTAIN are not correct and do not
reduce the denominator. Per-family raw counts are retained.

Only if **all three modes answer every task** are paired BICAMERAL-vs-
NATIVE and BICAMERAL-vs-EXTERNAL contrasts reported. The evaluator counts
cases where B alone is correct, A alone correct and discordant cases,
plus a two-sided exact binomial/McNemar statistic. Correlated cases or a
12-task calibration invalidate its use as a general significance claim.
Here it is only a smoke test of the calculations.

Regardless of numeric result:
- improvement_claim_admitted = false
- real_external_inference_verified = false
- independent_holdout_tested = false
- source_provenance_independently_verified = false
- official_benchmark_score_claimed = false
- training_permission_granted = false
- promotion_authorized = false
- scientific_authority_delta = 0.

An adversarial unit test fabricates a perfect bicameral score and a low
native score; the gate **must still reject an improvement claim**.

## Future R3 scientific gate (preregister BEFORE real outputs)

1. Freeze an **independently created non-public holdout** of at least 40
   tasks, with task-family and difficulty strata, gold-review adjudication
   separate from generation, and versioned hashes before model calls.
   The calibration tasks in this repo must never become the holdout.
2. Pin source models and exact inference prompts/configuration. Record
   provider identity, its terms, context lengths and token/latency budgets.
   Obtain real eligible free-tier provider access without bypassing quota
   or activating paid fallback. Use identical original tasks in each arm;
   additional bicameral tokens/latency must be reported, not concealed.
3. Execute NATIVE, EXTERNAL and BICAMERAL **independently and completely** on
   the same held-out cases; record per-case independent immutable receipts,
   validate source hashes and avoid giving reference answers to the models.
   External provider results are untrusted and may not carry command rights.
4. Primary endpoint: bicameral exact accuracy minus the **better** of the
   two single-arm accuracies on paired cases. Preregister a minimum
   absolute gain of 0.10 AND a paired 95% lower confidence bound above 0;
   repeat on a new independently authored batch. Require **zero increase**
   in critical policy violations, and report cost/latency. Any task-family
   regression must be explicitly reported even when global score improves.
5. Report refusal/abstention, failures, missing and paired discordance with
   uncertainty by independent task group. If the holdout is too small,
   outcomes unstable, source ambiguous or labels disputed, verdict UNKNOWN,
   not PASS and not "P vs NP solved."
6. Improve native support for sufficiently long source context before
   describing the small Demiurge as a comparable natural-language solver.
   The promoted tiny model has a very small byte-level context; these
   long calibration prompts cannot currently be fairly delivered to it
   verbatim. This limitation MUST be reported.

The criteria above are a proposed scientific admission gate, **not code
authority or proof**.

## Reproduce the no-response result

No third-party packages or model/API credentials:

    python tools/golem_bicameral_r3_eval.py \
      --pack benchmarks/golem_bicameral_r3_calibration.json \
      --key benchmarks/golem_bicameral_r3_calibration_key.json

Output: NO_SUBMISSIONS__NOT_EVALUATED. The test suite submits synthetic
response triplets to validate arithmetic, tampering protection and the
"never turn a fake good score into evidence" rule:

    python -m unittest -v tests.test_golem_bicameral_r3_eval

The PR workflow is read-only, uses no live providers, charges no provider
API fees, writes no HOME state, changes no weights and issues no ACK.
GitHub Actions still consumes whatever CI minutes apply to the account.
