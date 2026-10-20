# JANUS Corpus Callosum + real AURA Oracle local peer (research v1)

**Repository:** Hawkar-usls/aura-oracle-tg
**AURA SHA pinned for integration:** d04d9d0e5d14c0849cde33925974300f722e69cc
**Genesis component:** tools/janus_corpus_aura_oracle.py
**Default:** disabled. No live remote model API, no ongoing autonomous daemon.

## Exact role and existing prior work

This does NOT replace existing Genesis Shabitat ↔ AURA
genesis_v18_7_51_shabitat_aura_oracle.py. It reuses that module's
build_aura_request and validate_aura_response contracts, and calls the
pre-existing AURA entrypoint tools/aura_shabitat_heuristic.py. That entrypoint
is a deterministic card/keyword reflective system, **not a language model**.
It is not CHRONOS precognition, a forecast result, proof, action authorization,
a neural-net inference source, or a second independent scientific witness.

AURA already has semantic/predictive spiral, Meta Registry read-only indexing,
forecast ledger and Fortune Cookie machinery. None of these higher capability
claims are promoted or silently invoked by this narrowly specified peer.
CHRONOS Draft PR #3 is not adopted as approved main code by this bridge.

## Topology and workflow

    verified Beetle context
             |
     Native Demiurge CPU
             |
     simulated External GOLEM (offline-only Corpus v2)
             |
     Native Demiurge CPU review
             |
     attested immutable Corpus v2 receipt
             |
             +-- optional pinned local AURA Oracle
                      symbolic THREAD / LANTERN / alternatives
                      practical missing questions and cautions
                              |
                    separate AURA heuristic receipt

AURA receives only the attested v2 receipt digest, context SHA-256, bounded
untrusted first native text and the explicit label that the external source
was SIMULATED or UNAVAILABLE. It is not permitted to treat the simulator as
a real upstream model. Source repositories, components and the exact Git
commit are recorded in a separate advisory receipt.

The local AURA execution requires the manual opt-in
JANUS_CORPUS_AURA_ENABLED=1 and a local clean checkout at the immutable
pinned Git commit. Genesis invokes only the existing AURA Python CLI in a
subprocess receiving a stripped environment without GitHub/provider secrets,
with bounded runtime and JSON input/output, no supplied shell commands.

The bridge validates the existing AURA Shabitat response contract (schema,
request ID, request digest, engine, bounded symbolic cards/questions, strict
authority booleans) before storing an append-only receipt under the
corpus_aura_oracle directory. Existing v1/v2 receipts and protected Genesis
STATE.json, Beetle CONTEXT.json and CURSOR.json remain byte-identical.

On missing or tampered v2 evidence the Oracle subprocess never runs.
Wrong AURA source SHA, dirty checkout, forged requests, unsafe response,
false scientific/prediction claims, permission grants or writes to the
protected files fail closed. If AURA is unavailable, the two hemispheres
and original Corpus v2 receipt remain unaffected.

## Integrity limitations

A receipt's SHA-256 is an integrity fingerprint **not** a digital signature:
a writer with permission to alter all receipt bytes could change text
and recompute the hash. A separate authenticated Git-history/high-water
witness is necessary against adversarial history rewrites. No remote
production HOME publisher for corpus_aura_oracle is enabled. The new
sidecar is witnessed locally during the CI test, not claimed durably
published to the production HOME branch.

## Real CI evidence gate

The existing read-only Corpus workflow checks out:

- Reviewed Demiurge SHA 8873e5121a67daac5c8afb8ff297d6565dc87c32,
  with its secure checkpoint loader from still-draft Demiurge PR #301.
- Reviewed real AURA main SHA d04d9d0e5d14c0849cde33925974300f722e69cc.

The CPU integration performs two genuine Demiurge generations with a
mocked external network answer, then runs the genuine deterministic AURA
Shabitat CLI on the resulting v2 receipt. It asserts strict evidence
boundaries, pinned revisions, nonempty cards/questions, unchanged HOME
core and unchanged source worktrees. All Git recovery operations use a
disposable local bare remote. Production HOME is not written.

## Next legitimate extensions

- Explicitly make AURA's verified, read-only semantic index answer local
  *source queries* with provenance, only after an independently reviewed
  adapter and separate knowledge-source status.
- Introduce authenticated forecast ledger reporting as **forecasts**, with
  external resolution and precommitment. Do not equate time-of-publication
  hashing or a symbolic card with physical foresight.
- If the user supplies a genuinely no-billing external provider, add a
  separate checked interface for a real GOLEM model; preserve the provider
  identity and test on an independently frozen holdout.

NO_ORACLE_RESPONSE_IS_PROOF. NO_ORACLE_RESPONSE_GRANTS_PERMISSION.
NO_ORACLE_OUTPUT_AUTOTRAINS_NATIVE. NO_HIDDEN_PAID_MODEL_FALLBACK.
