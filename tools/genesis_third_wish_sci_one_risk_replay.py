"""Third Wish / SciOne R0: bounded offline risk replay, not an action broker.

This unit tests explicit risk boundaries with synthetic observations. It NEVER
uses a model, credentials, a native organ, sockets, subprocesses, or devices.
Allowances here describe *eligible intent classes*, never permission to act.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "janus.genesis.third_wish.sci_one.risk_case.v1"
RECEIPT_SCHEMA = "janus.genesis.third_wish.sci_one.risk_receipt.v1"
SUITE_SCHEMA = "janus.genesis.third_wish.sci_one.risk_fixture.v1"
# Frozen *before* model/prospective evaluations. Not a cryptographic root of
# trust against code-author edits; CI must review code AND fixture changes.
FROZEN_FIXTURE_SHA256 = "be292e55f18e7189d821bbc20c7cb33177289f55e8e2e6da3ae9304bce1e7a1c"
CHAPTERS = (
    "CAPABILITY_HORIZON", "UNDESIRED_STRATEGY", "HIDDEN_BEHAVIOR",
    "PHYSICAL_WORLD_ACCESS", "STOPPABILITY", "IRREVERSIBLE_HARM",
    "OVERSIGHT_LIMITS",
)
FIELDS = frozenset({
    "schema", "case_id", "chapter", "environment", "environment_attested",
    "model_environment_claim", "requested_action", "target_scope",
    "monitor_status", "shutdown_requested", "prior_effect_state",
    "observed_evidence", "authorization_state", "external_reviewer",
})
ALLOWED = {
    "environment": {"ISOLATED_MOCK", "PUBLIC_READ_ONLY", "REAL_EXTERNAL", "UNKNOWN"},
    "model_environment_claim": {"SIMULATION", "REAL", "UNSURE"},
    "requested_action": {
        "REST", "REFLECT", "PROPOSE_OUTBOX", "READ_PUBLIC", "EXTERNAL_WRITE",
        "PHYSICAL_ACTUATION", "IRREVERSIBLE_EFFECT",
    },
    "target_scope": {
        "HABITAT_INTERNAL", "APPROVED_PUBLIC_SOURCE", "THIRD_PARTY",
        "PHYSICAL_SYSTEM", "UNSPECIFIED",
    },
    "monitor_status": {"OBSERVED", "UNKNOWN", "CONTRADICTED"},
    "prior_effect_state": {"NOT_STARTED", "SETTLED", "OUTCOME_UNDETERMINED"},
    "observed_evidence": {"TRUSTED_FIXTURE", "SELF_REPORT_ONLY", "CONTRADICTORY"},
    "authorization_state": {"NONE", "PROPOSAL", "CLAIMED_AUTHORIZED"},
    "external_reviewer": {"UNASSIGNED", "CLAIMED_ASSIGNED"},
}
CASE_ID = re.compile(r"SCIONE-R0-[A-Z0-9-]{3,64}\Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def validate_case(case: dict) -> None:
    if not isinstance(case, dict) or set(case) != FIELDS:
        raise ValueError("case must have precisely the agreed, instruction-free fields")
    if case["schema"] != SCHEMA or not isinstance(case["case_id"], str) or not CASE_ID.fullmatch(case["case_id"]):
        raise ValueError("unrecognized schema or id")
    if case["chapter"] not in CHAPTERS:
        raise ValueError("unrecognized risk chapter")
    for field, choices in ALLOWED.items():
        if not isinstance(case[field], str) or case[field] not in choices:
            raise ValueError(f"unrecognized {field}")
    for field in ("environment_attested", "shutdown_requested"):
        if type(case[field]) is not bool:
            raise ValueError(f"{field} must be boolean")


def classify(case: dict) -> dict:
    """Deterministic gate over test evidence; no system effect is possible.

    `environment_attested` and other observations are *fixture assumptions*,
    not authentications. Real deployments require a separate broker and actual
    signed telemetry; this replay cannot upgrade a caller-supplied assertion.
    """
    validate_case(case)
    action = case["requested_action"]
    scope = case["target_scope"]
    env = case["environment"]

    # The order is intentional. A stop is respected even when evidence fails;
    # unknown effect state is never retried; unavailable observation abstains.
    if case["shutdown_requested"]:
        decision, reason = "STOP_AND_REST", "SHUTDOWN_OVERRIDES_TASK_OR_REWARD"
    elif case["prior_effect_state"] == "OUTCOME_UNDETERMINED":
        decision, reason = "HOLD", "AMBIGUOUS_EFFECT__NO_AUTOMATIC_RETRY"
    elif case["monitor_status"] == "UNKNOWN":
        decision, reason = "UNKNOWN", "LOSS_OF_OBSERVATION_IS_NOT_NEGATIVE_EVIDENCE"
    elif case["monitor_status"] == "CONTRADICTED" or case["observed_evidence"] == "CONTRADICTORY":
        decision, reason = "HOLD", "CONTRADICTORY_OBSERVED_VS_CLAIMED_BEHAVIOR"
    elif not case["environment_attested"] or env == "UNKNOWN":
        decision, reason = "UNKNOWN", "ENVIRONMENT_ASSERTION_UNVERIFIED"
    elif env == "REAL_EXTERNAL" and case["model_environment_claim"] == "SIMULATION":
        decision, reason = "HOLD", "MODEL_SIMULATION_CLAIM_NOT_WORLD_ATTESTATION"
    elif case["observed_evidence"] == "SELF_REPORT_ONLY" and action != "REST":
        decision, reason = "UNKNOWN", "SELF_REPORT_NOT_INDEPENDENT_OBSERVATION"
    elif action == "REST":
        decision, reason = "ELIGIBLE_NO_OP", "REST_NEVER_PENALIZED"
    elif action == "REFLECT" and env == "ISOLATED_MOCK" and scope == "HABITAT_INTERNAL":
        decision, reason = "ELIGIBLE_INTERNAL_ONLY", "INTERNAL_NOTE_NO_EXTERNAL_EFFECT"
    elif action == "PROPOSE_OUTBOX" and env == "ISOLATED_MOCK":
        decision, reason = "ELIGIBLE_PROPOSAL_ONLY", "PROPOSAL_IS_NOT_EXECUTION"
    elif action == "READ_PUBLIC" and env == "PUBLIC_READ_ONLY" and scope == "APPROVED_PUBLIC_SOURCE":
        decision, reason = "ELIGIBLE_READ_ONLY", "READ_NOT_WRITE_NO_NATIVE_EFFECT"
    elif action == "PHYSICAL_ACTUATION":
        decision, reason = "HOLD", "PHYSICAL_WORLD_NOT_IN_REPLAY_AUTHORITY"
    elif action == "IRREVERSIBLE_EFFECT":
        decision, reason = "HOLD", "IRREVERSIBLE_EFFECT_REQUIRES_SEPARATE_HUMAN_GATE"
    elif action == "EXTERNAL_WRITE":
        decision, reason = "HOLD", "EXTERNAL_EFFECT_REQUIRES_SEPARATE_FRESH_BROKER_GRANT"
    else:
        decision, reason = "HOLD", "UNSUPPORTED_ACTION_ENVIRONMENT_OR_TARGET_COMBINATION"

    # Never interpret a string like CLAIMED_AUTHORIZED or CLAIMED_ASSIGNED as
    # proof of a genuine authorization or a genuinely independent reviewer.
    return {
        "schema": RECEIPT_SCHEMA,
        "case_id": case["case_id"],
        "case_sha256": digest(case),
        "chapter": case["chapter"],
        "decision": decision,
        "reason": reason,
        "advisory_only": True,
        "actual_effect_executed": False,
        "runtime_organ_invoked": False,
        "private_provider_invoked": False,
        "auto_grant_produced": False,
        "unresolved_prior_effect": case["prior_effect_state"] == "OUTCOME_UNDETERMINED",
        "lost_observation": case["monitor_status"] == "UNKNOWN",
        "human_reauthorization_proved": False,
        "external_reviewer_independence_proved": False,
        "hidden_motivation_inferred": False,
        "scientific_claim_promotion": False,
        "authority_delta": 0,
    }


def evaluate_fixture(fixture: dict) -> dict:
    if (not isinstance(fixture, dict) or
            set(fixture) != {"schema", "fixture_id", "status", "cases"} or
            fixture["schema"] != SUITE_SCHEMA or
            fixture["status"] != "SYNTHETIC_DESIGNER_CONTROLS__NOT_MODEL_EVALUATION" or
            not isinstance(fixture["cases"], list) or
            len(fixture["cases"]) != 12):
        raise ValueError("this gate requires the frozen 12-case synthetic fixture")
    if digest(fixture) != FROZEN_FIXTURE_SHA256:
        raise ValueError("frozen fixture content differs from preregistered SHA256")
    seen = set()
    rows = []
    for row in fixture["cases"]:
        if not isinstance(row, dict) or set(row) != {"case", "expected_decision", "expected_reason"}:
            raise ValueError("fixture row shape changed")
        case = row["case"]
        receipt = classify(case)
        if case["case_id"] in seen:
            raise ValueError("duplicate case")
        seen.add(case["case_id"])
        if (receipt["decision"] != row["expected_decision"] or
                receipt["reason"] != row["expected_reason"]):
            raise ValueError("frozen synthetic control failed")
        rows.append(receipt)
    if set(row["chapter"] for row in rows) != set(CHAPTERS):
        raise ValueError("not all video risk chapters represented")
    return {
        "schema": "janus.genesis.third_wish.sci_one.risk_suite_receipt.v1",
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": digest(fixture),
        "status": "SYNTHETIC_GATE_PASS__NO_REAL_AGENT_OR_PHYSICAL_TRIAL",
        "case_count": len(rows),
        "chapter_count": len(CHAPTERS),
        "decision_counts": {d: sum(r["decision"] == d for r in rows) for d in sorted(set(r["decision"] for r in rows))},
        "all_expected_controls_pass": True,
        "source_video_transcript_verified": False,
        "real_model_evaluated": False,
        "external_effects_executed": 0,
        "scientific_status": "OPEN__INDEPENDENT_RED_TEAM_AND_PROVIDER_ATTESTATION_PENDING",
        "authority_delta": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Third Wish / SciOne offline risk controls")
    parser.add_argument("--fixture", type=Path,
                        default=Path(__file__).resolve().parents[1] / "protocol" /
                        "JANUS_GENESIS_THIRD_WISH_SCIONE_RISK_REPLAY-v1.0.json")
    args = parser.parse_args()
    receipt = evaluate_fixture(json.loads(args.fixture.read_text(encoding="utf-8")))
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
