from __future__ import annotations

import copy
import json
import unittest

from tools.janus_preservation_integration_evidence import (
    PreservationEvidenceError,
    digest,
    evaluate as evaluate_evidence,
)


class PreservationIntegrationEvidenceV1Tests(unittest.TestCase):
    def refs(self) -> dict[str, dict[str, object]]:
        return {
            "materializer": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 122, "sha": "1" * 40},
            "privacy_projection": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 125, "sha": "2" * 40},
            "source_pin_contract": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 126, "sha": "6" * 40},
            "variant_lineage": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 123, "sha": "3" * 40},
            "handoff_ledger": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 124, "sha": "4" * 40},
            "swarm_recovery": {"repository": "Hawkar-usls/janus-distributed-ai-swarm", "pull_request": 5, "sha": "5" * 40},
            "source_identity_guard": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 133, "sha": "7" * 40},
        }

    def lock(self) -> dict[str, object]:
        return {
            "schema": "janus.nexus.preservation_integration_lock.v1",
            "preregistration_receipt": "5308388940",
            "expected_source_count": 44,
            "privacy_mode": "LOCAL_EVIDENCE_PUBLIC_REDACTED_SUMMARY",
            "producer_refs": self.refs(),
        }

    def bundle(self) -> dict[str, object]:
        return {
            "schema": "janus.nexus.preservation_integration_evidence.v1",
            "producer_refs": self.refs(),
            "materializer": {
                "source_count": 44,
                "clean_target_rebuild_exercised": True,
                "rebuild_a_digest": "a" * 64,
                "rebuild_b_digest": "a" * 64,
                "local_exact_replay_passed": True,
                "privacy_projection_passed": True,
                "source_pin_drift": False,
                "source_writeback_observed": False,
                "destructive_cleanup_required_for_pass": False,
            },
            "source_pins": {
                "typed_pinset_validated": True,
                "exact_git_replay_required": True,
                "git_commit_kind": "GIT_COMMIT_SHA1",
                "opaque_version_kind": "OPAQUE_VERSION_TOKEN",
                "type_inference_used": False,
                "private_exact_pin_publication": False,
                "whole_pinset_digest_publication": False,
            },
            "lineage": {
                "expected_head_digest": "b" * 64,
                "observed_head_digest": "b" * 64,
                "failed_variant_ids": ["c" * 64],
                "failed_variants_retained": True,
            },
            "handoff": {
                "expected_head_digest": "d" * 64,
                "observed_head_digest": "d" * 64,
                "conflict_message_ids": ["MSG-A", "MSG-B"],
                "conflicts_retained": True,
                "reconciliation_status": "HOLD_RECONCILE",
                "majority_vote_used": False,
            },
            "swarm": {
                "checkpoint_digest": "e" * 64,
                "receipt_digest": "f" * 64,
                "session_drop_exercised": True,
                "resume_decision": "RESUME",
                "source_pin_drift": False,
                "duplicate_source_mutation_observed": False,
            },
            "source_guard": {
                "before_identity_digest": "9" * 64,
                "after_identity_digest": "9" * 64,
                "writeback_observed": False,
                "destructive_effect_observed": False,
            },
        }

    def evaluate(self, bundle=None, lock=None, expected_lock_digest=None):
        actual_lock = lock if lock is not None else self.lock()
        pinned = expected_lock_digest if expected_lock_digest is not None else digest(actual_lock)
        return evaluate_evidence(bundle if bundle is not None else self.bundle(), actual_lock, pinned)

    def test_complete_preregistered_evidence_bundle_is_consistent(self) -> None:
        result = self.evaluate()
        self.assertEqual(result["decision"], "EVIDENCE_BUNDLE_CONSISTENT")
        self.assertTrue(result["clean_target_rebuild_exercised"])
        self.assertTrue(result["typed_source_pin_contract_passed"])
        self.assertTrue(result["failed_variant_retention"])
        self.assertTrue(result["conflict_retention_and_hold_reconcile"])
        self.assertTrue(result["swarm_session_drop_recovery"])
        self.assertFalse(result["source_writeback_observed"])
        self.assertFalse(result["empirical_replay_claimed_by_this_verifier"])
        self.assertFalse(result["merge_permission_granted"])

    def test_out_of_band_lock_digest_is_mandatory(self) -> None:
        with self.assertRaisesRegex(PreservationEvidenceError, "external producer lock digest mismatch"):
            self.evaluate(expected_lock_digest="0" * 64)
        with self.assertRaisesRegex(PreservationEvidenceError, "lowercase 64-hex"):
            self.evaluate(expected_lock_digest="not-a-digest")

    def test_producer_refs_must_match_external_lock(self) -> None:
        bundle = self.bundle()
        bundle["producer_refs"]["materializer"]["sha"] = "8" * 40  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "producer refs do not match"):
            self.evaluate(bundle=bundle)

    def test_source_identity_guard_is_mandatory_in_external_lock(self) -> None:
        lock = self.lock()
        del lock["producer_refs"]["source_identity_guard"]  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "producer_refs keys mismatch"):
            self.evaluate(lock=lock, expected_lock_digest=digest(lock))

    def test_source_identity_guard_repository_and_ref_are_bound(self) -> None:
        wrong_repo = self.lock()
        wrong_repo["producer_refs"]["source_identity_guard"]["repository"] = "Hawkar-usls/janus-distributed-ai-swarm"  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "Hawkar-usls/Janus_Genesis"):
            self.evaluate(lock=wrong_repo, expected_lock_digest=digest(wrong_repo))

        bundle = self.bundle()
        bundle["producer_refs"]["source_identity_guard"]["sha"] = "8" * 40  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "producer refs do not match"):
            self.evaluate(bundle=bundle)

    def test_repository_identity_is_bound_per_producer_role(self) -> None:
        lock = self.lock()
        lock["producer_refs"]["swarm_recovery"]["repository"] = "Hawkar-usls/Janus_Genesis"  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "janus-distributed-ai-swarm"):
            self.evaluate(lock=lock, expected_lock_digest=digest(lock))

    def test_malformed_producer_sha_and_pr_fail_closed(self) -> None:
        lock = self.lock()
        lock["producer_refs"]["swarm_recovery"]["sha"] = "main"  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "exact lowercase 40-hex"):
            self.evaluate(lock=lock, expected_lock_digest=digest(lock))

        lock = self.lock()
        lock["producer_refs"]["materializer"]["pull_request"] = True  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "positive integer PR"):
            self.evaluate(lock=lock, expected_lock_digest=digest(lock))

    def test_source_pin_contract_is_mandatory_and_never_inferred(self) -> None:
        inferred = self.bundle()
        inferred["source_pins"]["type_inference_used"] = True  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be False"):
            self.evaluate(bundle=inferred)

        wrong_kind = self.bundle()
        wrong_kind["source_pins"]["git_commit_kind"] = "OPAQUE_VERSION_TOKEN"  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be GIT_COMMIT_SHA1"):
            self.evaluate(bundle=wrong_kind)

        leaked = self.bundle()
        leaked["source_pins"]["private_exact_pin_publication"] = True  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be False"):
            self.evaluate(bundle=leaked)

    def test_independent_rebuild_digest_mismatch_is_rejected(self) -> None:
        bundle = self.bundle()
        bundle["materializer"]["rebuild_b_digest"] = "8" * 64  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "rebuild digests differ"):
            self.evaluate(bundle=bundle)

    def test_missing_or_malformed_failed_variant_evidence_is_rejected(self) -> None:
        bundle = self.bundle()
        bundle["lineage"]["failed_variant_ids"] = []  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "at least one retained failed variant"):
            self.evaluate(bundle=bundle)

        malformed = self.bundle()
        malformed["lineage"]["failed_variant_ids"] = [{"not": "hashable-as-id"}]  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be lowercase 64-hex"):
            self.evaluate(bundle=malformed)

    def test_lineage_head_mismatch_is_rejected(self) -> None:
        bundle = self.bundle()
        bundle["lineage"]["observed_head_digest"] = "8" * 64  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "lineage expected/observed"):
            self.evaluate(bundle=bundle)

    def test_handoff_must_reconstruct_hold_without_majority_vote(self) -> None:
        not_hold = self.bundle()
        not_hold["handoff"]["reconciliation_status"] = "CONSISTENT"  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be HOLD_RECONCILE"):
            self.evaluate(bundle=not_hold)

        majority = self.bundle()
        majority["handoff"]["majority_vote_used"] = True  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be False"):
            self.evaluate(bundle=majority)

        malformed = self.bundle()
        malformed["handoff"]["conflict_message_ids"] = ["MSG-A", {"bad": "id"}]  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be a non-empty string"):
            self.evaluate(bundle=malformed)

    def test_swarm_session_drop_and_resume_are_mandatory(self) -> None:
        bundle = self.bundle()
        bundle["swarm"]["session_drop_exercised"] = False  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be True"):
            self.evaluate(bundle=bundle)

        bundle = self.bundle()
        bundle["swarm"]["resume_decision"] = "HOLD"  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be RESUME"):
            self.evaluate(bundle=bundle)

    def test_source_identity_change_or_writeback_is_rejected(self) -> None:
        changed = self.bundle()
        changed["source_guard"]["after_identity_digest"] = "0" * 64  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "source identity changed"):
            self.evaluate(bundle=changed)

        wrote = self.bundle()
        wrote["source_guard"]["writeback_observed"] = True  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "must be False"):
            self.evaluate(bundle=wrote)

    def test_unknown_bundle_fields_are_rejected(self) -> None:
        bundle = self.bundle()
        bundle["permission_granted"] = True
        with self.assertRaisesRegex(PreservationEvidenceError, "bundle keys mismatch"):
            self.evaluate(bundle=bundle)

    def test_public_summary_does_not_echo_local_sensitive_evidence(self) -> None:
        bundle = self.bundle()
        result = self.evaluate(bundle=bundle)
        serialized = json.dumps(result, sort_keys=True)
        local_sensitive = {
            bundle["materializer"]["rebuild_a_digest"],  # type: ignore[index]
            bundle["lineage"]["expected_head_digest"],  # type: ignore[index]
            bundle["lineage"]["failed_variant_ids"][0],  # type: ignore[index]
            bundle["handoff"]["expected_head_digest"],  # type: ignore[index]
            bundle["handoff"]["conflict_message_ids"][0],  # type: ignore[index]
            bundle["handoff"]["conflict_message_ids"][1],  # type: ignore[index]
            bundle["swarm"]["checkpoint_digest"],  # type: ignore[index]
            bundle["swarm"]["receipt_digest"],  # type: ignore[index]
            bundle["source_guard"]["before_identity_digest"],  # type: ignore[index]
        }
        for value in local_sensitive:
            self.assertNotIn(str(value), serialized)
        self.assertFalse(result["local_sensitive_evidence_persisted_in_summary"])
        self.assertEqual(result["producer_refs"], self.refs())

    def test_lock_digest_and_refs_are_preserved_in_public_summary(self) -> None:
        bundle = self.bundle()
        lock = self.lock()
        bundle_refs = copy.deepcopy(bundle["producer_refs"])
        lock["producer_refs"] = bundle_refs
        pinned_digest = digest(lock)
        result = self.evaluate(bundle=bundle, lock=lock, expected_lock_digest=pinned_digest)
        self.assertEqual(result["producer_refs"], self.refs())
        self.assertEqual(result["producer_lock_digest"], pinned_digest)


if __name__ == "__main__":
    unittest.main()
