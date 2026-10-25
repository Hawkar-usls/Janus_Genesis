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


### Opt-in strict three-stage CLI (isolated research HOME only)

When the owner of an isolated, independently validated research HOME and a
clean pinned `Janus-Demiurge` checkout chooses to run all three stages, use:

```bash
python tools/golem_ai_horde_anonymous.py \
  --execute-public-demo \
  --home-root /path/to/isolated-research-home \
  --native-repo /path/to/clean-pinned-Janus-Demiurge \
  --native-head FULL_40_HEX_NATIVE_COMMIT \
  --require-real-answer --require-native-review \
  --out /path/to/research-receipts/keyless-r13.json
```

`--require-native-review` exits nonzero unless a genuine digest-bound
anonymous HTTPS answer **and** an exact-checkpoint pinned local Demiurge
review both exist, with AURA source hashes attached locally. Missing or
mismatched flags fail before contacting a provider. The public CI runs
only the generic question canary; it does not have the operator's HOME
or native model and cannot assert completion of this full three-stage
path. This CLI is an opt-in research sidecar, not an instruction to expose
production HOME. Nothing in the provider answer is granted authority
to modify user data, code, coins, inventory, ACK or model weights.

`REAL_NATIVE_E2E_R1_3_RUN = NOT_OBSERVED`


### Armor effect-inventory boundary

The optional R1.3 pinned-native preflight invokes `git rev-parse` and
`git status` in a sanitized environment to **inspect** an existing local
checkout. This adds a direct subprocess effect to the keyless adapter.
`audit_armor_effect_drift_v18_7_50.py` classifies it explicitly as an
**opt-in research-only, not Armor-admitted** effect surface. Classification
does not grant production admission and does not establish whole-repository
Armor routing coverage. No subprocess is started by the default standalone
public canary.

`GOLEM_NATIVE_PREFLIGHT_ARMOR_ADMISSION = NO`


### R1.3.1 — no-leak invalid-generation diagnostics

An invalid upstream `done=true` generation remains a **failed** live canary:
`status=INVALID_EXTERNAL_GENERATION`, `response=null`,
`network_model_response_observed=false`. For diagnosis only, the saved receipt
now contains a bounded **reviewed enum** as `failure_class`:

`HORDE_GENERATION_ENTRY_INVALID`,
`HORDE_GENERATION_TEXT_MISSING`, `..._TEXT_BLANK`,
`..._TEXT_OVERSIZE`, `..._TEXT_CONTROLS`,
`..._MODEL_MISSING`, `..._MODEL_OVERSIZE`,
`..._MODEL_CONTROLS`.

No invalid upstream model label, raw text, arbitrary error message, or prompt
is copied into the diagnostics. The failure classification does not
trigger another POST, rotate worker identities, or count as real inference.
Valid multiline answers are still allowed; nonprintable or blank model names
cannot populate success logs. The strict end-to-end gate also requires
valid 64-character hexadecimal hashes for AURA and context receipts rather
than accepting arbitrary nonempty labels.

The earlier failed canary run #39937556471 cannot be diagnosed retrospectively
beyond `INVALID_EXTERNAL_GENERATION`, because its recorded evidence has no
reason code. Later runs can be distinguished without retaining provider text.

`INVALID_GENERATION_REASON = SANITIZED_CLASSIFICATION_ONLY`
`INVALID_GENERATION_NETWORK_SUCCESS = FALSE`
`LIVE_NATIVE_END_TO_END = NOT_ATTESTED`


### R1.3.2 — native checkpoint descriptor hardening

The optional pinned-local Demiurge preflight no longer trusts a path stat
followed by an unrestricted `Path.read_bytes()`. It opens the native checkout,
`janus_model`, `checkpoints`, and `promoted.pt` through a directory-descriptor
chain with `O_NOFOLLOW`, checks that the opened leaf is a regular file via
`fstat`, and reads no more than 100,000,001 bytes before hashing. A replaced
symlink, directory traversal into a link, FIFO/device, oversized or mismatched
checkpoint fails closed **before public AURA question egress**. Offline
regressions cover the correct byte snapshot and an identical-content symlink
swapped immediately before the final open.

