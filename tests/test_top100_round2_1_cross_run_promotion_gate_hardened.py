# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path

from tools import run_top100_round2_1_cross_run_promotion_gate as core
from tools import run_top100_round2_1_cross_run_promotion_gate_hardened as hard

CONFIG_PATH = core.REPOSITORY_ROOT / "benchmarks/round2_1_cross_run_promotion_gate_v0.1.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def authenticated_metadata(*, authoritative: bool = False):
    cfg = load_config()
    rows = [
        {
            "workflow_run_id": 31349156794,
            "run_head_sha": "81898c0f4ee09d1b530e3cc1c38ecdd993d4d9c9",
            "run_status": "completed",
            "run_conclusion": "success",
            "run_event": "pull_request",
            "artifact_id": 9048707870,
            "artifact_name": "janus-top100-round2-1-capability-admission",
            "artifact_digest": "sha256:1561a538076b8907326353f71a0e644987d77484e11f760f114fa029062daff6",
            "artifact_expired": False,
            "artifact_size_in_bytes": 12454,
            "artifact_workflow_run_id": 31349156794,
            "artifact_workflow_head_sha": "81898c0f4ee09d1b530e3cc1c38ecdd993d4d9c9",
        },
        {
            "workflow_run_id": 31352475058,
            "run_head_sha": "692f88dd2bccf211487e9c675a981fc530d81095",
            "run_status": "completed",
            "run_conclusion": "success",
            "run_event": "pull_request",
            "artifact_id": 9049984941,
            "artifact_name": "janus-top100-round2-1-capability-admission",
            "artifact_digest": "sha256:0f85f51a0114ca7f2dd8d14f0244db63c63e3e7bc23b10aae79baf60da631213",
            "artifact_expired": False,
            "artifact_size_in_bytes": 13338,
            "artifact_workflow_run_id": 31352475058,
            "artifact_workflow_head_sha": "692f88dd2bccf211487e9c675a981fc530d81095",
        },
    ]
    if authoritative:
        for row, source in zip(rows, cfg["source_reports"]):
            row.update({
                "artifact_archive_sha256": str(source["artifact_digest"]).removeprefix("sha256:"),
                "artifact_report_member": "report.json",
                "artifact_report_json_sha256": source["report_json_sha256"],
                "artifact_report_raw_git_blob_sha1": source["report_raw_git_blob_sha1"],
                "artifact_report_byte_count": 1,
                "artifact_report_matches_frozen_source": True,
            })
    return {
        "schema": "janus.genesis.github_actions_source_authentication.v2",
        "repository": "Hawkar-usls/Janus_Genesis",
        "fetched_live": authoritative,
        "artifact_payloads_authenticated": authoritative,
        "authentication_mode": (
            hard.LIVE_AUTHENTICATION_MODE if authoritative else hard.FIXTURE_AUTHENTICATION_MODE
        ),
        "sources": rows,
    }


def reconstructed_raw_report(source):
    encoded = (core.REPOSITORY_ROOT / source["encoded_path"]).read_bytes()
    compressed = base64.b64decode(encoded.strip(), validate=True)
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == source["report_json_sha256"]
    assert core.git_blob_sha1_bytes(raw) == source["report_raw_git_blob_sha1"]
    return raw


