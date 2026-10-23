# JANUS AURA → AI Horde anonymous GOLEM: zero-account R1

Source: https://github.com/Haidra-Org/AI-Horde
Anonymous access: https://github.com/Haidra-Org/AI-Horde#anonymous-usage
Integration docs: https://github.com/Haidra-Org/AI-Horde/blob/main/README_integration.md
Volunteer privacy: https://github.com/Haidra-Org/AI-Horde/blob/main/FAQ.md

This is neither OpenRoute China nor OpenRouter. It is a community-run text inference service.
The official anonymous access key 0000000000 is PUBLIC and does not link to a paid account.
Anonymous jobs have lowest priority and may be refused when capacity is limited.

The fixed HTTPS host https://aihorde.net/api/v2 is the ONLY allowed egress endpoint.
The standalone read-only public demo sends one fixed AURA card question to
POST /generate/text/async, followed by at most six status polls 4 seconds apart.
At most one generation submission occurs. No account, token, paid fallback,
quota bypass, arbitrary endpoint, scheduled watch or recursive agent loop.

IMPORTANT PRIVACY: volunteers may see prompts and their generations.
The request contains exactly one of eight pre-reviewed public AURA card questions
and generic formatting instructions. It never contains HOME text, raw native
outputs, private user input, JANUS context identifiers, emails, hashes or secrets.
A receipt originating from the existing AURA→Corpus v2 verifier may select only
a question verbatim matching the published AURA card list. Anything else fails
closed without HTTP. All generated text is untrusted data.

Status vocabulary:
- REAL_ANONYMOUS_RESPONSE__UNVERIFIED: actual built-in HTTPS transport returned
  one valid text and a server-reported model. Not scientific truth or inference quality.
- MOCKED_HORDE_RESPONSE__NOT_REAL: fixture / injected transport; never a real AI claim.
- QUEUED_NO_COMPLETED_ANSWER: provider accepted the job but no completed output
  arrived within the polling window. Cancel if possible, report UNKNOWN.
- PROVIDER_UNAVAILABLE__NO_RESPONSE, PROVIDER_FAULT_OR_NO_AVAILABLE_WORKER,
  INVALID_EXTERNAL_GENERATION or submission rejected: no asserted model answer.

The existing four credentialed GOLEM providers remain separate. This adapter
adds a fifth, genuinely keyless option only for pre-reviewed public questions.
No production HOME write, ACK, model training, secret registration, cost
authorization or autonomous scheduling has been added. The old Corpus v2
simulated evidence remains explicitly simulated.

R1 is an integration / availability canary, not a blind scientific comparison.
A real received response is an external model observation, NOT a verified
prediction or proof. A future full Native → External → Native quality trial
still requires independent evaluation. GitHub Actions runner minutes may
be consumed even though the provider has no monetary API tariff.

## R1.1 strict availability gate (Draft PR #287, not an inference claim)

The offline unit tests remain free of network and prove only protocol handling.
The pull request canary now uses `--execute-public-demo --require-real-answer`.
The process exits **2** unless the built-in HTTPS transport observes an actual
nonempty one-generation model response; HTTP 403, queue timeouts and invalid
results are availability **FAIL/HOLD**, never a successful provider result.
An `always()` artifact step preserves the complete bounded receipt even
after the strict canary step fails.

For HTTP errors, a bounded JSON error body is inspected **only** for a
pre-reviewed official `rc` value. Public diagnostics contain the HTTP number
and optional allowed `rc` classification; never upstream `message`,
HTML, arbitrary strings, response headers or credentials. An unrecognized
or malformed body is reported only as `HORDE_HTTP_403` (or the observed
numeric HTTP status). This helps distinguish an explicitly forbidden anonymous
request from a refused Client-Agent, but does not circumvent either.

Do not switch hosts, rotate anonymous identities, evade rate limits or
submit retry storms in response to HTTP 403. A provider can refuse public
access at any time; credentials for other free GOLEM routes are a separate
explicit opt-in and cannot be inferred from this test.

