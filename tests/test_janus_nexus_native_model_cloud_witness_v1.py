"""Negative controls for bounded native MODEL.CALL Git provenance witness."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "janus_native_cloud_witness_test",
    ROOT/"tools/janus_nexus_native_model_cloud_witness_v1.py")
assert spec and spec.loader
w=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=w
spec.loader.exec_module(w)


class NativeWitnessTests(unittest.TestCase):
    def fixture(self, root: Path):
        lab=root/"lab"
        brain=root/"brain"
        base=lab/"data/nexus_closed_loop_lab/runs"/str(w.LAB_RUN_ID)
        base.mkdir(parents=True)
        (brain/"janus_model/state").mkdir(parents=True)
        (brain/"janus_model/checkpoints").mkdir(parents=True)
        (base/"worker-b.json").write_text(json.dumps({
            "schema":"janus.nexus.bounded_two_cloud_writer_lab.v1.worker_b",
            "source_git_checkpoint_commit":w.LAB_A_COMMIT,
            "status":"COMPLETED_ONCE_IN_LAB_ONLY",
            "event_id":"nexus-lab-"+str(w.LAB_RUN_ID),
            "failed_variant_ids_retained":["rejected"],
        }))
        (base/"checkpoint.json").write_text(json.dumps({
            "source":{"source_run_id":41049447362,
                      "source_commit":"e4baea1840173648150d10161096134e43b81926"},
        }))
        (base/"variants.json").write_text(json.dumps({
            "failed_variant_ids":["rejected"],
        }))
        fake_ckpt=b"fake-fixture-not-actual-checkpoint"
        ckpt_hash=hashlib.sha256(fake_ckpt).hexdigest()
        (brain/"janus_model/checkpoints/promoted.pt").write_bytes(fake_ckpt)
        (brain/"janus_model/state/JANUS_MODEL_STATE.json").write_text(
            json.dumps({"checkpoint_sha256":ckpt_hash}))
        output=root/"native.txt"
        output.write_text(w.PROMPT+"\nmock generated completion\n")
        return lab,brain,output,base,ckpt_hash

    def evaluate(self, lab,brain,output,ckpt_hash):
        def git_head(root):
            return w.LAB_COMMIT if root==lab else w.DEMIURGE_SOURCE
        with patch.object(w,"git_head",side_effect=git_head),\
             patch.object(w,"CHECKPOINT_SHA256",ckpt_hash):
            return w.inspect(lab,brain,output)

    def test_scoped_pass_does_not_claim_model_truth_or_full_162(self):
        with tempfile.TemporaryDirectory() as temp:
            lab,brain,out,base,digest=self.fixture(Path(temp))
            value=self.evaluate(lab,brain,out,digest)
            self.assertTrue(value["model_call_executed"])
            self.assertFalse(value["full_issue_162_acceptance"])
            self.assertFalse(value["model_output_quality_verified"])
            self.assertFalse(value["live_cross_organ_receiver_consumption"])
            self.assertFalse(value["raw_model_output_archived"])
            self.assertFalse(value["paid_provider_invoked"])

    def test_corrupted_source_ref_or_missing_failed_variant_holds(self):
        with tempfile.TemporaryDirectory() as temp:
            lab,brain,out,base,digest=self.fixture(Path(temp))
            p=base/"worker-b.json"
            body=json.loads(p.read_text())
            body["source_git_checkpoint_commit"]="0"*40
            p.write_text(json.dumps(body))
            with self.assertRaises(w.WitnessHold):
                self.evaluate(lab,brain,out,digest)
            body["source_git_checkpoint_commit"]=w.LAB_A_COMMIT
            body["failed_variant_ids_retained"]=[]
            p.write_text(json.dumps(body))
            with self.assertRaises(w.WitnessHold):
                self.evaluate(lab,brain,out,digest)

    def test_wrong_model_checkpoint_and_empty_output_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            lab,brain,out,base,digest=self.fixture(Path(temp))
            with self.assertRaises(w.WitnessHold):
                self.evaluate(lab,brain,out,"0"*64)
            out.write_text("not the pinned prompt\n")
            with self.assertRaises(w.WitnessHold):
                self.evaluate(lab,brain,out,digest)
            out.write_bytes(b"")
            with self.assertRaises(w.WitnessHold):
                self.evaluate(lab,brain,out,digest)

if __name__=="__main__":
    unittest.main()
