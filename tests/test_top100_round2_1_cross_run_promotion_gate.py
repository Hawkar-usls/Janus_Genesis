# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools import run_top100_round2_1_cross_run_promotion_gate as gate

CONFIG_PATH = gate.REPOSITORY_ROOT / "benchmarks/round2_1_cross_run_promotion_gate_v0.1.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class CrossRunPromotionGateTests(unittest.TestCase):
    def test_clean_evidence_blocks_q8_and_preserves_fp16(self):
        receipt = gate.evaluate(load_config())
        self.assertEqual(receipt["receipt_count"], 2)
        self.assertEqual(receipt["candidate_positive_receipt_count"], 1)
        self.assertEqual(receipt["candidate_negative_receipt_count"], 1)
        self.assertTrue(receipt["cross_run_status_divergence_observed"])
        self.assertTrue(receipt["cross_run_output_divergence_observed"])
        by_run = {row["workflow_run_id"]: row for row in receipt["receipts"]}
        self.assertEqual(by_run[31349156794]["candidate_pass_trials"], 20)
        self.assertEqual(by_run[31349156794]["candidate_nonpass_trials"], 4)
        self.assertEqual(by_run[31352475058]["candidate_pass_trials"], 24)
        self.assertEqual(by_run[31352475058]["candidate_nonpass_trials"], 0)
        self.assertFalse(receipt["promotion"]["authoritative_runtime_promoted"])
        self.assertEqual(receipt["promotion"]["selected_runtime_representation"], "FP16")
        self.assertEqual(receipt["promotion"]["decision"], "BLOCKED_BY_HISTORICAL_NEGATIVE_EVIDENCE")
        self.assertFalse(receipt["promotion"]["fresh_positive_compensates_historical_negative"])

    def test_genesis_negative_anchor_cannot_be_removed(self):
        cfg = load_config()
        evidence, _ = gate.load_evidence(cfg)
        evidence = copy.deepcopy(evidence)
        evidence["receipts"] = [r for r in evidence["receipts"] if r["source"]["workflow_run_id"] != 31349156794]
        with tempfile.TemporaryDirectory(dir=gate.REPOSITORY_ROOT / "benchmarks/frozen_receipts") as tmp:
            path = Path(tmp) / "missing-anchor.json"
            raw = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            cfg["evidence_path"] = path.relative_to(gate.REPOSITORY_ROOT).as_posix()
            cfg["evidence_git_blob_sha1"] = gate.git_blob_sha1_bytes(raw)
            import hashlib
            cfg["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, "cannot be forgotten"):
                gate.evaluate(cfg)

    def test_negative_anchor_config_is_immutable(self):
        cfg = load_config()
        cfg["required_genesis_negative_anchor"]["report_json_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "removed or altered"):
            gate.evaluate(cfg)

    def test_evidence_blob_tamper_fails_closed(self):
        cfg = load_config()
        path = gate._repo_path(cfg["evidence_path"])
        raw = bytearray(path.read_bytes())
        raw[0] ^= 1
        with tempfile.TemporaryDirectory(dir=gate.REPOSITORY_ROOT / "benchmarks/frozen_receipts") as tmp:
            tampered = Path(tmp) / "tampered.json"
            tampered.write_bytes(raw)
            cfg["evidence_path"] = tampered.relative_to(gate.REPOSITORY_ROOT).as_posix()
            with self.assertRaisesRegex(ValueError, "Git blob mismatch"):
                gate.evaluate(cfg)

    def test_source_report_encoded_tamper_fails_closed(self):
        cfg = load_config()
        source = cfg["source_reports"][0]
        path = gate._repo_path(source["encoded_path"])
        raw = bytearray(path.read_bytes())
        raw[10] = ord("A") if raw[10] != ord("A") else ord("B")
        with tempfile.TemporaryDirectory(dir=gate.REPOSITORY_ROOT / "benchmarks/frozen_receipts") as tmp:
            tampered = Path(tmp) / "tampered-source.json.gz.b64"
            tampered.write_bytes(raw)
            source["encoded_path"] = tampered.relative_to(gate.REPOSITORY_ROOT).as_posix()
            with self.assertRaisesRegex(ValueError, "encoded Git blob mismatch"):
                gate.evaluate(cfg)

    def test_rebound_compact_fabrication_is_rejected_by_exact_source_derivation(self):
        cfg = load_config()
        evidence, _ = gate.load_evidence(cfg)
        evidence = copy.deepcopy(evidence)
        historical = next(r for r in evidence["receipts"] if r["source"]["workflow_run_id"] == 31349156794)
        historical["candidate_records"][1]["status"] = "PASS"
        historical["candidate_assessment"]["pass_trials"] = 21
        historical["candidate_assessment"]["nonpass_trials"] = 3
        with tempfile.TemporaryDirectory(dir=gate.REPOSITORY_ROOT / "benchmarks/frozen_receipts") as tmp:
            path = Path(tmp) / "fabricated-but-rebound.json"
            raw = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            cfg["evidence_path"] = path.relative_to(gate.REPOSITORY_ROOT).as_posix()
            cfg["evidence_git_blob_sha1"] = gate.git_blob_sha1_bytes(raw)
            import hashlib
            cfg["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, "does not equal projection derived from exact source reports"):
                gate.evaluate(cfg)

    def test_different_spec_fingerprint_is_rejected(self):
        cfg = load_config()
        evidence, _ = gate.load_evidence(cfg)
        evidence = copy.deepcopy(evidence)
        evidence["experimental_spec"]["inference"]["seed"] = 1139
        with tempfile.TemporaryDirectory(dir=gate.REPOSITORY_ROOT / "benchmarks/frozen_receipts") as tmp:
            path = Path(tmp) / "different-spec.json"
            raw = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            cfg["evidence_path"] = path.relative_to(gate.REPOSITORY_ROOT).as_posix()
            cfg["evidence_git_blob_sha1"] = gate.git_blob_sha1_bytes(raw)
            import hashlib
            cfg["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, "embedded experimental spec"):
                gate.evaluate(cfg)

    def test_independence_requires_distinct_runs(self):
        cfg = load_config()
        evidence, _ = gate.load_evidence(cfg)
        evidence = copy.deepcopy(evidence)
        evidence["receipts"].append(copy.deepcopy(evidence["receipts"][1]))
        with tempfile.TemporaryDirectory(dir=gate.REPOSITORY_ROOT / "benchmarks/frozen_receipts") as tmp:
            path = Path(tmp) / "duplicate-run.json"
            raw = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            cfg["evidence_path"] = path.relative_to(gate.REPOSITORY_ROOT).as_posix()
            cfg["evidence_git_blob_sha1"] = gate.git_blob_sha1_bytes(raw)
            import hashlib
            cfg["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, "run IDs must be independent"):
                gate.evaluate(cfg)

    def test_promotion_rule_never_averages_away_negative(self):
        self.assertEqual(
            gate.decide_promotion(negative_receipt_count=1, positive_receipt_count=100, minimum_positive_receipts=2),
            (False, "BLOCKED_BY_HISTORICAL_NEGATIVE_EVIDENCE"),
        )
        self.assertEqual(
            gate.decide_promotion(negative_receipt_count=0, positive_receipt_count=1, minimum_positive_receipts=2),
            (False, "BLOCKED_INSUFFICIENT_INDEPENDENT_ALL_PASS_RECEIPTS"),
        )
        self.assertEqual(
            gate.decide_promotion(negative_receipt_count=0, positive_receipt_count=2, minimum_positive_receipts=2),
            (True, "AUTHORITATIVE_RUNTIME_PROMOTED"),
        )


if __name__ == "__main__":
    unittest.main()
