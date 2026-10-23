#!/usr/bin/env python3
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP))

P = EXP / "sierpinski_sw254_replication_probe.py"
spec = importlib.util.spec_from_file_location("ssr", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

import fms_page_media as resolver


class SierpinskiSW254ReplicationTests(unittest.TestCase):
    def test_manifest_is_frozen_to_candidate_planner(self):
        manifest = json.loads((EXP / "sierpinski_sw254_replication.json").read_text(encoding="utf-8"))
        traj = json.loads((EXP / "sources.json").read_text(encoding="utf-8"))
        m.assert_preregistered(manifest, traj)
        self.assertEqual(manifest["frozen_measurement"]["planner"], "fractalgpt_sierpinski")
        self.assertEqual(manifest["frozen_measurement"]["matched_random_trajectories"], 2048)

    def test_retuned_alpha_is_rejected(self):
        manifest = json.loads((EXP / "sierpinski_sw254_replication.json").read_text(encoding="utf-8"))
        traj = json.loads((EXP / "sources.json").read_text(encoding="utf-8"))
        manifest["frozen_measurement"]["replication_alpha"] = 0.01
        with self.assertRaises(AssertionError):
            m.assert_preregistered(manifest, traj)

    def test_both_endpoints_are_required(self):
        manifest = json.loads((EXP / "sierpinski_sw254_replication.json").read_text(encoding="utf-8"))
        entry = {
            "registration": {"quality_class": "USABLE_IMAGE_REGISTRATION"},
            "image_level_gate": {"status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"},
            "planner_random_null_tests": {
                "fractalgpt_sierpinski": {
                    "one_sided_empirical_p_composite": 0.0005,
                    "one_sided_empirical_p_hotspot": 0.01,
                }
            }
        }
        r = m.evaluate(entry, manifest)
        self.assertTrue(r["composite_pass"])
        self.assertFalse(r["hotspot_pass"])
        self.assertEqual(r["replication_gate"], "FAIL_TO_REPLICATE")

    def test_media_srcset_prefers_largest_width(self):
        tag = '<img src="small.jpg" srcset="small.jpg 400w, big.jpg 2000w">'
        self.assertEqual(resolver._largest_src_from_tag(tag), "big.jpg")


if __name__ == "__main__":
    unittest.main()