class HardenedCrossRunPromotionTests(unittest.TestCase):
    def test_caller_supplied_fixture_is_explicitly_non_authoritative(self):
        receipt = hard.evaluate_hardened(load_config(), authenticated_metadata())
        self.assertEqual(hard.HARDENED_SCHEMA, receipt["schema"])
        self.assertFalse(receipt["independence_authenticated_against_github_actions"])
        self.assertTrue(receipt["non_authoritative_fixture"])
        self.assertFalse(receipt["promotion_preconditions"]["github_actions_run_artifact_authentication"])
        self.assertFalse(receipt["promotion_preconditions"]["live_artifact_report_bytes_equal_frozen_reports"])
        self.assertFalse(receipt["promotion"]["authoritative_runtime_promoted"])
        self.assertEqual("FP16", receipt["promotion"]["selected_runtime_representation"])
        self.assertEqual("BLOCKED_NON_AUTHORITATIVE_METADATA_FIXTURE", receipt["promotion"]["decision"])

    def test_authoritative_metadata_requires_artifact_report_binding(self):
        receipt = hard.validate_authenticated_independence(
            load_config(), authenticated_metadata(authoritative=True)
        )
        self.assertEqual(
            "GITHUB_ACTIONS_SOURCE_AND_ARTIFACT_BYTES_AUTHENTICATED",
            receipt["status"],
        )
        self.assertTrue(receipt["live_artifact_payload_binding"])
        self.assertEqual(2, receipt["source_count"])
        self.assertTrue(receipt["distinct_workflow_run_ids"])
        self.assertTrue(receipt["distinct_artifact_ids"])
        self.assertTrue(receipt["distinct_raw_report_sha256"])

    def test_artifact_report_identity_binds_exact_frozen_report_bytes(self):
        source = copy.deepcopy(load_config()["source_reports"][0])
        raw = reconstructed_raw_report(source)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.json", raw)
        archive_bytes = buffer.getvalue()
        source["artifact_digest"] = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
        identity = hard._artifact_report_identity(archive_bytes, source=source)
        self.assertEqual(source["report_json_sha256"], identity["artifact_report_json_sha256"])
        self.assertEqual(source["report_raw_git_blob_sha1"], identity["artifact_report_raw_git_blob_sha1"])
        self.assertTrue(identity["artifact_report_matches_frozen_source"])

    def test_artifact_report_identity_rejects_different_report_bytes(self):
        source = copy.deepcopy(load_config()["source_reports"][0])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.json", b'{"different":true}\n')
        archive_bytes = buffer.getvalue()
        source["artifact_digest"] = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
        with self.assertRaisesRegex(ValueError, "does not equal frozen report SHA-256"):
            hard._artifact_report_identity(archive_bytes, source=source)

    def test_parser_has_no_local_github_metadata_authority_option(self):
        with self.assertRaises(SystemExit):
            hard._parser().parse_args([
                "--config",
                "benchmarks/round2_1_cross_run_promotion_gate_v0.1.json",
                "--github-metadata",
                "fixture.json",
            ])

    def test_substituted_unique_trial_key_is_rejected(self):
        cfg = load_config()
        evidence, _ = core.load_evidence(cfg)
        profile = hard.load_frozen_critical_profile(cfg)
        bad = copy.deepcopy(evidence)
        bad["receipts"][0]["candidate_records"][0]["sample_id"] = "not-a-frozen-critical-sample"
        with self.assertRaisesRegex(ValueError, "do not equal frozen critical sample/replay profile"):
            hard.validate_exact_critical_trial_profiles(bad, profile)

    def test_missing_replay_key_replaced_by_another_unique_key_is_rejected(self):
        cfg = load_config()
        evidence, _ = core.load_evidence(cfg)
        profile = hard.load_frozen_critical_profile(cfg)
        bad = copy.deepcopy(evidence)
        row = bad["receipts"][1]["candidate_records"][0]
        row["replay"] = 99
        with self.assertRaisesRegex(ValueError, "do not equal frozen critical sample/replay profile"):
            hard.validate_exact_critical_trial_profiles(bad, profile)

    def test_fake_run_head_is_rejected_by_authenticated_metadata(self):
        metadata = authenticated_metadata(authoritative=True)
        metadata["sources"][1]["run_head_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "head SHA is not authenticated"):
            hard.validate_authenticated_independence(load_config(), metadata)

    def test_fake_artifact_digest_is_rejected_by_authenticated_metadata(self):
        metadata = authenticated_metadata(authoritative=True)
        metadata["sources"][0]["artifact_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "artifact digest is not authenticated"):
            hard.validate_authenticated_independence(load_config(), metadata)

    def test_fake_artifact_report_sha_is_rejected(self):
        metadata = authenticated_metadata(authoritative=True)
        metadata["sources"][0]["artifact_report_json_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "artifact report SHA-256"):
            hard.validate_authenticated_independence(load_config(), metadata)

    def test_artifact_must_be_bound_to_same_workflow_run(self):
        metadata = authenticated_metadata(authoritative=True)
        metadata["sources"][0]["artifact_workflow_run_id"] = 31352475058
        with self.assertRaisesRegex(ValueError, "artifact is not bound"):
            hard.validate_authenticated_independence(load_config(), metadata)

    def test_duplicate_raw_report_identity_cannot_count_as_independent(self):
        cfg = load_config()
        cfg["source_reports"][1]["report_json_sha256"] = cfg["source_reports"][0]["report_json_sha256"]
        with self.assertRaisesRegex(ValueError, "reuse report_json_sha256"):
            hard.validate_authenticated_independence(cfg, authenticated_metadata(authoritative=True))

    def test_duplicate_artifact_identity_cannot_count_as_independent(self):
        cfg = load_config()
        cfg["source_reports"][1]["artifact_id"] = cfg["source_reports"][0]["artifact_id"]
        metadata = authenticated_metadata(authoritative=True)
        metadata["sources"][1]["artifact_id"] = cfg["source_reports"][0]["artifact_id"]
        with self.assertRaisesRegex(ValueError, "reuse artifact_id"):
            hard.validate_authenticated_independence(cfg, metadata)


if __name__ == "__main__":
    unittest.main()