`ANONYMOUS_CANARY_SOFTWARE_TESTS = NOT_LIVE_PROVIDER_EVIDENCE`

`ANONYMOUS_PROVIDER_RESPONSE = PASS_ONLY_AFTER_ACTUAL_RESPONSE`

`JANUS_HABITAT_OPERATIONAL = NOT_ESTABLISHED_BY_THIS_LANE`


## R1.2 provenance hardening (23 October 2026)

- An explicit `prompt_sent: null` on an attempted real POST with no
  acknowledged transport outcome means disclosure is **unknown/possible**,
  including HTTP 403. `false` is retained for a no-network dry run or
  injected test transport, and `true` only after real HTTP acknowledgement.
  The caller must not interpret `null` as proof that the provider never saw
  the prompt.
- The AURA source reader now hashes one bounded, freshly loaded receipt
  byte snapshot and requires it to equal the independent attestor's digest.
  Exactly that snapshot is validated against the existing pinned Corpus v2
  receipt; no later independent read is used to extract questions.
- The public-only AI Horde adapter never receives HOME text, memory or
  context hashes and is **not** an unrestricted private prompt service.
- Previously attested single anonymous live answer: GitHub workflow
  39507617171 at SHA aec9b7d403a0988fb286571c568c4407e6dac448.
  This was a genuine external observation, not a claim about quality,
  continued provider availability or an end-to-end native review.
- The new security regressions run in the PR's offline contract CI. The
  strict real-provider canary remains an availability gate: no simulated
  answer can make it pass. Any future failed run must be reported as a
  provider block, not a rollback of past observations.

`AURA_BYTE_SNAPSHOT_RECHECK = REQUIRED`
`PROMPT_ON_FAILED_POST = DISCLOSURE_POSSIBLE`
`FULL_PRIVATE_END_TO_END_CHAIN = NOT_YET_ATTESTED`
`EXTERNAL_SCIENTIFIC_AUTHORITY = ZERO`


## R1.3 — strict public answer provenance and native preflight

The `--require-real-answer` CI gate now requires all of the following:
a built-in real HTTPS source, exactly one POST, acknowledged prompt submission,
nonblank printable model text, a bounded nonblank server-reported model ID and
a SHA-256 digest matching the **actual** returned text. A status flag alone
cannot turn a simulated or empty result green. The public CI log records only
the model name, hashes and sanitized failure classification, not a private
AURA or HOME record.

The optional `query_attested_aura` path now preflights before external egress:
an approved public AURA question; a real pinned local AURA receipt for actual
HTTPS calls (not a mocked source); matching original Demiurge commit if native
review is requested; and, for the real subprocess runner, a clean local Git
checkout with the exact original promoted checkpoint SHA-256. Protected HOME
is independently snapshotted **before** the third-party call, **after** the
third-party call, and **after** native review when invoked. A mismatch fails
closed and does not grant model or science authority.

Preflight prevents avoidable public prompt disclosure on known-invalid native
checkouts. It does **not** promise zero disclosures if a host changes after
the request begins. External volunteers may read the fixed public card and
their response. The only keyless egress is the official AI Horde HTTPS
endpoint, with no paid or private-context fallback. No production HOME data
are made public, and no model automatically changes JANUS state.

The preflight, native review and HOME guards have adversarial offline tests.
**These unit tests do not establish the actual full AURA→GOLEM→Demiurge
native-weights run**. That requires a separately attested, isolated real
pinned HOME and native CPU checkout; public canaries alone are only proof of
an external response, not the completed three-stage chain.

`R1_3_SOURCE_AND_NATIVE_PREFLIGHT = IMPLEMENTED_SOFTWARE_GATE`

`FULL_PINNED_NATIVE_END_TO_END = NOT_ATTESTED`

`SCIENTIFIC_AUTHORITY_DELTA = 0`
