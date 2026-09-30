from __future__ import annotations

import unittest

from tools.janus_preservation_integration_evidence import (
    PreservationEvidenceError,
    digest,
    validate_lock,
)


class PreservationIntegrationProducerLockV1Tests(unittest.TestCase):
    def lock(self) -> dict[str, object]:
        return {
            "schema": "janus.nexus.preservation_integration_lock.v1",
            "preregistration_receipt": "5308388940",
            "expected_source_count": 44,
            "privacy_mode": "LOCAL_EVIDENCE_PUBLIC_REDACTED_SUMMARY",
            "producer_refs": {
                "materializer": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 122, "sha": "1" * 40},
                "privacy_projection": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 125, "sha": "2" * 40},
                "source_pin_contract": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 126, "sha": "3" * 40},
                "variant_lineage": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 123, "sha": "4" * 40},
                "handoff_ledger": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 124, "sha": "5" * 40},
                "swarm_recovery": {"repository": "Hawkar-usls/janus-distributed-ai-swarm", "pull_request": 5, "sha": "6" * 40},
                "source_identity_guard": {"repository": "Hawkar-usls/Janus_Genesis", "pull_request": 133, "sha": "7" * 40},
            },
        }

    def test_canonical_seven_role_lock_validates(self) -> None:
        lock = self.lock()
        validated = validate_lock(lock)
        self.assertEqual(validated["producer_refs"], lock["producer_refs"])
        self.assertEqual(len(validated["producer_refs"]), 7)
        self.assertEqual(len(digest(validated)), 64)

    def test_same_repository_wrong_pr_cannot_impersonate_materializer(self) -> None:
        lock = self.lock()
        lock["producer_refs"]["materializer"]["pull_request"] = 125  # type: ignore[index]
        with self.assertRaisesRegex(
            PreservationEvidenceError,
            "materializer.pull_request must be canonical producer PR 122",
        ):
            validate_lock(lock)

    def test_source_guard_role_cannot_point_to_another_genesis_pr(self) -> None:
        lock = self.lock()
        lock["producer_refs"]["source_identity_guard"]["pull_request"] = 122  # type: ignore[index]
        with self.assertRaisesRegex(
            PreservationEvidenceError,
            "source_identity_guard.pull_request must be canonical producer PR 133",
        ):
            validate_lock(lock)

    def test_legacy_six_role_lock_fails_closed(self) -> None:
        lock = self.lock()
        del lock["producer_refs"]["source_identity_guard"]  # type: ignore[index]
        with self.assertRaisesRegex(PreservationEvidenceError, "producer_refs keys mismatch"):
            validate_lock(lock)


if __name__ == "__main__":
    unittest.main()
