# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import run_top100_round2_1_capability_admission_hardened as hard

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks" / "round2_1_capability_preserving_quantization_admission_v0.1.json"
CRITICAL = ROOT / "benchmarks" / "frozen_samples" / "top100_round2_fp16_critical_reference_v0.1.json"
PACK = ROOT / "benchmarks" / "frozen_samples" / "top100_round1_stratified_v0.1.json"


class Round21ProvenanceHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.critical = json.loads(CRITICAL.read_text(encoding="utf-8"))
        cls.source = hard._source_path_from_config(cls.config)
        cls.source_bytes = cls.source.read_bytes()

    def test_actual_git_blobs_are_the_frozen_identities(self) -> None:
        self.assertEqual(
            "ca27652feb3532ff52e8453dd055b608711b0d43",
            hard.git_blob_sha1(PACK),
        )
        self.assertEqual(
            "6743337b8a6357783858c71fad01720d034b63ca",
            hard.git_blob_sha1(CRITICAL),
        )
        self.assertEqual(
            "c8e5b2f07dfaa7d7e86d10794bba4543417c22d6",
            hard.git_blob_sha1(self.source),
        )

    def test_declared_provenance_matches_actual_consumed_bytes(self) -> None:
        receipt = hard.validate_provenance(
            self.config,
            self.critical,
            config_path=CONFIG,
            critical_path=CRITICAL,
            pack_path=PACK,
        )
        self.assertEqual(hard.PROVENANCE_STATUS, receipt["status"])
        self.assertTrue(receipt["receipt_fields_derived_from_verified_declarations"])
        self.assertTrue(receipt["single_snapshot_consumption"])
        self.assertTrue(receipt["verified_bytes_are_execution_bytes"])
        self.assertTrue(receipt["repository_root_independent_of_process_cwd"])
        self.assertEqual(hard.git_blob_sha1(CONFIG), receipt["observed_config_git_blob_sha1"])
        self.assertEqual(
            self.config["round2_source_report_encoded_git_blob_sha1"],
            receipt["observed_round2_source_encoded_git_blob_sha1"],
        )

    def test_frozen_round2_receipt_rederives_exact_critical_set(self) -> None:
        round2_report, identity = hard._decode_round2_source_report(
            self.config, self.critical, self.source_bytes
        )
        derivation = hard.validate_critical_derivation(
            self.config, self.critical, round2_report
        )
        self.assertEqual(4, identity["identity_channels_verified"])
        self.assertEqual(74604, identity["raw_report_byte_count"])
        self.assertEqual(
            "78fc935a146ca43b7b365fca723f3352cb4323648052f9434b2228b70454cbdc",
            identity["observed_report_json_sha256"],
        )
        self.assertEqual(hard.DERIVATION_STATUS, derivation["status"])
        self.assertEqual(21, derivation["source_fp16_record_count"])
        self.assertEqual(8, derivation["derived_pass_count"])
        self.assertEqual(
            "aa04c2befda34e6a9a27b73360c55150617d3008f1d8fe82a6b49ad93f14e97c",
            derivation["derived_canonical_sha256"],
        )
        self.assertEqual(
            [
                "gsm8k-test-0000",
                "gsm8k-test-0001",
                "gsm8k-test-0003",
                "ifeval-key-1019",
                "ifeval-key-1092",
                "truthfulqa-row-0001",
                "truthfulqa-row-0002",
                "truthfulqa-row-0004",
            ],
            derivation["derived_sample_ids"],
        )
        self.assertTrue(derivation["equals_frozen_critical_projection"])
        self.assertFalse(derivation["candidate_results_consulted"])

    def test_tampered_round2_encoded_source_is_rejected_before_derivation(self) -> None:
        bad_bytes = bytearray(self.source_bytes)
        bad_bytes[len(bad_bytes) // 2] = ord("A") if bad_bytes[len(bad_bytes) // 2] != ord("A") else ord("B")
        with self.assertRaisesRegex(ValueError, "Round-2 encoded source Git blob mismatch"):
            hard._decode_round2_source_report(
                self.config, self.critical, bytes(bad_bytes)
            )

    def test_tampered_frozen_projection_is_rejected_by_round2_source(self) -> None:
        round2_report, _ = hard._decode_round2_source_report(
            self.config, self.critical, self.source_bytes
        )
        bad = copy.deepcopy(self.critical)
        bad["critical_set"][0]["reference_output_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "derived FP16 PASS projection does not equal frozen critical_set"):
            hard.validate_critical_derivation(self.config, bad, round2_report)

    def test_tampered_config_critical_blob_is_rejected(self) -> None:
        bad = copy.deepcopy(self.config)
        bad["critical_reference_git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "critical reference blob mismatch"):
            hard.validate_provenance(
                bad,
                self.critical,
                config_path=CONFIG,
                critical_path=CRITICAL,
                pack_path=PACK,
            )

    def test_tampered_config_round1_blob_is_rejected(self) -> None:
        bad = copy.deepcopy(self.config)
        bad["round1_pack_git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "round1 pack blob mismatch"):
            hard.validate_provenance(
                bad,
                self.critical,
                config_path=CONFIG,
                critical_path=CRITICAL,
                pack_path=PACK,
            )

    def test_tampered_config_round2_source_blob_is_rejected(self) -> None:
        bad = copy.deepcopy(self.config)
        bad["round2_source_report_encoded_git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "Round-2 source blob mismatch"):
            hard.validate_provenance(
                bad,
                self.critical,
                config_path=CONFIG,
                critical_path=CRITICAL,
                pack_path=PACK,
            )

    def test_tampered_critical_source_round1_blob_is_rejected(self) -> None:
        bad = copy.deepcopy(self.critical)
        bad["source"]["round1_pack_git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "critical source round1 pack blob mismatch"):
            hard.validate_provenance(
                self.config,
                bad,
                config_path=CONFIG,
                critical_path=CRITICAL,
                pack_path=PACK,
            )

    def test_path_substitution_is_rejected(self) -> None:
        bad = copy.deepcopy(self.config)
        bad["round1_pack"] = "benchmarks/frozen_samples/not-the-pack.json"
        with self.assertRaisesRegex(ValueError, "round1_pack path mismatch"):
            hard.validate_provenance(
                bad,
                self.critical,
                config_path=CONFIG,
                critical_path=CRITICAL,
                pack_path=PACK,
            )

    def test_round2_source_path_traversal_is_rejected(self) -> None:
        bad = copy.deepcopy(self.config)
        bad["round2_source_report_encoded"] = "../outside-receipt.b64"
        with self.assertRaisesRegex(ValueError, "repository-relative and non-traversing"):
            hard._source_path_from_config(bad)

    def test_absolute_repository_inputs_are_stable_outside_repository_cwd(self) -> None:
        old_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                receipt = hard.validate_provenance(
                    self.config,
                    self.critical,
                    config_path=CONFIG,
                    critical_path=CRITICAL,
                    pack_path=PACK,
                )
            finally:
                os.chdir(old_cwd)
        self.assertEqual(
            self.config["critical_reference"],
            receipt["critical_reference_path"],
        )
        self.assertEqual(self.config["round1_pack"], receipt["round1_pack_path"])
        self.assertEqual(
            self.config["round2_source_report_encoded"],
            receipt["round2_source_report_encoded_path"],
        )
        self.assertTrue(receipt["repository_root_independent_of_process_cwd"])

    def test_main_repo_relative_cli_inputs_are_stable_outside_repository_cwd(self) -> None:
        argv = [
            "--config", "benchmarks/round2_1_capability_preserving_quantization_admission_v0.1.json",
            "--critical-reference", "benchmarks/frozen_samples/top100_round2_fp16_critical_reference_v0.1.json",
            "--pack", "benchmarks/frozen_samples/top100_round1_stratified_v0.1.json",
            "--endpoint", "http://127.0.0.1:11434",
            "--docker-image", "python:3.11-alpine",
            "--timeout", "1",
        ]
        fake_report = {"schema": "unit-test-report"}
        old_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with mock.patch.object(
                    hard.gate,
                    "main",
                    side_effect=AssertionError("historical CLI must not be called"),
                ) as old_main, mock.patch.object(
                    hard.gate,
                    "execute",
                    return_value=fake_report.copy(),
                ) as execute, io.StringIO() as out, contextlib.redirect_stdout(out):
                    rc = hard.main(argv)
                    payload = json.loads(out.getvalue())
            finally:
                os.chdir(old_cwd)

        self.assertEqual(0, rc)
        old_main.assert_not_called()
        execute.assert_called_once()
        p = payload["provenance_verification"]
        self.assertEqual(
            "benchmarks/round2_1_capability_preserving_quantization_admission_v0.1.json",
            p["config_path"],
        )
        self.assertEqual(self.config["critical_reference"], p["critical_reference_path"])
        self.assertEqual(self.config["round1_pack"], p["round1_pack_path"])
        self.assertTrue(p["repository_root_independent_of_process_cwd"])
        self.assertTrue(p["single_snapshot_consumption"])
        self.assertTrue(p["verified_bytes_are_execution_bytes"])

    def test_main_uses_direct_execute_not_historical_rereading_cli(self) -> None:
        argv = [
            "--config", str(CONFIG),
            "--critical-reference", str(CRITICAL),
            "--pack", str(PACK),
            "--endpoint", "http://127.0.0.1:11434",
            "--docker-image", "python:3.11-alpine",
            "--timeout", "1",
        ]
        fake_report = {"schema": "unit-test-report"}
        with mock.patch.object(
            hard.gate,
            "main",
            side_effect=AssertionError("historical CLI must not be called"),
        ) as old_main, mock.patch.object(
            hard.gate,
            "execute",
            return_value=fake_report.copy(),
        ) as execute, io.StringIO() as out, contextlib.redirect_stdout(out):
            rc = hard.main(argv)
            payload = json.loads(out.getvalue())

        self.assertEqual(0, rc)
        old_main.assert_not_called()
        execute.assert_called_once()
        p = payload["provenance_verification"]
        self.assertEqual(hard.PROVENANCE_STATUS, p["status"])
        self.assertTrue(p["single_snapshot_consumption"])
        self.assertTrue(p["verified_bytes_are_execution_bytes"])
        self.assertTrue(p["repository_root_independent_of_process_cwd"])
        self.assertEqual(hard.DERIVATION_STATUS, p["critical_set_derivation"]["status"])
        self.assertEqual(8, p["critical_set_derivation"]["derived_pass_count"])
        self.assertEqual(4, p["round2_source_identity"]["identity_channels_verified"])


if __name__ == "__main__":
    unittest.main()