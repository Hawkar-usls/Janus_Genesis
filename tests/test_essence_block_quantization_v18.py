"""ESSENCE v1.8 precision search: research only, no working model mutation."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".janus" / "essence"))
import adaptive_quantization_v15 as v15
import block_quantization_v18 as e

class BlockPrecisionEvolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=v15.load(ROOT / ".janus" / "essence" / "manifest.json")
        cls.fixture=v15.load(ROOT / ".janus" / "essence" / "fixture.json")

    def test_measured_packet_improvement_without_relaxing_error(self):
        numbers=[0.25]*256
        before=v15.choose(numbers,"memory")
        after=e.optimize(numbers,"memory")
        self.assertLess(len(after["packet"]),len(before["packet"]))
        self.assertEqual(after["bits"],4)
        self.assertIn(after["block"],e.BLOCKS)
        self.assertLessEqual(after["error"],v15.POLICY["memory"])
        self.assertEqual(after["exact"],v15.normalized(numbers)[1])

    def test_all_seven_roles_research_gated_and_fp32_untouched(self):
        report,packed,backup=e.run(self.root,self.fixture,explicit_readonly=True)
        self.assertEqual(len(report["lanes"]),7)
        self.assertEqual(len(packed),report["v18_packed_bytes"])
        self.assertEqual(len(backup),report["exact_fp32_backup_bytes"])
        self.assertGreaterEqual(report["additional_storage_saving_bytes"],0)
        self.assertFalse(report["model_weights_changed"])
        self.assertFalse(report["actual_neural_training"])
        self.assertFalse(report["production_authority"])
        self.assertFalse(report["automatic_promotion"])
        self.assertFalse(report["independent_closed_holdout"])
        self.assertFalse(report["live_service_rollback_proven"])

    def test_deterministic_replay(self):
        a,packed_a,backup_a=e.run(self.root,self.fixture,explicit_readonly=True)
        b,packed_b,backup_b=e.run(self.root,self.fixture,explicit_readonly=True)
        self.assertEqual(a,b)
        self.assertEqual(packed_a,packed_b)
        self.assertEqual(backup_a,backup_b)

    def test_duplicate_evidence_cannot_increment_generation(self):
        first,_,_=e.run(self.root,self.fixture,explicit_readonly=True)
        again,_,_=e.run(self.root,self.fixture,previous=first,explicit_readonly=True)
        self.assertEqual(first["generation"],again["generation"])
        self.assertEqual(again["research_status"],"HOLD_DUPLICATE_NUMERIC_STATE")

    def test_tampered_previous_receipt_rejected(self):
        first,_,_=e.run(self.root,self.fixture,explicit_readonly=True)
        forged=copy.deepcopy(first)
        forged["production_authority"]=True
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_PARENT_PRECISION_EVIDENCE"):
            e.run(self.root,self.fixture,previous=forged,explicit_readonly=True)

    def test_declared_numeric_state_not_mistaken_for_live_model(self):
        source={"schema":"janus.essence.numeric_state/1.5",
                "repository":self.root["repository"],
                "source_class":"DECLARED_NUMERIC_STATE_UNVERIFIED",
                "vectors":{r:[0.25]*256 for r in (*v15.ROLES,"essence_self")}}
        report,_,backup=e.run(self.root,self.fixture,source=source,explicit_readonly=True)
        self.assertGreater(report["additional_storage_saving_bytes"],0)
        self.assertEqual(report["source_class"],"DECLARED_NUMERIC_STATE_UNVERIFIED")
        self.assertEqual(len(backup),7*256*4)
        self.assertFalse(report["target_hardware_proven"])
        self.assertFalse(report["production_authority"])

    def test_cross_repository_numeric_state_denied(self):
        source={"schema":"janus.essence.numeric_state/1.5",
                "repository":"Hawkar-usls/Another_Repo",
                "source_class":"DECLARED_NUMERIC_STATE_UNVERIFIED",
                "vectors":{r:[0.25]*256 for r in (*v15.ROLES,"essence_self")}}
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_NUMERIC_STATE"):
            e.run(self.root,self.fixture,source=source,explicit_readonly=True)

    def test_v18_packet_corrupt_header_and_tail_rejected(self):
        packet=e.pack([0.2]*65,4,64)
        self.assertEqual(len(e.unpack(packet)),65)
        for corrupted in [b"ZZZZ"+packet[4:],packet+b"\0",
                          packet[:7]+b"\0"+packet[8:]]:
            with self.assertRaises(ValueError):
                e.unpack(corrupted)

    def test_unrepresentable_payload_denied(self):
        for values in ([float("nan")], [float("inf")], [1e12]):
            with self.assertRaises(ValueError):
                e.pack(values,4,64)

    def test_inert_without_explicit_research_permission(self):
        with self.assertRaises(PermissionError):
            e.run(self.root,self.fixture)

if __name__=="__main__":
    unittest.main()
