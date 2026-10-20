# JANUS Corpus — AURA → real free GOLEM → native Demiurge review (draft R0)

This new **opt-in, separate experimental sidecar** is not a replacement for
Corpus Callosum v2 (which is still explicitly simulated) or the merged AURA
advisory integration. It does **not** edit their receipt format.

## Code and evidence chain

`tools/janus_corpus_aura_golem_live.py` performs:

1. Revalidate the pre-existing, pinned real local AURA advisory receipt **and**
   its upstream Corpus v2. If either is absent or tampered, do not call GOLEM.
2. Extract a bounded **question** from AURA (heuristic, not evidence). Send
   only this question, SHA-256-derived pseudonymous context labels and bindings to a
   specifically selected free-plan model. No raw native generations, protected
   HOME text, model checkpoint, token or full conversation is sent.
3. Reuse `golem_free_federation`'s existing fixed providers, fixed model IDs,
   exact HTTPS endpoints, bounded `request_free_provider` call, and the shared
   durable `golem_adaptive_tower` quota / cooldown state. One request only;
   **no paid fallback, retry loop, dynamic URL or external tools**.
4. Parse a three-field JSON response. Validate context-ID subset, fixed intake
   marker, size and type bounds; record the actual provider name, requested
   model, and separately the model ID asserted in the server response.
5. Pass only a bounded, visibly untrusted excerpt to native Demiurge, with
   the exact same pinned checkpoint hash as the original Native stage.
6. Verify protected HOME state remains unchanged, then save an exclusive
   `corpus_aura_golem_live/` sidecar. Neither an AURA card nor a model answer
   can train weights, grant permissions, advance ACK or establish scientific
   truth. Independent replay validates the receipt's source bindings and
   native review (but cannot authenticate a historical HTTPS response).

The pre-existing Corpus v2 chain still contains a simulator. The new sidecar
may record a **separate real provider call** after that simulation; the old
simulation is NEVER rewritten or mislabeled as external AI.

## Explicit opt-in (operator-managed free account only)

This draft defaults to dry-run. Live mode requires all three separate gates:

```text
JANUS_CORPUS_AURA_GOLEM_LIVE_ENABLED=1
JANUS_GOLEM_FREE_ENABLED=1
JANUS_GOLEM_NO_BILLING_CONFIRMED=1
```

The operator must separately set an existing fixed provider key and explicit
name, for example `JANUS_CORPUS_AURA_GOLEM_PROVIDER=openrouter-free` with
`JANUS_GOLEM_OPENROUTER_TOKEN` provided through a **private** environment,
never committed to Git. Other pre-existing allowlisted routes require their
corresponding original account/plan gates. Confirm no billing is enabled on
the provider account; the code's flag alone cannot verify account status.

Official OpenRouter shows `openrouter/free` at zero prompt and completion
token price, but the selected underlying free model can change. Free quotas,
uptime, restrictions and availability depend on the provider.

Example (after the operator has provisioned clean, pinned checkouts and a
verified HOME fixture):

```bash
python tools/janus_corpus_aura_golem_live.py --home-root /path/to/research-home
python tools/janus_corpus_aura_golem_live.py --home-root /path/to/research-home \
  --native-repo /path/to/pinned-Demiurge --native-head FULL40HEX --execute
```

No program path is an invitation to point the tool at production HOME; test
in an isolated research HOME. One network call to a selected third party is
an external data disclosure of the AURA question and context identifiers.

## What is actually established

- Local, offline **contract tests**: validate opt-in, provider allowlist,
  response schema, no false real provenance for injected fixtures,
  hash binding, no secret in receipts, native-review checkpoint match,
  no network on dry run, and exclusive append-only receipt.
- Real provider inference: **NOT PERFORMED** in this checkpoint. No private
  provider token was found or used in this experiment; do not substitute an
  offline fixture and call it real.
- Synthetic test transport emits `TEST_TRANSPORT__NOT_REAL_EXTERNAL`.
- The real default transport, if executed under valid operator configuration,
  would emit `REAL_EXTERNAL_RESPONSE__UNVERIFIED` (not a science verdict).
- Provider output can be useful as hypotheses to check, never as a witness
  proving its own facts. Native review quality is not established.
- No production HOMЕ promotion, durable publish, code merge, auto-training,
  claimed precognition, or authority changes.

## Scientific next gate

Run a fresh, consented provider request on an isolated HOME, record the actual
endpoint-model receipt and separately blind-score the output quality.
Compare Native-only, free-GOLEM-only and AURA→GOLEM→Native against one
independently preregistered answer set. Do not use model-generated judgments as
their own gold labels.

`AURA_GOLEM_LIVE_ADAPTER = DRAFT_SOFTWARE_CONTROL`

`EXTERNAL_LLM_LIVE_RESPONSE_OBSERVED = FALSE`

`AURA_ORACLE_EVIDENCE_AUTHORITY = ZERO`

`CORPUS_V2_SIMULATED_RESULT = PRESERVED`
