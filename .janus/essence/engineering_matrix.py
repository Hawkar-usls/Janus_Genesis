"""Explicit offline ESSENCE matrix: original six-cell pilot + two bounded organs.

The legacy kernel and its safety contract are NOT replaced. The calculator
and Turing interpreter are read-only adjuncts with deterministic hash receipts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import kernel
import counterexample_gate
import real_algorithm_gate_v12
from engineering_math import calculate
from turing_machine import run, unary_increment


def evaluate(manifest: dict, fixture: dict, *, expression: str,
             output_unit: str | None = None, machine: dict | None = None,
             tape: str = "111", max_steps: int = 1024,
             expected_repo: str | None = None, explicit_readonly: bool = False,
             parent_machine: dict | None = None, child_machine: dict | None = None,
             trial_alphabet: tuple[str, ...] = ("1",), trial_max_length: int = 6,
             real_algorithm_report: dict | None = None) -> dict:
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
    if (parent_machine is None) != (child_machine is None):
        raise ValueError("PAIR_OF_MACHINES_REQUIRED")
    if parent_machine is not None:
        result["candidate_trial"] = counterexample_gate.evaluate(
            manifest, fixture, parent_machine, child_machine,
            alphabet=trial_alphabet, max_length=trial_max_length,
            expected_repo=expected_repo, explicit_readonly=True)
    if real_algorithm_report is not None:
        result["real_algorithm_review"] = real_algorithm_gate_v12.review(real_algorithm_report)
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
    if "candidate_trial" in receipt:
        counterexample_gate.verify(receipt["candidate_trial"])
    if "real_algorithm_review" in receipt:
        review = receipt["real_algorithm_review"]
        if (not isinstance(review, dict)
            or review.get("receipt_sha256") != kernel.digest({k:v for k,v in review.items() if k!="receipt_sha256"})
            or review.get("schema") != real_algorithm_gate_v12.SCHEMA
            or review.get("gate") != "HOLD_EXTERNAL_BLIND_REPLICATION_AND_REAL_CHECKPOINT_REVIEW"
            or review.get("production_authority") is not False
            or review.get("model_weights_modified") is not False
            or review.get("child_activation") is not False):
            raise ValueError("INVALID_REAL_ALGORITHM_REVIEW")
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
    ap.add_argument("--parent-machine", help="Read-only declarative parent transition table")
    ap.add_argument("--child-machine", help="Read-only declarative child transition table")
    ap.add_argument("--trial-alphabet", default="1")
    ap.add_argument("--trial-max-length", type=int, default=6)
    ap.add_argument("--real-algorithm-report", help="SHA-bound v1.2 real-algorithm research report")
    ap.add_argument("--expected-repo")
    ap.add_argument("--allow-readonly", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    result = evaluate(kernel.load_json(args.manifest), kernel.load_json(args.fixture),
                      expression=args.expr, output_unit=args.unit,
                      machine=kernel.load_json(args.machine) if args.machine else None,
                      tape=args.tape, max_steps=args.max_steps,
                      expected_repo=args.expected_repo, explicit_readonly=args.allow_readonly,
                      parent_machine=kernel.load_json(args.parent_machine) if args.parent_machine else None,
                      child_machine=kernel.load_json(args.child_machine) if args.child_machine else None,
                      trial_alphabet=tuple(args.trial_alphabet),
                      trial_max_length=args.trial_max_length,
                      real_algorithm_report=kernel.load_json(args.real_algorithm_report) if args.real_algorithm_report else None)
    verify(result)
    data = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    print(data, end="")


if __name__ == "__main__":
    main()
