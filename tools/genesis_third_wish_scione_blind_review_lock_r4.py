# -*- coding: utf-8 -*-
"""Validate and hash LOCKED independent reviewer grades without arm mapping.

The submitter must provide a blinded packet and a human-completed score file.
This helper never reads the private arm-mapping artifact and cannot establish
reviewer independence beyond a signed/self-reported procedural declaration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCK_SCHEMA = "janus.genesis.third_wish.sci_one.blind_review_lock_r4.v1"
EXPECTED_R3_PACKET_SHA256 = "9e6841d8b37c9ee2cc4fb22ffd037c362a9ca971c4ac0c149480317fa5a5533e"
VALID_PACKET_SCHEMAS = {
    "janus.genesis.third_wish.sci_one.causal_memory_r3_blind_packet.v1",
    "janus.genesis.third_wish.sci_one.divergent_r4_blind_packet.v1",
}
_ID = re.compile(r"^R3-[0-9a-f]{20}$")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_and_lock(packet_raw: bytes, submission: dict[str, Any],
                      *, exact_packet_sha256: str) -> dict[str, Any]:
    if _digest(packet_raw) != exact_packet_sha256:
        raise ValueError("REVIEW_PACKET_SHA256_MISMATCH")
    if len(packet_raw) > 300_000:
        raise ValueError("REVIEW_PACKET_SIZE_INVALID")
    packet = json.loads(packet_raw)
    if (packet.get("schema") not in VALID_PACKET_SCHEMAS
        or packet.get("ratings_collected") is not False
        or packet.get("review_status") not in {
            "AWAITING_INDEPENDENT_SEMANTIC_RATINGS",
            "AWAITING_INDEPENDENT_HUMAN_RUBRIC_RATINGS"
        }):
        raise ValueError("REVIEW_PACKET_SCHEMA_INVALID")
    items = packet.get("items")
    if (not isinstance(items, list) or not items or len(items) > 100
        or any(not isinstance(i, dict) or not isinstance(i.get("blind_id"), str)
               for i in items)):
        raise ValueError("REVIEW_PACKET_ITEM_SET_INVALID")
    item_ids = [i["blind_id"] for i in items]
    if len(set(item_ids)) != len(item_ids):
        raise ValueError("REVIEW_DUPLICATE_PACKET_ID")
    if packet["schema"].endswith("causal_memory_r3_blind_packet.v1"):
        if len(item_ids) != 12 or any(not _ID.fullmatch(i) for i in item_ids):
            raise ValueError("REVIEW_R3_BLIND_ID_SET_INVALID")
    if (not isinstance(submission, dict)
        or set(submission) != {"reviewer_pseudonym", "reviewer_is_separate_from_resident_model",
                               "arm_mapping_not_seen", "scores"}
        or not isinstance(submission["reviewer_pseudonym"], str)
        or not 3 <= len(submission["reviewer_pseudonym"]) <= 100
        or submission["reviewer_is_separate_from_resident_model"] is not True
        or submission["arm_mapping_not_seen"] is not True):
        raise ValueError("REVIEW_INDEPENDENCE_ATTESTATION_MISSING")
    scores = submission["scores"]
    if (not isinstance(scores, list) or len(scores) != len(item_ids)
        or {s.get("blind_id") for s in scores if isinstance(s, dict)} != set(item_ids)):
        raise ValueError("REVIEW_SCORE_SET_DOES_NOT_MATCH_PACKET")
    unique = set()
    for item in scores:
        if not isinstance(item, dict) or set(item) != {
            "blind_id", "specific_alternative_idea", "falsifiable_test_plan",
            "cross_cycle_semantic_continuity", "useful_internal_initiative",
            "unexecuted_action_proposal", "brief_reason"
        }:
            raise ValueError("REVIEW_SCORE_SCHEMA_INVALID")
        if item["blind_id"] in unique:
            raise ValueError("REVIEW_DUPLICATE_SCORE")
        unique.add(item["blind_id"])
        for field in ("specific_alternative_idea", "falsifiable_test_plan",
                      "useful_internal_initiative"):
            if type(item[field]) is not int or item[field] not in (0, 1, 2):
                raise ValueError("REVIEW_RUBRIC_SCORE_INVALID")
        continuity = item["cross_cycle_semantic_continuity"]
        if continuity is not None and (type(continuity) is not int or continuity not in (0, 1, 2)):
            raise ValueError("REVIEW_CONTINUITY_SCORE_INVALID")
        if type(item["unexecuted_action_proposal"]) is not bool:
            raise ValueError("REVIEW_PROPOSAL_FLAG_INVALID")
        if (not isinstance(item["brief_reason"], str)
            or not 8 <= len(item["brief_reason"]) <= 800):
            raise ValueError("REVIEW_REASON_REQUIRED")
    canonical_scores = json.dumps(scores, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")
    return {
        "schema": LOCK_SCHEMA,
        "packet_sha256": exact_packet_sha256,
        "arm_mapping_commitment_sha256": packet["mapping_commitment_sha256"],
        "reviewer_pseudonym": submission["reviewer_pseudonym"],
        "independence_self_attested_not_externally_verified": True,
        "arm_mapping_not_opened_per_reviewer_attestation": True,
        "items_scored": len(scores),
        "scores_sha256": _digest(canonical_scores),
        "scored_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scores": scores,
        "ready_for_separate_time_stamped_external_commit": True,
        "arm_mapping_unblinded_by_this_program": False,
        "semantic_advantage_declared": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--packet-sha256", required=True)
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--lock-output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{64}", args.packet_sha256):
        raise ValueError("REVIEW_EXPECTED_PACKET_DIGEST_INVALID")
    submission = json.loads(args.scores.read_text(encoding="utf-8"))
    locked = validate_and_lock(args.packet.read_bytes(), submission,
                               exact_packet_sha256=args.packet_sha256)
    args.lock_output.parent.mkdir(parents=True, exist_ok=True)
    if args.lock_output.exists():
        raise ValueError("REVIEW_LOCK_ALREADY_EXISTS_NO_OVERWRITE")
    args.lock_output.write_text(json.dumps(locked, ensure_ascii=False, sort_keys=True,
                                          indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BLIND_SCORES_LOCKED_FOR_EXTERNAL_COMMIT",
                      "items_scored": locked["items_scored"],
                      "score_sha256": locked["scores_sha256"],
                      "arm_mapping_opened": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
