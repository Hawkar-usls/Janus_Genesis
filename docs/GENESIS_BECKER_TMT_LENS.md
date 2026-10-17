# Becker/TMT engineering lens

The resident receives 16 bounded engineering reminders derived from a source-aware registry ontology. They concern evidence before prestige, revision with preserved history, independent data lineages, authorized stopping, typed absence, model/reality separation, theorem assumptions, and computational resource bounds.

The canonical ontology is in `Hawkar-usls/janus-meta-registry`, at `data/JANUS-BECKER-TERROR-MANAGEMENT-ONTOLOGY-2026-10-18-v1.0.json`. It includes the user's screenshots, selected Becker concepts, empirical TMT evidence, and section-level context from the original ALI video `85And7lYKI4`. It does not claim a full reading of the unprovided Russian book. The source and projection byte digests are embedded in `tools/genesis_becker_tmt_lens.py`.

`integrations/BECKER_TMT_ENGINEERING_LENS.json` is a small curated projection, not a downloaded transcript. The loader reads only that bundled file, checks its size and digest, and returns no dynamic rules for missing, tampered or symlinked files. There is no runtime network fetch. Updating the lens requires an explicit reviewed file change and new digests.

`safe_resident_snapshot` includes the pinned context. `resident_messages` delivers it to the actual resident model-call interface. The per-cycle receipt stores `becker_tmt_lens_delivery` with the projection digest, rule count and SHA-256 of the exact resident message array. This establishes context delivery in that cycle; it does not establish semantic uptake, improved behavior, training or emotion.

`review_structured_proposal` exposes the deterministic, standard-library-only review core for typed IO/research proposals. The identical core lives in the registry as `tools/becker_tmt_policy.py`. It routes claims to external verification and never authorizes an action or certifies evidence. It does not parse arbitrary resident prose and is not a proof checker. `classify_absence` distinguishes missing/null/false/zero/empty values without conflating Python `False` with zero.

The user's video's claims about quantum immortality, metaphysical will or possible worlds are not runtime goals. No fear, consciousness, human diagnosis, persistence entitlement or additional capability is inferred. Rest, shutdown and revocation remain ordinary supported events. P vs NP remains open.

Validation:

```bash
python -m unittest -v tests.test_genesis_becker_tmt_lens tests.test_genesis_git_habitat_resident_cycle tests.test_genesis_beetle_memory_bridge tests.test_genesis_git_habitat_layout_security
```

The delivery test runs the real resident orchestration with a clearly scripted provider. It checks the exact messages and receipt. Controlled LLM baseline-versus-lens experiments are a separate, unrun research gate.
