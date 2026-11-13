#!/usr/bin/env python3
"""ESSENCE v0.7: preregistered, fail-closed paired prospective trial scorer.

ONLY calculates research metrics. Does NOT authenticate source records, create
independent verification, promote a microcore or produce production authority.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

PROTO = "janus.essence.preregistered_dual_lane/0.7"
PACKET = "janus.essence.paired_trial_packet/0.7"
REPORT = "janus.essence.paired_trial_report/0.7"
MAX_BYTES = 2_000_000
MAX_ROWS = 2000

def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()

def sha(x):
    return hashlib.sha256(canonical(x)).hexdigest()

def load(path):
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ValueError("OVERSIZE_INPUT")
    return json.loads(p.read_text(encoding="utf-8"),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))

def timestamp(x):
    if not isinstance(x, str):
        raise ValueError("MISSING_TIMESTAMP")
    try:
        t = dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIMESTAMP") from None
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t.astimezone(dt.timezone.utc)

def preregistered(protocol):
    if not isinstance(protocol, dict) or protocol.get("schema") != PROTO:
        raise ValueError("BAD_PREREGISTRATION")
    thresholds = protocol["thresholds"]
    if (thresholds != {
        "min_cases_each_cohort": 60,
        "min_absolute_accuracy_gain": 0.05,
        "max_one_sided_mcnemar_p_each_cohort": 0.005,
        "allow_healthy_false_rejection": False,
    }):
        raise ValueError("PREREGISTERED_THRESHOLDS_CHANGED")
    if (protocol.get("research_only") is not True
        or protocol.get("automatic_promotion") is not False
        or protocol.get("governance", {}).get("no_production_authority") is not True
        or protocol.get("governance", {}).get("independent_verifier_not_yet_onboarded") is not True):
        raise ValueError("DANGEROUS_AUTHORITY")
    freeze = timestamp(protocol["precommit_not_before"])
    cohorts = protocol.get("cohorts")
    if not isinstance(cohorts, list) or len(cohorts) != 2:
        raise ValueError("REQUIRE_TWO_FUTURE_COHORTS")
    before = freeze
    for c in cohorts:
        if (not isinstance(c, dict) or set(c) != {"id", "start", "end"}
            or timestamp(c["start"]) < before
            or timestamp(c["start"]) >= timestamp(c["end"])):
            raise ValueError("OVERLAP_OR_EARLY_COHORT")
        before = timestamp(c["end"])
    arms = protocol.get("arms")
    if not isinstance(arms, list) or len(arms) != 2 or len({a["id"] for a in arms}) != 2:
        raise ValueError("BAD_DUAL_LANE")
    for arm in arms:
        if (not isinstance(arm, dict)
            or arm["origin_repo"] not in (
                "Hawkar-usls/janus-distributed-ai-swarm",
                "Hawkar-usls/Demi_Head")
            or not isinstance(arm["origin_receipt_sha256"], str)
            or len(arm["origin_receipt_sha256"]) != 64):
            raise ValueError("INVALID_GENE_ORIGIN")
    return True

def exact_binomial_one_sided(candidate_only, baseline_only):
    """McNemar one-sided exact test of candidate winning paired disagreements."""
    n = candidate_only + baseline_only
    if not n or candidate_only <= baseline_only:
        return 1.0
    return sum(math.comb(n, i) for i in range(candidate_only, n + 1)) / (2 ** n)

def score(protocol, packet):
    preregistered(protocol)
    if not isinstance(packet, dict) or packet.get("schema") != PACKET:
        raise ValueError("BAD_PACKET")
    if packet.get("protocol_sha256") != sha(protocol):
        raise ValueError("PREREGISTRATION_HASH_MISMATCH")
    candidate = next((x for x in protocol["arms"] if x["id"] == packet.get("candidate_id")), None)
    if candidate is None:
        raise ValueError("UNREGISTERED_CANDIDATE")
    if packet.get("origin_repo") != candidate["origin_repo"]:
        raise ValueError("SOURCE_ORIGIN_MISMATCH")
    # Name in a JSON document is not an identity credential, especially under
    # a common GitHub owner. Only a separate human/custodian can attest source.
    verifier = packet.get("claimed_verifier_repo")
    if not isinstance(verifier, str) or not verifier.startswith("Hawkar-usls/") or verifier == candidate["origin_repo"]:
        raise ValueError("SELF_VERIFICATION_OR_INVALID_IDENTITY")
    if packet.get("claimed_production_authority") is not False:
        raise ValueError("UNSAFE_AUTHORITY_CLAIM")
    rows = packet.get("rows")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("UNBOUNDED_ROWS")
    if packet.get("rows_sha256") != sha(rows):
        raise ValueError("TAMPERED_ROWS")
    cohorts = {c["id"]: {"correct_baseline": 0, "correct_candidate": 0,
                          "wins_candidate": 0, "wins_baseline": 0,
                          "candidate_false_reject_healthy": 0, "n": 0}
               for c in protocol["cohorts"]}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "task_id", "origin_sha256", "event_at", "observed_at",
            "actual_bad", "baseline_says_bad", "candidate_says_bad"}:
            raise ValueError("BAD_OBSERVATION_SHAPE")
        task = row["task_id"]
        if not isinstance(task, str) or not (1 <= len(task) <= 128) or task in seen:
            raise ValueError("REPLAYED_OR_INVALID_TASK_ID")
        seen.add(task)
        if not isinstance(row["origin_sha256"], str) or len(row["origin_sha256"]) != 64:
            raise ValueError("MISSING_SOURCE_FINGERPRINT")
        t, observed = timestamp(row["event_at"]), timestamp(row["observed_at"])
        if observed < t:
            raise ValueError("FUTURE_LEAKAGE_OR_EARLY_OBSERVATION")
        cohort = next((c for c in protocol["cohorts"]
                       if timestamp(c["start"]) <= t < timestamp(c["end"])), None)
        if cohort is None:
            raise ValueError("OUTSIDE_PREREGISTERED_FUTURE_WINDOW")
        if any(type(row[k]) is not bool for k in
               ("actual_bad", "baseline_says_bad", "candidate_says_bad")):
            raise ValueError("NON_BOOLEAN_LABEL")
        z = cohorts[cohort["id"]]
        truth = row["actual_bad"]
        base = row["baseline_says_bad"] == truth
        proposed = row["candidate_says_bad"] == truth
        z["n"] += 1
        z["correct_baseline"] += int(base)
        z["correct_candidate"] += int(proposed)
        z["wins_candidate"] += int(proposed and not base)
        z["wins_baseline"] += int(base and not proposed)
        z["candidate_false_reject_healthy"] += int(not truth and row["candidate_says_bad"])
    results = {}
    meets = True
    for cohort_id, z in cohorts.items():
        n = z["n"]
        delta = ((z["correct_candidate"] - z["correct_baseline"]) / n) if n else 0.
        p = exact_binomial_one_sided(z["wins_candidate"], z["wins_baseline"])
        ok = (n >= 60 and delta >= 0.05 and p <= 0.005
              and z["candidate_false_reject_healthy"] == 0)
        results[cohort_id] = {
            **z, "absolute_accuracy_gain": round(delta, 6),
            "mcnemar_one_sided_p": round(p, 10),
            "internal_scientific_gate": "METRIC_PASS_UNAUTHENTICATED" if ok else "HOLD",
        }
        meets = meets and ok
    has_both = all(z["n"] >= 60 for z in cohorts.values())
    outcome = ("PENDING_FUTURE_HOLDOUT" if not has_both else
               "HOLD_NO_REPLICATED_GAIN" if not meets else
               "RESEARCH_METRIC_PASS_REQUIRES_EXTERNAL_AUTHENTICATION")
    result = {
        "schema": REPORT, "candidate_id": candidate["id"],
        "source_kind": candidate["source_kind"],
        "protocol_sha256": sha(protocol), "rows_sha256": sha(rows),
        "claimed_verifier_repo": verifier, "source_claims_not_authenticated": True,
        "cohorts": results, "research_gate": outcome,
        "independent_external_replication": False,
        "production_authority": False, "offspring_activated": False,
    }
    result["report_sha256"] = sha(result)
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", required=True)
    p.add_argument("--packet", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = score(load(a.protocol), load(a.packet))
    output = Path(a.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("NO_OVERWRITE")
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate": result["research_gate"], "production_authority": False}))
if __name__ == "__main__":
    main()
