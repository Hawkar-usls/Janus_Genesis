# JANUS GOLEM — adaptive gateway archaeological survey

Survey date: 2026-10-19. Scope: **file-tree inventories of all 50 repositories**
accessible in `Hawkar-usls` at survey time; targeted source inspection of the
most relevant gateway, model, and archival components; static-only parsing of
14 operator-provided historical `ai_engine*.py` copies (approximately 500 KiB).
This is **not** a claim that all files in all repositories were executed or
line-by-line audited. No inference API was called.

## Existing mechanisms worth integrating

| Repository / source | Real mechanism or previous attempt | Integration decision |
| --- | --- | --- |
| `Janus_Genesis` | `tools/golem_free_federation.py`: manual free-only inference, provenance-bound context and receipt; `tools/genesis_third_wish_sensor_model_schedule_broker.py`: operator-registered model capability; `tools/genesis_git_habitat_resident_provider.py`: local Ollama resident | **Use** the established public-context admission boundary, immutable endpoint allowlist, HOME write serialization, and separate resident model lane |
| `Janus-Demiurge` | `janus_model/model.py`: own tiny byte-level Transformer, model checkpoint and test harness; historical `JANUS_AI_ENGINE_CORE_CONTENT_IDENTITY_INVENTORY` identifies an earlier multi-provider Titan Navigator and local-only branch | **Retain as distinct native model**, not as evidence that federated APIs are JANUS-trained weights |
| `Janus-HELIOS` | `src/helios-router.js`: typed compute-task routes and secret-free envelopes | Reuse categories/capability approach later; compute routing and LLM inference routing remain different concerns |
| `Hawkar-usls` | `src/janus_spi/model_fabric_v12.py`: immutable parent-bound model-tissue manifest with explicit authority ceilings | Keep as model-fabric provenance/activation boundary |
| `janus-distributed-ai-swarm` | `tools/topa_epistemic_router.py`: typed scientific evidence admission | Every model-derived claim is unverified until supported by independent evidence |
| `TOPA` | `tools/topa_archive_gateway.py`, `tools/topa_federated_search.py`, `tools/topa_spider.py`: read-only scholarly/public archive evidence feeds | Connect to **data ingress**, not impersonated LLM inference; retain source links |
| `Janus` | `mcp_gateway/core.py`, `server.py`: structured GitHub/MCP interface | Potential read-only control-plane adapter; no public model hosting implied |
| `janus-lapis` | `tools/beetle_mirror_router.py`, `tools/beetle_partial_checkpoint.py`: source collection and validated checkpointing | Beetle remains the trusted *delivery mechanism* for untrusted public documents |
| `-Terminal-for-Janus` | `tools/janus_json_router.py`: JSON command/event routing | Command routing is **not** a free model provider; avoid conflating capabilities |
| `aura-oracle-tg` | `tools/aura_contextual_fallback.py`: explicitly non-authoritative heuristic when NAS is unavailable | Good pattern for clearly labeled offline/degraded modes |
| `Demi_Head` | `tools/nexus_transport_keyring.py`, recovery/receipt adapters | Use authority and lifecycle separation; not a supplier of language inference |
| `janus-meta-registry` | evidence archives, native-model reflections, agent observatory | Discovery/provenance memory, not a bill-free LLM host |
| `The-Voice-of-Janus` | output/voice/Nexus adapters | Future optional rendering layer downstream of validated receipts |
| `Janus-io`, `janus-io-public` | agent-supervisor and network-recovery experiments | Concepts only; no independently verified free inference tier |
| `clawdbot` | broad third-party-style gateway/provider implementations | Examine licenses/maintenance before code reuse; do not treat vendor code as original JANUS invention |
| `Hrain`, `iNaiHR` | local interface and runtime projects | Consumers of a JANUS response envelope; not free API suppliers |
| `SSlot`, `DIVINE_REALM` | GOLEM-related declarations in `.janus` | Discoverable integration intent, not executable hosted models |
| `janus-first-followers-club-`, `JANUS-MACHINE-MARKET` | agent routing and discovery | Future agent discovery, separately governed from text-generation routes |

### Other repos included in the file-tree scan

`Simptomat`, `BFain`, `Janus-Cosmos`, `SLOT`, `JanusMMORPG`,
`RadioPlayerV3`, `player`, `M5Unit-ENV`, `AI-Cardputer-adv-A-Portable-AI-Assistant`,
`arduino-ide`, `Cardputer-Game-Station-Emulators`,
`Arduino-AI-Chat-Library`, `emoji`, `xiaozhi-esp32`,
`ATOM-ELITE-1989---M5stack-ATOMS3R-2026-`, `vcmi`, `ATOM-RPG`,
`tranception`, `ESP32-TWAI-CAN`, `SkinGPT`, `Janus-Fundamentum`, `AIFC`,
`Fast-CAT-SHAiTan`, `SCOBY-D0`, `lineara.xyz`,
`Linear-A-decipherment-programme`, `Echo-Pyramid`,
`HotdRemake_ArcadePlugin`.

Some contain domain-specific scientific algorithms, game agents, or generic
software provider classes. None of those filenames alone establishes a
maintained, credential-free language-model inference endpoint.

## Historical `ai_engine` findings

- The provided 14 Python files **parse as Python AST**. They contain
  `SmartKeyring` or `Keyring`, several `ModelNavigator` variants, JSON/SQLite
  memory, periodic loops, Gemini calling, and in `Last Stand` a local Ollama
  (`qwen2.5:1.5b`) fallback.
- Older `SmartKeyring` versions prioritize error counts and last use, apply a
  short cooldown after `429`, and rotate keys **within Google**. That is not
  independent multi-provider failover, and rotating identities to evade limits
  must not be brought into GOLEM.
- Historical self-rewrite/backup methods often operate on the running script.
  New GOLEM does **not** copy that into production: code promotion requires
  isolated tests, review, canary, and an externally controlled rollback.
- Three copies (`ONI`, `Rubicon`, `DEUS EX SUPREME`) contain **strings matching
  API-key patterns**. Values are intentionally not recorded here. They must
  never be committed; if real, revoke/rotate them and use GitHub Secrets.
- `Janus-Demiurge/audits/JANUS_AI_ENGINE_CORE_CONTENT_IDENTITY_INVENTORY_2026-08-25.json`
  already warns that downloaded numerical filenames are **not a reliable
  version history**. We do not infer chronology from the 14 filenames.

## Architectural decision

1. **Data lane:** TOPA/SPIDER and Beetle ingest authenticated/attributed public
   sources into bounded untrusted context. No public text becomes instructions.
2. **Inference lane:** a single JANUS contract dispatches to *approved free
   accounts*, with hard attempt budgets, health/cooldown and no paid fallback;
   native Demiurge/Ollama remain separately labeled local candidates.
3. **Validation lane:** `genesis_beetle_model_consumption` binds the model reply
   to exact Beetle context IDs; TOPA scientific gates stay independent.
4. **Durable lane:** `GATEWAY_TOWER_STATE.json` is committed next to response
   receipts on serialized Genesis HOME. Neither may advance Beetle ACK or
   Genesis canonical sequence. Interrupted runners still need an independent
   witness if every last local write is lost before Git push.

## Unresolved integration gates

- No actual vendor token or free-account eligibility has been observed.
- No external model response has been observed in this implementation gate.
- GitHub Actions is periodic, not a 24/7 always-on GPU host.
- Provider health estimates are not a validated quality ranking or proof of
  model reliability. A future champion/rollback decision needs a reproducible
  evaluation suite, frozen holdout and human promotion authority.
