# JANUS GOLEM — free federated intelligence bridge (proposal)

Status: **IMPLEMENTED AS OFFLINE-GATED CODE; NO EXTERNAL MODEL CONNECTED**.

Goal: one JANUS voice backed by several legitimately free third-party inference
interfaces. A unified answer is a JANUS *interface*, not ownership of upstream
model weights. Every response retains its originating provider and model.

## First-party boundaries

- `janus-lapis` Beetle collects, validates, shards and persists bounded research.
- Genesis HOME receives and stages source-ID-bound, **untrusted** summaries.
- GOLEM Free Federation reads those summaries, tries up to two free endpoints,
  and accepts only a completed JSON response that cites actual context IDs.
- A receipt with provider, actual reported model, prompt/answer hashes and
  unverified summary may be committed under `model_federation/` on HOME's
  durable branch. `STATE.sequence`, receiver ACK and science gates never move.
- No provider may grant itself repository write permission or tool execution.

## Fixed allowlist (review again before enabling an account)

| Provider | Pinned route/model | Credentials | Additional operator gate |
| --- | --- | --- | --- |
| OpenRouter free router | `openrouter/free` | `JANUS_GOLEM_OPENROUTER_TOKEN` | None beyond manual opt-in |
| Groq Free Plan | `openai/gpt-oss-20b` | `JANUS_GOLEM_GROQ_TOKEN` | `JANUS_GOLEM_GROQ_FREE_PLAN=1` |
| Gemini Free Tier | `gemini-2.5-flash-lite` | `JANUS_GOLEM_GEMINI_TOKEN` | `JANUS_GOLEM_GEMINI_FREE_PLAN=1` |
| Cloudflare Workers AI Free | `@cf/openai/gpt-oss-20b` | `JANUS_GOLEM_CLOUDFLARE_TOKEN` | `JANUS_GOLEM_CLOUDFLARE_FREE_PLAN=1`, valid account ID |

Each token belongs in **GitHub Actions Secrets**; the plan indicators and
Cloudflare account ID belong in **GitHub Actions Variables**. Do not commit
tokens, paste them into a conversation, or reuse a hosted runtime token.
Models are pinned to avoid selecting a paid model by accident. The software
cannot inspect account billing plans: only enable a source after confirming
its provider account is strictly free, no payment method/paid fallback is
enabled, and any quotas and permitted purposes still match the provider terms.

Not automatically enrolled yet: Hugging Face routed inference credits (can
be charged after credits expire), finite Cerebras trial, and other providers.
They require separate billing controls, approved model identifiers and tests.
Do not scrape private web-chat sessions or create accounts to evade quotas.

## No-cost activation ladder

1. PR and CI: Python unit tests use mocked providers; **zero network calls**.
2. Manual GitHub workflow `JANUS GOLEM Free Federation`: select
   `execute=false`. It checks the verified HOME context and prints only a
   dry-run plan; **no model API keys are passed to that step**.
3. User explicitly creates an eligible free-plan account, verifies billing is
   disabled, and sets the corresponding GitHub Secret and (if necessary) gate
   Variable. No account registration or payment is performed by this code.
4. Only after another explicit user decision, dispatch with `execute=true`.
   The workflow may send *public research summaries only* to at most two
   enrolled providers. API quota/timeout/provider errors move to the next
   configured free provider; there is no paid retry or unknown host fallback.
5. The first valid completed reply becomes `EXTERNAL_PROVIDER__UNVERIFIED`.
   A future independently evaluated synthesis may select or compare replies;
   a single provider response does not constitute cross-model consensus.

## What this does **not** claim

- No self-trained model weights, full-time online runtime, or guaranteed free
  throughput. Actions are episodic, providers can throttle, models can change.
- No license to misattribute third-party results or ignore API conditions.
- No automatic source-of-truth promotion, scientific proof or autonomous
  self-modifying production code. Candidate fixes still require isolated tests,
  review, rollback manifests and the existing Genesis witness gates.
- No permanent independence from GitHub availability; an external observation
  channel and off-GitHub backups remain necessary.

Official current references:

- https://openrouter.ai/docs/api_reference/limits
- https://openrouter.ai/openrouter/free
- https://console.groq.com/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/openai
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- https://huggingface.co/docs/inference-providers/pricing
