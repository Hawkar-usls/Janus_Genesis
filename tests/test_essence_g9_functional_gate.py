"""G9 Genesis frozen functional gate: synthetic unit tests do not run neural inference."""
from __future__ import annotations
from pathlib import Path
import copy
import unittest

from tools import essence_g9_functional_gate as g

ROOT=Path(__file__).resolve().parents[1]


def provenance():
    return {
      "source_repositories":["Hawkar-usls/Janus-Demiurge","Hawkar-usls/Janus_Genesis"],
      "generation":9,
      "parent_generation":8,
      "research_only":True,
      "production_promotion":False,
      "suite_git_blob_sha1":g.SUITE_BLOB,
      "legacy_git_blob_sha1":g.LEGACY_BLOB,
      "model_adapter_sha256":{"G3":g.REFERENCE["G3"],"G8":g.REFERENCE["G8"],"G9":"f"*64},
      "real_cpu_qwen_inference":True,
      "weights_sealed_before_holdout_opened":True,
      "heldout_used_in_training":False,
      "source_commits_verified":True,
    }


def output(known):
    cases=g.read_suite(ROOT)
    return [{"id":c["id"],"response":c["expected"] if c["id"] in known else "INVALID_ANSWER"}
            for c in cases]


class G9FunctionalRecovery(unittest.TestCase):
    def test_freeze_16_plus_48_cases_no_mutation(self):
        cases=g.read_suite(ROOT)
        self.assertEqual(len(cases),64)
        self.assertEqual(len({c["id"] for c in cases}),64)
        self.assertEqual(sum(c["id"].startswith("G9-") for c in cases),48)

    def test_fair_three_way_gain_requires_preserving_parent_union(self):
        tasks=[r["id"] for r in g.read_suite(ROOT)]
        g3=set(tasks[:5])
        g8=set(tasks[2:6])
        child=g3|g8|set(tasks[6:8])
        result=g.score(ROOT,{"G3":output(g3),"G8":output(g8),"G9":output(child)},provenance())
        self.assertEqual(result["status"],"ELIGIBLE_FOR_INDEPENDENT_REVIEW_NOT_PRODUCTION")
        self.assertEqual(result["newly_correct_beyond_either_parent"],2)
        self.assertEqual(result["previously_correct_by_either_parent_lost"],0)
        self.assertTrue(result["eligible_for_research_review"])
        self.assertFalse(result["accepted_into_essence_ledger"])
        self.assertFalse(result["production_promotion"])
        self.assertFalse(result["actual_external_independent_validation"])

    def test_child_losing_one_previously_correct_is_hold_even_when_total_high(self):
        tasks=[r["id"] for r in g.read_suite(ROOT)]
        result=g.score(ROOT,{"G3":output(set(tasks[:5])),
                             "G8":output(set(tasks[2:6])),
                             "G9":output(set(tasks[1:15]))},provenance())
        self.assertEqual(result["status"],"HOLD_G9_FUNCTIONAL_RECOVERY_NOT_PROVEN")
        self.assertGreater(result["previously_correct_by_either_parent_lost"],0)
        self.assertFalse(result["eligible_for_research_review"])

    def test_identical_to_g8_is_not_improvement(self):
        cases=g.read_suite(ROOT)
        tasks=set(r["id"] for r in cases[:5])
        result=g.score(ROOT,{m:output(tasks) for m in g.MODELS},provenance())
        self.assertFalse(result["eligible_for_research_review"])

    def test_one_new_correct_is_not_enough(self):
        tasks=[r["id"] for r in g.read_suite(ROOT)]
        g3=set(tasks[:5]);g8=set(tasks[2:6]);child=g3|g8|set(tasks[6:7])
        r=g.score(ROOT,{"G3":output(g3),"G8":output(g8),"G9":output(child)},provenance())
        self.assertFalse(r["eligible_for_research_review"])
        self.assertEqual(r["newly_correct_beyond_either_parent"],1)

    def test_cannot_claim_training_on_heldout_or_fake_external_acceptance(self):
        p=provenance();p["heldout_used_in_training"]=True
        with self.assertRaisesRegex(ValueError,"G9_REAL_FIRST_LOOK"):
            g.score(ROOT,{m:output(set()) for m in g.MODELS},p)
        p=provenance();p["production_promotion"]=True
        with self.assertRaisesRegex(ValueError,"G9_LINEAGE_OR_AUTHORITY"):
            g.score(ROOT,{m:output(set()) for m in g.MODELS},p)

    def test_missing_cases_and_duplicate_answer_fail_closed(self):
        p=provenance();rows={m:output(set()) for m in g.MODELS}
        rows["G9"].pop()
        with self.assertRaisesRegex(ValueError,"G9_INCOMPLETE"):
            g.score(ROOT,rows,p)
        rows={m:output(set()) for m in g.MODELS}
        rows["G3"][-1]["id"]=rows["G3"][0]["id"]
        with self.assertRaisesRegex(ValueError,"G9_INVALID_MODEL_OUTPUT"):
            g.score(ROOT,rows,p)

    def test_adapter_identity_cannot_equal_parent(self):
        p=provenance();p["model_adapter_sha256"]["G9"]=p["model_adapter_sha256"]["G8"]
        with self.assertRaisesRegex(ValueError,"G9_NOT_DISTINCT"):
            g.check_provenance(p)

    def test_no_duplicate_or_unexpected_model_names(self):
        with self.assertRaisesRegex(ValueError,"G9_EXPECT_THREE_REAL"):
            g.score(ROOT,{"G3":output(set()),"G9":output(set())},provenance())

    def test_same_owner_is_never_external_proof(self):
        t=[r["id"] for r in g.read_suite(ROOT)]
        out=g.score(ROOT,{"G3":output(set(t[:4])),"G8":output(set(t[:6])),"G9":output(set(t[:9]))},provenance())
        self.assertTrue(out["eligible_for_research_review"])
        self.assertFalse(out["actual_external_independent_validation"])
        self.assertEqual(out["scope"],"SAME_OWNER_CROSS_REPO_INTERNAL_FIRST_LOOK_ONLY")


if __name__=="__main__":
    unittest.main()
