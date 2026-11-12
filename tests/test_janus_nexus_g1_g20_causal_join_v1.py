"""Adversarial join tests: same run/source/parent/variant or fail closed."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.janus_nexus_g1_g20_causal_join_v1 import (
    reconcile,JoinHold,digest
)
from tools.janus_nexus_live_git_lease_expiry_v1 import (
    seed,renew,takeover,TTL_MS
)
RUN="43290000001"
SOURCE="a"*40
B_HEAD="b"*40
SEED_SHA="c"*40
RENEW_SHA="d"*40
TAKE_SHA="e"*40
T=1_800_000_000_000

class CohortJoinTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        base=self.root/"data/nexus_integrated_native_lab/runs"/(RUN+"-1")
        leasebase=self.root/"data/nexus_lease_expiry_lab/runs"/(RUN+"-1")
        base.mkdir(parents=True);leasebase.mkdir(parents=True)
        self.base=base
        self.leasebase=leasebase
        candidates=[
          {"variant_id":"model-1","proposal":{"proposal_sha256":"1"*64,"text":"reject"}},
          {"variant_id":"model-2","proposal":{"proposal_sha256":"2"*64,"text":"selected"}}]
        self.variants={
          "schema":"janus.nexus.integrated_native_git_lab.v1.variants",
          "model_generated_count":2,
          "selected_variant_id":"model-2",
          "rejected_variant_ids_retained":["model-1"],
          "candidates":candidates}
        self.checkpoint={
          "schema":"janus.nexus.integrated_native_git_lab.v1.checkpoint",
          "run_id":RUN,"attempt":1,"code_sha":SOURCE,
          "variant_digest":digest(self.variants),
          "selected_variant_id":"model-2",
          "source_witness":{"same_run_real44_materialized":False},
          "authority_delta":0,"source_writeback":False}
        self.a={"run_id":RUN,"attempt":1,"variant_digest":digest(self.variants),
                "checkpoint_digest":digest(self.checkpoint),"authority_delta":0}
        self.receiver={
          "selected_variant_id":"model-2",
          "consumed_proposal_sha256":"2"*64,
          "authority_delta":0}
        self.b={"run_id":RUN,"attempt":1,
                "status":"LAB_CONSUMED_COMPLETED_ONCE",
                "completion_id":"3"*64,
                "checkpoint_digest":digest(self.checkpoint),
                "variants_digest":digest(self.variants),
                "receiver_digest":digest(self.receiver),
                "authority_delta":0}
        for name,row in [
             ("checkpoint.json",self.checkpoint),("variants.json",self.variants),
             ("worker-a.json",self.a),("worker-b.json",self.b),
             ("receiver.json",self.receiver)]:
            (base/name).write_text(json.dumps(row))
        x=seed(RUN,1,SOURCE,T,"1"*32)
        y=renew(x,T+1000)
        z=takeover(x,y,y["expires_at_ms"]+2000,"2"*32)
        for name,row in [("seed.json",x),("renew.json",y),("takeover.json",z)]:
            (leasebase/name).write_text(json.dumps(row))
        self.phase2={
          "schema":"janus.nexus.phase2_live_gates.v1.independent_verdict",
          "status":"PASS_SCOPED_NATIVE_CONSUMER_GIT_CAS_LAB_WITH_HARD_HOLDS",
          "run_id":RUN,"attempt":1,"source_code_sha":SOURCE,
          "b_head":B_HEAD,"completion_id":self.b["completion_id"],
          "real_native_consumer":True,
          "real_github_branch_ref_cas_winner":True,
          "real44_two_clean_rebuilds_same_run":True,
          "full_issue_162_acceptance":False,"source_writeback":False,
          "authority_delta":0}
        self.ttl={
          "schema":"janus.nexus.git_lease_expiry.v1.verdict",
          "status":"PASS_SCOPED_REAL_WALLCLOCK_TTL_TAKEOVER_GIT_STALE_FENCE",
          "run_id":RUN,"attempt":1,"source_sha":SOURCE,
          "seed_git_sha":SEED_SHA,"renew_git_sha":RENEW_SHA,
          "takeover_git_sha":TAKE_SHA,"real_wallclock_tested":True,
          "late_owner_semantic_rejected":True,
          "late_owner_git_nonforce_rejected":True,
          "external_effect_lease_fence_tested":False,
          "full_issue_162_acceptance":False,"source_writeback":False,
          "authority_delta":0}

    def joined(self,**updates):
        params={"root":self.root,"run_id":RUN,"attempt":1,
          "source_sha":SOURCE,"phase2":self.phase2,"ttl":self.ttl,
          "phase2_b_head":B_HEAD,"ttl_takeover_head":TAKE_SHA,
          "ttl_seed_parent":B_HEAD}
        params.update(updates)
        return reconcile(**params)

    def test_one_real_run_parent_join_scoped_not_full(self):
        d=self.joined()
        self.assertTrue(d["same_run_phase2_to_ttl_git_parent_verified"])
        self.assertTrue(d["phase2_two_clean_real44_verified"])
        self.assertTrue(d["lease_expiry_stale_owner_git_fence_verified"])
        self.assertFalse(d["g1_to_g20_full_acceptance"])
        self.assertFalse(d["full_issue_162_acceptance"])
        self.assertEqual(d["scientific_authority_delta"],0)
        self.assertIn("HOLD_REAL44_MODEL_INPUT_CAUSAL_LINK",d["hard_holds"])
        self.assertIn("HOLD_CAUSAL_EXTERNAL_DEMIURGE_ACK",d["hard_holds"])
        self.assertIn("HOLD_NATIVE_NEURAL_SOURCE_REPAIR",d["hard_holds"])
        self.assertEqual(len(d["g1_g20_scoped_observations"]),20)

    def test_cross_run_phase2_rejected(self):
        a=copy.deepcopy(self.phase2);a["run_id"]="43290000002"
        with self.assertRaisesRegex(JoinHold,"CROSS_RUN_OR_SOURCE_MISMATCH"):
            self.joined(phase2=a)

    def test_foreign_ttl_rejected(self):
        x=copy.deepcopy(self.ttl);x["source_sha"]="f"*40
        with self.assertRaisesRegex(JoinHold,"CROSS_RUN_OR_SOURCE_MISMATCH"):
            self.joined(ttl=x)

    def test_phase2_replay_head_drift_rejected(self):
        x=copy.deepcopy(self.phase2);x["b_head"]="f"*40
        with self.assertRaisesRegex(JoinHold,"PHASE2_GATE_INCOMPLETE"):
            self.joined(phase2=x)

    def test_old_head_as_ttl_parent_rejected(self):
        with self.assertRaisesRegex(JoinHold,"TTL_GIT_PARENT_OR_SCOPE_MISMATCH"):
            self.joined(ttl_seed_parent="f"*40)

    def test_ttl_wrong_epoch_rejected(self):
        p=self.leasebase/"takeover.json"
        j=json.loads(p.read_text());j["fence_epoch"]=1
        p.write_text(json.dumps(j))
        with self.assertRaisesRegex(JoinHold,"TTL_REPLAY_INVALID"):
            self.joined()

    def test_variant_digest_tamper_rejected(self):
        p=self.base/"variants.json"
        j=json.loads(p.read_text());j["candidates"][1]["proposal"]["text"]="forged"
        p.write_text(json.dumps(j))
        with self.assertRaisesRegex(JoinHold,"VARIANT_CHECKPOINT_CHAIN_BROKEN"):
            self.joined()

    def test_cross_run_external_ack_rejected(self):
        external={
          "sender_source_run_id":"43275243138",
          "sender_source_attempt":1,
          "sender_code_sha":SOURCE,
          "selected_proposal_sha256":"2"*64,
          "receiver_repository":"Hawkar-usls/Janus-Demiurge",
          "real_external_organ_readonly_consumption_proven":True,
          "external_organ_is_separate_git_repository_and_runner":True,
          "source_writeback":False,"full_issue_162_acceptance":False}
        with self.assertRaisesRegex(JoinHold,"EXTERNAL_ACK_WRONG_RUN_OR_PROPOSAL"):
            self.joined(external_ack=external)

    def test_source_archive_same_run_claim_is_not_retroactively_inferred(self):
        p=self.base/"checkpoint.json"
        row=json.loads(p.read_text())
        self.assertFalse(row["source_witness"]["same_run_real44_materialized"])
        d=self.joined()
        self.assertEqual(d["g1_g20_scoped_observations"]["G2_MATERIALIZED_NEXUS_ID_REPRODUCED"],
                         "PASS_SCOPED_REAL44_BUT_MODEL_INPUT_NOT_BOUND")

    def test_false_neural_patch_current_run_rejected(self):
        bogus={"run_id":RUN,"attempt":1,"source_sha":SOURCE,
               "model_generated_actual_source_patch":False,
               "independent_heldout_pass":True,"source_writeback":False,
               "authority_delta":0}
        with self.assertRaisesRegex(JoinHold,"NEURAL_PATCH_WRONG_RUN_OR_FALSE_ATTESTATION"):
            self.joined(neural_patch=bogus)

    def test_source_writeback_claim_fails_closed(self):
        p=self.base/"worker-b.json"
        b=json.loads(p.read_text());b["source_writeback"]=True
        p.write_text(json.dumps(b))
        with self.assertRaisesRegex(JoinHold,"AUTHORITY_OR_SOURCE_WRITEBACK_ESCALATION"):
            self.joined()

    def test_wrong_completion_and_history_rejected(self):
        p=copy.deepcopy(self.phase2);p["completion_id"]="f"*64
        with self.assertRaisesRegex(JoinHold,"VARIANT_OR_COMPLETION_DRIFT"):
            self.joined(phase2=p)
        t=copy.deepcopy(self.ttl);t["takeover_git_sha"]="f"*40
        with self.assertRaisesRegex(JoinHold,"TTL_GIT_PARENT_OR_SCOPE_MISMATCH"):
            self.joined(ttl=t)

if __name__=="__main__":
    unittest.main()
