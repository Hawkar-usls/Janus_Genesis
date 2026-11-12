#!/usr/bin/env python3
"""One-run real native MODEL.CALL -> Git checkpoint -> clean B lab for Genesis #162.

Research-only. Two model-generated *text* candidates are structurally checked,
not executed as code, trusted as instructions, or evaluated for scientific truth.
A is deliberately killed after its commit. B resumes only from pinned Git state
and writes a bounded INTERNAL lab-consumer receipt. An independent read-only
worker replays every receipt. This is NOT REAL44 same-run or full G1-G20.
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

if __package__:
    from tools.janus_nexus_same_run_model_handoff_v1 import (
        MODEL_COMMIT, CHECKPOINT_SHA256, PROMPT, bounded_bytes,
        suffix_from_output, verify_model_source,
    )
else:
    from janus_nexus_same_run_model_handoff_v1 import (
        MODEL_COMMIT, CHECKPOINT_SHA256, PROMPT, bounded_bytes,
        suffix_from_output, verify_model_source,
    )

SCHEMA = "janus.nexus.integrated_native_git_lab.v1"
ROOT = Path("data/nexus_integrated_native_lab/runs")
REGISTRY_SCHEMA = "janus.nexus.real44.public_latest.v1"
REGISTRY_SOURCE_RUN = 42609770065
REGISTRY_SOURCE_SHA = "d19db049b7e02eccd0b7e870c6dcf133f2c701ab"
SHA40 = re.compile(r"^[a-f0-9]{40}$")
RUN = re.compile(r"^[1-9][0-9]{3,23}$")
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})")
MAX_PROPOSAL_BYTES = 512


class Hold(Exception):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Hold(reason)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def raw_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "RECEIPT_MISSING_OR_SYMLINK")
    require(path.stat().st_size <= 65_536, "RECEIPT_TOO_LARGE")
    result = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(result, dict), "RECEIPT_NOT_OBJECT")
    return result


def save_once(path: Path, value: dict) -> bool:
    require(not path.is_symlink(), "SYMLINK_OUTPUT_FORBIDDEN")
    raw = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    require(len(raw.encode("utf-8")) <= 65_536, "OUTPUT_TOO_LARGE")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.is_file() and path.read_text(encoding="utf-8") == raw,
                "IMMUTABLE_RECEIPT_CONFLICT")
        return False
    with path.open("x", encoding="utf-8") as stream:
        stream.write(raw)
    return True


def run_path(root: Path, run_id: str, attempt: int) -> Path:
    require(bool(RUN.fullmatch(run_id)), "RUN_ID_INVALID")
    require(type(attempt) is int and 1 <= attempt <= 1000, "ATTEMPT_INVALID")
    target = root.resolve() / ROOT / (run_id + "-" + str(attempt))
    require(target.resolve().is_relative_to(root.resolve()), "RUN_PATH_ESCAPE")
    return target


def source_witness(value: dict) -> dict:
    require(value.get("schema") == REGISTRY_SCHEMA, "REAL44_SCHEMA_INVALID")
    require(value.get("status") == "PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE",
            "REAL44_ARCHIVE_NOT_PASS")
    require(value.get("source_run_id") == REGISTRY_SOURCE_RUN and
            value.get("source_commit") == REGISTRY_SOURCE_SHA,
            "REAL44_PIN_DRIFT")
    require(value.get("full_issue_162_acceptance") is False and
            value.get("actual_cross_organ_runtime_execution_attested") is False,
            "REAL44_FALSE_AUTHORITY")
    return {"archived_real44_run": REGISTRY_SOURCE_RUN,
            "archived_genesis_sha": REGISTRY_SOURCE_SHA,
            "archive_record_digest": digest(value),
            "same_run_real44_materialized": False}


def proposal(raw: bytes) -> dict:
    suffix = suffix_from_output(raw)
    size = len(suffix.encode("utf-8"))
    require(0 < size <= MAX_PROPOSAL_BYTES, "MODEL_PROPOSAL_SIZE")
    require(all(x.isprintable() or x in "\n\t" for x in suffix),
            "MODEL_PROPOSAL_CONTROL_CHARACTER")
    require(not SECRET.search(suffix), "MODEL_PROPOSAL_SECRET_LIKE")
    require(bool(suffix.strip()), "MODEL_PROPOSAL_EMPTY")
    return {
        "text": suffix,
        "proposal_sha256": raw_sha(suffix.encode("utf-8")),
        "raw_stdout_sha256": raw_sha(raw),
        "model_generated": True,
    }


def structural_score(text: str) -> dict:
    encoded = text.encode("utf-8")
    require(0 < len(encoded) <= MAX_PROPOSAL_BYTES, "CANDIDATE_OUT_OF_BOUNDS")
    require(bool(text.strip()), "CANDIDATE_EMPTY")
    require(not SECRET.search(text), "CANDIDATE_SECRET_LIKE")
    require(all(x.isprintable() or x in "\n\t" for x in text),
            "CANDIDATE_CONTROL_CHAR")
    words = re.findall(r"[A-Za-z]{2,}", text)
    return {"utf8_bytes": len(encoded), "word_count": len(text.split()),
            "latin_words": len(words),
            "score": min(len(words), 20) * 100 - len(encoded)}


def make_variants(proposals: list[dict]) -> dict:
    require(len(proposals) == 2, "TWO_REAL_MODEL_OUTPUTS_REQUIRED")
    require(proposals[0]["proposal_sha256"] != proposals[1]["proposal_sha256"],
            "MODEL_OUTPUTS_IDENTICAL_HOLD")
    candidates = []
    for idx, item in enumerate(proposals):
        tests = structural_score(item["text"])
        require(item["proposal_sha256"] == raw_sha(item["text"].encode("utf-8")),
                "PROPOSAL_DIGEST_MISMATCH")
        candidates.append({
            "variant_id": "model-" + str(idx + 1),
            "source": "PINNED_REAL_NATIVE_MODEL_CALL",
            "proposal": item,
            "structural_tests": tests,
            "unsafe_execution_attempted": False,
        })
    # A model did NOT pick the winner: a deterministic, scoped text-structure
    # comparator only ranks two distinct actual model outputs.
    ranked = sorted(candidates, key=lambda c:
                    (-c["structural_tests"]["score"], c["variant_id"]))
    selected = ranked[0]["variant_id"]
    return {
        "schema": SCHEMA + ".variants",
        "candidates": candidates,
        "selected_variant_id": selected,
        "rejected_variant_ids_retained": [c["variant_id"] for c in candidates
                                         if c["variant_id"] != selected],
        "selection_basis": "DETERMINISTIC_TEXT_STRUCTURE_ONLY_NOT_MODEL_QUALITY",
        "model_generated_count": 2,
        "code_patch_generated_or_tested": False,
        "science_improvement_verified": False,
        "authority_delta": 0,
    }


def make_a(root: Path, run_id: str, attempt: int, code_sha: str,
           registry: dict, raw_a: bytes, raw_b: bytes) -> dict:
    require(bool(SHA40.fullmatch(code_sha)), "GENESIS_SHA_INVALID")
    base = run_path(root, run_id, attempt)
    require(not base.exists(), "RUN_ID_ALREADY_PRESENT_HOLD")
    variants = make_variants([proposal(raw_a), proposal(raw_b)])
    witness = source_witness(registry)
    checkpoint = {
        "schema": SCHEMA + ".checkpoint",
        "run_id": run_id, "attempt": attempt,
        "code_sha": code_sha,
        "source_witness": witness,
        "model_commit": MODEL_COMMIT,
        "checkpoint_model_sha256": CHECKPOINT_SHA256,
        "variant_digest": digest(variants),
        "selected_variant_id": variants["selected_variant_id"],
        "fence_epoch": 1,
        "lease_owner": "worker-a",
        "lease_state": "A_CHECKPOINT_PREPARED",
        "stage": "PENDING_CLEAN_WORKER_B",
        "source_writeback": False, "external_effect": False,
        "full_issue_162_acceptance": False, "authority_delta": 0,
    }
    a = {
        "schema": SCHEMA + ".worker_a",
        "run_id": run_id, "attempt": attempt,
        "checkpoint_digest": digest(checkpoint),
        "variant_digest": digest(variants),
        "status": "PREPARED_FOR_GIT_COMMIT_THEN_PROCESS_DEATH",
        "fence_epoch": 1,
        "model_generated_variants": 2,
        "a_git_commit": "CHECKED_BY_CLEAN_WORKER_B",
        "authority_delta": 0,
    }
    for filename, value in (("variants.json", variants),
                            ("checkpoint.json", checkpoint),
                            ("worker-a.json", a)):
        save_once(base / filename, value)
    return a


def validate_a(root: Path, run_id: str, attempt: int, registry: dict
               ) -> tuple[Path, dict, dict]:
    base = run_path(root, run_id, attempt)
    variants, state, a = (read(base / name) for name in
                          ("variants.json", "checkpoint.json", "worker-a.json"))
    require(state.get("schema") == SCHEMA + ".checkpoint" and
            variants.get("schema") == SCHEMA + ".variants" and
            a.get("schema") == SCHEMA + ".worker_a", "SCHEMA_MISMATCH")
    require(state.get("run_id") == a.get("run_id") == run_id and
            state.get("attempt") == a.get("attempt") == attempt,
            "RUN_ID_OR_ATTEMPT_MISMATCH")
    require(bool(SHA40.fullmatch(str(state.get("code_sha", "")))),
            "SOURCE_SHA_INVALID")
    require(state.get("source_witness") == source_witness(registry),
            "FROZEN_REAL44_WITNESS_MISMATCH")
    require(state.get("model_commit") == MODEL_COMMIT and
            state.get("checkpoint_model_sha256") == CHECKPOINT_SHA256,
            "MODEL_SOURCE_DRIFT")
    require(state.get("variant_digest") == digest(variants) ==
            a.get("variant_digest"), "VARIANT_DIGEST_MISMATCH")
    require(a.get("checkpoint_digest") == digest(state), "CHECKPOINT_DIGEST_MISMATCH")
    proposals = [c["proposal"] for c in variants.get("candidates", [])]
    require(make_variants(proposals) == variants, "MODEL_VARIANT_REPLAY_MISMATCH")
    require(state.get("selected_variant_id") == variants["selected_variant_id"],
            "SELECTED_VARIANT_DRIFT")
    require(state.get("lease_owner") == "worker-a" and
            state.get("fence_epoch") == a.get("fence_epoch") == 1 and
            state.get("stage") == "PENDING_CLEAN_WORKER_B",
            "LEASE_FENCE_STATE_INVALID")
    require(state.get("source_writeback") is False and
            state.get("external_effect") is False and
            state.get("authority_delta") == a.get("authority_delta") == 0 and
            state.get("full_issue_162_acceptance") is False,
            "AUTHORITY_ESCALATION")
    return base, state, variants


def receiver_receipt(state: dict, variants: dict, a_head: str) -> dict:
    selected = next(c for c in variants["candidates"]
                    if c["variant_id"] == variants["selected_variant_id"])
    checked = structural_score(selected["proposal"]["text"])
    require(checked == selected["structural_tests"], "RECEIVER_TEST_DRIFT")
    return {
        "schema": SCHEMA + ".receiver",
        "consumer": "CLEAN_WORKER_B_INTERNAL_LAB_EVALUATOR_ONLY",
        "source_a_git_commit": a_head,
        "selected_variant_id": selected["variant_id"],
        "received": "RECEIVED",
        "parsed": "PARSED",
        "loaded": "LOADED",
        "executed": "EXECUTED_PURE_STRUCTURAL_TEST_ONLY",
        "consumed_proposal_sha256": selected["proposal"]["proposal_sha256"],
        "result": checked,
        "external_downstream_consumer_ack": False,
        "production_model_loaded": False,
        "model_text_instructions_executed": False,
        "authority_delta": 0,
    }


def worker_b_receipt(state: dict, variants: dict, receiver: dict,
                     a_head: str) -> dict:
    require(bool(SHA40.fullmatch(a_head)), "A_COMMIT_INVALID")
    completion = digest({"run": state["run_id"], "attempt": state["attempt"],
                         "checkpoint": digest(state),
                         "selected": variants["selected_variant_id"]})
    return {
        "schema": SCHEMA + ".worker_b", "run_id": state["run_id"],
        "attempt": state["attempt"],
        "a_git_commit": a_head,
        "checkpoint_digest": digest(state),
        "variants_digest": digest(variants),
        "receiver_digest": digest(receiver),
        "completion_id": completion,
        "status": "LAB_CONSUMED_COMPLETED_ONCE",
        "fence_from": 1, "fence_to": 2,
        "lease_takeover": "CLEAN_B_AFTER_A_PROCESS_EXIT",
        "external_receiver_ack": False,
        "full_issue_162_acceptance": False,
        "source_writeback": False, "authority_delta": 0,
    }


def make_b(root: Path, run_id: str, attempt: int,
           registry: dict, a_head: str) -> str:
    require(bool(SHA40.fullmatch(a_head)), "A_COMMIT_INVALID")
    base, state, variants = validate_a(root, run_id, attempt, registry)
    rx = receiver_receipt(state, variants, a_head)
    b = worker_b_receipt(state, variants, rx, a_head)
    already = (base / "worker-b.json").exists()
    save_once(base / "receiver.json", rx)
    save_once(base / "worker-b.json", b)
    return "IDEMPOTENT_EXISTING" if already else "COMPLETED_NEW"


def verify(root: Path, run_id: str, attempt: int,
           registry: dict, a_head: str, b_head: str) -> dict:
    require(bool(SHA40.fullmatch(b_head)) and a_head != b_head,
            "GIT_A_B_HEADS_INVALID")
    base, state, variants = validate_a(root, run_id, attempt, registry)
    rx = read(base / "receiver.json")
    b = read(base / "worker-b.json")
    require(rx == receiver_receipt(state, variants, a_head),
            "CONSUMER_ACK_FORGED")
    require(b == worker_b_receipt(state, variants, rx, a_head),
            "WORKER_B_RECEIPT_FORGED")
    require(b["completion_id"] and b["status"] == "LAB_CONSUMED_COMPLETED_ONCE",
            "COMPLETION_MISSING")
    files = {p.name for p in base.iterdir()}
    require(files == {"checkpoint.json", "variants.json", "worker-a.json",
                      "worker-b.json", "receiver.json"},
            "EXTRA_OR_MISSING_RECEIPTS")
    return {
        "schema": SCHEMA + ".independent_verdict",
        "status": "PASS_SCOPED_NATIVE_MODEL_GIT_A_B_LAB_ONLY",
        "run_id": run_id, "attempt": attempt,
        "source_code_sha": state["code_sha"],
        "a_git_commit": a_head, "b_git_commit": b_head,
        "model_generated_text_variants": 2,
        "failed_or_unselected_variant_retained": True,
        "real_native_model_outputs_persisted_as_bounded_text": True,
        "a_process_death_asserted_by_workflow_job": True,
        "durable_git_handoff_verified": True,
        "lab_receiver_evaluation_executed": True,
        "production_receiver_ack": False,
        "live_lease_race_tested": False,
        "source44_same_run_materialization": False,
        "real_software_patch_selected_and_tested": False,
        "g1_g20_same_run_full_pass": False,
        "full_issue_162_acceptance": False,
        "source_writeback": False,
        "authority_delta": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("a", "death", "b", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--brain", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--code-sha", default="")
    parser.add_argument("--a-head", default="")
    parser.add_argument("--b-head", default="")
    parser.add_argument("--raw-a", type=Path)
    parser.add_argument("--raw-b", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        registry = read(args.registry)
        if args.brain is not None:
            verify_model_source(args.brain)
        if args.phase == "a":
            require(args.brain is not None and args.raw_a is not None
                    and args.raw_b is not None, "PINNED_MODEL_AND_TWO_OUTPUTS_REQUIRED")
            make_a(args.root, args.run_id, args.attempt, args.code_sha,
                   registry, bounded_bytes(args.raw_a), bounded_bytes(args.raw_b))
            print("NEXUS_INTEGRATED_MODEL_A=PREPARED_FOR_DURABLE_GIT")
        elif args.phase == "death":
            validate_a(args.root, args.run_id, args.attempt, registry)
            os._exit(77)
        elif args.phase == "b":
            result = make_b(args.root, args.run_id, args.attempt,
                            registry, args.a_head)
            print("NEXUS_INTEGRATED_MODEL_B=" + result)
        else:
            result = verify(args.root, args.run_id, args.attempt, registry,
                            args.a_head, args.b_head)
            require(args.output is not None and not args.output.exists(),
                    "FRESH_INDEPENDENT_OUTPUT_REQUIRED")
            save_once(args.output, result)
            print("NEXUS_INTEGRATED_NATIVE_GIT_LAB=" + result["status"])
        return 0
    except (Hold, OSError, ValueError, KeyError, TypeError, UnicodeError,
            json.JSONDecodeError) as exc:
        reason = str(exc) if isinstance(exc, Hold) else "INPUT_OR_IO_HOLD"
        print("NEXUS_INTEGRATED_MODEL=HOLD:" + reason, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
