# ESSENCE v1.2 — real JANUS algorithms, provenance-bound holdout, controlled rollback

This is an offline research benchmark, not autonomous model promotion.

## Real source identities

- research/essence/v12/sources/janus_model_model.py.txt is the exact
  Git blob 11e359e89d3946895b2e0d6817c54253f09dfed1 from the real
  Hawkar-usls/Janus-Demiurge/janus_model/model.py. The harness extracts and
  executes only its pinned ByteTokenizer class for stdlib CI tests. The full
  pinned real JanusTinyTransformer is executed on the owner's CPU only when
  PyTorch is installed, with fresh random fixed-seed weights and no training.
- The real ESSENCE .janus/essence/gene_bank.py algorithm is pinned to Git blob
  e7fe6f59591009df1905dbbf06b164d49e422660. The test benchmarks actual
  normalized_model() against a contained candidate implementation.
- The frozen corpus is copied verbatim from the separate repository
  Hawkar-usls/janus-meta-registry, recorded before the candidate implementation
  in commit 5fcd50ad7fc26f9e26aef6ff25ebcb42ef7c8f28. The exact corpus
  Git blob is 71f23a157a9849998dc9655bc6bdf15c08d9934a.
  This is a public cross-repository frozen holdout, NOT a hidden blind set or
  independent externally attested evaluation.

## Run

    python -m unittest discover -s tests -p test_essence_v12_real_bench.py -v
    python tools/essence_v12_real_bench.py --skip-torch
    python tools/essence_v12_real_bench.py

The second command is stdlib-only, so it can run in ordinary GitHub Actions.
The last additionally runs real PyTorch forward inference if already installed;
it never downloads packages, loads arbitrary pickle, trains, or alters weights.

The comparison has baseline/candidate runtime medians (ns/call) and
tracemalloc Python peak allocations (bytes). Those bytes do NOT capture
native PyTorch tensor memory, GPU memory, or full process RSS. Benchmarks
are local and subject to hardware, warmup and OS load effects. A speed number
is descriptive and does not constitute an independent performance claim.

If a candidate changes any output, exceeds resource thresholds, or loses speed,
the gate holds it. A deliberately broken decoder and a misrouting gene lookup
are rejected, followed by an in-memory recovery that replays baseline outputs
with the same SHA-256 fingerprints. This is a rollback drill, NOT an actual
production checkpoint or deployment rollback.

No automatic execution of user-provided historical code, no new network
capabilities, no model weight updates, no automatic offspring activation.
The production admission gate remains frozen pending real independent blinded
replication, genuine trained-model evaluation, signatures, and reviewed rollback.
