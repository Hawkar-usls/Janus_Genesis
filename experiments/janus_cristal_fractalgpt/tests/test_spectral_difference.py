#!/usr/bin/env python3
import importlib.util
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
P = EXP / "spectral_difference_probe.py"
spec = importlib.util.spec_from_file_location("sdp", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SpectralDifferenceTests(unittest.TestCase):
    def test_difference_identity_zero(self):
        rng = np.random.default_rng(1138)
        img = rng.integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
        mask = np.ones(img.shape[:2], dtype=np.uint8)
        fields = m.difference_channels(img, img.copy(), mask)
        for name, field in fields.items():
            self.assertLess(float(np.max(field)), 1e-7, name)

    def test_gamma_control_preserves_chromaticity_nearly(self):
        rng = np.random.default_rng(42)
        img = rng.integers(20, 240, size=(96, 96, 3), dtype=np.uint8)
        mask = np.ones(img.shape[:2], dtype=np.uint8)
        gamma = m.gamma_control(img, 0.72)
        fields = m.difference_channels(img, gamma, mask)
        self.assertLess(float(np.median(fields["chromaticity"])), 0.04)

    def test_hotspots_are_objective_and_bounded(self):
        field = np.zeros((100, 120), dtype=np.float32)
        field[20:40, 30:55] = 0.9
        field[60:80, 80:110] = 0.7
        mask = np.ones_like(field, dtype=np.uint8)
        binary, rows, threshold = m.hotspots(field, mask)
        self.assertEqual(binary.shape, field.shape)
        self.assertGreaterEqual(threshold, 0.0)
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            self.assertTrue(all(0 <= v <= 1 for v in row["bbox_norm"]))
            self.assertTrue(all(0 <= v <= 1 for v in row["centroid_norm"]))

    def test_matched_random_preserves_scale_sequence(self):
        template = [
            {"index": i, "cx": 0.5, "cy": 0.5, "scale": s}
            for i, s in enumerate([0.55, 0.4, 0.3, 0.22, 0.16] * 3)
        ]
        a = m.matched_random_trajectory("seed", template)
        b = m.matched_random_trajectory("seed", template)
        self.assertEqual(a, b)
        self.assertEqual([x["scale"] for x in a], [x["scale"] for x in template])

    def test_rect_mean_matches_numpy(self):
        a = np.arange(100, dtype=np.float32).reshape(10, 10)
        ii = m.integral(a)
        bounds = (2, 3, 8, 9)
        got = m.rect_mean(ii, bounds)
        x0, y0, x1, y1 = bounds
        expected = float(a[y0:y1, x0:x1].mean())
        self.assertAlmostEqual(got, expected, places=8)

    def test_registration_identity_pair(self):
        img = np.zeros((160, 180, 3), dtype=np.uint8)
        cv2.circle(img, (60, 70), 25, (220, 120, 50), -1)
        cv2.rectangle(img, (105, 35), (150, 125), (70, 230, 180), 3)
        registered, mask, receipt = m.register_uv_to_visible(img, img.copy())
        self.assertEqual(registered.shape, img.shape)
        self.assertEqual(mask.shape, img.shape[:2])
        self.assertGreater(receipt["overlap_fraction"], 0.8)
        self.assertGreater(receipt["edge_correlation_after"], 0.9)


if __name__ == "__main__":
    unittest.main()
