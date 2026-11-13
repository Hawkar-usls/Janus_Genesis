"""ESSENCE v1.2 real-algorithm research receipt integration safety tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
ESS=ROOT/".janus"/"essence"
sys.path.insert(0,str(ESS))
import engineering_matrix as matrix
import kernel
import real_algorithm_gate_v12 as guard


class RealAlgorithmReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/"research"/"essence"/"v12"/"comparison.json").read_text(encoding="utf-8"))
        cls.manifest=kernel.load_json(ESS/"manifest.json")
        cls.fixture=kernel.load_json(ESS/"fixture.json")

    def reseal(self,data):
        data["receipt_sha256"]=kernel.digest({k:v for k,v in data.items() if k!="receipt_sha256"})
        return data

    def test_real_report_holds_instead_of_promotion(self):
        r=guard.review(self.report)
        self.assertTrue(guard.verify(r,self.report))
        self.assertEqual(r["gate"],"HOLD_EXTERNAL_BLIND_REPLICATION_AND_REAL_CHECKPOINT_REVIEW")
        self.assertFalse(r["production_authority"])
        self.assertFalse(r["child_activation"])
        self.assertFalse(r["external_blind_verification_completed"])

    def test_manifest_still_six_inert_cores(self):
        self.assertFalse(self.manifest["enabled"])
        self.assertEqual(len(self.manifest["microkernels"]),6)
        self.assertTrue(all(not right for right in self.manifest["capabilities"].values()))

    def test_connected_to_original_matrix_without_automatic_authority(self):
        r=matrix.evaluate(self.manifest,self.fixture,expression="5*kN*2*m",output_unit="kJ",
                          explicit_readonly=True,real_algorithm_report=self.report)
        self.assertEqual(r["calculator"]["value"],"10")
        self.assertEqual(r["legacy_microkernels"],6)
        self.assertTrue(matrix.verify(r))
        self.assertFalse(r["production_promotion"])
        self.assertEqual(r["real_algorithm_review"]["benchmark_receipt_sha256"],
                         self.report["receipt_sha256"])

    def test_inert_by_default(self):
        with self.assertRaises(PermissionError):
            matrix.evaluate(self.manifest,self.fixture,expression="1+1",
                            real_algorithm_report=self.report)

    def test_tampered_source_report_fails(self):
        bad=copy.deepcopy(self.report)
        bad["byte_tokenizer"]["candidate_output_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"TAMPERED"):
            guard.review(bad)

    def test_resealed_source_mismatch_fails(self):
        bad=self.reseal(copy.deepcopy(self.report))
        bad["byte_tokenizer"]["source_git_blob_sha1"]="0"*40
        self.reseal(bad)
        with self.assertRaisesRegex(ValueError,"SOURCE_FINGERPRINT"):
            guard.review(bad)

    def test_external_attestation_forgery_fails(self):
        bad=copy.deepcopy(self.report)
        bad["independent_external_evaluator_attested"]=True
        self.reseal(bad)
        with self.assertRaisesRegex(ValueError,"PREMATURE_AUTHORITY"):
            guard.review(bad)

    def test_weight_modification_forgery_fails(self):
        bad=copy.deepcopy(self.report)
        bad["model_weights_updated"]=True
        self.reseal(bad)
        with self.assertRaisesRegex(ValueError,"PREMATURE_AUTHORITY"):
            guard.review(bad)

    def test_rollback_proof_resealed_forgery_fails(self):
        bad=copy.deepcopy(self.report)
        bad["essence_gene_bank"]["negative_control"]["rollback_verified"]=False
        self.reseal(bad)
        with self.assertRaisesRegex(ValueError,"ROLLBACK_DRILL"):
            guard.review(bad)

    def test_cpu_claim_resealed_forgery_fails(self):
        bad=copy.deepcopy(self.report)
        bad["transformer_forward"]["exact_logits_match"]=False
        self.reseal(bad)
        with self.assertRaisesRegex(ValueError,"CPU_EVIDENCE"):
            guard.review(bad)

    def test_integrated_review_tamper_holds(self):
        r=matrix.evaluate(self.manifest,self.fixture,expression="1+1",
                          real_algorithm_report=self.report,explicit_readonly=True)
        r["real_algorithm_review"]["production_authority"]=True
        r["receipt_sha256"]=kernel.digest({k:v for k,v in r.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"INVALID_REAL_ALGORITHM"):
            matrix.verify(r)

    def test_replay_rejects_forged_attestation(self):
        result=guard.review(self.report)
        result["external_blind_verification_completed"]=True
        result["receipt_sha256"]=kernel.digest({k:v for k,v in result.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"REPLAY_MISMATCH"):
            guard.verify(result,self.report)


if __name__=="__main__":
    unittest.main()
