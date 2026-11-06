"""These tests prove deterministic geometry and report boundaries, not material properties."""
import json
import tempfile
import unittest
from pathlib import Path

from janus_genesis.scoby_skin_genesis import generate, occupancy


class TestDigitalPrototype(unittest.TestCase):
    def test_repeatable_geometry_and_unqualified_claims(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            a = generate(Path(left))
            b = generate(Path(right))
            self.assertEqual(a["digital_prototype"]["stl_sha256"], b["digital_prototype"]["stl_sha256"])
            self.assertEqual(a["geometric_predictions"], b["geometric_predictions"])
            self.assertGreater(a["geometric_predictions"]["open_area_fraction"], 0)
            self.assertLess(a["geometric_predictions"]["open_area_fraction"], 1)
            self.assertIsNone(a["biological_forecasts"]["BC_PLA_bond_strength_MPa"])
            self.assertIsNone(a["sensing_forecasts"]["SkinGPT_severe_fault_recall"])
            self.assertIn("NOT_GENERATED", a["blocked_arms"]["C_BC_PLUS_ARTICULATED_PLA_FABRIC"])
            self.assertEqual(json.loads((Path(left) / "predictions.json").read_text()), a)

    def test_bad_input_rejected(self):
        with self.assertRaises(ValueError):
            occupancy(71, 10, 1.5)
        with self.assertRaises(ValueError):
            occupancy(70, 10, 0.1)

    def test_manifest_validation_must_not_be_turned_into_sensor_accuracy(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            good = root / "manifest.json"
            good.write_text(json.dumps({
                "schema": "skingpt.session_manifest.v0.3",
                "claim_ceiling": "PROVENANCE_ONLY_NOT_PHYSICAL_VALIDATION",
                "hash_semantics": "SHA256_IS_INTEGRITY_NOT_TRUTH",
                "source_log": {"sha256": "a" * 64},
            }))
            result = generate(root / "out", manifest_path=good)
            self.assertEqual(
                result["skinGPT_reference"]["state"],
                "MANIFEST_REFERENCE_ONLY_NOT_VERIFIED_RAW_FRAMES",
            )
            good.write_text("{}")
            with self.assertRaises(ValueError):
                generate(root / "fail", manifest_path=good)


if __name__ == "__main__":
    unittest.main()
