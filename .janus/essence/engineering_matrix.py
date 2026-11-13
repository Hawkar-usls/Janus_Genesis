"""Explicit offline ESSENCE matrix: original six-cell pilot + two bounded organs.

The legacy kernel and its safety contract are NOT replaced. The calculator
and Turing interpreter are read-only adjuncts with deterministic hash receipts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import kernel
from engineering_math import calculate
from turing_machine import run, unary_increment


def evaluate(manifest: dict, fixture: dict, *, expression: str,
             output_unit: str | None = None, machine: dict | None = None,
             tape: str = "111", max_steps: int = 1024,
             expected_repo: str | None = None, explicit_readonly: bool = False) -> dict:
    if explicit_readonly is not True:
        raise PermissionError("EXPLICIT_READONLY_REQUIRED")
    base = kernel.evaluate(manifest, fixture, explicit_readonly=True,
                           expected_repo=expected_repo)
    kernel.verify_report(base)
    calc = calculate(expression, output_unit)
    simulation = run(machine if machine is not None else unary_increment(),
                     tape, max_steps=max_steps)
    result = {
        "schema": "janus.essence.engineering_matrix/0.1",
        "repository": base["repository"],
        "legacy_receipt_sha256": base["report_sha256"],
        "legacy_microkernels": base["microkernel_count"],
        "calculator": calc,
        "turing": simulation,
        "status": "DEVELOPMENT_ONLY_READ_ONLY",
        "model_weights_modified": False,
        "gene_admission": "PROPOSAL_ONLY",
        "self_modification": False,
        "production_promotion": False,
        "network_access": False,
    }
    result["receipt_sha256"] = kernel.digest(result)
    return result


def verify(receipt: dict) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != "janus.essence.engineering_matrix/0.1":
        raise ValueError("BAD_MATRIX_RECEIPT")
    sha = receipt.get("receipt_sha256")
    if sha != kernel.digest({k: v for k, v in receipt.items() if k != "receipt_sha256"}):
        raise ValueError("TAMPERED_MATRIX_RECEIPT")
    for field in ("model_weights_modified", "self_modification", "production_promotion", "network_access"):
        if receipt.get(field) is not False:
            raise ValueError("ELEVATED_AUTHORITY")
    if receipt.get("gene_admission") != "PROPOSAL_ONLY":
        raise ValueError("UNREVIEWED_ADMISSION")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="ESSENCE offline calculator + Turing machine")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--expr", required=True)
    ap.add_argument("--unit")
    ap.add_argument("--machine", help="JSON transition table; default unary increment")
    ap.add_argument("--tape", default="111")
    ap.add_argument("--max-steps", type=int, default=1024)
    ap.add_argument("--expected-repo")
    ap.add_argument("--allow-readonly", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    result = evaluate(kernel.load_json(args.manifest), kernel.load_json(args.fixture),
                      expression=args.expr, output_unit=args.unit,
                      machine=kernel.load_json(args.machine) if args.machine else None,
                      tape=args.tape, max_steps=args.max_steps,
                      expected_repo=args.expected_repo, explicit_readonly=args.allow_readonly)
    verify(result)
    data = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    print(data, end="")


if __name__ == "__main__":
    main()
