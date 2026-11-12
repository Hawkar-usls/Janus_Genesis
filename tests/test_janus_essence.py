"""Contract tests for the effect-free ESSENCE R0 microkernel."""
import copy
import math
import unittest

from tools import janus_essence as e


class EssenceContractTests(unittest.TestCase):
    def setUp(self):
        self.parent = e.genome("Hawkar-usls/Janus-Demiurge")
        self.child = e.genome(
            "Hawkar-usls/Janus_Genesis", parent=self.parent, specialty="genesis",
        )
        self.packet = e.peer_packet(
            origin_repo=self.parent["repository"],
            source_sha="a" * 40, target_role="learning",
            artifact_sha256="b" * 64,
            summary="Only an unverified research candidate",
            metrics={"baseline_accuracy": 0.5, "candidate_accuracy": 0.6},
        )

    def test_root_and_child_integrity_and_independent_identity(self):
        self.assertTrue(e.verify_genome(self.parent))
        self.assertTrue(e.verify_genome(self.child))
        self.assertEqual(self.child["parent_integrity_sha256"],
                         self.parent["integrity_sha256"])
        self.assertNotEqual(self.child["integrity_sha256"],
                            self.parent["integrity_sha256"])
        self.assertEqual(self.child["generation"], 1)

    def test_reject_forged_child_privileges(self):
        forged = dict(self.child)
        forged["deployment_authority"] = True
        with self.assertRaises(ValueError):
            e.verify_genome(forged)
        # Rehashing cannot turn an unapproved capability into an admitted one.
        fraud = e._sealed({**{k: v for k, v in forged.items()
                               if k != "integrity_sha256"}}, "integrity_sha256")
        with self.assertRaises(ValueError):
            e.verify_genome(fraud)

    def test_child_cannot_gain_parent_roles(self):
        parent = e.genome("Hawkar-usls/Janus-Demiurge",
                          roles=("identity", "memory", "verification",
                                 "governance", "resource"))
        with self.assertRaisesRegex(ValueError, "CHILD_CANNOT_GAIN_NEW_ROLES"):
            e.genome("Hawkar-usls/Janus_Genesis", parent=parent)

    def test_peer_packet_tamper_and_nan_fail_closed(self):
        self.assertTrue(e.verify_packet(self.packet))
        broken = copy.deepcopy(self.packet)
        broken["metrics"]["candidate_accuracy"] = 1.0
        with self.assertRaises(ValueError):
            e.verify_packet(broken)
        with self.assertRaises(ValueError):
            e.peer_packet(origin_repo=self.parent["repository"],
                          source_sha="a" * 40, target_role="learning",
                          artifact_sha256="b" * 64, summary="invalid",
                          metrics={"score": math.nan})

    def test_unauthorized_peer_refused(self):
        node = e.EssenceCore(self.child, allowed_peers=())
        with self.assertRaisesRegex(ValueError, "PEER_NOT_ALLOWLISTED"):
            node.receive(self.packet)
        self.assertEqual(node.inbox, [])

    def test_exchange_is_quarantined_never_train_or_execute(self):
        node = e.EssenceCore(self.child,
                             allowed_peers=(self.parent["repository"],))
        status = node.receive(self.packet)
        self.assertEqual(status["status"], "QUARANTINED_LEARNING_CANDIDATE")
        self.assertFalse(status["authenticated_source"])
        self.assertFalse(status["trained_from_packet"])
        self.assertEqual(node.receive(self.packet)["status"], "DEDUPLICATED")
        pulse = node.pulse()
        self.assertEqual(pulse["candidate_count"], 1)
        self.assertEqual(pulse["verified_evidence_count"], 0)
        self.assertFalse(pulse["neural_training_performed"])
        self.assertEqual(pulse["external_actions"], 0)
        self.assertFalse(pulse["full_autonomy"])

    def test_missing_evidence_and_invalid_target_rejected(self):
        with self.assertRaises(ValueError):
            e.peer_packet(origin_repo=self.parent["repository"],
                          source_sha="a" * 40, target_role="memory",
                          artifact_sha256="", summary="empty evidence")
        node = e.EssenceCore(
            e.genome("Hawkar-usls/Janus_Genesis", roles=(
                "identity", "memory", "verification", "governance", "resource"
            )), allowed_peers=(self.parent["repository"],))
        with self.assertRaisesRegex(ValueError, "TARGET_NOT_INSTALLED"):
            node.receive(self.packet)

    def test_failure_of_one_microcore_does_not_kill_siblings(self):
        node = e.EssenceCore(self.child)
        receipt = node.pulse(simulate_failure=("planning",))
        roles = {x["role"]: x["status"] for x in receipt["microcores"]}
        self.assertEqual(roles["planning"], "ISOLATED_FAILURE")
        self.assertEqual(roles["memory"], "LOCAL_POLICY_READY")
        self.assertEqual(roles["learning"], "HOLD_INDEPENDENT_VALIDATION_REQUIRED")
        self.assertEqual(len(roles), 13)
        self.assertEqual(receipt["receipt_sha256"],
                         e.digest({k: v for k, v in receipt.items()
                                   if k != "receipt_sha256"}))

    def test_reject_payload_with_extra_semantics_even_if_rehashed(self):
        packet = dict(self.packet)
        data = {k: v for k, v in packet.items() if k != "packet_sha256"}
        data["auto_execute"] = True
        malicious = e._sealed(data, "packet_sha256")
        with self.assertRaises(ValueError):
            e.verify_packet(malicious)


    def test_unified_six_cell_adapter_inside_one_essence(self):
        six = ("sensing", "memory", "planning", "verification", "recovery", "coding")
        adapter = {
            "schema": "janus.essence.microkernel/0.1",
            "repository": "Hawkar-usls/Janus_Genesis",
            "enabled": False,
            "activation": "EXPLICIT_READONLY_TEST_ONLY",
            "capabilities": {x: False for x in (
                "network", "shell", "repo_write", "workflow_dispatch",
                "secrets", "hardware",
            )},
            "birth_policy": "PROPOSAL_ONLY",
            "microkernels": [
                {"id": f"cell-{role}", "role": role, "generation": 0,
                 "gene_sources": ["historical_source"]}
                for role in six
            ],
        }
        profile = e.unified_profile(adapter, self.child)
        self.assertEqual(profile["logical_core_instances"], 1)
        self.assertEqual(len(profile["legacy_adapter_roles"]), 6)
        self.assertEqual(len(profile["extended_roles"]), 7)
        self.assertFalse(profile["model_weights_imported"])
        forged = copy.deepcopy(adapter)
        forged["capabilities"]["network"] = True
        with self.assertRaises(ValueError):
            e.unified_profile(forged, self.child)
        forged = copy.deepcopy(adapter)
        forged["repository"] = "Hawkar-usls/Janus-Demiurge"
        with self.assertRaisesRegex(ValueError, "REPOSITORY_IDENTITY_SPLIT"):
            e.unified_profile(forged, self.child)


if __name__ == "__main__":
    unittest.main()
