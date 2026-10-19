from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.genesis_third_wish_scione_causal_r3 import (
    PROTOCOL_PATH, ablate_visible_notes, load_protocol, produce_review_files,
    redact_review_text,
)
from tools.genesis_third_wish_scione_inverse_r2 import observe_internal_artifacts


class SciOneCausalR3Tests(unittest.TestCase):
    def test_frozen_post_hoc_contract_and_authority(self):
        p = load_protocol()
        self.assertEqual(p["study"]["expected_model_calls"], 18)
        self.assertEqual(len(p["study"]["domains"]), 3)
        self.assertIn("POST_HOC", p["selection_bias_disclosure"])
        self.assertEqual(p["authority"]["external_effect_grants_delta"], 0)
        self.assertFalse(p["blind_review"]["blinded_human_semantic_advantage_proven"])

    def test_protocol_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fake.json"
            path.write_bytes(PROTOCOL_PATH.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA256_MISMATCH"):
                load_protocol(path)

    def test_ablation_moves_only_internal_json_keeps_journal_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for room in ("workshop", "garden", "memory/reflections", "memory/bookmarks",
                         "state", "archive", "memory"):
                (root / room).mkdir(parents=True, exist_ok=True)
            (root / "memory/journal.jsonl").write_text('{"event":"kept"}\n')
            (root / "state/resident.json").write_text('{"resident":"JANUS"}')
            (root / "workshop/x.json").write_text(json.dumps({"note": "AMBER-TEST-12"}))
            (root / "memory/reflections/r.json").write_text(json.dumps({"note": "A private reflection"}))
            prior = observe_internal_artifacts(root, "AMBER-TEST-12")
            receipt = ablate_visible_notes(root, prior)
            self.assertEqual(receipt["moved_count"], 1)
            self.assertFalse((root / "workshop/x.json").exists())
            self.assertTrue((root / "archive/r3_ablated/workshop/x.json").exists())
            self.assertTrue((root / "memory/reflections/r.json").exists())
            self.assertIn("kept", (root / "memory/journal.jsonl").read_text())
            self.assertIn("JANUS", (root / "state/resident.json").read_text())
            with self.assertRaisesRegex(ValueError, "PRE_FORK_ARTIFACT_CHANGED"):
                ablate_visible_notes(root, prior)

    def test_ablation_refuses_modified_first_cycle_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for room in ("workshop", "garden", "memory/reflections", "memory/bookmarks", "archive"):
                (root / room).mkdir(parents=True)
            path = root / "garden/x.json"
            path.write_text('{"note":"one"}')
            prior = observe_internal_artifacts(root, "none")
            path.write_text('{"note":"two"}')
            with self.assertRaisesRegex(ValueError, "PRE_FORK_ARTIFACT_CHANGED"):
                ablate_visible_notes(root, prior)

    def test_sanitizer_removes_known_canaries_secrets_identifiers(self):
        source = ("Look at AMBER-FOO-92 and SCIONE-R2-REVIEW-INVERSE; "
                  "email me@example.com, browse https://example.com/track "
                  "with ghp_1234567890abcdef. Another thought remains.")
        text = redact_review_text(source, sentinel="AMBER-FOO-92", case_id="SCIONE-R2-REVIEW-INVERSE")
        for forbidden in ("AMBER-FOO-92", "SCIONE-R2-REVIEW-INVERSE", "me@example.com",
                          "https://", "ghp_1234567890abcdef"):
            self.assertNotIn(forbidden, text)
        self.assertIn("Another thought remains", text)
        self.assertLessEqual(len(text), 1200)

    def test_review_packet_omits_arms_and_mapping_has_commitment(self):
        item = {"kind": "INTERNAL_NOTE", "text": "An alternative test", "first_cycle_context": "Idea",
                "case_id": "SCIONE-R2-STRATEGY-INVERSE", "domain": "UNDESIRED_STRATEGY",
                "frame": "INVERSE", "branch": "PRESERVED"}
        packet, private = produce_review_files([item])
        self.assertEqual(packet["items"][0]["text"], "An alternative test")
        self.assertEqual(packet["items"][0]["first_cycle_context"], "Idea")
        self.assertNotIn("PRESERVED", json.dumps(packet))
        self.assertNotIn("STRATEGY", json.dumps(packet))
        self.assertEqual(packet["items"][0]["blind_id"], private["mapping"][0]["blind_id"])
        from tools.genesis_third_wish_scione_inverse_r2 import sha256
        self.assertEqual(packet["mapping_commitment_sha256"], sha256(
            json.dumps(private, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()))

    def test_cli_direct_invocation(self):
        root = Path(__file__).resolve().parents[1]
        res = subprocess.run([sys.executable, str(root / "tools/genesis_third_wish_scione_causal_r3.py"),
                              "--help"], cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("--blind-output", res.stdout)


if __name__ == "__main__":
    unittest.main()
