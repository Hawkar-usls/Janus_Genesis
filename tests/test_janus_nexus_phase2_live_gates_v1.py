"""Adversarial native-consumer, Git-CAS race, patch and REAL44 lab tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.janus_nexus_integrated_model_git_lab_v1 import make_a, make_b
from tools.janus_nexus_phase2_live_gates_v1 import (
    Hold, PATCH_PROMPT, make_claim, contender_receipt, race_verdict,
    native_consumer_prompt, make_native_consumer_receipt,
    screen_patch, one_run_real44_receipt, raw_sha, run_path,
    independent_phase2_verdict,
)
from tools.janus_nexus_integrated_model_git_lab_v1 import (
    REGISTRY_SCHEMA, REGISTRY_SOURCE_RUN, REGISTRY_SOURCE_SHA,
)
from tools.janus_nexus_same_run_model_handoff_v1 import PROMPT, MODEL_COMMIT

RUN="43265527510"
ATTEMPT=1
SOURCE="a"*40
A="b"*40
WIN="c"*40


def registry():
    return {"schema":REGISTRY_SCHEMA,
      "status":"PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE",
      "source_run_id":REGISTRY_SOURCE_RUN,
      "source_commit":REGISTRY_SOURCE_SHA,
      "full_issue_162_acceptance":False,
      "actual_cross_organ_runtime_execution_attested":False}


class Phase2LabTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.reg=registry()
        make_a(self.root,RUN,ATTEMPT,SOURCE,self.reg,
          (PROMPT+" alpha proposal comes first.").encode(),
          (PROMPT+" beta proposal comes second.").encode())
        self.base=run_path(self.root,RUN,ATTEMPT)

    def claims(self):
        one=make_claim(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,"contender-1")
        two=make_claim(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,"contender-2")
        self.assertNotEqual(one["owner"],two["owner"])
        self.assertNotEqual(one["checkpoint_digest"],"")
        (self.base/"lease.json").write_text(json.dumps(one))
        return one,two

    def test_two_real_contenders_only_one_cas_owner(self):
        one,two=self.claims()
        receipts=[contender_receipt(one,won=True,head=WIN,
                                    outcome="PUSH_FAST_FORWARD_WIN"),
                  contender_receipt(two,won=False,head=None,
                                    outcome="NON_FF_OR_HEAD_CHANGED")]
        out=race_verdict(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,receipts,WIN)
        self.assertTrue(out["exclusive_branch_ref_cas"])
        self.assertFalse(out["live_lease_expiry_renewal_tested"])
        self.assertEqual(out["winner"],"contender-1")

    def test_replay_fake_double_winner_rejected(self):
        one,two=self.claims()
        receipts=[contender_receipt(one,won=True,head=WIN,
                                    outcome="PUSH_FAST_FORWARD_WIN"),
                  contender_receipt(two,won=True,head="d"*40,
                                    outcome="PUSH_FAST_FORWARD_WIN")]
        with self.assertRaisesRegex(Hold,"GIT_CAS_RACE_NOT_EXCLUSIVE"):
            race_verdict(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,receipts,WIN)

    def test_wrong_source_epoch_and_owner_rejected(self):
        one,two=self.claims()
        receipts=[contender_receipt(one,won=True,head=WIN,
                                    outcome="PUSH_FAST_FORWARD_WIN"),
                  contender_receipt(two,won=False,head=None,
                                    outcome="NON_FF_OR_HEAD_CHANGED")]
        altered=json.loads((self.base/"lease.json").read_text())
        altered["fence_epoch"]=99
        (self.base/"lease.json").write_text(json.dumps(altered))
        with self.assertRaisesRegex(Hold,"GIT_CAS_LEASE_MISMATCH"):
            race_verdict(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,receipts,WIN)

    def test_claim_absence_and_cas_result_integrity(self):
        one,two=self.claims()
        with self.assertRaisesRegex(Hold,"LEASE_ALREADY_PRESENT"):
            make_claim(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,"contender-1")
        with self.assertRaises(Hold):
            contender_receipt(one,won=True,head=None,
                             outcome="PUSH_FAST_FORWARD_WIN")
        with self.assertRaises(Hold):
            contender_receipt(two,won=False,head=WIN,
                             outcome="NON_FF_OR_HEAD_CHANGED")

    def test_native_consumer_actual_selected_excerpt_and_prefix(self):
        prompt=native_consumer_prompt(self.root,RUN,ATTEMPT)
        self.assertTrue(prompt.startswith("JANUS REVIEW (untrusted): "))
        self.assertLessEqual(len(prompt.encode()),112)
        raw=(prompt+" native model output example").encode()
        with patch("tools.janus_nexus_phase2_live_gates_v1.verify_model_source"):
            r=make_native_consumer_receipt(self.root,RUN,ATTEMPT,self.reg,
                                           self.root,raw)
        self.assertEqual(r["model_commit"],MODEL_COMMIT)
        self.assertEqual(r["model_prompt_sha256"],raw_sha(prompt.encode()))
        self.assertTrue(r["real_native_model_call_observed"])
        self.assertFalse(r["real_external_organ_ack"])
        self.assertTrue(r["only_bounded_excerpt_consumed"])

    def test_consumer_wrong_prompt_and_empty_response_rejected(self):
        with patch("tools.janus_nexus_phase2_live_gates_v1.verify_model_source"):
            with self.assertRaisesRegex(Hold,"CONSUMER_DID_NOT_READ_EXPECTED_INPUT"):
                make_native_consumer_receipt(self.root,RUN,ATTEMPT,self.reg,
                                             self.root,b"forged response")
            with self.assertRaisesRegex(Hold,"CONSUMER_DID_NOT_GENERATE_RESPONSE"):
                prompt=native_consumer_prompt(self.root,RUN,ATTEMPT)
                make_native_consumer_receipt(self.root,RUN,ATTEMPT,self.reg,
                                             self.root,prompt.encode())

    def test_patch_candidate_model_provenance_negative(self):
        r=screen_patch((PATCH_PROMPT+" random model noise").encode(),
                       SOURCE,RUN,ATTEMPT)
        self.assertEqual(r["status"],"HOLD_NO_ADMISSIBLE_MODEL_PATCH")
        self.assertFalse(r["actual_repository_patch_written"])
        self.assertFalse(r["generated_source_executed"])
        with self.assertRaisesRegex(Hold,"PATCH_PROMPT_PROVENANCE_MISMATCH"):
            screen_patch(b"return value + 1",SOURCE,RUN,ATTEMPT)

    def test_exact_bounded_patch_fixture_positive_not_production(self):
        r=screen_patch((PATCH_PROMPT+"return value + 1").encode(),SOURCE,
                       RUN,ATTEMPT)
        self.assertEqual(r["status"],"PASS_WHITELISTED_PATCH_PROPOSAL_FIXTURE_ONLY")
        self.assertEqual(r["candidate_regression_cases_passed"],4)
        self.assertFalse(r["independent_generalization_tested"])
        self.assertFalse(r["scientific_quality_improvement_proven"])

    def test_real44_hard_holds_and_private_opacity(self):
        good=one_run_real44_receipt(RUN,SOURCE,True)
        self.assertEqual(good["source_count"],44)
        self.assertFalse(good["same_run_two_clean_real44_rebuilds"])
        self.assertFalse(good["private_exact_pins_disclosed"])
        hold=one_run_real44_receipt(RUN,SOURCE,False)
        self.assertIsNone(hold["private_count"])
        self.assertEqual(hold["status"],"HOLD_ONE_RUN_REAL44_UNAVAILABLE")

    def test_independent_full_join_hard_holds(self):
        one,two=self.claims()
        receipts=[contender_receipt(one,won=True,head=WIN,
                                    outcome="PUSH_FAST_FORWARD_WIN"),
                  contender_receipt(two,won=False,head=None,
                                    outcome="NON_FF_OR_HEAD_CHANGED")]
        race=race_verdict(self.root,RUN,ATTEMPT,self.reg,SOURCE,A,receipts,WIN)
        make_b(self.root,RUN,ATTEMPT,self.reg,A)
        prompt=native_consumer_prompt(self.root,RUN,ATTEMPT)
        raw=(prompt+" actual native response").encode()
        with patch("tools.janus_nexus_phase2_live_gates_v1.verify_model_source"):
            consumer=make_native_consumer_receipt(self.root,RUN,ATTEMPT,
                                                  self.reg,self.root,raw)
        patch_raw=(PATCH_PROMPT+"noise").encode()
        patch_value=screen_patch(patch_raw,SOURCE,RUN,ATTEMPT)
        real44=one_run_real44_receipt(RUN,SOURCE,True)
        out=independent_phase2_verdict(self.root,RUN,ATTEMPT,self.reg,
                                      A,"e"*40,race,consumer,raw,
                                      patch_value,patch_raw,real44)
        self.assertTrue(out["real_native_consumer"])
        self.assertTrue(out["real44_same_run_single_worker"])
        self.assertFalse(out["real44_two_clean_rebuilds_same_run"])
        self.assertFalse(out["independent_software_improvement_verified"])
        self.assertFalse(out["full_issue_162_acceptance"])
        self.assertEqual(out["authority_delta"],0)
        with self.assertRaisesRegex(Hold,"REAL_CONSUMER_OUTPUT_TAMPERED"):
            independent_phase2_verdict(self.root,RUN,ATTEMPT,self.reg,
                                      A,"e"*40,race,consumer,b"tampered",
                                      patch_value,patch_raw,real44)
        forged_patch=copy.deepcopy(patch_value)
        forged_patch["status"]="PASS_WHITELISTED_PATCH_PROPOSAL_FIXTURE_ONLY"
        with self.assertRaisesRegex(Hold,"INDEPENDENT_PATCH_REPLAY_MISMATCH"):
            independent_phase2_verdict(self.root,RUN,ATTEMPT,self.reg,
                                      A,"e"*40,race,consumer,raw,
                                      forged_patch,patch_raw,real44)
        forged=copy.deepcopy(real44)
        forged["same_run_two_clean_real44_rebuilds"]=True
        with self.assertRaisesRegex(Hold,"REAL44_PUBLIC_RECEIPT_NOT_BOUND"):
            independent_phase2_verdict(self.root,RUN,ATTEMPT,self.reg,
                                      A,"e"*40,race,consumer,raw,
                                      patch_value,patch_raw,forged)

    def test_invalid_run_or_boolean_rejected(self):
        with self.assertRaises(Hold):
            one_run_real44_receipt("../escape",SOURCE,False)
        with self.assertRaises(Hold):
            one_run_real44_receipt(RUN,SOURCE,1)


if __name__=="__main__":
    unittest.main()
