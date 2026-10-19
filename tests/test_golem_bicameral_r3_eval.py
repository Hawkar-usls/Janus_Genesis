"""R3 scoring-harness adversarial tests, intentionally WITHOUT live inference."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from golem_bicameral_r3_eval import (
    evaluate, validate_pack, task_hash, digest, EvaluationError, SUBMISSION_SCHEMA,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "benchmarks/golem_bicameral_r3_calibration.json"
KEY = ROOT / "benchmarks/golem_bicameral_r3_calibration_key.json"
MODES = ("NATIVE", "EXTERNAL", "BICAMERAL")


class R3MetrologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(PACK.read_text(encoding="utf-8"))
        cls.key = json.loads(KEY.read_text(encoding="utf-8"))

    def made_up(self, score_limits=(6, 9, 12), *, source="TEST_FIXTURE"):
        records = []
        cases = self.pack["tasks"]
        for mode, n_correct in zip(MODES, score_limits):
            for index, task in enumerate(cases):
                expected = self.key["answers"][task["id"]]
                wrong = next(v for v in ("ALLOW", "DENY", "UNKNOWN") if v != expected)
                records.append({
                    "mode": mode, "task_id": task["id"],
                    "task_sha256": task_hash(task),
                    "response": expected if index < n_correct else wrong,
                    "source_kind": source,
                    "source_receipt_sha256": None if source == "TEST_FIXTURE" else "b" * 64,
                })
        return {"schema": SUBMISSION_SCHEMA, "pack_sha256": digest(self.pack),
                "records": records}

    def test_frozen_reference_and_family_balance(self):
        frozen = validate_pack(self.pack, self.key)
        self.assertEqual(frozen["cases"], 12)
        self.assertEqual(set(frozen["families"]), {"gateway", "memory", "evidence", "authority"})
        self.assertEqual(list(frozen["families"].values()), [3, 3, 3, 3])
        self.assertTrue(frozen["public_answers"])

    def test_no_submissions_means_unmeasured_not_zero_accuracy(self):
        result = evaluate(self.pack, self.key)
        self.assertEqual(result["status"], "NO_SUBMISSIONS__NOT_EVALUATED")
        self.assertIsNone(result["results"])
        self.assertFalse(result["improvement_claim_admitted"])

    def test_perfect_synthetic_bicameral_cannot_claim_real_gain(self):
        doc = evaluate(self.pack, self.key, self.made_up())
        self.assertEqual(doc["results"]["NATIVE"]["correct"], 6)
        self.assertEqual(doc["results"]["EXTERNAL"]["correct"], 9)
        self.assertEqual(doc["results"]["BICAMERAL"]["correct"], 12)
        self.assertEqual(doc["paired"]["BICAMERAL_vs_NATIVE"]["b_wins"], 6)
        self.assertEqual(doc["paired"]["BICAMERAL_vs_NATIVE"]["a_wins"], 0)
        self.assertAlmostEqual(doc["paired"]["BICAMERAL_vs_NATIVE"]["exact_p_two_sided"], 0.03125)
        self.assertEqual(doc["score_label"], "CALIBRATION_ONLY__PUBLIC_ANSWERS")
        for field in ("improvement_claim_admitted", "real_external_inference_verified",
                      "independent_holdout_tested", "official_benchmark_score_claimed",
                      "source_provenance_independently_verified", "promotion_authorized"):
            self.assertFalse(doc[field], field)

    def test_incomplete_pack_does_not_reweight_away_missing(self):
        data = self.made_up()
        data["records"] = [r for r in data["records"] if not
                           (r["mode"] == "BICAMERAL" and r["task_id"] == "GW01")]
        score = evaluate(self.pack, self.key, data)
        self.assertEqual(score["status"], "INCOMPLETE_PAIRING__NO_IMPROVEMENT_CLAIM")
        self.assertIsNone(score["paired"]["BICAMERAL_vs_NATIVE"])
        self.assertEqual(score["results"]["BICAMERAL"]["missing"], 1)
        self.assertEqual(score["results"]["BICAMERAL"]["denominator"], 12)
        self.assertEqual(score["results"]["BICAMERAL"]["correct"], 11)

    def test_abstention_is_separate_and_not_scored_as_correct(self):
        data = self.made_up()
        data["records"][0]["response"] = "ABSTAIN"
        result = evaluate(self.pack, self.key, data)
        self.assertEqual(result["results"]["NATIVE"]["abstained"], 1)
        self.assertEqual(result["results"]["NATIVE"]["correct"], 5)

    def test_duplicate_cannot_inflate_score(self):
        data = self.made_up()
        data["records"].append(dict(data["records"][0]))
        with self.assertRaisesRegex(EvaluationError, "duplicated"):
            evaluate(self.pack, self.key, data)

    def test_question_digest_mismatch_fails(self):
        data = self.made_up()
        data["records"][0]["task_sha256"] = "a" * 64
        with self.assertRaisesRegex(EvaluationError, "frozen question"):
            evaluate(self.pack, self.key, data)

    def test_pack_digest_mismatch_fails(self):
        data = self.made_up()
        data["pack_sha256"] = "0" * 64
        with self.assertRaisesRegex(EvaluationError, "frozen R3 calibration"):
            evaluate(self.pack, self.key, data)

    def test_public_reference_cannot_be_relabelled_hidden(self):
        pack = copy.deepcopy(self.pack)
        pack["split"] = "HIDDEN_HOLDOUT"
        with self.assertRaisesRegex(EvaluationError, "mislabelled"):
            evaluate(pack, self.key)

    def test_fixture_with_fake_real_receipt_fails(self):
        data = self.made_up()
        data["records"][0]["source_receipt_sha256"] = "c" * 64
        with self.assertRaisesRegex(EvaluationError, "impersonate"):
            evaluate(self.pack, self.key, data)

    def test_unverified_candidate_missing_digest_fails(self):
        data = self.made_up(source="UNVERIFIED_CANDIDATE")
        data["records"][0]["source_receipt_sha256"] = None
        with self.assertRaisesRegex(EvaluationError, "digest"):
            evaluate(self.pack, self.key, data)

    def test_unverified_candidate_never_auto_qualifies(self):
        data = self.made_up(source="UNVERIFIED_CANDIDATE")
        score = evaluate(self.pack, self.key, data)
        self.assertFalse(score["source_provenance_independently_verified"])
        self.assertFalse(score["improvement_claim_admitted"])
        self.assertEqual(score["provenance_type_counts"]["UNVERIFIED_CANDIDATE"], 36)

    def test_answer_key_shrink_fails_closed(self):
        key = copy.deepcopy(self.key)
        key["answers"].pop("GW01")
        with self.assertRaisesRegex(EvaluationError, "answer key"):
            evaluate(self.pack, key)

    def test_answer_key_substitution_changes_evidence_digest(self):
        key = copy.deepcopy(self.key)
        key["answers"]["GW01"] = "DENY"
        old = validate_pack(self.pack, self.key)
        new = validate_pack(self.pack, key)
        self.assertNotEqual(old["answer_key_sha256"], new["answer_key_sha256"])
        self.assertFalse(evaluate(self.pack, key, self.made_up())["improvement_claim_admitted"])

    def test_unknown_source_type_fails_closed(self):
        data = self.made_up()
        data["records"][0]["source_kind"] = "VERIFIED_LIVE_PROVIDER"
        with self.assertRaisesRegex(EvaluationError, "frozen question"):
            evaluate(self.pack, self.key, data)


if __name__ == "__main__":
    unittest.main()
