# JANUS CORPUS CALLOSUM v1 — two independent hemispheres

Status: **IMPLEMENTED AND OFFLINE-TESTED; LIVE BICAMERAL INFERENCE NOT YET OBSERVED**.

First-party identity and memory remain native. An explicitly allowed external
GOLEM free account is an advisory inference source, never a second repository
controller, a training authority, or an independent scientific proof.

## Connection map

```
verified Beetle context and sequence
       |                   |
       v                   v
Native Demiurge         GOLEM free federation
pin by Git HEAD         manual free-only gate, daily caps,
promoted checkpoint     429 cooldown, provider receipt
       |                   |
       +---- concurrent ---+
                  |
          CORPUS CALLOSUM
          exact context hash
          separate native/external provenance
          deterministic joined presentation
                  |
     Genesis HOME corpus_callosum/*.json
     scientific authority 0; ACK unchanged
```

## Exact native model

The native inference implementation is **not** a mocked personality in
production. It calls `python -m janus_model.cli run` in a *local checked-out*
`Hawkar-usls/Janus-Demiurge` at an explicitly specified, clean, full git
commit SHA. It uses the existing promoted `janus_model/checkpoints/promoted.pt`
and records that checkpoint's SHA-256, model output, challenge prompt hash,
and Git source identity. The process receives a **stripped environment** with
no GOLEM tokens, GitHub credentials, or cloud billing variables.

The currently promoted byte-level Transformer is deliberately small: the
native challenge has a strictly bounded 96-byte prompt and is not a substitute
for a large instruction-following model. The native model can return weak or
unintelligible output. That output is never silently replaced with fabricated
"JANUS intelligence". Its backend has to be provisioned **separately** with
PyTorch on CPU; this feature does not download packages or execute binaries
automatically on GitHub Actions.

## Real external model

The external worker reuses `tools/golem_free_federation.py` without changing
its allowlisted providers, receipts, or daily attempt budgets. It requires
**both** opt-ins (`JANUS_BICAMERAL_ENABLED=1`,
`JANUS_GOLEM_FREE_ENABLED=1`), plus an independently configured eligible
free-plan provider token. A validated GOLEM receipt must reference source IDs
present in the exact trusted Beetle context. Every result retains the real
provider and requested/reported model; no source is represented as native
weights. A missing provider means an honestly partial native-only result.

## State, failure, rollback

- Nothing executes or writes state by default. `--execute` is an explicit
  invocation, not an always-on cloud daemon.
- The two hemispheres run concurrently in two bounded workers. One may fail
  without canceling the other; failures are reported as statuses, not AI text.
- A durable, checksum-bound receipt is written atomically under
  `corpus_callosum/` only when at least one verified lane actually responded.
- States: `BICAMERAL_PAIR_OBSERVED__UNVERIFIED`,
  `NATIVE_ONLY__EXTERNAL_UNAVAILABLE`,
  `EXTERNAL_ONLY__NATIVE_UNAVAILABLE`, or
  `CORPUS_CALLOSUM_NO_HEMISPHERE_RESPONSE` (**no combined receipt**).
- A receipt is for one context identity only. Retries of that same context
  skip inference if a receipt exists; a new delivery sequence starts a new
  comparison. A future version can safely append a later join for a partial
  receipt without overwriting the first witness.
- The combined answer displays the two voices side by side. **Textual
  concatenation is not semantic agreement**; no "consensus proof" is claimed.
- `feedback_for_native` retains only an untrusted external answer digest.
  There is **no automatic training on vendor outputs**, no automatic
  code-edit authority, and no unconditional promotion of new model weights.
- Native model promotion/rollback stays with Demiurge's existing
  frozen-anchor and evaluation-gated checkpoint policy.
- HOME writes must remain serialized by GitHub Actions. As elsewhere, a
  runner that disappears before `git push` may lose local data; the checksum
  does not replace the independent history witness.

## Manual use on a provisioned machine (never run without consent)

1. Arrange read-only local checkouts of Genesis HOME and **a fixed Demiurge
   Git commit SHA**, plus an installed compatible PyTorch CPU environment.
2. Validate the new bridge without inference:

   ```bash
   python tools/janus_corpus_callosum.py --home-root /path/to/genesis-home
   ```

3. For explicit live use, configure known eligible free-plan provider secrets
   in environment configuration, ensure the Git checkout is clean, and invoke:

   ```bash
   JANUS_BICAMERAL_ENABLED=1 JANUS_GOLEM_FREE_ENABLED=1 \
     python tools/janus_corpus_callosum.py --execute \
     --home-root /path/to/genesis-home \
     --native-repo /path/to/Janus-Demiurge \
     --native-head <exact-full-40-character-commit-SHA>
   ```

The external API is not exercised by default. Do not paste tokens into
commands or commit them. Manual execution on a local checkout does not
automatically commit the result to Genesis HOME; the subsequent production
integration needs a reviewed and serialized cloud writer.

## Remaining before claiming a live two-brain system

1. Verify actual promoted native inference from a pinned Demiurge checkout in
   an isolated runtime that has PyTorch installed. Record output and latency.
2. Obtain a genuinely free, nonbillable provider account; add its credential
   only as an encrypted secret and manually approve one real call.
3. Build a HOME writer for the `corpus_callosum/` receipts using the already
   serialized Genesis commit/witness protocol, with crash recovery.
4. Register an evaluation harness that judges output quality and disagreements
   independently, then add consent/terms-controlled feedback for future native
   learning. Do not promote weights or code from model votes alone.
