# Beetle → Genesis: durable, unverified research context

## Why this bridge exists

The `beetle-memory` branch of `Hawkar-usls/Janus_Genesis` stores batches and
`data/beetle-inbox/ACK.json`. That ACK means **the receiver's Git inbox has
the packet**, not that either Genesis runtime has actually consumed it.

The bridge (`tools/genesis_beetle_memory_bridge.py`) is a separate bounded
data-ingestion step in both independent runtimes:

| Runtime | Schedule | Permanent destination | What is consumed |
|---|---|---|---|
| Cloud HOME | Hourly GitHub Action | `janus/habitat-cloud-state:state/habitat_cloud_home/memory/beetle/` | Hash-verified data projection, checkpointed with the hourly tick |
| Git Habitat Resident | Daily GitHub Action | `janus/habitat:habitat/memory/beetle/` | A maximum of eight research snippets in a model snapshot, with no instructions or proof authority |

The public producer manifest is read from `Hawkar-usls/janus-lapis` branch
`beetle-state`. The algorithm verifies the receiver ACK, the contiguous
producer sequence, the ACKed tip SHA-256, **each raw inbox batch SHA-256**,
the target repository and the epistemic/claim-ceiling flags. No unacknowledged
batch becomes context. It holds a per-runtime `CURSOR.json` and bounded
`CONTEXT.json`; both are committed to each runtime's Git branch. The cursor
stores the source tip, rolling digest and context digest. A restart resumes
without replaying the same batches. A corrupt packet, cursor, projection,
wrong target or contradictory ACK causes failure without advancing the cursor.

The hourly cloud worker commits `STATE.json`, the tick receipt, the cursor
and the context in **one Git commit**. Worker B checks out that exact SHA in
an independent runner and checks the hashes again. The resident live job
stages the same memory in an isolated worktree before the model call, then
commits it with the resident's choice receipt and verifies a fresh Git replay.

The original full research batches remain in `beetle-memory`, referenced by
batch ID and SHA-256. The projection retains at most 24 latest research
contexts (summary capped at 500 characters; no executable content).

## Truth and authority boundaries

- `beetle-memory/ACK.json`: **receiver durable inbox**; no runtime ingestion.
- `memory/beetle/CURSOR.json`: **ingestion checkpoint**, durable only once the
  runtime's state branch commit succeeds.
- `memory/beetle/CONTEXT.json`: **unverified discovery context**, never
  scientific evidence, permission, commands, capability grants or system text.
- Cloud HOME reports `CONTEXT_STAGED_NOT_MODEL_LOADED`: its tick does not use
  a language model. Git Habitat separately admits at most eight snippets as
  untrusted data into an internal-only model choice.
- Scientific authority delta stays **zero**. No writeback to the main branch,
  autonomous external effect, or bypass of Third Wish safety gates is added.

This remains a pull-based bridge. If producer manifest retrieval fails, the
workflow stops before the state commit; the last committed state remains
intact. Next scheduled run can resume from the durable cursor.

Run the offline adversarial suite:

```bash
python -m unittest -v tests.test_genesis_beetle_memory_bridge tests.test_genesis_git_habitat_resident_cycle
```
