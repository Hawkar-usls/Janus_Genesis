"""Real source bounded program synthesis, held-out proof and tamper tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.janus_nexus_real_source_self_repair_v1 import (
    TARGET,OLD,CANDIDATES,RepairHold,_read,_write,
    candidate_text,choose,verify,sha
)

REAL=Path(__file__).resolve().parents[1]/TARGET


class RealSourceRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=REAL.read_bytes()
        assert OLD in cls.original.decode("utf-8"),"expected original real flaw moved"

    def setup_candidate(self,root):
        receipt,source,diff=choose(REAL)
        candidate=root/"patched.py"
        candidate.write_bytes(source)
        return candidate,receipt,diff

    def test_proven_real_bug_and_only_one_training_winner(self):
        receipt,patched,diff=choose(REAL)
        self.assertEqual(receipt["selected_candidate_id"],"ALL_SYMLINK_ANCESTORS")
        self.assertEqual(receipt["baseline_training_passed"],3)
        self.assertEqual(receipt["baseline_training_total"],5)
        self.assertEqual(receipt["candidate_scores"]["ALL_SYMLINK_ANCESTORS"],5)
        self.assertLess(receipt["candidate_scores"]["DIRECT_PARENT_ONLY"],5)
        self.assertIn(b"not any(ancestor.is_symlink()",patched)
        self.assertIn(b"@@",diff)
        self.assertFalse(receipt["neural_model_generated_this_code"])
        self.assertFalse(receipt["source_writeback"])

    def test_real_independent_holdout_and_authority_ceiling(self):
        with tempfile.TemporaryDirectory() as d:
            candidate,receipt,diff=self.setup_candidate(Path(d))
            out=verify(REAL,candidate,receipt,diff)
            self.assertEqual(out["status"],
              "PASS_REAL_FILE_BOUND_RULE_REPAIR_INDEPENDENT_HELDOUT")
            self.assertEqual(out["candidate_holdout_passed"],out["heldout_total"])
            self.assertLess(out["source_holdout_passed"],out["heldout_total"])
            self.assertFalse(out["neural_model_self_patch_proven"])
            self.assertFalse(out["production_main_modified"])
            self.assertFalse(out["full_issue_162_acceptance"])

    def test_tampered_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            candidate,receipt,diff=self.setup_candidate(Path(d))
            candidate.write_bytes(candidate.read_bytes()+b"\n# unauthorized extra code\n")
            with self.assertRaisesRegex(RepairHold,"CANDIDATE_NOT_WHITELISTED_TRANSFORM"):
                verify(REAL,candidate,receipt,diff)

    def test_forged_baseline_digest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            candidate,receipt,diff=self.setup_candidate(Path(d))
            receipt["original_source_sha256"]="0"*64
            with self.assertRaisesRegex(RepairHold,"CANDIDATE_HASH_OR_DIFF_MISMATCH"):
                verify(REAL,candidate,receipt,diff)

    def test_claim_neural_model_generated_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            candidate,receipt,diff=self.setup_candidate(Path(d))
            receipt["neural_model_generated_this_code"]=True
            with self.assertRaisesRegex(RepairHold,"SELECTION_RECEIPT_NOT_TRUSTED"):
                verify(REAL,candidate,receipt,diff)

    def test_privilege_claim_in_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            candidate,receipt,diff=self.setup_candidate(Path(d))
            receipt["authority_delta"]=1
            with self.assertRaisesRegex(RepairHold,"SELECTION_RECEIPT_NOT_TRUSTED"):
                verify(REAL,candidate,receipt,diff)

    def test_diff_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            candidate,receipt,diff=self.setup_candidate(Path(d))
            with self.assertRaisesRegex(RepairHold,"CANDIDATE_HASH_OR_DIFF_MISMATCH"):
                verify(REAL,candidate,receipt,diff+b"malicious")

    def test_static_edit_cannot_touch_multiple_hunks(self):
        source=self.original.decode("utf-8")
        with self.assertRaisesRegex(RepairHold,"EXPECTED_REAL_SOURCE_PREIMAGE_MISSING"):
            candidate_text(source+OLD,"ALL_SYMLINK_ANCESTORS")
        with self.assertRaisesRegex(RepairHold,"REPAIR_RULE_NOT_ADMITTED"):
            candidate_text(source,"RUN_SHELL")
        self.assertEqual(candidate_text(source,"ALL_SYMLINK_ANCESTORS").
                         replace(CANDIDATES["ALL_SYMLINK_ANCESTORS"],OLD),
                         source)

    def test_immutable_output_and_symlink_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"one"
            _write(p,b"data")
            with self.assertRaisesRegex(RepairHold,"OUTPUT_ALREADY_PRESENT"):
                _write(p,b"overwritten")
            alias=root/"shortcut"
            alias.symlink_to(p)
            with self.assertRaisesRegex(RepairHold,"SOURCE_PATH_NOT_REGULAR"):
                _read(alias)

    def test_original_real_source_remains_byte_identical(self):
        self.assertEqual(sha(REAL.read_bytes()),sha(self.original))
        self.assertTrue(OLD in REAL.read_text())


if __name__=="__main__":
    unittest.main()
