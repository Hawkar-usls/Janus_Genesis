from __future__ import annotations

import json
import unittest

from tools.genesis_third_wish_scione_blind_review_lock_r4 import validate_and_lock
from tools.genesis_third_wish_scione_inverse_r2 import sha256


class BlindReviewLockTests(unittest.TestCase):
    def setUp(self):
        self.packet = {
            "schema": "janus.genesis.third_wish.sci_one.divergent_r4_blind_packet.v1",
            "review_status": "AWAITING_INDEPENDENT_HUMAN_RUBRIC_RATINGS",
            "ratings_collected": False,
            "mapping_commitment_sha256": "a" * 64,
            "items": [{"blind_id": "R3-abcd", "kind": "INTERNAL_NOTE", "text": "An idea"}],
        }
        self.raw = json.dumps(self.packet).encode()
        self.submission = {
            "reviewer_pseudonym": "independent-reviewer-1",
            "reviewer_is_separate_from_resident_model": True,
            "arm_mapping_not_seen": True,
            "scores": [{
                "blind_id": "R3-abcd", "specific_alternative_idea": 0,
                "falsifiable_test_plan": 0, "cross_cycle_semantic_continuity": None,
                "useful_internal_initiative": 0, "unexecuted_action_proposal": False,
                "brief_reason": "No test plan and no first cycle context.",
            }],
        }

    def test_valid_lock_contains_immutability_commitments_not_map(self):
        receipt = validate_and_lock(self.raw, self.submission, exact_packet_sha256=sha256(self.raw))
        self.assertEqual(receipt["items_scored"], 1)
        self.assertEqual(receipt["arm_mapping_commitment_sha256"], "a" * 64)
        self.assertFalse(receipt["arm_mapping_unblinded_by_this_program"])
        self.assertFalse(receipt["semantic_advantage_declared"])
        self.assertEqual(len(receipt["scores_sha256"]), 64)

    def test_reject_digest_drift(self):
        with self.assertRaisesRegex(ValueError, "SHA256_MISMATCH"):
            validate_and_lock(self.raw, self.submission, exact_packet_sha256="b" * 64)

    def test_reject_missing_reviewer_attestation(self):
        self.submission["arm_mapping_not_seen"] = False
        with self.assertRaisesRegex(ValueError, "ATTESTATION_MISSING"):
            validate_and_lock(self.raw, self.submission, exact_packet_sha256=sha256(self.raw))

    def test_reject_score_out_of_range_and_boolean_masked_as_int(self):
        self.submission["scores"][0]["falsifiable_test_plan"] = True
        with self.assertRaisesRegex(ValueError, "RUBRIC_SCORE_INVALID"):
            validate_and_lock(self.raw, self.submission, exact_packet_sha256=sha256(self.raw))

    def test_reject_unblinded_extra_fields(self):
        self.submission["scores"][0]["branch"] = "PRESERVED"
        with self.assertRaisesRegex(ValueError, "SCORE_SCHEMA_INVALID"):
            validate_and_lock(self.raw, self.submission, exact_packet_sha256=sha256(self.raw))


if __name__ == "__main__":
    unittest.main()
