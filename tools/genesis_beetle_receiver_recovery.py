#!/usr/bin/env python3
"""Fail-closed missed-Beetle-receiver wake using existing Genesis cloud worker.

Read only: verified sender manifest, current inbox ACK, same-repository run list.
Writes only a boolean GitHub Actions output. Never writes ACK, queue or HOME.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

REPOSITORY = "Hawkar-usls/Janus_Genesis"
WORKFLOW = ".github/workflows/janus-beetle-memory-receiver.yml"
ACK_STATUS = "INBOX_DURABLE_UNVERIFIED__NOT_RUNTIME_CONSUMPTION"
MIN_LAST_ATTEMPT_SECONDS = 75 * 60
MIN_SUCCESS_SECONDS = 90 * 60
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_EVENTS = frozenset({"schedule", "workflow_dispatch", "push"})
ALLOWED_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending", "completed"})


class Hold(ValueError):
    pass


def utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise Hold("UNTRUSTED_RUN_TIMESTAMP")
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise Hold("UNTRUSTED_RUN_TIMESTAMP") from e
    if t.utcoffset() is None:
        raise Hold("UNTRUSTED_RUN_TIMESTAMP")
    return t


def pending_exact(queue, ack):
    if (not isinstance(queue, dict) or
        queue.get("schema") != "janus.beetle.delivery_queue.v1" or
        queue.get("target_repository") != REPOSITORY or
        not isinstance(queue.get("entries"), list) or
        type(queue.get("next_sequence")) is not int or
        queue["next_sequence"] != len(queue["entries"]) + 1):
        raise Hold("UNTRUSTED_SENDER_QUEUE")
    if (not isinstance(ack, dict) or
        ack.get("schema") != "janus.beetle.inbox_ack.v1" or
        ack.get("target_repository") != REPOSITORY or
        ack.get("status") != ACK_STATUS or
        ack.get("scientific_authority_delta") != 0 or
        type(ack.get("last_sequence")) is not int or
        not 0 <= ack["last_sequence"] <= len(queue["entries"])):
        raise Hold("UNTRUSTED_RECEIVER_ACK")
    acknowledged = ack["last_sequence"]
    if acknowledged:
        entry = queue["entries"][acknowledged - 1]
        if (not isinstance(entry, dict) or
            not isinstance(entry.get("sha256"), str) or
            not SHA256.fullmatch(entry["sha256"]) or
            ack.get("sha256") != entry["sha256"] or
            ack.get("batch_id") != entry.get("batch_id")):
            raise Hold("ACK_BATCH_SHA_MISMATCH")
    return len(queue["entries"]) - acknowledged


def decide(queue, ack, runs, now):
    behind = pending_exact(queue, ack)
    if not behind:
        return {"action": "CURRENT_ACK", "dispatch": False, "pending": 0}
    if (not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list) or
        not isinstance(now, datetime) or now.tzinfo is None):
        raise Hold("RUN_COLLECTION_UNVERIFIED")
    accepted = []
    for run in runs["workflow_runs"]:
        if not isinstance(run, dict):
            raise Hold("RUN_ENTRY_INVALID")
        if (run.get("path") != WORKFLOW or run.get("head_branch") != "main" or
            run.get("event") not in ALLOWED_EVENTS):
            continue
        origin = run.get("head_repository")
        if isinstance(origin, dict) and origin.get("full_name") != REPOSITORY:
            continue
        if (type(run.get("id")) is not int or run["id"] < 1 or
            run.get("status") not in ALLOWED_STATUSES):
            raise Hold("RUN_ENTRY_UNVERIFIED")
        age = (now - utc(run.get("created_at"))).total_seconds()
        if age < -60:
            raise Hold("FUTURE_RUN_CLOCK")
        accepted.append((age, run))
    if not accepted:
        raise Hold("NO_TRUSTED_RECEIVER_RUN_HISTORY")
    if any(run["status"] != "completed" for _, run in accepted):
        return {"action": "HOLD_ACTIVE_RECEIVER", "dispatch": False, "pending": behind}
    if min(age for age, _ in accepted) < MIN_LAST_ATTEMPT_SECONDS:
        return {"action": "HOLD_RECENT_RECEIVER_ATTEMPT", "dispatch": False, "pending": behind}
    successes = [age for age, run in accepted if run.get("conclusion") == "success"]
    if successes and min(successes) < MIN_SUCCESS_SECONDS:
        return {"action": "HOLD_RECENT_RECEIVER_SUCCESS", "dispatch": False, "pending": behind}
    return {"action": "RECOVER_MISSED_RECEIVER", "dispatch": True, "pending": behind}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sender-queue", type=Path, required=True)
    ap.add_argument("--ack", type=Path, required=True)
    ap.add_argument("--runs", type=Path, required=True)
    args = ap.parse_args()
    try:
        queue = json.loads(args.sender_queue.read_bytes())
        ack = json.loads(args.ack.read_bytes())
        runs = json.loads(args.runs.read_bytes())
        result = decide(queue, ack, runs, datetime.now(timezone.utc))
    except (OSError, ValueError, Hold) as e:
        print("JANUS_RECEIVER_RECOVERY=HOLD_UNTRUSTED_SOURCE:" + type(e).__name__)
        return 2
    print(json.dumps({"schema": "janus.genesis.receiver_recovery_decision.v1",
                      **result, "authority_delta": 0}, sort_keys=True))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("dispatch=" + ("true" if result["dispatch"] else "false") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
