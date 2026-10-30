#!/usr/bin/env python3
"""Independent bounded wake for the existing Genesis Cloud HOME.

This worker cannot mutate HOME state: only the already-reviewed main-branch
HOME workflow may reconstruct and checkpoint the resident. Fail closed on
missing durable evidence, active runs, recent attempts, or untrusted history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re

WORKFLOW = ".github/workflows/janus-habitat-cloud-home-v1.yml"
HOME_STATE = "state/habitat_cloud_home/STATE.json"
RECEIPT = re.compile(r"state/habitat_cloud_home/receipts/[0-9]{8}-[0-9]{5,}-[1-9][0-9]*\.json\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
LAST_ATTEMPT_SECONDS = 75 * 60
LAST_SUCCESS_SECONDS = 90 * 60
ALLOWED_EVENTS = frozenset({"schedule", "workflow_dispatch", "push", "workflow_run"})
RUN_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending", "completed"})
REQUIRED_DISABLED = ("pc_required", "remote_desktop_required", "nas_required",
                     "lan_required", "process_uptime_required")


class HomeRecoveryHold(ValueError):
    pass


def utc(raw: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise HomeRecoveryHold("RUN_TIMESTAMP_INVALID")
    try:
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HomeRecoveryHold("RUN_TIMESTAMP_INVALID") from exc
    if date.tzinfo is None:
        raise HomeRecoveryHold("RUN_TIMESTAMP_INVALID")
    return date


def verify_durable_home(directory: Path) -> dict:
    """Check the current exact Git checkpoint before requesting a new worker."""
    directory = Path(directory)
    path = directory / HOME_STATE
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise HomeRecoveryHold("HOME_SYMLINK")
    try:
        raw = path.read_bytes()
        state = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise HomeRecoveryHold("HOME_CHECKPOINT_UNAVAILABLE") from exc
    if (len(raw) > 100_000 or not isinstance(state, dict) or
        state.get("schema") != "JANUS_HABITAT_CLOUD_HOME_STATE_V1" or
        state.get("durable_identity") != "JANUS_HABITAT_RESIDENT_V1" or
        state.get("status") != "CLOUD_HOME_ACTIVE" or
        state.get("cloud_execution_required") is not True or
        state.get("source_writeback_default") != "DENY" or
        state.get("destructive_action") != "FORBIDDEN" or
        state.get("authority_delta") != 0 or
        type(state.get("sequence")) is not int or state["sequence"] < 1 or
        any(state.get(k) is not False for k in REQUIRED_DISABLED)):
        raise HomeRecoveryHold("HOME_CHECKPOINT_INVALID")
    name = state.get("checkpoint_head")
    if (not isinstance(name, str) or not RECEIPT.fullmatch(name) or
        state.get("handoff_head") != name or
        not isinstance(state.get("last_receipt_sha256"), str) or
        not SHA.fullmatch(state["last_receipt_sha256"])):
        raise HomeRecoveryHold("HOME_RECEIPT_POINTER_INVALID")
    receipt_path = directory / name
    if receipt_path.is_symlink() or any(p.is_symlink() for p in receipt_path.parents):
        raise HomeRecoveryHold("HOME_RECEIPT_SYMLINK")
    try:
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
    except (OSError, ValueError) as exc:
        raise HomeRecoveryHold("HOME_RECEIPT_UNAVAILABLE") from exc
    if (not receipt_raw or len(receipt_raw) > 100_000 or
        hashlib.sha256(receipt_raw).hexdigest() != state["last_receipt_sha256"] or
        not isinstance(receipt, dict) or
        receipt.get("schema") != "JANUS_HABITAT_CLOUD_HOME_RECEIPT_V1" or
        receipt.get("sequence") != state["sequence"] or
        receipt.get("source_main_sha") != state.get("source_main_sha") or
        receipt.get("run_id") != state.get("last_run_id") or
        receipt.get("resident_identity") != state["durable_identity"] or
        receipt.get("execute_status") != "CHECKPOINT_ONLY" or
        receipt.get("authority_delta") != 0 or
        receipt.get("source_writeback_observed") is not False or
        receipt.get("hidden_session_context_used") is not False):
        raise HomeRecoveryHold("HOME_RECEIPT_INTEGRITY")
    beetle = state.get("beetle_memory")
    if (not isinstance(beetle, dict) or
        beetle.get("status") not in
          ("HASH_MATCHED_UNVERIFIED_CONTEXT_STAGED", "NO_ACKED_CONTEXT_AVAILABLE") or
        beetle.get("command_authority") is not False or
        beetle.get("external_effect_authority") is not False or
        beetle.get("scientific_authority_delta") != 0 or
        receipt.get("beetle_memory") != beetle):
        raise HomeRecoveryHold("HOME_CONTEXT_AUTHORITY_MISMATCH")
    if beetle["status"] == "HASH_MATCHED_UNVERIFIED_CONTEXT_STAGED":
        folder = directory / "state/habitat_cloud_home/memory/beetle"
        ctx, cursor_path = folder / "CONTEXT.json", folder / "CURSOR.json"
        if any(p.is_symlink() for p in (ctx, cursor_path, *folder.parents)):
            raise HomeRecoveryHold("HOME_STAGED_CONTEXT_SYMLINK")
        try:
            ctx_raw = ctx.read_bytes()
            cursor_raw = cursor_path.read_bytes()
            context, cursor = json.loads(ctx_raw), json.loads(cursor_raw)
        except (OSError, ValueError) as exc:
            raise HomeRecoveryHold("HOME_STAGED_CONTEXT_UNAVAILABLE") from exc
        if (not ctx_raw or len(ctx_raw) > 180_000 or
            not cursor_raw or len(cursor_raw) > 100_000 or
            hashlib.sha256(ctx_raw).hexdigest() != beetle.get("context_sha256") or
            hashlib.sha256(cursor_raw).hexdigest() != beetle.get("cursor_sha256") or
            type(beetle.get("cursor_sequence")) is not int or
            cursor.get("last_sequence") != beetle["cursor_sequence"] or
            context.get("last_sequence") != beetle["cursor_sequence"] or
            cursor.get("context_sha256") != beetle["context_sha256"] or
            context.get("untrusted_research_only") is not True or
            context.get("model_text_is_command") is not False or
            context.get("scientific_authority_delta") != 0 or
            context.get("external_effect_authority_delta") != 0):
            raise HomeRecoveryHold("HOME_STAGED_CONTEXT_INTEGRITY")
    return {"sequence": state["sequence"], "receipt_sha256": state["last_receipt_sha256"]}


def decide(collection: dict, now: datetime) -> dict:
    """One dispatch at most; never replace a queued or running HOME worker."""
    if not isinstance(collection, dict) or not isinstance(collection.get("workflow_runs"), list):
        raise HomeRecoveryHold("HOME_RUN_COLLECTION_UNAVAILABLE")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise HomeRecoveryHold("HOME_CLOCK_INVALID")
    rows = []
    for run in collection["workflow_runs"]:
        if not isinstance(run, dict):
            raise HomeRecoveryHold("HOME_RUN_ENTRY_INVALID")
        if (run.get("path") != WORKFLOW or run.get("head_branch") != "main" or
            run.get("event") not in ALLOWED_EVENTS):
            continue
        if (type(run.get("id")) is not int or run["id"] < 1 or
            run.get("status") not in RUN_STATUSES):
            raise HomeRecoveryHold("HOME_RUN_ID_OR_STATUS_INVALID")
        age = (now - utc(run.get("created_at"))).total_seconds()
        if age < -60:
            raise HomeRecoveryHold("HOME_RUN_CLOCK_FUTURE")
        rows.append((age, run))
    if not rows:
        raise HomeRecoveryHold("HOME_RUN_HISTORY_UNVERIFIED")
    if any(run["status"] != "completed" for _, run in rows):
        return {"status": "HOLD_ACTIVE_HOME_RUN", "dispatch": False}
    if min(age for age, _ in rows) < LAST_ATTEMPT_SECONDS:
        return {"status": "HOLD_RECENT_HOME_ATTEMPT", "dispatch": False}
    successes = [age for age, run in rows if run["conclusion"] == "success"]
    if successes and min(successes) < LAST_SUCCESS_SECONDS:
        return {"status": "HOLD_RECENT_HOME_SUCCESS", "dispatch": False}
    return {"status": "RECOVER_MISSED_CLOUD_HOME", "dispatch": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        verified = verify_durable_home(args.state_root)
        runs = json.loads(args.runs.read_bytes())
        decision = decide(runs, datetime.now(timezone.utc))
    except (HomeRecoveryHold, OSError, ValueError) as exc:
        print("JANUS_CLOUD_HOME_RECOVERY=HOLD_" + str(exc))
        return 2
    print(json.dumps({"schema": "janus.habitat.home_recovery_decision.v1",
                      "durable_sequence": verified["sequence"], **decision,
                      "authority_delta": 0, "pc_required": False}, sort_keys=True))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("dispatch=" + ("true" if decision["dispatch"] else "false") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
