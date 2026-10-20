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
