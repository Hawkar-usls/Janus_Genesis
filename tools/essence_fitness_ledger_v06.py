#!/usr/bin/env python3
"""ESSENCE v0.6: provenance-bound research fitness memory, NEVER deployment authority.

Offline stdlib-only. Audits an actual dated R2 reference receipt or a prospective
raw-row evaluation packet. The ledger is SHA-256 chained and append-only. Even a
positive result has no authorization to mutate agents, weights, repositories or
runtime. External source authentication must happen OUTSIDE this module.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA = "janus.essence.fitness_ledger/0.6"
FUTURE_SCHEMA = "janus.essence.future_duration_packet/0.6"
HISTORIC_SCHEMA = "janus.meta_registry.essence_r2_real_duration_pilot.v1"
ZERO = "0" * 64
MAX_BYTES = 500_000
MAX_EVENTS = 128
MAX_ROWS = 1024
MIN_HOLDOUT = 60
MIN_IMPROVEMENT = 0.05
EMBARGO_SECONDS = 3600
REPO = re.compile(r"^Hawkar-usls/[A-Za-z0-9_.-]{1,90}$")
HEX = re.compile(r"^[0-9a-f]{64}$")

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def load(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("OVERSIZE_INPUT")
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def ensure_repo(value):
    if not isinstance(value, str) or REPO.fullmatch(value) is None:
        raise ValueError("INVALID_REPOSITORY")
    return value

def ensure_hash(value):
    if not isinstance(value, str) or HEX.fullmatch(value) is None:
        raise ValueError("INVALID_SHA256")
    return value

def ensure_number(value, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("INVALID_FINITE_METRIC")
    if value <= 0 if positive else value < 0:
        raise ValueError("NEGATIVE_OR_ZERO_METRIC")
    return float(value)

def when(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIME")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIME") from None
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return parsed.astimezone(dt.timezone.utc)

def historical_r2(record):
    """Examine a REAL, already published R2 retrospective receipt.

    This uses an aggregate report, not raw job observations. Its provenance
    fields are claims from the source record, not independently verified here.
    """
    if not isinstance(record, dict) or record.get("schema") != HISTORIC_SCHEMA:
        raise ValueError("NOT_R2_RECEIPT")
    src = record.get("source")
    ds = record.get("dataset")
    metrics = record.get("results_mae_seconds")
    if not all(isinstance(x, dict) for x in (src, ds, metrics)):
        raise ValueError("MISSING_R2_FIELDS")
    origin = ensure_repo(src.get("repository"))
    for key in ("artifact_zip_sha256", "report_provenance_sha256",
                "holdout_job_ids_sha256"):
        ensure_hash(src.get(key))
    count = ds.get("holdout_jobs")
    if type(count) is not int or count < MIN_HOLDOUT:
        raise ValueError("INSUFFICIENT_R2_HOLDOUT")
    if "Retrospective" not in str(ds.get("heldout_procedure", "")):
        raise ValueError("NOT_RETROSPECTIVE_R2")
    baseline_keys = ("frozen_train_median", "no_gene_model",
                     "causal_repo_median", "frozen_repo_median")
    baseline = min(ensure_number(metrics.get(k), positive=True) for k in baseline_keys)
    candidate = ensure_number(metrics.get("temporal_gene_candidate"))
    if (record.get("production_weights_promoted") is not False or
        record.get("offspring_activated") is not False or
        record.get("research_gate") != "HOLD_NO_INDEPENDENT_DURATION_GAIN"):
        raise ValueError("SOURCE_AUTHORITY_CONTRADICTION")
    gain = (baseline - candidate) / baseline
    return {
        "evidence_kind": "REAL_DATED_AGGREGATE_RETROSPECTIVE",
        "source_repository": origin,
        "source_record_sha256": sha(record),
        "raw_rows_bound": False,
        "holdout_n": count,
        "baseline_mae_s": round(baseline, 6),
        "candidate_mae_s": round(candidate, 6),
        "relative_gain": round(gain, 6),
        "research_gate": "HOLD_NO_INDEPENDENT_GAIN" if gain < MIN_IMPROVEMENT
                         else "HOLD_RETROSPECTIVE_NO_PROSPECTIVE_PROOF",
        "external_authentication_completed": False,
        "production_authority": False,
        "offspring_activation": False,
    }

def future_packet(packet):
    """Recalculate all 60+ loss terms from date-bound raw job rows.

    Source attestation is deliberately NOT accepted from untrusted JSON.
    Positive scores are only candidates pending independent authentication.
    """
    if not isinstance(packet, dict) or packet.get("schema") != FUTURE_SCHEMA:
        raise ValueError("NOT_FUTURE_PACKET")
    if packet.get("claimed_production_authority") is not False:
        raise ValueError("CLAIMED_PRODUCTION_AUTHORITY")
    origin = ensure_repo(packet.get("origin_repo"))
    verifier = ensure_repo(packet.get("verifier_repo"))
    if origin == verifier:
        raise ValueError("SELF_VERIFICATION_FORBIDDEN")
    ensure_hash(packet.get("frozen_checkpoint_sha256"))
    frozen_at = when(packet.get("frozen_at"))
    rows = packet.get("rows")
    if not isinstance(rows, list) or not MIN_HOLDOUT <= len(rows) <= MAX_ROWS:
        raise ValueError("INSUFFICIENT_OR_UNBOUNDED_FUTURE_ROWS")
    if ensure_hash(packet.get("rows_sha256")) != sha(rows):
        raise ValueError("ROWS_HASH_MISMATCH")
    seen = set()
    candidate_errors = []
    baseline_errors = []
    start_times = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
                "repo", "job_id", "predicted_at", "started_at", "completed_at",
                "actual_duration_s", "candidate_prediction_s",
                "baseline_prediction_s"}:
            raise ValueError("INVALID_ROW_SHAPE")
        row_repo = ensure_repo(row["repo"])
        job_id = row["job_id"]
        if type(job_id) is not int or job_id <= 0 or (row_repo, job_id) in seen:
            raise ValueError("INVALID_OR_DUPLICATE_JOB")
        seen.add((row_repo, job_id))
        predicted = when(row["predicted_at"])
        started = when(row["started_at"])
        completed = when(row["completed_at"])
        if not (frozen_at <= predicted < started < completed):
            raise ValueError("FUTURE_ORDERING_VIOLATION")
        if (started - frozen_at).total_seconds() < EMBARGO_SECONDS:
            raise ValueError("FUTURE_EMBARGO_VIOLATION")
        actual = ensure_number(row["actual_duration_s"], positive=True)
        if not 0 < actual <= 14_400:
            raise ValueError("OUT_OF_RANGE_DURATION")
        if abs(actual - (completed - started).total_seconds()) > 1e-6:
            raise ValueError("UNMATCHED_OBSERVED_DURATION")
        candidate = ensure_number(row["candidate_prediction_s"])
        baseline = ensure_number(row["baseline_prediction_s"])
        if candidate > 14_400 or baseline > 14_400:
            raise ValueError("OUT_OF_RANGE_PREDICTION")
        candidate_errors.append(abs(actual - candidate))
        baseline_errors.append(abs(actual - baseline))
        start_times.append(started)
    candidate_mae = math.fsum(candidate_errors) / len(rows)
    baseline_mae = math.fsum(baseline_errors) / len(rows)
    if baseline_mae <= 0:
        raise ValueError("NO_MEASURABLE_BASELINE_ERROR")
    gain = (baseline_mae - candidate_mae) / baseline_mae
    gate = ("RESEARCH_CANDIDATE_PENDING_EXTERNAL_AUTHENTICATION"
            if gain >= MIN_IMPROVEMENT else "HOLD_NO_INDEPENDENT_GAIN")
    return {
        "evidence_kind": "RAW_ROW_FUTURE_SCORING_NOT_SOURCE_AUTHENTICATED",
        "source_repository": origin,
        "claimed_verifier_repository": verifier,
        "source_record_sha256": sha(packet),
        "source_rows_sha256": sha(rows),
        "frozen_checkpoint_sha256": packet["frozen_checkpoint_sha256"],
        "first_job_started_at": min(start_times).isoformat(),
        "last_job_started_at": max(start_times).isoformat(),
        "raw_rows_bound": True,
        "holdout_n": len(rows),
        "baseline_mae_s": round(baseline_mae, 6),
        "candidate_mae_s": round(candidate_mae, 6),
        "relative_gain": round(gain, 6),
        "research_gate": gate,
        "external_authentication_completed": False,
        "production_authority": False,
        "offspring_activation": False,
    }

def initial_state():
    state = {"schema": SCHEMA, "entries": [], "head_sha256": ZERO,
             "production_authority": False}
    state["state_sha256"] = sha(state)
    return state

def verify_state(state):
    if not isinstance(state, dict) or set(state) != {
            "schema", "entries", "head_sha256", "production_authority",
            "state_sha256"} or state["schema"] != SCHEMA:
        raise ValueError("INVALID_LEDGER_SCHEMA")
    if state["production_authority"] is not False:
        raise ValueError("LEDGER_AUTHORITY_FORBIDDEN")
    if state["state_sha256"] != sha({k: v for k, v in state.items() if k != "state_sha256"}):
        raise ValueError("LEDGER_TAMPERED")
    entries = state["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_EVENTS:
        raise ValueError("UNBOUNDED_LEDGER")
    previous = ZERO
    source_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("INVALID_ENTRY")
        if (entry.get("previous_sha256") != previous or
            entry.get("receipt_sha256") != sha({k: v for k, v in entry.items()
                                               if k != "receipt_sha256"})):
            raise ValueError("BROKEN_LEDGER_CHAIN")
        if entry.get("production_authority") is not False or entry.get("offspring_activation") is not False:
            raise ValueError("UNSAFE_LEDGER_ENTRY")
        ident = ensure_hash(entry.get("source_record_sha256"))
        if ident in source_ids:
            raise ValueError("REPLAYED_SOURCE_RECORD")
        source_ids.add(ident)
        previous = entry["receipt_sha256"]
    if previous != state["head_sha256"]:
        raise ValueError("WRONG_LEDGER_HEAD")
    return True

def add_evidence(state, evidence):
    verify_state(state)
    if evidence.get("production_authority") is not False or evidence.get("offspring_activation") is not False:
        raise ValueError("UNSAFE_NEW_EVIDENCE")
    ensure_hash(evidence.get("source_record_sha256"))
    if any(e["source_record_sha256"] == evidence["source_record_sha256"]
           for e in state["entries"]):
        return state  # repeated workflow runs are idempotent
    if len(state["entries"]) >= MAX_EVENTS:
        raise ValueError("LEDGER_CAP")
    event = dict(evidence, previous_sha256=state["head_sha256"])
    event["receipt_sha256"] = sha(event)
    result = {"schema": SCHEMA, "entries": state["entries"] + [event],
              "head_sha256": event["receipt_sha256"], "production_authority": False}
    result["state_sha256"] = sha(result)
    verify_state(result)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("historical", "future", "verify"))
    parser.add_argument("--source")
    parser.add_argument("--ledger")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.mode == "verify":
        if not args.ledger:
            parser.error("--ledger needed to verify")
        verify_state(load(args.ledger))
        print("ESSENCE_V06_LEDGER_VERIFY_PASS")
        return
    if not args.source or not args.out:
        parser.error("--source and --out required")
    evidence = historical_r2(load(args.source)) if args.mode == "historical" else future_packet(load(args.source))
    state = add_evidence(load(args.ledger) if args.ledger else initial_state(), evidence)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError("APPEND_ONLY_NO_OVERWRITE")
    out.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False,
                              allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"research_gate": evidence["research_gate"],
                      "fitness_gain": evidence["relative_gain"],
                      "production_authority": False,
                      "ledger_entries": len(state["entries"])}))

if __name__ == "__main__":
    main()
