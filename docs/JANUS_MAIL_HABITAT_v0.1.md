# JANUS MAIL Habitat v0.1

`MAIL-HABITAT-00` is the first bounded extension of JANUS Habitat from repository topology into an external communication environment.

It does **not** make Gmail a command bus and does not grant JANUS autonomous correspondence authority.

## Canonical model

```text
HABITAT = HOME / MEMORY / EXISTENCE TOPOLOGY
NEXUS   = TYPED ROUTING / NERVOUS TRANSPORT
MAILBOX = SOURCE AUTHORITY FOR MAIL CONTENT
REGISTRY = PROVENANCE / RECEIPTS, NOT PRIVATE MAIL MIRROR
```

## Phase 00

```text
MAIL PROVIDER
  -> authorized read observation
  -> privacy normalization
  -> MAIL_OBSERVATION
  -> Nexus read-only envelope
  -> context / bounded classification
  -> next-gate recommendation
  -> receipt
```

No mailbox mutation is admitted in this phase.

## Capability ladder

| Level | Capability | Phase 00 |
|---|---|---:|
| M0 | Observe metadata/history delta | allowed |
| M1 | Read selected authorized content | allowed as input to normalization |
| M2 | Organize/label mutation | forbidden / later gate |
| M3 | Draft creation | forbidden / later gate |
| M4 | Send | forbidden / explicit human gate required |
| D* | Trash/delete/bulk effects | separate capability, never inherited |

## Privacy boundary

The public/reference `MAIL_OBSERVATION` does not contain:

- raw body;
- raw subject;
- raw sender address;
- provider message ID;
- provider thread ID;
- attachment bytes;
- credentials or OAuth tokens.

Provider references are transformed using domain-separated SHA-256 references. These hashes are provenance handles, not proof that message content is true.

## Reference implementation

- `protocol/JANUS_MAIL_HABITAT_v0.1.json` — frozen contract.
- `schemas/mail-observation.schema.json` — public receipt schema.
- `tools/mail_habitat_normalizer.py` — deterministic offline normalizer; no network calls.
- `examples/mail_habitat_private_runtime_fixture.example.json` — synthetic private/runtime-shaped input.
- `tests/test_mail_habitat_normalizer.py` — replay, redaction, authority and fail-closed tests.

Run locally from repository root:

```bash
python -m unittest tests.test_mail_habitat_normalizer
python tools/mail_habitat_normalizer.py examples/mail_habitat_private_runtime_fixture.example.json
```

## First live adapter gate

A future Gmail adapter may be admitted only after this offline boundary is accepted. It should keep provider checkpoint/history state private at runtime and emit only normalized observations downstream.

Required before a live adapter can be called admitted:

1. least-privilege read-only provider access;
2. incremental history/delta checkpointing;
3. stale checkpoint and expired-history fail-closed behavior;
4. idempotent duplicate replay;
5. attachment metadata boundary;
6. no mutation methods in the adapter surface;
7. secret-scanning / credential non-persistence;
8. exact-head tests and registry receipt.

## Research-reply vertical

The first useful live vertical is intentionally narrow:

```text
incoming research reply
 -> existing thread identity
 -> project/gate mapping
 -> REVIEW_FEEDBACK / DATA_OFFER / QUESTION / ...
 -> next gate recommendation
 -> human-visible notification
 -> NO AUTO-REPLY
```

This can eventually replace the current reminder-style reply watcher with a durable Habitat contract while preserving the same scientific rule:

```text
EXTERNAL INTEREST != VALIDATION
REVIEW FEEDBACK != PROOF
DATA OFFER != GATE PASS
```

## Constitutional invariants

```text
READING != AUTHORITY
UNDERSTANDING != AUTHORITY
DRAFTING != SENDING
ROUTE != DELIVERY
DELIVERY != TRUTH
MAILBOX_SOURCE != PUBLIC_REGISTRY
CLASSIFICATION != VALIDATION
CONNECTIVITY != AUTHORITY
CONNECTION PRESERVES PROVENANCE
CONNECTION DOES NOT CREATE AUTHORITY
```

## Claim ceiling

This branch establishes a deterministic, privacy-bounded **offline reference contract** for a future Mail Habitat adapter. It does not establish a production mail service, autonomous agent correspondence, live Gmail ingestion, or any permission to mutate a mailbox.
