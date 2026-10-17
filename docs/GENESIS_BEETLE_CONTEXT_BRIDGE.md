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
`beetle-state` by a fixed GitHub Contents API **GET**. This read-only network
surface is explicitly inventoried in both Armor drift audit versions;
classification does not confer execution or routing authority. The algorithm
verifies the receiver ACK, the contiguous
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

## Model research-review witness

Each Git Habitat model cycle with validated Beetle context now writes
`habitat/memory/beetle/reviews/<cycle-id>.json` alongside the resident choice
receipt. The review binds the source projection SHA-256 and cursor sequence to
the **exact bounded model snapshot SHA-256**, model-messages SHA-256, output
SHA-256 and the admitted choice payload hash. It lists how many snippets were
presented, and records an observable **exact `context_id` string mention** only
if a valid choice actually includes that ID.

The model may ignore the findings, choose REST, or reference a relevant ID;
there is no compulsory claim and no reward for citing anything. A string
mention is **not** proof that a model understood, used, or independently
verified a source. The review hard-codes `model_causal_influence_proven: false`,
`independent_scientific_confirmation_established: false` and
`research_promoted_to_evidence: false`. It never stores raw snippets or raw
model output. The review and resident choice receipt are committed in one Git
transaction, with a SHA link between them.

PR model smoke now stages the real ACKed inbox in a temporary Habitat and
requires a real Ollama call to create the review. The live Habitat job reopens
the review in a fresh Git worktree after its commit and independently verifies
its digest and provenance pointer. This is a **delivery-and-decision audit**,
not a scientific-validation gate.

Run the offline adversarial suite:

```bash
python -m unittest -v tests.test_genesis_beetle_memory_bridge tests.test_genesis_git_habitat_resident_cycle
```
