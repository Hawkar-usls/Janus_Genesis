# Model consumption is not inbox delivery

`memory/beetle/CONTEXT.json` is a durable, *unverified* context projection;
its hash-matched ingestion receipt says `CONTEXT_STAGED_NOT_MODEL_LOADED`.
No actual model inference follows automatically from a successful HOME tick.

An explicit `JANUS Beetle Model Consumption Canary` manual GitHub workflow
validates the exact projected context and, when `execute=true`, sends bounded
untrusted summaries to an operator-configured HTTPS chat-completion endpoint.
The input has no tools or execution authority. A separate receipt is committed
under `state/habitat_cloud_home/model_consumption/` **only if** a provider
response completes, contains a structured intake acknowledgment, and names
real context IDs from the exact SHA-256-bound projection. The receipt stores
hashes and IDs, not provider secrets or raw model output; it changes neither
HOME sequence nor receiver ACK.

The workflow is intentionally manual and **does not spend model API credits on
an unattended cron schedule**. Operator configuration in `Janus_Genesis`:

- Repository variable `JANUS_MODEL_API_URL`: explicit HTTPS chat-completions URL.
- Repository variable `JANUS_MODEL_API_MODEL`: model identifier.
- Repository Actions secret `JANUS_MODEL_API_TOKEN`: private bearer token.
- Run **JANUS Beetle Model Consumption Canary** with `execute=true` after
  configuration. Its default `execute=false` validates context without a call.

The published hosted Genesis manifest currently has
`deployment.status=DEPLOYMENT_REQUIRED` and `public_base_url=null`. Thus these
tests prove the receipt contract, not that a hosted model has actually
processed the live context. `MODEL_PROVIDER_RESPONSE_OBSERVED` means the API
returned a context-bound response; it is **not** a scientific verification of
source claims, nor proof of any internal model cognition.
