"""Regression proof of the real bounded patch, on BOTH baseline and fixed trees.

The tests never demand a vulnerability remain in production. The frozen
preimage is reconstructed only after validating an exact source hash against
the originally independently measured code. Nothing is trusted merely because
it has the expected patch string.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from tools.janus_nexus_real_source_self_repair_v1 import (
    TARGET,OLD,CANDIDATES,RepairHold,_read,_write,
    candidate_text,choose,verify,sha,run_tests,
)

REAL=Path(__file__).resolve().parents[1]/TARGET
SOURCE_PREIMAGE_SHA256="b631abd9441e78c50b8053cfdb116b6105a1ce66d4f244e2fa0e24bd3f149844"
CERTIFIED_PATCH_SHA256="d75b0e3dfdb81101705199e4d563268f504281d6cd5ccc318d418353c7eed7ea"
CERTIFIED_REPLACEMENT=CANDIDATES["ALL_SYMLINK_ANCESTORS"]


class RealSourceRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current=REAL.read_bytes()
        current=cls.current.decode("utf-8")
        if current.count(OLD)==1 and CERTIFIED_REPLACEMENT not in current:
            cls.original=cls.current
        else:
            # A fixed candidate must differ from the certified original in
            # exactly this one authorized source guard hunk.
            assert current.count(CERTIFIED_REPLACEMENT)==1
            cls.original=current.replace(CERTIFIED_REPLACEMENT,OLD).encode("utf-8")
        assert sha(cls.original)==SOURCE_PREIMAGE_SHA256, "UNEXPECTED_ORIGINAL_SOURCE"
        cls.patched=candidate_text(cls.original.decode("utf-8"),
                                   "ALL_SYMLINK_ANCESTORS").encode("utf-8")
        assert sha(cls.patched)==CERTIFIED_PATCH_SHA256,"UNEXPECTED_PATCH_SOURCE"
        assert cls.current in (cls.original,cls.patched),"UNREVIEWED_LIVE_SOURCE_DRIFT"
        # The fallback imports inside the trusted original implementation
        # require the project's real tools module directory; temp fixtures
        # contain ONLY the validated original source under test.
        sys.path.insert(0,str(REAL.parent))

    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root=Path(self.dir.name)/"tools"
        root.mkdir()
        self.baseline=root/REAL.name
        self.baseline.write_bytes(self.original)

    def setup_candidate(self):
        receipt,source,diff=choose(self.baseline)
        candidate=Path(self.dir.name)/"candidate.py"
        candidate.write_bytes(source)
        return candidate,receipt,diff

    def test_original_source_is_certified_and_candidate_exact(self):
        self.assertEqual(sha(self.original),SOURCE_PREIMAGE_SHA256)
        self.assertEqual(sha(self.patched),CERTIFIED_PATCH_SHA256)
        self.assertEqual(self.current in (self.original,self.patched),True)

    def test_proven_real_bug_and_only_one_training_winner(self):
        receipt,patched,diff=choose(self.baseline)
        self.assertEqual(receipt["selected_candidate_id"],"ALL_SYMLINK_ANCESTORS")
        self.assertEqual(receipt["baseline_training_passed"],3)
        self.assertEqual(receipt["baseline_training_total"],5)
        self.assertEqual(receipt["candidate_scores"]["ALL_SYMLINK_ANCESTORS"],5)
        self.assertLess(receipt["candidate_scores"]["DIRECT_PARENT_ONLY"],5)
        self.assertEqual(patched,self.patched)
        self.assertIn(b"@@",diff)
        self.assertFalse(receipt["neural_model_generated_this_code"])
        self.assertFalse(receipt["source_writeback"])

    def test_real_independent_holdout_and_authority_ceiling(self):
        candidate,receipt,diff=self.setup_candidate()
        out=verify(self.baseline,candidate,receipt,diff)
        self.assertEqual(out["status"],
          "PASS_REAL_FILE_BOUND_RULE_REPAIR_INDEPENDENT_HELDOUT")
        self.assertEqual(out["candidate_holdout_passed"],out["heldout_total"])
        self.assertLess(out["source_holdout_passed"],out["heldout_total"])
        self.assertFalse(out["neural_model_self_patch_proven"])
        self.assertFalse(out["production_main_modified"])
        self.assertFalse(out["full_issue_162_acceptance"])

    def test_tampered_candidate_rejected(self):
        candidate,receipt,diff=self.setup_candidate()
        candidate.write_bytes(candidate.read_bytes()+b"\n# unauthorized extra code\n")
        with self.assertRaisesRegex(RepairHold,"CANDIDATE_NOT_WHITELISTED_TRANSFORM"):
            verify(self.baseline,candidate,receipt,diff)

    def test_forged_baseline_digest_rejected(self):
        candidate,receipt,diff=self.setup_candidate()
        receipt["original_source_sha256"]="0"*64
        with self.assertRaisesRegex(RepairHold,"CANDIDATE_HASH_OR_DIFF_MISMATCH"):
            verify(self.baseline,candidate,receipt,diff)

    def test_claim_neural_model_generated_rejected(self):
        candidate,receipt,diff=self.setup_candidate()
        receipt["neural_model_generated_this_code"]=True
        with self.assertRaisesRegex(RepairHold,"SELECTION_RECEIPT_NOT_TRUSTED"):
            verify(self.baseline,candidate,receipt,diff)

    def test_privilege_claim_in_receipt_rejected(self):
        candidate,receipt,diff=self.setup_candidate()
        receipt["authority_delta"]=1
        with self.assertRaisesRegex(RepairHold,"SELECTION_RECEIPT_NOT_TRUSTED"):
            verify(self.baseline,candidate,receipt,diff)

    def test_diff_tamper_rejected(self):
        candidate,receipt,diff=self.setup_candidate()
        with self.assertRaisesRegex(RepairHold,"CANDIDATE_HASH_OR_DIFF_MISMATCH"):
            verify(self.baseline,candidate,receipt,diff+b"malicious")

    def test_static_edit_cannot_touch_multiple_hunks(self):
        source=self.original.decode("utf-8")
        with self.assertRaisesRegex(RepairHold,"EXPECTED_REAL_SOURCE_PREIMAGE_MISSING"):
            candidate_text(source+OLD,"ALL_SYMLINK_ANCESTORS")
        with self.assertRaisesRegex(RepairHold,"REPAIR_RULE_NOT_ADMITTED"):
            candidate_text(source,"RUN_SHELL")
        self.assertEqual(candidate_text(source,"ALL_SYMLINK_ANCESTORS").
                         replace(CERTIFIED_REPLACEMENT,OLD),source)

    def test_immutable_output_and_symlink_inputs(self):
        root=Path(self.dir.name)
        p=root/"one"
        _write(p,b"data")
        with self.assertRaisesRegex(RepairHold,"OUTPUT_ALREADY_PRESENT"):
            _write(p,b"overwritten")
        alias=root/"shortcut"
        alias.symlink_to(p)
        with self.assertRaisesRegex(RepairHold,"SOURCE_PATH_NOT_REGULAR"):
            _read(alias)

    def test_fixed_source_works_without_requirements_to_remain_broken(self):
        self.assertEqual(sha(REAL.read_bytes()),sha(self.current))
        if self.current==self.patched:
            self.assertTrue(all(run_tests(REAL,independent=True).values()))
            self.assertTrue(all(run_tests(REAL,independent=False).values()))
        else:
            self.assertEqual(self.current,self.original)
            cases=run_tests(REAL,independent=True)
            self.assertLess(sum(cases.values()),len(cases))
            self.assertTrue(all(run_tests(self.baseline,independent=False)[k]
                for k in ("normal_file_accepted","direct_file_symlink_rejected")))


if __name__=="__main__":
    unittest.main()
