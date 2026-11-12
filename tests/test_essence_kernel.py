"""No-network ESSENCE contract checks; safe on pull requests."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / ".janus" / "essence" / "kernel.py"
MANIFEST = ROOT / ".janus" / "essence" / "manifest.json"
FIXTURE = ROOT / ".janus" / "essence" / "fixture.json"
spec = importlib.util.spec_from_file_location("janus_essence_offline", CORE)
essence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(essence)


class EssencePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def run_pilot(self, *, child=None):
        return essence.evaluate(self.manifest, self.fixture, explicit_readonly=True,
                                propose_child=child, expected_repo=self.manifest["repository"])

    def test_inert_by_default(self):
        with self.assertRaises(PermissionError):
            essence.evaluate(self.manifest, self.fixture)

    def test_six_independent_role_receipts_and_hash_chain(self):
        report = self.run_pilot()
        self.assertTrue(essence.verify_report(report))
        self.assertEqual(report["status"], "PASS_WITH_OPERATIONAL_HOLD")
        self.assertEqual(len(report["receipts"]), 6)
        self.assertEqual(set(r["role"] for r in report["receipts"]), set(essence.ROLES))
        self.assertEqual(report["receipts"][0]["previous_sha256"], "0" * 64)
        self.assertFalse(report["action_authority"])

    def test_deterministic_receipts_with_same_source(self):
        first, second = self.run_pilot(), self.run_pilot()
        self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_tamper_report_and_chain_rejected(self):
        r = self.run_pilot()
        forged = copy.deepcopy(r)
        forged["receipts"][0]["result"]["mean"] = -1
        with self.assertRaises(ValueError):
            essence.verify_report(forged)
        forged = copy.deepcopy(r)
        forged["receipts"][1]["previous_sha256"] = "0" * 64
        forged["report_sha256"] = essence.digest({k: v for k, v in forged.items() if k != "report_sha256"})
        with self.assertRaises(ValueError):
            essence.verify_report(forged)

    def test_child_is_proposal_only_not_executed(self):
        report = self.run_pilot(child="memory")
        self.assertTrue(essence.verify_report(report))
        self.assertEqual(report["microkernel_count"], 6)
        self.assertEqual(len(report["receipts"]), 6)
        child = report["proposed_children"][0]
        self.assertEqual(child["state"], "PROPOSED_NOT_ACTIVE")
        self.assertFalse(child["activation_allowed"])
        self.assertNotIn(child["id"], [x["microkernel_id"] for x in report["receipts"]])
        forged = copy.deepcopy(report)
        forged["proposed_children"][0]["activation_allowed"] = True
        forged["report_sha256"] = essence.digest({k: v for k, v in forged.items() if k != "report_sha256"})
        with self.assertRaises(ValueError):
            essence.verify_report(forged)

    def test_privilege_escalation_rejected(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["capabilities"]["network"] = True
        with self.assertRaises(ValueError):
            essence.validate_manifest(candidate)
        candidate = copy.deepcopy(self.manifest)
        candidate["enabled"] = True
        with self.assertRaises(ValueError):
            essence.validate_manifest(candidate)
        candidate = copy.deepcopy(self.manifest)
        candidate["birth_policy"] = "AUTOMATIC"
        with self.assertRaises(ValueError):
            essence.validate_manifest(candidate)

    def test_duplicate_cell_and_missing_role_rejected(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["microkernels"][5]["id"] = candidate["microkernels"][0]["id"]
        with self.assertRaises(ValueError):
            essence.validate_manifest(candidate)
        candidate = copy.deepcopy(self.manifest)
        candidate["microkernels"][5]["role"] = "sensing"
        with self.assertRaises(ValueError):
            essence.validate_manifest(candidate)

    def test_repo_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            essence.validate_manifest(self.manifest, "Hawkar-usls/SOMETHING-ELSE")

    def test_nonfinite_or_out_of_bounds_fixture_rejected(self):
        for value in (math.nan, math.inf, -0.2, 1.3, True):
            candidate = copy.deepcopy(self.fixture)
            candidate["metrics"]["stability"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                essence.validate_fixture(candidate)

    def test_real_data_must_pass_future_independent_gate(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["kind"] = "REAL_WORLD_VALIDATED"
        with self.assertRaises(ValueError):
            essence.validate_fixture(candidate)


if __name__ == "__main__":
    unittest.main()
