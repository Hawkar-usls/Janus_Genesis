from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import janus_physical_gate_receipt_join as gate

GENESIS = "227d42d6848790031916cac53d39961a19c35d08"
SWARM = "b0bb07418cb1c0e1bc2da8ae443977825c0b19d1"


def owner_receipt():
    return {
        "schema": gate.SCHEMA,
        "kind": gate.OWNER_KIND,
        "view": {"genesis_main_sha": GENESIS, "swarm_main_sha": SWARM},
        "markers": copy.deepcopy(gate.OWNER_MARKERS),
        "privacy": copy.deepcopy(gate.OWNER_PRIVACY),
    }


def nas_receipt():
    return {
        "schema": gate.SCHEMA,
        "kind": gate.NAS_KIND,
        "view": {"genesis_main_sha": GENESIS, "swarm_main_sha": SWARM},
        "markers": copy.deepcopy(gate.NAS_MARKERS),
        "live": copy.deepcopy(gate.NAS_LIVE),
    }


def trusted_bindings(owner=None, nas=None):
    owner = owner_receipt() if owner is None else owner
    nas = nas_receipt() if nas is None else nas
    return {
        "status": gate.TRUST_STATUS,
        "binding_source": "SOURCE_CONTROLLED_PROTOCOL_ONLY",
        "owner44": {
            "projection_sha256": gate._sha256(owner),
            "evidence_sha256": "1" * 64,
            "execution_id": "OWNER44-REAL-TEST-001",
            "producer": "JANUS_OWNER44_PHYSICAL_RUNNER_V1",
        },
        "nas164": {
            "projection_sha256": gate._sha256(nas),
            "evidence_sha256": "2" * 64,
            "execution_id": "NAS164-REAL-TEST-001",
            "producer": "JANUS_NAS164_LIVE_RUNNER_V1",
        },
    }


def test_join(owner=None, nas=None, bindings=None):
    owner = owner_receipt() if owner is None else owner
    nas = nas_receipt() if nas is None else nas
    bindings = trusted_bindings(owner, nas) if bindings is None else bindings
    return gate._join_with_bindings_for_test(owner, nas, GENESIS, SWARM, bindings)


class PhysicalGateJoinTests(unittest.TestCase):
    def test_positive_test_seam_stops_below_final_acceptance(self):
        result = test_join()
        self.assertEqual(result["markers"]["REAL_OWNER44_SOURCE_REPLAY"], "PASS")
        self.assertEqual(result["markers"]["LIVE_NAS_164_HR1_HR10"], "PASS")
        self.assertEqual(result["markers"]["AUTHENTICATED_REAL_EXECUTION_BINDINGS"], "PASS")
        self.assertTrue(result["markers"]["READY_FOR_FINAL_162_GAUNTLET"])
        self.assertFalse(result["markers"]["FULL_ISSUE_162_ACCEPTANCE"])
        self.assertEqual(result["markers"]["AUTHORITY_DELTA"], 0)

    def test_public_join_uses_pending_source_control_and_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "TRUSTED_RECEIPT_BINDINGS_NOT_PINNED"):
            gate.join(owner_receipt(), nas_receipt(), GENESIS, SWARM)

    def test_public_join_rejects_caller_trust_root_parameter(self):
        with self.assertRaises(TypeError):
            gate.join(
                owner_receipt(),
                nas_receipt(),
                GENESIS,
                SWARM,
                trusted_bindings=trusted_bindings(),
            )

    def test_unpinned_bindings_fail_closed_in_test_seam(self):
        bindings = trusted_bindings()
        bindings["status"] = "PENDING_REAL_EXECUTION"
        with self.assertRaisesRegex(ValueError, "TRUSTED_RECEIPT_BINDINGS_NOT_PINNED"):
            test_join(bindings=bindings)

    def test_forged_projection_cannot_reuse_trusted_binding(self):
        owner = owner_receipt()
        nas = nas_receipt()
        bindings = trusted_bindings(owner, nas)
        forged = owner_receipt()
        forged["markers"]["TWO_CLEAN_TARGET_REBUILDS_MATCH"] = False
        with self.assertRaises(ValueError):
            test_join(owner=forged, nas=nas, bindings=bindings)

    def test_genesis_view_drift_fails_closed(self):
        value = owner_receipt()
        value["view"]["genesis_main_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "GENESIS_SHA_DRIFT"):
            test_join(owner=value)

    def test_private_exact_pin_disclosure_fails_closed(self):
        value = owner_receipt()
        value["privacy"]["private_exact_pins_disclosed"] = True
        with self.assertRaises(ValueError):
            test_join(owner=value)

    def test_reference_only_nas_cannot_pass_as_live(self):
        value = nas_receipt()
        value["live"]["reference_only"] = True
        with self.assertRaises(ValueError):
            test_join(nas=value)

    def test_bool_integer_substitution_fails_closed(self):
        value = nas_receipt()
        value["live"]["hr1_hr10_live_execution"] = 1
        with self.assertRaisesRegex(ValueError, "TYPE_MISMATCH"):
            test_join(nas=value)

    def test_false_is_not_accepted_for_integer_authority_delta(self):
        value = owner_receipt()
        value["markers"]["AUTHORITY_DELTA"] = False
        with self.assertRaisesRegex(ValueError, "TYPE_MISMATCH"):
            test_join(owner=value)

    def test_missing_hr_gate_fails_closed(self):
        value = nas_receipt()
        del value["markers"]["HR7"]
        with self.assertRaisesRegex(ValueError, "KEYSET_MISMATCH"):
            test_join(nas=value)

    def test_unknown_field_rejected_to_reduce_public_leak_surface(self):
        value = owner_receipt()
        value["private_repo"] = "must-not-be-accepted"
        with self.assertRaisesRegex(ValueError, "KEYSET_MISMATCH"):
            test_join(owner=value)

    def test_output_is_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "join.json"
            gate._write_private_no_overwrite(target, {"ok": True})
            self.assertTrue(target.exists())
            with self.assertRaises(FileExistsError):
                gate._write_private_no_overwrite(target, {"ok": False})


if __name__ == "__main__":
    unittest.main()
