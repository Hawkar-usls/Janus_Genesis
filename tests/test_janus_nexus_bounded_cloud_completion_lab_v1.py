"""Adversarial offline controls for create-only bounded two-cloud completion."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("nexus_two_cloud_lab",
    ROOT/"tools/janus_nexus_bounded_cloud_completion_lab_v1.py")
assert spec and spec.loader
lab=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=lab
spec.loader.exec_module(lab)

def source():
    return {
        "schema":"janus.nexus.real44.public_latest.v1",
        "status":"PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE",
        "source_run_id":41049447362,
        "source_commit":"e4baea1840173648150d10161096134e43b81926",
        "actual_cross_organ_runtime_execution_attested":False,
        "full_issue_162_acceptance":False,
    }

class TwoCloudLabTests(unittest.TestCase):
    RUN="41051000001"
    HEAD="b"*40
    A_COMMIT="a"*40

    def prepare(self, root):
        p=root/"registry.json"
        p.write_text(json.dumps(source()))
        lab.phase_a(root,self.RUN,p,self.HEAD)
        return p

    def test_prepare_replay_complete_idempotent_with_retained_loser(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.prepare(root)
            base=lab.run_dir(root,self.RUN)
            variants=lab.load(base/"variants.json")
            self.assertEqual(len(variants["candidates"]),2)
            self.assertEqual(len(variants["failed_variant_ids"]),1)
            self.assertEqual(lab.phase_b(root,self.RUN,self.A_COMMIT),"COMPLETED_NEW")
            frozen=(base/"worker-b.json").read_bytes()
            self.assertEqual(lab.phase_b(root,self.RUN,self.A_COMMIT),"IDEMPOTENT_EXISTING")
            self.assertEqual((base/"worker-b.json").read_bytes(),frozen)
            verdict=lab.inspect(root,self.RUN,self.A_COMMIT)
            self.assertEqual(verdict["status"],"PASS_LAB_TWO_CLEAN_CLOUD_WORKERS_ONLY")
            self.assertFalse(verdict["full_issue_162_acceptance"])
            self.assertFalse(verdict["model_call_in_lab"])
            self.assertFalse(verdict["real44_same_run_full_materialization"])
            self.assertFalse(verdict["live_cross_organ_receiver_consumption"])

    def test_source_claim_cannot_be_promoted_from_real44(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            pointer=source()
            pointer["full_issue_162_acceptance"]=True
            path=root/"registry.json"
            path.write_text(json.dumps(pointer))
            with self.assertRaises(lab.LabHold):
                lab.phase_a(root,self.RUN,path,self.HEAD)
            self.assertFalse((root/lab.ROOT/self.RUN).exists())

    def test_tampered_checkpoint_or_variant_cannot_finish(self):
        for which in ("checkpoint.json","variants.json"):
            with self.subTest(which=which), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                self.prepare(root)
                base=lab.run_dir(root,self.RUN)
                v=lab.load(base/which)
                v["tampered"]=True
                (base/which).write_text(json.dumps(v))
                with self.assertRaises(lab.LabHold):
                    lab.phase_b(root,self.RUN,self.A_COMMIT)
                self.assertFalse((base/"worker-b.json").exists())

    def test_same_run_conflicting_a_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=self.prepare(root)
            with self.assertRaises(lab.LabHold):
                lab.phase_a(root,self.RUN,p,"c"*40)

    def test_repeated_different_worker_commit_cannot_rebind_completion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.prepare(root)
            lab.phase_b(root,self.RUN,self.A_COMMIT)
            with self.assertRaises(lab.LabHold):
                lab.phase_b(root,self.RUN,"c"*40)

    def test_missing_loser_or_fake_double_completion_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.prepare(root)
            variants=root/lab.ROOT/self.RUN/"variants.json"
            row=lab.load(variants)
            row["candidates"].pop()
            variants.write_text(json.dumps(row))
            with self.assertRaises(lab.LabHold):
                lab.phase_b(root,self.RUN,self.A_COMMIT)

    def test_run_id_and_code_sha_input_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"registry.json"
            p.write_text(json.dumps(source()))
            with self.assertRaises(lab.LabHold):
                lab.phase_a(root,"../../private",p,self.HEAD)
            with self.assertRaises(lab.LabHold):
                lab.phase_a(root,self.RUN,p,"invalid")

if __name__=="__main__":
    unittest.main()
