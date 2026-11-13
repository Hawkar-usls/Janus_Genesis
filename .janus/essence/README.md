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

## Gene Bank v0.2 — learning from JANUS history without executing donor code

The ESSENCE sidecar `.janus/essence/gene_bank.py` reads seven bounded, allowlisted
historical JSON manifests from public read-only checkouts of Meta Registry and
Demiurge archaeology. Git commit SHA and raw file SHA-256 are preserved in the
output receipt, with a list of missing/unparseable source files. Data is
interpreted as architectural evidence, not instructions from untrusted JSON.

The reader recognizes reviewed candidate genes from MicroGPT/Slime,
JGPT/BrainTrio, All_starsGPT, CatGPT, FractalGPT, Yaksa/GEX, Physarum and
other archived GPTs and proposes them for the six local microkernel roles.
Only proposals are emitted; it **never imports models, downloads source code,
executes remote code, trains weights, edits manifests, or promotes children**.
Real neural training is still a separate Neural Kombucha workflow with
independent evaluation requirements.

The checked-in `legal_sources.json` catalogs MIT (micrograd, nanoGPT,
TheAlgorithms/Python) and Apache-2.0 (Transformers) repositories found through
public GitHub metadata. Metadata alone does not settle ownership or licensing
for each file, dependencies, model checkpoints or datasets. Any actual reuse
requires source-specific license and notice verification, sandbox tests,
attribution and reviewed changes. Unknown/changed license claims are HOLD.

GitHub Actions job `gene-bank-archaeology` runs contract tests and a read-only
checkout of both source repositories, then emits
`artifacts/essence/gene-bank.json` for audit. This artifact is a SHA-linked
checksum receipt, **not a cryptographic attestation** or evidence of real-world
model performance. ESSENCE remains disabled for autonomous actions.

## Offline engineering organs (2026-11-13, development-only)

ESSENCE gains two explicitly invoked, resource-bounded, deterministic specialist organs:
(1) engineering_math.py: Decimal-50 arithmetic with SI dimension validation, selected
physical units, square roots and explicitly approximate trigonometric/logarithmic functions;
(2) turing_machine.py: an interpreter of arbitrary finite deterministic one-tape
Turing-machine transition tables with halting states, head moves, trace hashes,
and strict tape/step limits. It is a bounded interpreter, not an unbounded
universal computer with infinite memory.

engineering_matrix.py binds both to the unchanged six-role ESSENCE offline kernel,
verifies its evidence chain and emits a SHA-256-bound combined receipt. It does
not grant children authority to modify code, weights, workflows, network or NAS.
The manifest records proposed gene-source names, not permission to auto-import.
This adds computational capability, NOT a model training or general reasoning gain.

Example (from repo root):
  python .janus/essence/engineering_matrix.py --manifest .janus/essence/manifest.json --fixture .janus/essence/fixture.json --expr "5*kN*2*m" --unit kJ --tape 111 --allow-readonly --expected-repo Hawkar-usls/Janus_Genesis

Tests (stdlib only):
  python -m unittest discover -s tests -p test_essence_engineering_matrix.py -v
  python -m unittest discover -s tests -p test_essence_kernel.py -v

Archived donor source copies live at archaeology/gpt_sources_20261113/reference_only
as inert *.py.txt files. They are never imported by ESSENCE or CI.
No archival source is promoted by its filename, hash or popularity alone.
