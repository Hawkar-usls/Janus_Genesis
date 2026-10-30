#!/usr/bin/env python3
"""Bounded Git-backed two-clean-cloud-worker completion lab for Habitat #162.

This tests a scoped checkpoint/variant/handoff/once lifecycle in a separate
dedicated LAB branch. It never executes source, calls models, writes source
repositories, changes production HOME, or claims full #162 admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "janus.nexus.bounded_two_cloud_writer_lab.v1"
ROOT = Path("data/nexus_closed_loop_lab/runs")
SHA = re.compile(r"^[0-9a-f]{40}$")
RUN = re.compile(r"^[1-9][0-9]{3,23}$")
REAL44_RUN = 41049447362
REAL44_SHA = "e4baea1840173648150d10161096134e43b81926"


class LabHold(Exception):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False)).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def expect(condition: bool, code: str) -> None:
    if not condition:
        raise LabHold(code)


def load(path: Path) -> dict[str, Any]:
    expect(not path.is_symlink() and path.is_file(), "MISSING_OR_SYMLINK_LAB_RECEIPT")
    value = json.loads(path.read_bytes())
    expect(isinstance(value, dict), "LAB_RECEIPT_NOT_OBJECT")
    return value


def create_only(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    expect(not path.is_symlink(), "LAB_SYMLINK_RECEIPT_REJECTED")
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(data)
    except FileExistsError:
        expect(path.read_text(encoding="utf-8") == data,
               "IMMUTABLE_LAB_RECEIPT_COLLISION")


def run_dir(root: Path, run_id: str) -> Path:
    expect(bool(RUN.fullmatch(run_id)), "RUN_ID_INVALID")
    root = root.resolve()
    path = root / ROOT / run_id
    expect(path.resolve().is_relative_to(root), "LAB_PATH_ESCAPE_REJECTED")
    return path


def verify_real44(pointer: dict[str, Any]) -> dict[str, Any]:
    expect(pointer.get("schema") == "janus.nexus.real44.public_latest.v1",
           "REAL44_INDEPENDENT_WITNESS_SCHEMA_INVALID")
    expect(pointer.get("status") == "PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE",
           "REAL44_SOURCE_WITNESS_NOT_PASS")
    expect(pointer.get("source_run_id") == REAL44_RUN and
           pointer.get("source_commit") == REAL44_SHA,
           "REAL44_SOURCE_PIN_NOT_ADMITTED")
    expect(pointer.get("actual_cross_organ_runtime_execution_attested") is False
           and pointer.get("full_issue_162_acceptance") is False,
           "REAL44_SOURCE_WITNESS_AUTHORITY_INVALID")
    return {"source_run_id": REAL44_RUN, "source_commit": REAL44_SHA,
            "source_public_witness_sha256": sha(pointer),
            "runtime_source_execution_proven": False}


def phase_a(root: Path, run_id: str, registry: Path,
            code_sha: str) -> dict[str, Any]:
    expect(bool(SHA.fullmatch(code_sha)), "GENESIS_CODE_SHA_INVALID")
    source = verify_real44(load(registry))
    event_id = "nexus-lab-" + run_id
    good = {"variant_id": "baseline-" + run_id, "parent": "none",
            "input_sha256": sha({"source": source, "event": event_id}),
            "bounded_mutation": "NO_EXTERNAL_EFFECT",
            "test_result": "PASS_LAB_DETERMINISTIC",
            "runtime_model_executed": False}
    bad = {"variant_id": "rejected-" + run_id, "parent": good["variant_id"],
           "input_sha256": "0" * 64,
           "bounded_mutation": "INTENTIONAL_SOURCE_DIGEST_MISMATCH",
           "test_result": "FAIL_LAB_SOURCE_DIGEST_MISMATCH",
           "retained": True,
           "runtime_model_executed": False}
    variants = {"schema": SCHEMA+".variants", "candidates": [good, bad],
                "selected_variant_id": good["variant_id"],
                "failed_variant_ids": [bad["variant_id"]],
                "source_writeback": False, "model_call": False}
    state = {"schema": SCHEMA+".checkpoint", "event_id": event_id,
             "run_id": run_id, "producer_code_sha": code_sha,
             "source": source, "variant_lineage_sha256": sha(variants),
             "status": "HANDOFF_DURABLY_PREPARED_NOT_COMPLETED",
             "source_writeback": False, "external_effect": False,
             "authority_delta": 0}
    receipt = {"schema": SCHEMA+".worker_a", "event_id": event_id,
               "run_id": run_id, "checkpoint_sha256": sha(state),
               "variant_lineage_sha256": sha(variants),
               "worker": "cloud-worker-a", "checkpoint_committed_in_git": "TO_BE_VERIFIED_BY_B",
               "synthesized_source_code_execution": False,
               "model_call": False, "worker_b_resumed": False}
    base = run_dir(root, run_id)
    for name, obj in (("variants.json", variants), ("checkpoint.json", state),
                      ("worker-a.json", receipt)):
        create_only(base / name, obj)
    return receipt


def _validate_a(root: Path, run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    base = run_dir(root, run_id)
    variants, state, a = (load(base / n) for n in
                          ("variants.json", "checkpoint.json", "worker-a.json"))
    expect(state.get("schema") == SCHEMA+".checkpoint" and
           variants.get("schema") == SCHEMA+".variants" and
           a.get("schema") == SCHEMA+".worker_a",
           "LAB_SCHEMA_MISMATCH")
    expect(state.get("run_id") == run_id and a.get("run_id") == run_id and
           state.get("event_id") == a.get("event_id") == "nexus-lab-"+run_id,
           "LAB_EVENT_ID_MISMATCH")
    expect(state.get("source_writeback") is False and
           state.get("authority_delta") == 0 and
           state.get("external_effect") is False,
           "LAB_AUTHORITY_ESCALATION")
    expect(state.get("source", {}).get("source_run_id") == REAL44_RUN and
           state.get("source", {}).get("source_commit") == REAL44_SHA,
           "LAB_REAL44_SOURCE_BINDING_MISMATCH")
    expect(sha(state) == a.get("checkpoint_sha256") and
           sha(variants) == state.get("variant_lineage_sha256") == a.get("variant_lineage_sha256"),
           "LAB_DURABLE_CHAIN_DIGEST_MISMATCH")
    rows = variants.get("candidates")
    expect(isinstance(rows, list) and len(rows) == 2, "LAB_VARIANTS_REQUIRED")
    pass_rows = [r for r in rows if r.get("test_result") == "PASS_LAB_DETERMINISTIC"]
    fail_rows = [r for r in rows if r.get("test_result") == "FAIL_LAB_SOURCE_DIGEST_MISMATCH"]
    expect(len(pass_rows) == len(fail_rows) == 1 and
           pass_rows[0].get("input_sha256") == sha({"source": state["source"], "event": state["event_id"]}) and
           fail_rows[0].get("input_sha256") != sha({"source": state["source"], "event": state["event_id"]}) and
           pass_rows[0].get("bounded_mutation") == "NO_EXTERNAL_EFFECT" and
           fail_rows[0].get("bounded_mutation") == "INTENTIONAL_SOURCE_DIGEST_MISMATCH" and
           fail_rows[0].get("retained") is True and
           variants.get("selected_variant_id") == pass_rows[0].get("variant_id") and
           variants.get("failed_variant_ids") == [fail_rows[0].get("variant_id")],
           "LAB_FAILED_VARIANT_NOT_RETAINED")
    expect(state.get("status") == "HANDOFF_DURABLY_PREPARED_NOT_COMPLETED" and
           a.get("worker_b_resumed") is False,
           "LAB_WORKER_A_CLAIM_MISMATCH")
    return base, state, variants


def phase_b(root: Path, run_id: str, a_git_commit: str) -> str:
    expect(bool(SHA.fullmatch(a_git_commit)), "LAB_A_GIT_COMMIT_INVALID")
    base, state, variants = _validate_a(root, run_id)
    out = {"schema": SCHEMA+".worker_b", "event_id": state["event_id"],
           "worker": "cloud-worker-b", "source_git_checkpoint_commit": a_git_commit,
           "checkpoint_sha256": sha(state),
           "variant_lineage_sha256": sha(variants),
           "selected_variant_id": variants["selected_variant_id"],
           "failed_variant_ids_retained": variants["failed_variant_ids"],
           "completion_id": sha({"event_id": state["event_id"],
                                 "checkpoint": sha(state)}),
           "status": "COMPLETED_ONCE_IN_LAB_ONLY",
           "external_model_call_executed": False,
           "production_receiver_consumption_proven": False,
           "full_issue_162_acceptance": False,
           "source_writeback": False, "authority_delta": 0}
    existed = (base / "worker-b.json").exists()
    create_only(base / "worker-b.json", out)
    return "IDEMPOTENT_EXISTING" if existed else "COMPLETED_NEW"


def inspect(root: Path, run_id: str, a_git_commit: str) -> dict[str, Any]:
    base, state, variants = _validate_a(root, run_id)
    b = load(base / "worker-b.json")
    expect(b.get("schema") == SCHEMA+".worker_b" and
           b.get("source_git_checkpoint_commit") == a_git_commit and
           b.get("checkpoint_sha256") == sha(state) and
           b.get("variant_lineage_sha256") == sha(variants) and
           b.get("event_id") == state["event_id"] and
           b.get("status") == "COMPLETED_ONCE_IN_LAB_ONLY" and
           b.get("source_writeback") is False and
           b.get("authority_delta") == 0,
           "LAB_WORKER_B_ATTESTATION_INVALID")
    expect(b.get("external_model_call_executed") is False and
           b.get("full_issue_162_acceptance") is False,
           "LAB_FALSE_RUNTIME_AUTHORITY")
    return {"schema": SCHEMA+".independent_verdict",
            "status": "PASS_LAB_TWO_CLEAN_CLOUD_WORKERS_ONLY",
            "source_run_id": REAL44_RUN,
            "frozen_source_commit": REAL44_SHA,
            "lab_run_id": run_id, "phase_a_git_head": a_git_commit,
            "event_id": state["event_id"],
            "checkpoint_sha256": sha(state),
            "variant_lineage_sha256": sha(variants),
            "failed_variant_retained": True,
            "completion_id": b["completion_id"],
            "model_call_in_lab": False,
            "live_cross_organ_receiver_consumption": False,
            "real44_same_run_full_materialization": False,
            "g1_to_g20_full_acceptance": False,
            "full_issue_162_acceptance": False,
            "source_writeback": False,
            "dedicated_lab_branch_write": True,
            "production_source_files_modified": False,
            "authority_delta": 0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("a", "b", "inspect", "death"))
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--registry", type=Path)
    p.add_argument("--code-sha", default="")
    p.add_argument("--a-git-commit", default="")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    try:
        if args.phase == "a":
            expect(args.registry is not None, "REAL44_REGISTRY_POINTER_REQUIRED")
            r = phase_a(args.root, args.run_id, args.registry, args.code_sha)
            print("LAB_WORKER_A_DURABLE_PREPARED=PASS")
        elif args.phase == "death":
            _validate_a(args.root, args.run_id)
            os._exit(77)  # intentional child-process death after durable Git commit
        elif args.phase == "b":
            r = phase_b(args.root, args.run_id, args.a_git_commit)
            print("LAB_WORKER_B_COMPLETION="+r)
        else:
            r = inspect(args.root, args.run_id, args.a_git_commit)
            if args.output:
                args.output.write_text(json.dumps(r, sort_keys=True, indent=2)+"\n")
            print("LAB_TWO_CLOUD_WRITERS=SCOPED_PASS")
    except (LabHold, OSError, ValueError, KeyError) as exc:
        code = str(exc) if isinstance(exc, LabHold) else "LAB_IO_OR_INPUT_HOLD"
        print("NEXUS_LAB_HOLD="+code, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
