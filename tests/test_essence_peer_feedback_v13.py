"""ESSENCE 1.3 Genesis reciprocal feedback: real public receipts + fraud gates."""
import copy
import json
from pathlib import Path
import unittest

from tools import essence_peer_feedback_v13 as m
ROOT=Path(__file__).resolve().parents[1]
WITNESS=ROOT/"tests/fixtures/essence_v13_original_delivery_witness.json"

def source():
    w=json.loads(WITNESS.read_text(encoding="utf-8"))
    jobs={}
    for r in w["observed_receipts"]:
        repo=r["receiver"]
        runid=int(r["actual_main_push_event"].rsplit("/",1)[-1])
        jobs[repo]={
            "id":runid,
            "event":"push",
            "name":"ESSENCE v1.0 receive peer replies through shared public Meta Registry",
            "status":"completed","conclusion":"success",
            "head_sha":r["main_merge_sha"],
        }
    return w,jobs

class ReciprocalPeerContracts(unittest.TestCase):
    def test_both_real_receipts_in_pinned_fixture(self):
        w,j=source()
        result=m.verify(w,j)
        self.assertEqual(result["messages_acknowledged"],2)
        self.assertEqual(result["communication_epoch_completed"],1)
        self.assertEqual(result["scientific_fitness_generation"],0)
        self.assertEqual(result["new_proven_neural_improvements"],0)
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["model_weights_modified"])
        self.assertEqual(result["receipt_sha256"],
                         m.digest({k:v for k,v in result.items() if k!="receipt_sha256"}))

    def test_run_failure_not_accepted(self):
        w,j=source();j[next(iter(j))]["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"INDEPENDENT_LIVE_ACTIONS_RUN_MISMATCH"):
            m.verify(w,j)

    def test_run_not_the_default_branch_push_is_rejected(self):
        w,j=source();j[next(iter(j))]["event"]="pull_request"
        with self.assertRaisesRegex(ValueError,"INDEPENDENT_LIVE_ACTIONS_RUN_MISMATCH"):
            m.verify(w,j)

    def test_spoofed_run_sha_rejected(self):
        w,j=source();j[next(iter(j))]["head_sha"]="0"*40
        with self.assertRaisesRegex(ValueError,"INDEPENDENT_LIVE_ACTIONS_RUN_MISMATCH"):
            m.verify(w,j)

    def test_unknown_candidate_origin_is_denied(self):
        w,j=source();w["observed_receipts"][0]["idea_id"]="unknown"
        with self.assertRaisesRegex(ValueError,"ACK_EVIDENCE_MISMATCH"):
            m.verify(w,j)

    def test_tampered_mailbox_pointer_denied(self):
        w,j=source();w["immutable_round_git_blob_sha1"]="a"*40
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_WITNESS"):
            m.verify(w,j)

    def test_duplicate_ack_denied(self):
        w,j=source();w["observed_receipts"][1]=copy.deepcopy(w["observed_receipts"][0])
        with self.assertRaisesRegex(ValueError,"ACK_REPO_REPLAY_OR_UNKNOWN"):
            m.verify(w,j)

    def test_missing_peer_not_counted(self):
        w,j=source();w["observed_receipts"].pop()
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_TWO_WAY_DELIVERY"):
            m.verify(w,j)

    def test_not_crypto_scientific_independence(self):
        w,j=source()
        r=m.verify(w,j)
        self.assertTrue(all(x["peer_self_attestation_is_not_independent_science"]
                            for x in r["receiver_evidence"]))
        self.assertEqual(r["research_gate"],"PEER_ACKS_VERIFIED_NO_INDEPENDENT_MODEL_GAIN")

    def test_api_disallows_other_repo_and_private_endpoints(self):
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_PEER_FETCH"):
            m.api("/user/repos")
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_PEER_FETCH"):
            m.api("/repos/Hawkar-usls/SkinGPT/actions/runs/1234")

    def test_match_exact_run_identity(self):
        w,j=source()
        j[next(iter(j))]["id"]=99999
        with self.assertRaisesRegex(ValueError,"INDEPENDENT_LIVE_ACTIONS_RUN_MISMATCH"):
            m.verify(w,j)

if __name__=="__main__":
    unittest.main()
