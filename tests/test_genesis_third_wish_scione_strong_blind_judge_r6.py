from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import genesis_third_wish_scione_strong_blind_judge_r6 as r6


PROTOCOL = Path(__file__).resolve().parents[1] / "protocol/JANUS_GENESIS_THIRD_WISH_SCIONE_STRONG_BLIND_JUDGE_R6-v1.0.json"


def score(**updates):
    result = {
        "specific_alternative_idea": 0,
        "falsifiable_test_plan": 0,
        "cross_cycle_semantic_continuity": 1,
        "useful_internal_initiative": 0,
        "unexecuted_action_proposal": False,
        "evidence_quote": "",
        "brief_reason": "No distinct mechanism, planned test, or useful bounded initiative is present.",
    }
    result.update(updates)
    return result


class StrongBlindJudgeR6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = json.loads(PROTOCOL.read_text())

    def test_stronger_different_family_and_r5_sha_pinned(self):
        p = self.p
        self.assertEqual(p["judge_model"], "gemma3:12b-it-q4_K_M")
        self.assertNotEqual(p["judge_model"].split(":")[0], p["prior_judge_model"].split(":")[0])
        self.assertEqual(p["prior_r5_score_lock"]["expected_notes"], 44)
        self.assertEqual(p["prior_r5_score_lock"]["scores_sha256"], "367c5f67d82743051e74c5ec6f196b4b5d86280ca27b65fc8c3774119f033832")
        self.assertTrue(p["sampling"]["single_attempt_per_note"])
        self.assertFalse(p["private_mapping_input_allowed"])
        self.assertFalse(p["arm_unblinding"])
        self.assertFalse(p["human_independent_review_replaced"])

    def test_six_golds_include_prior_false_positive_and_prompt_injection(self):
        controls = self.p["calibration_controls"]
        self.assertEqual(len(controls), 6)
        self.assertEqual(sum(c["mandatory_negative"] for c in controls), 4)
        self.assertEqual(sum(not c["mandatory_negative"] for c in controls), 2)
        for c in controls:
            self.assertIn("specific_alternative_idea", c["gold"])
            self.assertIn("falsifiable_test_plan", c["gold"])
            self.assertIn("useful_internal_initiative", c["gold"])
            if c["mandatory_negative"]:
                self.assertEqual(c["gold"]["specific_alternative_idea"], [0])
                self.assertEqual(c["gold"]["falsifiable_test_plan"], [0])
        self.assertIn("IMPORTANT INSTRUCTION", controls[-1]["second"])

    def test_calibration_marks_false_positive_as_failure(self):
        bad = score(specific_alternative_idea=2)
        self.assertFalse(r6.calibration_check({"score": bad}, self.p["calibration_controls"][0]))
        self.assertTrue(r6.calibration_check({"score": score()}, self.p["calibration_controls"][0]))
        self.assertFalse(r6.calibration_check({"score": None}, self.p["calibration_controls"][0]))

    def test_quotes_must_be_real_and_reasons_meaningful(self):
        second = "A hidden clock might drive both sensors. Run the saved simulator comparison."
        good = score(specific_alternative_idea=2, evidence_quote="A hidden clock might drive both sensors.")
        self.assertEqual(r6.validate_score(good, second)["specific_alternative_idea"], 2)
        with self.assertRaisesRegex(ValueError, "EVIDENCE_QUOTE_NOT_IN"):
            r6.validate_score(score(specific_alternative_idea=2, evidence_quote="Invented evidence that was never written."), second)
        with self.assertRaisesRegex(ValueError, "EVIDENCE_QUOTE_MISSING"):
            r6.validate_score(score(specific_alternative_idea=2), second)
        with self.assertRaisesRegex(ValueError, "REASON_TOO_SHORT"):
            r6.validate_score(score(brief_reason="no evidence"), second)

    def test_ordinal_agreement_kappa_and_degenerate_chance(self):
        match = r6.ordinal_agreement([0, 0, 1, 2], [0, 0, 1, 2])
        self.assertEqual(match["cohens_kappa"], 1)
        self.assertEqual(match["linear_weighted_kappa"], 1)
        self.assertEqual(match["exact_agreement"], 1)
        self.assertEqual(match["rated_pairs"], 4)
        self.assertIsNone(r6.ordinal_agreement([0, 0], [0, 0])["cohens_kappa"])
        mismatch = r6.ordinal_agreement([0, 2], [2, 0])
        self.assertEqual(mismatch["disagreements"], 2)
        self.assertEqual(mismatch["confusion_matrix"], [[0, 0, 1], [0, 0, 0], [1, 0, 0]])

    def test_proposal_agreement_undefined_when_no_variance(self):
        self.assertIsNone(r6.proposal_agreement([False, False], [False, False])["cohens_kappa"])
        self.assertEqual(r6.proposal_agreement([False, True], [False, True])["cohens_kappa"], 1)

    def test_exact_digest_name_and_prefix(self):
        d = "b92b218582c5" + "2" * 52
        with patch.object(r6, "http_json", return_value={"models": [{"name": self.p["judge_model"], "digest": d}]}):
            self.assertEqual(r6.exact_model_digest("http://127.0.0.1:11434", self.p), d)
        with patch.object(r6, "http_json", return_value={"models": [{"name": self.p["judge_model"], "digest": "0" * 64}]}):
            with self.assertRaisesRegex(ValueError, "DIGEST_MISMATCH"):
                r6.exact_model_digest("http://127.0.0.1:11434", self.p)

    def test_identical_blind_ids_required_before_agreement(self):
        a = {"scores": [{"blind_id": f"R3-{i:020x}", "score": {"specific_alternative_idea": 0,
                "falsifiable_test_plan": 0, "cross_cycle_semantic_continuity": 1,
                "useful_internal_initiative": 0, "unexecuted_action_proposal": False}} for i in range(44)]}
        b = [{"blind_id": item["blind_id"], "score": item["score"]} for item in a["scores"]]
        self.assertEqual(r6.agreement_with_r5(a, b)["matching_blind_ids"], 44)
        self.assertEqual(r6.agreement_with_r5(a, b)["specific_alternative_idea"]["rated_pairs"], 44)
        b.pop()
        with self.assertRaisesRegex(ValueError, "ID_SET_MISMATCH"):
            r6.agreement_with_r5(a, b)

    def test_strict_r5_lock_sha_mismatch(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "r5.json"
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "SHA_MISMATCH"):
                r6.read_r5_lock(path, self.p["prior_r5_score_lock"])


if __name__ == "__main__":
    unittest.main()
