# JANUS Hephaestus Crystal v2

Hephaestus Crystal is a hardened continuation of the historical JANUS `hephaestus_crystal.py` line from 2026-01-24.

The historical module is preserved as design provenance. It is not rewritten to pretend that later scientific/engineering boundaries were already present at its creation.

## Historical lesson

The January line mixed four different layers:

1. filesystem metadata scanning;
2. Shannon entropy of file sizes;
3. a tail-slack estimate;
4. a fictional/simulated `Quantum-P=NP / Perfect Fit` interpretation.

A later `quantum_success_sim.py` branch went further: simulated or hardcoded dominant measurement counts were interpreted as verification that P=NP had been solved, and a database insert was described as recording the successful theorem result.

v2 preserves those outputs as **historical claims**, not as current theorem evidence.

```text
HISTORICAL_CLAIM_PRESERVED != HISTORICAL_CLAIM_ENDORSED
SIMULATED_CONVERGENCE != COMPLEXITY_CLASS_PROOF
QISKIT_COUNTS != P_EQUALS_NP
HARDCODED_COUNTS != EXPERIMENTAL_EVIDENCE
SQL_INSERT_SUCCESS != THEOREM_VERIFICATION
```

## What v2 actually measures

### File-size entropy

For positive file sizes `s_i` and total logical bytes `S`, v2 computes:

```text
H = -sum((s_i / S) * log2(s_i / S))
  = log2(S) - sum(s_i * log2(s_i)) / S
```

This is a statistic of the byte-weighted file-size distribution. It is **not** a fragmentation metric.

### Tail-slack model

For a declared/modelled allocation unit `A`, v2 computes:

```text
slack_i = (A - (size_i mod A)) mod A
```

and sums it across regular files.

The allocation unit may come from an explicit parameter or a `statvfs` hint. It remains a model. Real filesystem semantics can differ because of sparse files, compression, reflinks, inline data, sub-allocation and other implementation details.

### Observed allocation counters

Where the platform exposes POSIX `st_blocks`, v2 separately records `st_blocks * 512` for namespace entries. This is not called tail slack and is not claimed to be unique physical-space usage when hardlinks or shared extents exist.

### Fragmentation

v2 does not inspect extents and therefore reports:

```text
fragmentation_measured = false
extent_layout_measured = false
seek_locality_measured = false
```

A future HDD optimization gate must add extent/layout and seek measurements before making defragmentation, latency, wear or lifetime claims.

## Read-only analysis boundary

The analyzer:

- uses metadata traversal only;
- does not open regular files for content;
- does not follow symlinks;
- rejects a symlink scan root;
- stays on the starting filesystem by default;
- has maximum file-count and depth limits;
- performs no network access or subprocess execution;
- performs no file move, rewrite, deletion or defragmentation.

The aggregate report contains no file names, file paths or target path.

## Optional persistence

Local SQLite persistence is disabled by default. If explicitly enabled, v2 stores the privacy-safe aggregate report under a caller-supplied opaque `target_id`.

The database row is a receipt of analyzer output only.

## Quantum/P-vs-NP boundary

The historical label `Quantum-P=NP / Perfect Fit` is retained as lineage for the theoretical zero-tail-slack byte-stream lower bound. v2 executes no Shor adaptation, Grover search, QND measurement or quantum solver and claims no result about `P = NP`, `BQP = NP`, or arbitrary NP-complete optimization.

```text
PERFECT_BYTE_STREAM_LOWER_BOUND != REAL_FILESYSTEM_ZERO_OVERHEAD
PERFECT_BYTE_STREAM_LOWER_BOUND != P_EQUALS_NP_PROOF
```

This is the intended JANUS behavior: preserve the path, including the mistake, while preventing the mistake from silently becoming present-day authority.
