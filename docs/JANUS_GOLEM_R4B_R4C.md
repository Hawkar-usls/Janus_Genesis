# JANUS GOLEM R4B + R4C — diagnostics without retrospective scoring

Research status: **R4B EXECUTION UNDER TEST; R4C PROVIDER NOT VERIFIED**.
This is not an evaluation of bicameral superiority, and not an independently
blinded study.

## R4B: separate three native-model behaviors

The frozen public diagnostic tasks are in:

- benchmarks/golem_r4b_public_diagnostics.json
- benchmarks/golem_r4b_public_diagnostics_key.json

Nine tasks in exactly three families:

- CONTINUATION: observe bounded raw generated text, length, nonempty and
  printable ratio; do not assert it is semantically coherent without
  independent human or objective review. No gold "correct next story" exists.
- INSTRUCTION: three strict exact-format commands; only the entire text
  (after stripping surrounding whitespace) equals the specified expected
  marker to count as correct.
- MULTIPLE_CHOICE: three binary questions; the entire text must be the
  correct standalone label A or B. Casual occurrence of A/B in a rambling
  answer is not a correct response.

These are **not** the R4A twelve-choice tasks. R4A's previously observed
0/12 and 12 abstentions remain untouched. No R4A prompts, scores or reference
answers are retroactively edited or rescued.

The real CI task uses the same pinned, clean SHA
8873e5121a67daac5c8afb8ff297d6565dc87c32 from Demiurge PR #301 as
earlier verified CPU execution. The existing native subprocess runner verifies
the clean Git checkout, source SHA and bounded prompt output; stripped
environment excludes all external provider or GitHub tokens. Nine fresh CPU
generations are measured, not a synthetic "model" fixture.

Evidence is published as a short-lived GitHub Actions artifact
golem-r4b-public-native-diagnostics. Each task records source prompt SHA,
generated text SHA, byte-safe bounded excerpt (up to 160 characters), raw
length, native commit and immutable checkpoint digest. Only public diagnostic
prompts are used; no HOME context or user secrets are included. The report
cannot be a training source, does not update any native weights, and has
zero scientific/external action authority.

A broken runtime produces INCOMPLETE_NATIVE_FAILURE rather than silently
assigning failures as zero accuracy. A changed model checkpoint digest in
one session fails closed.

## R4C: external provider preflight, NOT a connection

tools/golem_r4c_provider_preflight.py uses exactly the static four-provider
production allowlist from golem_free_federation.py. It inspects the current
process's configuration only, redacting token values, complete URLs and
account IDs. It calls no HTTP endpoint, invokes no inference, and never
pushes to GitHub HOME.

Even a present-looking API key with all opt-in flags does not establish
an independently verified no-billing account. This module therefore
**always** declares live_inference_admitted=false. A separate legitimate
account-level verification is required before real API use. GitHub's encrypted
secret store cannot be listed or verified by this read-only CI check, so
absence in the workflow environment is not a definitive claim that the
user has never configured a key.

The R4C gate requires a user-authorized genuinely free plan, positive
billing-control verification, and a reviewed live-inference adapter that
preserves provider/model provenance, public-data filtering and rate limits.
It must not scrape consumer chat interfaces or rotate accounts to evade
quotas. No provider model answers are represented as native-model weights.

## Interpretation

R4B answers three narrow questions about one very small byte-level model:
whether any text is emitted, whether exact instruction markers are produced,
and whether exact multiple-choice labels are produced. It does NOT show that
the native model learned from external AI, that a second brain is online, or
that it is globally incapable of reasoning.

Until authenticated real external calls can be made under verified free-only
conditions, both External and Bicameral scientific comparisons remain
NOT_EXECUTED. The next admissible gate is a separately preregistered matched
three-arm evaluation with independent hidden holdout and human-adjudicated
safety/quality, not another synthetic vote.

No change to productive HOME, ACK, Git control-plane authority, model weights,
or self-training is authorized by this report. GitHub hosted CI may consume
the user's runner minutes; no rented GPU or paid model API is required.
