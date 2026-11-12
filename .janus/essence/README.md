# ESSENCE v0.1 — repository-local microkernel pilot

Status: **OFFLINE READ-ONLY RESEARCH PILOT**. No autonomous deployment or trained model is implied by this package.

This directory contains a local controller and a manifest with six bounded microkernel **adapters**: sensing, memory, planning, verification, recovery and coding. They are simple deterministic policy adapters, not six pretrained GPTs. The separate Demiurge Neural Kombucha experiment does train six real `JanusTinyTransformer` models on synthetic benchmarks, but those weights are **not automatically loaded here**.

## Run locally (Python 3.11+; no dependencies)

```bash
python .janus/essence/kernel.py \
  --manifest .janus/essence/manifest.json \
  --fixture .janus/essence/fixture.json \
  --allow-readonly --propose-child recovery \
  --out artifacts/essence/receipt.json
python .janus/essence/kernel.py --verify artifacts/essence/receipt.json
python -m unittest discover -s tests -p test_essence_kernel.py -v
```

Without `--allow-readonly`, the runtime refuses to evaluate. The manifest must have `enabled: false` and **all six protected capabilities set to false**. The prototype accepts only explicit synthetic fixtures, never external signals, repositories, messages, credentials or model-generated code. It does not use network, shell, GitHub API, model weights, Telegram, radio, video, NAS or hardware.

The resulting report has a SHA-256 hash chain between microkernel receipts and an overall report digest; it is useful for *consistency checking*, not an authenticated signature. Independent external provenance/attestation is required before trusting a report from an untrusted author. A child is a proposed manifest record only and never joins the active microkernel list, writes code or starts a workflow.

## ESSENCE evolution admission gates

1. Recover and SHA-identify donor source; apply source review and privacy/security checks.
2. Import a single bounded operator into an isolated adapter, not its old whole runtime.
3. Compare to a frozen baseline, with disjoint training, calibration and holdout data.
4. Verify results independently and bind code SHA, inputs and metrics to an append-only registry.
5. Review a proposed offspring by PR; preserve rollback and the original independent test.
6. Enable any real execution, data egress or autonomous writes only through a separately reviewed capability approval.

Historical architecture donors: MicroGPT/Slime, JGPT/HighBrain/Trinity, CatGPT, FractalGPT, All_starsGPT, Yaksa BlackholeGuard, Physarum and Ocean. See `Hawkar-usls/Janus-Demiurge/audits/JANUS_GPT_MODEL_ZOO_ARCHAEOLOGY_2026-08-25.json` and `Hawkar-usls/janus-meta-registry` ESSENCE lineage. Donor names in the manifest are **provenance labels**, not imported executable modules or checkpoints.

Operational gate: **HOLD**. Passing the synthetic pilot must not be reported as physical retrocausality, real-world predictive generalization, or full JANUS autonomy.
