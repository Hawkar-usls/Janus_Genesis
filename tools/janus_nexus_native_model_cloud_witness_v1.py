#!/usr/bin/env python3
"""Source-pinned, non-authoritative cloud native MODEL.CALL witness for Nexus #162.

This checks an actual native inference subprocess outcome against public Git
source/checkpoint provenance, not response truth, model quality or live organ
consumption. No read/write secrets or production state changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

LAB_RUN_ID = 41054190160
LAB_COMMIT = "6de3fc20c0b5a09d045d2fb321018e9b8d2b0b09"
LAB_A_COMMIT = "89173e799320c0cc4fbca75e583c4982b04b9966"
DEMIURGE_SOURCE = "c8c890206f53591d6bfe444d103ed5dd07ec2296"
CHECKPOINT_SHA256 = "fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463"
PROMPT = "JANUS NEXUS LAB 41054190160: give a short non-authoritative research status."


class WitnessHold(Exception):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise WitnessHold(code)


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        stderr=subprocess.DEVNULL, text=True
    ).strip()


def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "WITNESS_SOURCE_FILE_MISSING")
    value = json.loads(path.read_bytes())
    require(isinstance(value, dict), "WITNESS_SOURCE_NOT_OBJECT")
    return value


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect(lab: Path, brain: Path, output: Path) -> dict:
    require(git_head(lab) == LAB_COMMIT, "LAB_SOURCE_COMMIT_DRIFT")
    require(git_head(brain) == DEMIURGE_SOURCE, "NATIVE_MODEL_SOURCE_COMMIT_DRIFT")
    base = lab / "data/nexus_closed_loop_lab/runs" / str(LAB_RUN_ID)
    b = read_json(base / "worker-b.json")
    state = read_json(base / "checkpoint.json")
    variants = read_json(base / "variants.json")
    require(b.get("schema") == "janus.nexus.bounded_two_cloud_writer_lab.v1.worker_b"
            and b.get("source_git_checkpoint_commit") == LAB_A_COMMIT
            and b.get("status") == "COMPLETED_ONCE_IN_LAB_ONLY"
            and b.get("event_id") == "nexus-lab-"+str(LAB_RUN_ID),
            "LAB_COMPLETION_SOURCE_INVALID")
    require(state.get("source", {}).get("source_run_id") == 41049447362
            and state.get("source", {}).get("source_commit") ==
            "e4baea1840173648150d10161096134e43b81926",
            "LAB_REAL44_SOURCE_BINDING_INVALID")
    require(variants.get("failed_variant_ids") and
            b.get("failed_variant_ids_retained") == variants.get("failed_variant_ids"),
            "LAB_FAILED_VARIANT_EVIDENCE_MISSING")
    state_json = read_json(brain / "janus_model/state/JANUS_MODEL_STATE.json")
    require(state_json.get("checkpoint_sha256") == CHECKPOINT_SHA256,
            "NATIVE_MODEL_STATE_PIN_MISMATCH")
    ckpt = brain / "janus_model/checkpoints/promoted.pt"
    require(ckpt.is_file() and not ckpt.is_symlink() and
            digest(ckpt.read_bytes()) == CHECKPOINT_SHA256,
            "NATIVE_MODEL_CHECKPOINT_DIGEST_MISMATCH")
    require(output.is_file() and not output.is_symlink(),
            "NATIVE_GENERATED_OUTPUT_MISSING")
    raw = output.read_bytes()
    require(0 < len(raw) <= 15000, "NATIVE_GENERATED_OUTPUT_OUT_OF_BOUNDS")
    decoded = raw.decode("utf-8")
    require(decoded.strip() and PROMPT in decoded,
            "NATIVE_GENERATION_PROMPT_NOT_PRESENT")
    receipt = {
      "schema": "janus.nexus.source_pinned_native_model_cloud_call.v1",
      "status": "PASS_PINNED_REAL_NATIVE_MODEL_CALL_SCOPED_ONLY",
      "lab_run_id": LAB_RUN_ID,
      "lab_frozen_commit": LAB_COMMIT,
      "lab_worker_a_checkpoint_commit": LAB_A_COMMIT,
      "real44_source_run_id": 41049447362,
      "native_model_repository_commit": DEMIURGE_SOURCE,
      "native_checkpoint_sha256": CHECKPOINT_SHA256,
      "generated_text_sha256": digest(raw),
      "generated_text_bytes": len(raw),
      "model_call_executed": True,
      "raw_model_output_archived": False,
      "model_output_quality_verified": False,
      "model_output_is_truth": False,
      "model_output_is_authority": False,
      "source_code_execution": True,
      "source_code_execution_scope": "PINNED_LOCAL_DEMIURGE_NATIVE_INFERENCE_ONLY",
      "live_cross_organ_receiver_consumption": False,
      "same_run_integrated_g1_to_g20": False,
      "full_issue_162_acceptance": False,
      "source_writeback": False,
      "production_home_modified": False,
      "paid_provider_invoked": False,
      "authority_delta": 0,
    }
    return receipt


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lab", type=Path, required=True)
    p.add_argument("--brain", type=Path, required=True)
    p.add_argument("--model-output", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    try:
        value = inspect(a.lab, a.brain, a.model_output)
        require(not a.receipt.is_symlink(), "RECEIPT_DESTINATION_SYMLINK")
        a.receipt.write_text(json.dumps(value, sort_keys=True, indent=2)+"\n",
                             encoding="utf-8")
        print("NEXUS_NATIVE_MODEL_CLOUD_CALL=SCOPED_PASS")
        return 0
    except (WitnessHold, OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, WitnessHold) else "SOURCE_PINNED_MODEL_WITNESS_HOLD"
        print("NEXUS_NATIVE_MODEL_HOLD="+code, file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
