#!/usr/bin/env python3
"""Deterministic stdlib-only benchmark: ESSENCE root before vs v1.1 gate after."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / ".janus" / "essence"
FIXTURES = REPO / "research" / "essence" / "counterexample_v11"
sys.path.insert(0, str(SOURCE))

import counterexample_gate as gate
import engineering_matrix
import kernel


def run(*, out: Path | None = None) -> dict:
    manifest = kernel.load_json(SOURCE / "manifest.json")
    fixture = kernel.load_json(SOURCE / "fixture.json")
    parent = kernel.load_json(FIXTURES / "parent_delayed_unary.json")
    child = kernel.load_json(FIXTURES / "child_optimized_unary.json")
    defective = kernel.load_json(FIXTURES / "child_bad_unary.json")
    repo = manifest["repository"]

    # Before: the unchanged ESSENCE root only proposes a child without executing it.
    before = kernel.evaluate(
        manifest, fixture, explicit_readonly=True, expected_repo=repo,
        propose_child="coding")
    kernel.verify_report(before)
    original_base = kernel.evaluate(
        manifest, fixture, explicit_readonly=True, expected_repo=repo)
    kernel.verify_report(original_base)
    if len(before["proposed_children"]) != 1:
        raise RuntimeError("BEFORE_PROPOSAL_NOT_CREATED")

    good = gate.evaluate(
        manifest, fixture, parent, child,
        explicit_readonly=True, expected_repo=repo)
    bad = gate.evaluate(
        manifest, fixture, parent, defective,
        explicit_readonly=True, expected_repo=repo)
    matrix = engineering_matrix.evaluate(
        manifest, fixture, expression="5*kN*2*m", output_unit="kJ",
        parent_machine=parent, child_machine=child,
        explicit_readonly=True, expected_repo=repo)
    for result, candidate in ((good, child), (bad, defective)):
        gate.verify_replay(result, manifest, fixture, parent, candidate)
    engineering_matrix.verify(matrix)

    if (good["gate"] != "RESEARCH_PASS_FINITE_DOMAIN_ONLY"
            or bad["gate"] != "HOLD_SEMANTIC_COUNTEREXAMPLE"
            or original_base["report_sha256"] != good["root_essence_receipt_sha256"]
            or original_base["report_sha256"] != matrix["legacy_receipt_sha256"]
            or matrix["candidate_trial"] != good):
        raise RuntimeError("BEFORE_AFTER_GATE_CONTRACT_BROKEN")

    report = {
        "schema": "janus.essence.counterexample_benchmark/1.1",
        "repository": repo,
        "environment": "OFFLINE_DEVELOPMENT_STATIC_FIXTURES",
        "baseline": {
            "role_count": before["microkernel_count"],
            "proposed_children": len(before["proposed_children"]),
            "candidate_comparison_capability": False,
            "offspring_activation": False,
            "root_receipt_sha256": original_base["report_sha256"],
            "proposal_receipt_sha256": before["report_sha256"],
        },
        "upgraded": {
            "role_count": matrix["legacy_microkernels"],
            "root_unchanged": matrix["legacy_receipt_sha256"] == original_base["report_sha256"],
            "candidate_comparison_capability": True,
            "finite_inputs_checked": good["cases_exhausted"],
            "optimized_child_gate": good["gate"],
            "optimized_parent_total_steps": good["parent_total_steps"],
            "optimized_child_total_steps": good["child_total_steps"],
            "optimized_child_faster_cases": good["faster_child_cases"],
            "defective_child_gate": bad["gate"],
            "first_counterexample": bad["witnesses"][0],
            "matrix_math_work_kJ": matrix["calculator"]["value"],
            "no_model_weights_modified": True,
            "production_authority": False,
        },
        "evidence": {
            "optimized_receipt_sha256": good["receipt_sha256"],
            "rejected_receipt_sha256": bad["receipt_sha256"],
            "integrated_matrix_receipt_sha256": matrix["receipt_sha256"],
        },
        "limits": {
            "blind": False, "universal_equivalence_proven": False,
            "cross_repo_models_executed": False,
            "real_software_performance_proven": False,
        },
    }
    report["report_sha256"] = kernel.digest(report)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",
                       encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run(out=FIXTURES / "comparison.json")
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
