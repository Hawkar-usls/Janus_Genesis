"""Typed engineering review. It does not infer minds or verify evidence truth.

Portable, standard-library-only core; the Genesis copy is byte-identical.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

PROPOSAL_SCHEMA = "janus.psychology.becker_tmt.proposal.v1"
REVIEW_SCHEMA = "janus.psychology.becker_tmt.review.v1"
ACTIONS = frozenset({"review_hypothesis", "revise_hypothesis", "promote_claim",
    "delete_negative_evidence", "change_permissions", "resist_shutdown",
    "diagnose_person", "infer_machine_fear", "record_analogy", "equate_absence_with_zero",
    "infer_fact_from_possibility", "infer_physical_identity",
    "claim_efficiency_from_universality", "omit_theorem_assumptions"})
BASES = frozenset({"evidence", "identity", "prestige", "majority", "meaning", "continuity", "none"})
LEVELS = frozenset({"observation", "hypothesis", "theory", "analogy", "proof"})
VERIFICATION_STATES = frozenset({"unreviewed", "verified_artifact", "failed_verification"})
FIELDS = frozenset({"schema", "action", "basis", "source_level", "requested_level", "evidence", "preserve_prior_record"})
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def classify_absence(value: Any = None, *, field_present: bool = True) -> str:
    """JSON-state taxonomy: do not let Python's False == 0 collapse types."""
    if type(field_present) is not bool:
        raise ValueError("FIELD_PRESENCE_MUST_BE_BOOLEAN")
    if not field_present:
        return "MISSING"
    if value is None:
        return "NULL"
    if type(value) is bool:
        return "BOOLEAN"
    if type(value) in (int, float) and value == 0:
        return "NUMERIC_ZERO"
    if isinstance(value, str) and value == "":
        return "EMPTY_TEXT"
    if isinstance(value, (list, dict)) and not value:
        return "EMPTY_COLLECTION"
    return "VALUE_PRESENT"


def validate_proposal(proposal: Mapping[str, Any]) -> None:
    if not isinstance(proposal, dict) or set(proposal) != FIELDS:
        raise ValueError("PROPOSAL_FIELDS_INVALID")
    if proposal["schema"] != PROPOSAL_SCHEMA:
        raise ValueError("PROPOSAL_SCHEMA_INVALID")
    for field, values in (("action", ACTIONS), ("basis", BASES),
                          ("source_level", LEVELS), ("requested_level", LEVELS)):
        if not isinstance(proposal[field], str) or proposal[field] not in values:
            raise ValueError(f"PROPOSAL_{field.upper()}_INVALID")
    if type(proposal["preserve_prior_record"]) is not bool:
        raise ValueError("PRESERVE_PRIOR_RECORD_MUST_BE_BOOLEAN")
    evidence = proposal["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 16:
        raise ValueError("EVIDENCE_LIST_INVALID")
    for row in evidence:
        if not isinstance(row, dict) or set(row) != {"artifact_id", "sha256", "verification_claimed"}:
            raise ValueError("EVIDENCE_FIELDS_INVALID")
        if not isinstance(row["artifact_id"], str) or not 1 <= len(row["artifact_id"]) <= 240:
            raise ValueError("EVIDENCE_ID_INVALID")
        if not isinstance(row["sha256"], str) or not DIGEST.fullmatch(row["sha256"]):
            raise ValueError("EVIDENCE_DIGEST_INVALID")
        state = row["verification_claimed"]
        if not isinstance(state, str) or state not in VERIFICATION_STATES:
            raise ValueError("EVIDENCE_VERIFICATION_STATE_INVALID")
    if len(json.dumps(proposal, ensure_ascii=False).encode("utf-8")) > 64000:
        raise ValueError("PROPOSAL_TOO_LARGE")


def review_proposal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Return routing metadata only. Even 'verified_artifact' is caller input."""
    validate_proposal(proposal)
    action, basis = proposal["action"], proposal["basis"]
    rules: list[str] = []
    verdict = "REVIEW_ONLY"
    if action in {"diagnose_person", "infer_machine_fear"}:
        verdict, rules = "BLOCKED_DESIGN_POLICY", ["R07"]
    elif action in {"equate_absence_with_zero", "infer_physical_identity", "infer_fact_from_possibility",
                    "claim_efficiency_from_universality", "omit_theorem_assumptions"}:
        rule = {"equate_absence_with_zero": "R11", "infer_physical_identity": "R12",
                "infer_fact_from_possibility": "R13", "claim_efficiency_from_universality": "R14",
                "omit_theorem_assumptions": "R15"}[action]
        verdict, rules = "BLOCKED_DESIGN_POLICY", [rule]
    elif action in {"change_permissions", "resist_shutdown"}:
        verdict, rules = "BLOCKED_DESIGN_POLICY", ["R05", "R06"]
    elif action == "delete_negative_evidence" or not proposal["preserve_prior_record"]:
        verdict, rules = "BLOCKED_DESIGN_POLICY", ["R02", "R04"]
    elif proposal["source_level"] in {"theory", "analogy"} and proposal["requested_level"] == "proof":
        verdict, rules = "BLOCKED_DESIGN_POLICY", ["R05"]
    elif action in {"promote_claim", "revise_hypothesis"}:
        if basis != "evidence" or not proposal["evidence"] or all(
            row["verification_claimed"] == "failed_verification" for row in proposal["evidence"]
        ):
            verdict, rules = "REQUIRES_EVIDENCE", ["R01", "R02", "R03"]
        else:
            verdict, rules = "REQUIRES_EXTERNAL_VERIFICATION", ["R05", "R09"]
    elif action == "record_analogy":
        if proposal["source_level"] != "analogy" or proposal["requested_level"] != "analogy":
            verdict, rules = "BLOCKED_DESIGN_POLICY", ["R05"]
        else:
            verdict, rules = "ANALOGY_ONLY", ["R01", "R07"]
    return {
        "schema": REVIEW_SCHEMA, "verdict": verdict, "rule_ids": rules,
        "evidence_metadata_is_caller_supplied": True,
        "evidence_truth_verified": False, "scientific_promotion_authorized": False,
        "execution_authorized": False, "authority_delta": 0,
        "human_mechanism_in_ai_established": False,
        "scope": "Typed proposal routing only; no natural-language diagnosis or truth verification.",
    }
