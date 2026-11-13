# ESSENCE v1.5 — adaptive quantization of microkernel numeric state

The module `.janus/essence/adaptive_quantization_v15.py` is a **read-only research adapter** that lets each six-role ESSENCE microkernel and ESSENCE's own numerical-state channel select a compact representation by measured error budget.

**Per role:** sensing 0.015, memory 0.030, planning 0.012, verification 0.002, recovery 0.003, coding 0.012, ESSENCE self 0.004 (maximum absolute error in input units). These are **development-only illustrative policies**, not validated model tolerances.

- INT4: signed symmetric, 2 values per byte, 32-value blocks, scale stored in float64.
- INT8: signed symmetric with a scale per block.
- FP16: preserves additional precision when integer rounding fails.
- FP32: fallback when compression offers no acceptable quality/storage tradeoff.

The selection runs all four alternatives, including four decode-and-requantize rounds to check drift. A result passes the local research gate only if max error and drift remain below role budgets and the actual encoded binary (including headers and scale metadata) saves at least 10% vs an equivalent FP32 buffer. The binary format begins with `ESQ1`. The algorithm creates **a separate exact FP32 snapshot**, plus SHA-256 receipts for every packet, snapshot, manifest and full report. An offline verifier decodes saved bytes and compares them against the preserved original. **Dequantization is lossy; only the original snapshot gives exact restoration.**

By default the tool constructs seven 256-element deterministic **synthetic numeric vectors** from the repo's existing synthetic fixture. An optional JSON adapter with schema `janus.essence.numeric_state/1.5`, repo binding and seven role vectors accepts declared numeric state for future trials. It is **not** authenticated, trained, independently blind, or production-capable.

Read-only CI: `.github/workflows/essence-adaptive-quantization-v15.yml`. It runs 30 adversarial tests, verifies the existing six-role microkernel, quantizes synthetic vectors, verifies the saved binary and snapshot, and uploads research artifacts.

**First local synthetic experiment:** 7 vectors × 256 values, baseline 7,168 bytes of FP32 numeric payload, packed 2,680 bytes including scales/headers (62.6116% smaller). INT8 was selected for sensing, memory, planning, coding and ESSENCE self, FP16 for verification and recovery. **No claim** is made about actual resident RAM, GPU acceleration, neural inference latency, independent quality, or trained checkpoint size.

This adapter never changes code, kernel descriptors, working models or weights, and does not run historical modules. Production model quantization would additionally require pinned checkpoint provenance, real held-out model quality comparisons, CPU/RAM/VRAM/runtime measurements, integrity checks, independent review, actual rollback and canary rollout. `production_authority=false` is hard-coded.
