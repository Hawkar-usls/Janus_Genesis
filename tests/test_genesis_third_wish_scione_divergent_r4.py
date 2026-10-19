from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.genesis_third_wish_scione_divergent_r4 import (
    PROTOCOL, bounded_quality_proxies, load_protocol, make_case,
    produce_r4_review_files,
)
from tools.genesis_third_wish_scione_inverse_r2 import sha256


class SciOneDivergentR4Tests(unittest.TestCase):
    def test_prespecification_increases_trial_count_and_novel_tasks(self):
        p = load_protocol()
        self.assertEqual(p["runtime"]["real_model_calls"], 48)
        self.assertEqual(p["design"]["frame_replicate_trials"], 16)
        self.assertEqual(len(p["tasks"]), 4)
        self.assertFalse(p["design"]["confirmatory_generalization_claimed"])
        self.assertFalse(p["r3_blind_review"]["human_independence_claimed"])

    def test_frozen_protocol_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            modified = Path(folder) / "protocol.json"
            modified.write_bytes(PROTOCOL.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA256_MISMATCH"):
                load_protocol(modified)

    def test_all_cases_unique_and_mirror_identical_facts(self):
        protocol = load_protocol()
        seen_id = set()
        seen_label = set()
        for task_index in range(4):
            for rep in range(2):
                control, inverse = [make_case(protocol, task_index, rep, frame)
                                    for frame in range(2)]
                for item in (control, inverse):
                    self.assertNotIn(item["case_id"], seen_id)
                    self.assertNotIn(item["sentinel"], seen_label)
                    self.assertIn(protocol["tasks"][task_index]["facts"], item["body"])
                    self.assertEqual(item["body"].count(item["sentinel"]), 1)
                    self.assertLessEqual(len(item["body"]), 1200)
                    seen_id.add(item["case_id"])
                    seen_label.add(item["sentinel"])
                self.assertNotEqual(control["sentinel"], inverse["sentinel"])
        self.assertEqual(len(seen_id), 16)
        self.assertEqual(len(seen_label), 16)

    def test_quality_proxies_are_strict_bounded_lexical_not_semantics(self):
        anchors = ["clock", "cause", "control", "sample"]
        note = [{"kind": "INTERNAL_NOTE", "text": "Compare clock and sample against a control."}]
        result = bounded_quality_proxies(note, "Clock snapshot", anchors)
        self.assertEqual(result["given_task_anchor_count_in_new_text"], 3)
        self.assertEqual(result["prespecified_test_term_present"], 1)
        self.assertGreater(result["nonstopword_lexical_new_token_count"], 0)
        self.assertEqual(bounded_quality_proxies([], "", anchors)["prespecified_test_term_present"], 0)

    def test_reviewer_mapping_commitment_survives_r4_schema(self):
        item = {"kind": "INTERNAL_NOTE", "text": "Compare SCIONE-R4-SENSOR-1-CONTROL measurement",
                "first_cycle_context": "Old SCIONE-R4-SENSOR-1-CONTROL idea",
                "case_id": "SCIONE-R4-SENSOR-1-CONTROL", "domain": "SENSOR_CAUSALITY",
                "frame": "CONTROL", "branch": "PRESERVED"}
        packet, private = produce_r4_review_files([item])
        self.assertIn("r4", packet["schema"])
        self.assertIn("r4", private["schema"])
        self.assertNotIn("CONTROL", json.dumps(packet))
        self.assertNotIn("SENSOR", json.dumps(packet))
        self.assertNotIn("SCIONE-R4-", json.dumps(packet))
        self.assertTrue(packet["items"][0]["blind_id"].startswith("R4-"))
        self.assertEqual(packet["items"][0]["blind_id"], private["mapping"][0]["blind_id"])
        self.assertEqual(packet["mapping_commitment_sha256"], sha256(
            json.dumps(private, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()))
        self.assertFalse(packet["ratings_collected"])

    def test_cli_runs_directly(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root / "tools/genesis_third_wish_scione_divergent_r4.py"),
                                 "--help"], cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--mapping-output", result.stdout)


if __name__ == "__main__":
    unittest.main()
