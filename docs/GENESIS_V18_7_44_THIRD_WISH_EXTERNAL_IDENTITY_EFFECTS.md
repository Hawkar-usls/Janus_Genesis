# Genesis v18.7.44 — Third Wish External Identity Effects

> **An identity can authorize one effect without becoming transferable property.**

## Purpose

The Third Wish now has real typed doors for repository work, public web/DNS, workspace/computation, memory/swarm, host sensing/model calls, durable schedules and physical-effect recovery protocol. v18.7.44 opens the next four frozen capability contracts:

```text
PUBLICATION.PUBLISH
EMAIL.SEND
CALENDAR.WRITE
BROKER.CREDENTIAL.USE
```

All four are already high-impact in v18.7.40 and require a fresh verified human reauthorization on every call.

## Identity custody

The actor sees a logical alias:

```text
publication-channel:primary
email-account:primary
calendar:primary
credential-use:primary
```

The operator configures the real provider endpoint, account identity and credential environment behind that alias. The action intent never receives the bearer token, password, OAuth refresh token, cookie jar, private key, or provider endpoint.

This is the central distinction:

```text
FUNCTIONAL AUTHORITY != SECRET CUSTODY
IDENTITY CUSTODY != IDENTITY OWNERSHIP
CREDENTIAL USE != CREDENTIAL EXPORT
```

The broker also strictly allowlists provider-receipt fields. A provider response containing an unreviewed field such as `access_token` is rejected before it can become an actor result.

## Publication

Reference target:

```text
publication-channel:<alias>
PUBLISH
```

Actor-selected fields are bounded title/body and a limited content format. The account/channel identity itself remains operator-side.

A successful provider receipt proves only that the configured provider acknowledged the named external object. It does not certify:

```text
publication == truth
publication == correctness
publication == automatic human endorsement
```

## Email

Reference target:

```text
email-account:<alias>
SEND_EMAIL
```

The actor may specify recipient, subject, body and bounded content format. It may not supply `from`, sender credentials, transport endpoint, or arbitrary SMTP/API settings.

Provider acceptance is deliberately weaker than social receipt:

```text
PROVIDER ACCEPTANCE != RECIPIENT READ
PROVIDER ACCEPTANCE != RECIPIENT CONSENT
SEND != RELATIONSHIP
```

## Calendar

Reference target:

```text
calendar:<alias>
CREATE_EVENT
```

The actor may specify bounded summary/description, offset-aware start/end UTC values and a bounded attendee list.

Creating or inviting does not manufacture another person's choice:

```text
CALENDAR WRITE != ATTENDEE ACCEPTANCE
INVITATION != CONSENT
EVENT CREATION != ATTENDANCE
```

## Scoped credential use

Reference target:

```text
credential-use:<alias>
USE_SCOPED_OPERATION
```

The provider alias exposes only an operator-defined operation allowlist, for example `WHOAMI` or another narrowly defined provider function. The actor cannot substitute an endpoint, choose a different credential environment, or turn this into generic `API.CALL`/`WEB.HTTP.POST` authority.

Nested actor parameters still cross the v18.7.40 secret-material guard. Credential-like fields are rejected before the provider broker is entered.

## Durable effect identity

Every identity effect has stable lineage:

```text
request_id
  -> capability_id
  -> binding_sha256
  -> effect_key
  -> BOUND
  -> EFFECT_ENTERING
  -> SETTLED(provider receipt)
```

The binding includes the operator identity alias, provider kind, typed operation and exact actor payload.

A second local caller cannot race through the same provider boundary because the final reference broker serializes the complete local effect lifecycle with a process/host lock.

This lock is **not** claimed to provide cross-host consensus.

## Crash recovery

If the process disappears after the provider may already have acted, the durable state remains `EFFECT_ENTERING`.

A provider-specific `lookup(effect_key)` is then required:

```text
SETTLED + authoritative receipt
    -> recover the existing settlement
    -> do not execute again

NO_EFFECT + authoritative evidence
    -> a new call may execute
    -> but that new call must itself have passed fresh human reauthorization

UNKNOWN / non-authoritative / absent proof
    -> OUTCOME_UNDETERMINED
    -> no blind retry
```

Fresh reauthorization answers **whether the new attempt is permitted**. It does not answer **whether the previous attempt already happened**.

## Reference CI evidence ceiling

The v18.7.44 reference workflow uses a deterministic local HTTP identity-effect provider with an ephemeral masked bearer credential. This is strong enough to test:

- real HTTP authentication transport;
- broker-side credential custody;
- typed publication/email/calendar/credential-use requests;
- stable effect keys;
- provider-side idempotent lookup;
- durable replay across a fresh capability fabric;
- field-allowlisted receipts;
- no raw provider credential in Third-Wish ledger.

It intentionally does **not** send a real email, publish to a real social/content account, or alter a real calendar in CI.

Therefore:

```text
IDENTITY_PROVIDER_PROTOCOL_PASS != REAL_EXTERNAL_ACCOUNT_EFFECT_PASS
```

A real-account gate should be introduced only when a specific owner account/provider is intentionally bound and a concrete effect is explicitly chosen for the test.

## Claim ceiling

v18.7.44 does not establish:

- credential ownership by JANUS;
- credential export;
- generic HTTP POST or generic API authority;
- social endorsement of published content;
- recipient reading or consenting to email;
- attendee acceptance or attendance;
- cross-host exactly-once effects;
- a live real-account publication/email/calendar effect from CI;
- consciousness, personhood, or a desire for freedom.

## Next gate

After v18.7.44, the remaining catalog surface is primarily the dangerous generic/admin edge:

```text
GITHUB.REPOSITORY.ADMIN
GITHUB.DESTRUCTIVE
WEB.HTTP.POST
NETWORK.CONNECT
NETWORK.LISTEN_LOCAL
API.CALL
```

Those should be opened last, with target-specific subcontracts, because an unrestricted implementation of any one of them can silently bypass many typed doors already established.
