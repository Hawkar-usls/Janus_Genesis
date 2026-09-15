#!/usr/bin/env python3
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP))

P = EXP / "spectral_replication_probe.py"
spec = importlib.util.spec_from_file_location("srp", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

A = EXP / "spectral_replication_admission.py"
aspec = importlib.util.spec_from_file_location("sra", A)
adm = importlib.util.module_from_spec(aspec)
aspec.loader.exec_module(adm)


class SpectralReplicationTests(unittest.TestCase):
    def test_frozen_manifest_matches_runtime(self):
        manifest = json.loads((EXP / "spectral_replication_pairs.json").read_text(encoding="utf-8"))
        m.assert_frozen_protocol(manifest)
        self.assertEqual(m.EXPECTED_WEIGHTS, {"luminance": 0.40, "chromaticity": 0.40, "edge": 0.20})
        self.assertEqual(m.EXPECTED_HOTSPOT_QUANTILE, 0.95)
        self.assertEqual(m.EXPECTED_GAMMA, 0.72)

    def test_retuning_is_rejected(self):
        manifest = json.loads((EXP / "spectral_replication_pairs.json").read_text(encoding="utf-8"))
        manifest["frozen_protocol"]["difference_weights"]["edge"] = 0.21
        with self.assertRaises(AssertionError):
            m.assert_frozen_protocol(manifest)

    def test_candidate_provenance_is_not_silently_confirmed(self):
        manifest = json.loads((EXP / "spectral_replication_pairs.json").read_text(encoding="utf-8"))
        pair = next(p for p in manifest["pairs"] if p["id"].startswith("LUCASFASSARI"))
        status = pair["same_specimen_status"]
        self.assertTrue(status.startswith("PROBABLE"))
        self.assertNotEqual(status, "CONFIRMED_SAME_SPECIMEN")
        self.assertIn("NOT_EXPLICITLY_CONFIRMED", status)

    def test_fms_primary_is_confirmed_same_specimen_before_measurement(self):
        manifest = json.loads((EXP / "spectral_replication_pairs.json").read_text(encoding="utf-8"))
        pair = next(p for p in manifest["pairs"] if p["id"] == "FMS_1226_PAKISTAN_QUARTZ_NORMAL_LW365")
        self.assertTrue(pair["same_specimen_status"].startswith("CONFIRMED"))
        self.assertEqual(pair["role"], "PRIMARY_INDEPENDENT_CONFIRMED_SAME_SPECIMEN_REPLICATION_CANDIDATE")
        self.assertEqual(pair["uv"]["modality"], "LONGWAVE_UV_365_NM_LED_RECORDED")

    def test_fms_shortwave_is_confirmatory_not_second_independent_specimen(self):
        manifest = json.loads((EXP / "spectral_replication_pairs.json").read_text(encoding="utf-8"))
        pair = next(p for p in manifest["pairs"] if p["id"] == "FMS_1226_PAKISTAN_QUARTZ_NORMAL_SW254")
        self.assertEqual(pair["role"], adm.CONFIRMATORY_ROLE)
        self.assertEqual(pair["uv"]["modality"], "SHORTWAVE_UV_254_NM_MERCURY_LAMP_RECORDED")

    def test_anchor_is_explicitly_not_replication(self):
        manifest = json.loads((EXP / "spectral_replication_pairs.json").read_text(encoding="utf-8"))
        anchor = next(p for p in manifest["pairs"] if p["id"].startswith("ALATAY"))
        self.assertEqual(anchor["role"], "FROZEN_DISCOVERY_ANCHOR_NOT_REPLICATION")

    def test_geometry_corroboration_on_identical_textured_scene(self):
        rng = np.random.default_rng(1138)
        img = rng.integers(0, 256, (420, 620, 3), dtype=np.uint8)
        for i in range(25):
            x = 20 + (i * 23) % 560
            y = 20 + (i * 37) % 360
            cv2.circle(img, (x, y), 7 + i % 5, (255, 255, 255), 2)
        r = m.geometry_corroboration(img, img.copy())
        self.assertEqual(r["status"], "IMAGE_GEOMETRY_SUPPORTS_SAME_SCENE")
        self.assertGreaterEqual(r["homography_inliers"], 12)

    def test_failed_positive_control_invalidates_geometry_as_necessary_gate(self):
        raw = {"pairs": [
            {
                "pair_id": "anchor",
                "role": "FROZEN_DISCOVERY_ANCHOR_NOT_REPLICATION",
                "same_specimen_status": "CONFIRMED_BY_SOURCE",
                "geometry_corroboration": {"status": "INSUFFICIENT_MATCHES"},
                "image_level_gate": {"status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"},
                "planner_enrichment": {"status": "NO_PLANNER_ENRICHMENT"},
            },
            {
                "pair_id": "candidate",
                "role": "INDEPENDENT_REPLICATION_CANDIDATE",
                "same_specimen_status": "PROBABLE_NOT_EXPLICITLY_CONFIRMED_BY_SOURCE",
                "geometry_corroboration": {"status": "INSUFFICIENT_MATCHES"},
                "image_level_gate": {"status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"},
                "planner_enrichment": {"status": "NO_PLANNER_ENRICHMENT"},
            },
        ]}
        r = adm.admit(raw)
        self.assertFalse(r["geometry_validator"]["usable_for_admission"])
        self.assertIn("INVALIDATED_FALSE_NEGATIVE", r["geometry_validator"]["status"])
        self.assertEqual(r["candidate_count"], 1)
        self.assertEqual(r["formal_independent_replication_count"], 0)
        self.assertEqual(r["cross_specimen_replication_gate"], "OPEN_NOT_ESTABLISHED")

    def test_confirmatory_same_specimen_pair_does_not_double_count_formal_replication(self):
        raw = {"pairs": [
            {
                "pair_id": "anchor",
                "role": "FROZEN_DISCOVERY_ANCHOR_NOT_REPLICATION",
                "same_specimen_status": "CONFIRMED_BY_SOURCE",
                "geometry_corroboration": {"status": "INSUFFICIENT_MATCHES"},
                "image_level_gate": {"status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"},
                "planner_enrichment": {"status": "NO_PLANNER_ENRICHMENT"},
            },
            {
                "pair_id": "fms-lw",
                "role": "PRIMARY_INDEPENDENT_CONFIRMED_SAME_SPECIMEN_REPLICATION_CANDIDATE",
                "same_specimen_status": "CONFIRMED_BY_SINGLE_RECORD",
                "geometry_corroboration": {"status": "INSUFFICIENT_MATCHES"},
                "image_level_gate": {"status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"},
                "planner_enrichment": {"status": "NO_PLANNER_ENRICHMENT"},
            },
            {
                "pair_id": "fms-sw",
                "role": adm.CONFIRMATORY_ROLE,
                "same_specimen_status": "CONFIRMED_BY_SINGLE_RECORD",
                "geometry_corroboration": {"status": "INSUFFICIENT_MATCHES"},
                "image_level_gate": {"status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"},
                "planner_enrichment": {"status": "NO_PLANNER_ENRICHMENT"},
            },
        ]}
        r = adm.admit(raw)
        self.assertEqual(r["formal_independent_replication_count"], 1)
        self.assertEqual(r["confirmatory_modality_count"], 1)
        self.assertEqual(r["cross_specimen_replication_gate"], "PASS")


if __name__ == "__main__":
    unittest.main()
