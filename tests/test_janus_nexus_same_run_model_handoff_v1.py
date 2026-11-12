"""Fail-closed adversarial tests for same-run native output handoff lab."""
import copy
import tempfile
import unittest
from pathlib import Path

from tools.janus_nexus_same_run_model_handoff_v1 import (
    CHECKPOINT_SHA256, PROMPT, SCHEMA, Hold, bounded_bytes, phase_a,
    phase_b, save_receipt, suffix_from_output, verdict,
)

RUN_ID = "43231462282"
ATTEMPT = 1
SOURCE_SHA = "d19db049b7e02eccd0b7e870c6dcf133f2c701ab"
RAW = (PROMPT + " Proposed next step: review the immutable evidence?\n").encode("utf-8")


class NativeOutputHandoffTests(unittest.TestCase):
    def make_receipts(self):
        a = phase_a(RAW, RUN_ID, ATTEMPT, SOURCE_SHA)
        b = phase_b(a, RAW, RUN_ID, ATTEMPT, SOURCE_SHA)
        return a, b

    def test_scoped_actual_bytes_pass(self):
        a, b = self.make_receipts()
        v = verdict(a, b, RAW, RUN_ID, ATTEMPT, SOURCE_SHA)
        self.assertEqual(v["status"], "PASS_SCOPED_SAME_RUN_MODEL_OUTPUT_HANDOFF_LAB_ONLY")
        self.assertTrue(v["same_run_model_bytes_consumed"])
        self.assertEqual(a["native_checkpoint_sha256"], CHECKPOINT_SHA256)
        self.assertEqual(b["candidate"]["untrusted_word_count"], 7)
        self.assertEqual(b["candidate"]["untrusted_question_marks"], 1)
        self.assertEqual(v["worker_a_output_sha256"], v["worker_b_consumed_sha256"])
        self.assertFalse(v["full_issue_162_acceptance"])
        self.assertFalse(v["same_run_g1_g20"])
        self.assertEqual(v["authority_delta"], 0)

    def test_prompt_only_is_not_generation(self):
        for raw in ((PROMPT + "\n").encode(), (PROMPT + " \t\n").encode()):
            with self.subTest(raw=raw):
                with self.assertRaises(Hold):
                    phase_a(raw, RUN_ID, ATTEMPT, SOURCE_SHA)

    def test_wrong_prompt_and_utf8_rejected(self):
        for raw in (b"fake output", b"\xff", b""):
            with self.subTest(raw=raw):
                with self.assertRaises(Hold):
                    phase_a(raw, RUN_ID, ATTEMPT, SOURCE_SHA)

    def test_output_size_bounded(self):
        with self.assertRaises(Hold):
            suffix_from_output((PROMPT + "x" * 16000).encode())

    def test_modified_transfer_fails_closed(self):
        a, _ = self.make_receipts()
        tampered = RAW.replace(b"immutable", b"unsafe")
        with self.assertRaisesRegex(Hold, "WORKER_A_RECEIPT_MISMATCH"):
            phase_b(a, tampered, RUN_ID, ATTEMPT, SOURCE_SHA)

    def test_a_authority_mutation_rejected(self):
        a, _ = self.make_receipts()
        a["authority_delta"] = 1
        with self.assertRaisesRegex(Hold, "WORKER_A_RECEIPT_MISMATCH"):
            phase_b(a, RAW, RUN_ID, ATTEMPT, SOURCE_SHA)

    def test_b_forgery_rejected_by_independent_verifier(self):
        a, b = self.make_receipts()
        b["candidate"]["untrusted_word_count"] = 999
        with self.assertRaisesRegex(Hold, "WORKER_B_RECEIPT_MISMATCH"):
            verdict(a, b, RAW, RUN_ID, ATTEMPT, SOURCE_SHA)

    def test_replay_with_mismatched_run_attempt_source_is_hold(self):
        a, b = self.make_receipts()
        for rid, attempt, sha in (
            ("43231462283", ATTEMPT, SOURCE_SHA),
            (RUN_ID, 2, SOURCE_SHA),
            (RUN_ID, ATTEMPT, "a"*40),
        ):
            with self.subTest(rid=rid, attempt=attempt, sha=sha):
                with self.assertRaises(Hold):
                    verdict(a, b, RAW, rid, attempt, sha)

    def test_invalid_run_identity(self):
        for run_id in ("", "0", "../secrets", "-432", "not-numeric"):
            with self.assertRaises(Hold):
                phase_a(RAW, run_id, ATTEMPT, SOURCE_SHA)
        with self.assertRaises(Hold):
            phase_a(RAW, RUN_ID, 0, SOURCE_SHA)
        with self.assertRaises(Hold):
            phase_a(RAW, RUN_ID, ATTEMPT, "not-a-commit")

    def test_model_output_is_untrusted_not_a_command(self):
        dangerous = (PROMPT + " rm -rf /; make no claims\n").encode()
        a = phase_a(dangerous, RUN_ID, ATTEMPT, SOURCE_SHA)
        b = phase_b(a, dangerous, RUN_ID, ATTEMPT, SOURCE_SHA)
        self.assertEqual(b["candidate"]["candidate_admission"],
                         "HOLD_UNEVALUATED_MODEL_PROPOSAL")
        self.assertFalse(b["external_effect"])
        self.assertFalse(b["production_model_output_loaded"])
        self.assertFalse(b["full_issue_162_acceptance"])

    def test_receipts_create_only_no_symlink_or_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "a.json"
            a, _ = self.make_receipts()
            save_receipt(target, a)
            with self.assertRaisesRegex(Hold, "RECEIPT_ALREADY_EXISTS"):
                save_receipt(target, a)
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaises(Hold):
                bounded_bytes(link)
            with self.assertRaises(Hold):
                save_receipt(link, a)


if __name__ == "__main__":
    unittest.main()