This protects the **preflight stage**, not the entire filesystem from hostile
concurrent mutation. A real native review still requires the independent
pinned source/weights receipt and the protected-HOME checks. The public
no-HOME canary cannot prove this real native chain.

`NATIVE_PRE_EGRESS_CHECKPOINT_DESCRIPTOR = HARDENED`

`NATIVE_REVIEW_PROVEN_AT_RUNTIME = NOT_YET`


### R1.3.3 — hostile checkout Git configuration hardening

The optional real native preflight now runs read-only Git checks with
`GIT_OPTIONAL_LOCKS=0`, disabled system/global Git configuration and terminal
prompts, `core.fsmonitor=false`, `core.hooksPath=/dev/null`, and
`status.showUntrackedFiles=all`. It explicitly requests
`--porcelain=v1 --untracked-files=all --ignore-submodules=none` and rejects
any dirty/unignored untracked checkout before external public-card egress.
Offline adversarial tests assert the exact command and sanitized environment
and reject a checkout with a newly introduced untracked Python file.

Git ignores may conceal executable source from normal `status`.
The preflight now additionally enumerates ignored files with
`git ls-files --others --ignored --exclude-standard -z` and rejects
ignored Python/native loadable suffixes (`.py`, `.pyc`, `.so`, `.pyd`,
`.pth`, and their platform equivalents) or an oversized inventory.
The ignored promoted `.pt` checkpoint is allowed only if the separate
no-follow descriptor hash equals the original trusted checkpoint SHA-256.
The new code has adversarial cases for ignored Python modules and shared
libraries, including filenames protected by NUL-delimited parsing.

**Boundary:** This is an *inventory* of known executable suffixes, not a
sandbox or proof that all executable loaders and dynamically evaluated files
are absent. Concurrent mutations and unexpected loader mechanisms remain
possible. A stronger isolation boundary or exact file manifest would be
needed before making an end-to-end source/weight guarantee.

`R1_3_3_GIT_CONFIG_AND_FS_MONITOR_GUARD = IMPLEMENTED`

`IGNORED_EXECUTABLE_SUFFIX_INVENTORY = FAIL_CLOSED`

`IGNORED_EXECUTABLE_FILE_ABSENCE_PROVEN = NOT_UNIVERSAL`

`FULL_REAL_NATIVE_E2E = NOT_ATTESTED`


### R1.4 — Native review causal replay and private receipt file

The optional native three-stage research result now includes a local-only
**allowlisted native review projection** and the locally pinned source commit,
checkpoint SHA-256, AURA public card, AURA/context digests and context sequence.
The strict `--require-native-review` gate recomputes the exact public prompt,
the answer-to-native `JANUS:REVIEW_UNTRUSTED` prompt, the native review's
prompt SHA-256 and schema, the original checkpoint binding and the full
review SHA-256. Merely setting `native_review_status` and supplying a
64-character digest cannot create a passing replay. Adversarial offline tests
modify individual links of the causal chain and require fail-closed decisions.

**Important:** A well-formed, self-consistent JSON receipt can still be
forged by someone who controls the entire receipt. This replay detects
alterations and accidental misbinding; it is **not independent CPU attestation,
a cryptographic signature, a proof of inference, scientific validation or
authority to change anything in JANUS**. A real pinned local native run must
be separately observed. Injected native test runners always remain labelled
`MOCK_OR_PARTIAL_REVIEW_NOT_SCIENTIFIC_EVIDENCE`.

The native review projection, including native-generated text, is for a
**local research receipt only**. No native projection, context digest or
checkout metadata is inserted into the anonymous AI Horde prompt or its
public-only CI canary. The `--out` path must be a new file in a directory
without symlink ancestors: the file is created with exclusive `O_EXCL`,
`O_NOFOLLOW` where available, and restrictive permissions `0600`. Existing
files or symlink paths are rejected *before* contacting the provider.
The CLI console prints only sanitized outcome and hash metadata, not native
or AURA text. The operator must not publish a native report artifact.

`NATIVE_CAUSAL_REPLAY = IMPLEMENTED_SOFTWARE_CHECK`

`PRIVATE_LOCAL_RECEIPT = EXCLUSIVE_0600`

`ACTUAL_PINNED_NATIVE_CPU_E2E = NOT_ATTESTED`

`SCIENTIFIC_AUTHORITY_DELTA = 0`
