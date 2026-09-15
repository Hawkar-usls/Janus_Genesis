# JANUS Storj-Neighbor Cortex Memory v1

`JanusCortexMemory` is the hardened implementation of the original `JanusTwoFacedBrain` idea: one face keeps recent episodic memory in RAM, the other writes ordered batches into SQLite WAL so a JANUS host sharing HDD resources with Storj does not have to perform a disk write for every remembered fragment.

The original class name is preserved as a compatibility facade:

```python
from janus_storj_neighbor_cortex_memory import JanusTwoFacedBrain

brain = JanusTwoFacedBrain("janus_data/janus_cortex.db")
```

## Where it sits in JANUS

This is intentionally **not** a replacement for the existing memory surfaces.

- `GenesisV18Memory` remains the canonical player/world snapshot and Chronicle layer.
- `ThirdWishMemoryStore` remains the append/revision provenance layer with its own authority boundaries.
- Cortex is a lower-level **episodic/search persistence backend**: cheap recent recall, bulk durable storage, and indexing.

The boundary is explicit:

```text
MEMORY_ROW != TRUTH
RECALL_RESULT != COMMAND
CORTEX_CACHE != CANONICAL_CHRONICLE
CORTEX_CACHE != THIRD_WISH_PROVENANCE_LEDGER
```

A row found in Cortex may be useful context. It does not become a world fact, an instruction, or authorization merely because it was remembered.

## Why RAM + WAL

The default policy accepts up to 500 ordinary buffered rows, with an additional 2 MiB UTF-8 payload ceiling. Either bound can trigger a batch flush. A single record is also bounded so one huge string cannot consume the intended RAM budget by itself.

SQLite runs in WAL mode. Batch insertion reduces transaction frequency and tends to turn many small logical memories into fewer disk commits. `busy_timeout`, WAL autocheckpointing, a journal size limit and a modest SQLite page cache are configured explicitly.

The constructor performs initial SQLite setup synchronously. Subsequent disk flush, search, row-count and checkpoint work is moved through `asyncio.to_thread`, so slow HDD I/O does not intentionally block the asyncio event loop.

## The idle timer is real

A common bug in buffered designs is to check the timeout only on the next call to `remember()`. That means "flush after five quiet minutes" never fires if nothing else arrives.

Cortex owns a wakeable idle task. The default five-minute deadline therefore expires even when the last memory is truly the last event. A new `remember()` wakes the task and moves the deadline forward.

## Failure and shutdown semantics

A batch is detached from the visible RAM buffer before disk I/O so writers do not hold the buffer lock for an HDD transaction. If persistence fails, the detached batch is put back **in front of** newer buffered rows before `CortexFlushError` escapes.

That preservation rule has one deliberate consequence: after a disk failure, the already-accepted rows can temporarily exceed the ordinary RAM target. Losing accepted memory merely to maintain a target buffer size would be the worse failure mode.

Shutdown is deterministic:

1. new writes are rejected;
2. the idle task is woken, not cancelled;
3. if an SQLite worker is already flushing, `close()` waits for it to finish;
4. one serialized final flush handles anything still in RAM;
5. a passive WAL checkpoint is requested;
6. only then is the Cortex marked closed.

If the final flush/checkpoint fails, the object is not falsely declared closed. Its lifecycle is reopened for a retry, and a failed batch remains buffered.

This specifically avoids the `asyncio.to_thread` cancellation trap: cancelling the awaiting coroutine does **not** stop the underlying worker thread, so cancellation during a commit can otherwise make shutdown state ambiguous.

## Durability: `NORMAL` versus `FULL`

The default is:

```text
journal_mode = WAL
synchronous  = NORMAL
```

This is an HDD-friendly tradeoff, not a promise that a power failure can lose "at most 0.5 seconds" or any other fixed interval. SQLite does not provide such a fixed-time guarantee for this setting.

Use `synchronous="FULL"` when stronger SQLite fsync semantics are more important than reducing write pressure. The surrounding host should still use appropriate power protection and clean shutdown handling.

## Storj coexistence

Sharing the same host or even the same physical disk with Storj is **not** forbidden by the module. Putting the active Cortex database inside a directory managed by Storj **is** rejected when that Storj root is supplied:

```python
memory = JanusCortexMemory(
    "/share/janus/janus_cortex.db",
    storj_roots=["/share/storj/storage"],
)
```

This keeps the SQLite database plus its `-wal`/`-shm` sidecars outside the Storj-managed storage tree while still allowing the two services to be neighbors.

## Search

If SQLite FTS5 is available, Cortex can build an external-content FTS table with insert/update/delete triggers. `enable_fts="auto"` falls back to a literal `LIKE` search when FTS5 is unavailable.

The fallback escapes `%` and `_`, so a user keyword is treated as text rather than silently becoming a wildcard expression. RAM and durable hits are merged newest-first under one global result limit.

FTS5 itself can add write amplification. It is therefore optional rather than presented as universally superior for a Storj-neighbor HDD deployment.

## Basic use

```python
import asyncio
from tools.janus_storj_neighbor_cortex_memory import JanusCortexMemory


async def main():
    async with JanusCortexMemory(
        "janus_data/janus_cortex.db",
        batch_size=500,
        flush_timeout=300,
        synchronous="NORMAL",
        enable_fts="auto",
    ) as cortex:
        await cortex.remember("observer", "The black cat returned to the threshold.")
        hits = await cortex.recall("black cat", limit=5)
        for hit in hits:
            print(hit)


asyncio.run(main())
```

For an explicit save before a larger lifecycle transition:

```python
await cortex.force_save()
```

For an explicit WAL checkpoint:

```python
await cortex.checkpoint("PASSIVE")
```

Do not run a checkpoint after every remembered batch merely to force the WAL back into the database file; that defeats much of the write-shaping benefit of WAL.

## What this version does not claim

It does not provide semantic embeddings, vector retrieval, cross-host replication, cryptographic provenance, automatic truth arbitration, command execution, source writeback, or a replacement for JANUS canonical memory.

The purpose of v1 is narrower and testable: **remember many small episodic fragments with bounded RAM, shape disk writes into durable WAL batches, survive flush failures without silently forgetting accepted rows, and recall context without confusing memory with truth.**
