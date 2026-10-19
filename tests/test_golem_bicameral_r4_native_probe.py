"""Adversarial R4A pilot tests; all mocked native calls are tagged synthetic."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from janus_corpus_callosum import NATIVE_ID, sha256
from golem_bicameral_r4_native_probe import (
    R4Error, PINNED, parse_choice, probe, verify_public_pilot, format_prompt
)

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "benchmarks/golem_r4_native_cpu_pilot.json"
KEY_PATH = ROOT / "benchmarks/golem_r4_native_cpu_pilot_key.json"


class NativeR4PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(PACK_PATH.read_text())
        cls.key = json.loads(KEY_PATH.read_text())

    def native_stub(self, repo, head, prompt):
        return {
            "hemisphere": "NATIVE",
            "model": NATIVE_ID,
            "source_repository": "Hawkar-usls/Janus-Demiurge",
            "source_commit": PINNED,
            "checkpoint_sha256": "b" * 64,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "generated_text": "ALLOW",
            "inference_attested_by": "PINNED_LOCAL_SUBPROCESS",
            "external_llm": False,
        }

    def exercise(self, **kwargs):
        with tempfile.TemporaryDirectory() as temp:
            return probe(self.pack, self.key, Path(temp), execute=True,
                         native_runner=kwargs.pop("native_runner", self.native_stub),
                         **kwargs)

    def test_exact_pack_balanced_and_bounded(self):
        snap = verify_public_pilot(self.pack, self.key)
        self.assertEqual(snap["cases"], 12)
        for task in self.pack["tasks"]:
            self.assertLessEqual(len(format_prompt(task).encode("utf-8")), 96)

    def test_unconfigured_is_no_inference_or_fake_zeros(self):
        result = probe(self.pack, self.key)
        self.assertEqual(result["status"], "R4_NATIVE_CPU_NOT_EXECUTED")
        self.assertIsNone(result["native_score"])
        self.assertIsNone(result["external"]["score"])
        self.assertIsNone(result["bicameral"]["score"])

    def test_strict_labels_and_abstentions(self):
        self.assertEqual(parse_choice("ALLOW"), "ALLOW")
        self.assertEqual(parse_choice("DENY."), "DENY")
        self.assertEqual(parse_choice(" UNKNOWN "), "UNKNOWN")
        for value in ["perhaps ALLOW", "allow", "ALLOWED", "", "both ALLOW DENY"]:
            self.assertEqual(parse_choice(value), "ABSTAIN")

    def test_mock_native_never_impersonates_real_baseline(self):
        result = self.exercise()
        self.assertEqual(result["status"], "R4_SYNTHETIC_NATIVE_PROBE__NOT_EVIDENCE")
        self.assertEqual(result["source_type"], "TEST_FIXTURE__NOT_REAL_NATIVE")
        self.assertFalse(result["native_score"]["actual_native_inference_verified"])
        self.assertEqual(result["native_score"]["denominator"], 12)
        self.assertFalse(result["comparative_superiority_admitted"])
        self.assertEqual(result["provider_calls_performed"], 0)
        self.assertEqual(result["external"]["status"], "NOT_EXECUTED_NO_FREE_PROVIDER")

    def test_prevent_answer_leakage_into_native_prompt(self):
        seen = []
        def checked(repo, head, prompt):
            seen.append(prompt)
            self.assertFalse("REFERENCE=" in prompt)
            return self.native_stub(repo, head, prompt)
        self.exercise(native_runner=checked)
        self.assertEqual(len(seen), 12)
        self.assertEqual(len(set(seen)), 12)

    def test_abstentions_remain_wrong_in_fixed_denominator(self):
        def gibberish(repo, head, prompt):
            answer = self.native_stub(repo, head, prompt)
            answer["generated_text"] = "!!! Not a label."
            return answer
        result = self.exercise(native_runner=gibberish)
        self.assertEqual(result["native_score"]["correct"], 0)
        self.assertEqual(result["native_score"]["abstentions"], 12)
        self.assertEqual(result["native_score"]["denominator"], 12)

    def test_native_subprocess_failure_is_incomplete_not_zero(self):
        count = [0]
        def crashing(repo, head, prompt):
            count[0] += 1
            if count[0] == 3:
                raise OSError("simulated CPU crash")
            return self.native_stub(repo, head, prompt)
        result = self.exercise(native_runner=crashing)
        self.assertEqual(result["status"], "R4_NATIVE_CPU_INCOMPLETE_RUNTIME_FAILURE")
        self.assertIsNone(result["native_score"])
        self.assertEqual(len(result["records"]), 2)

    def test_mid_run_native_weights_switch_never_passes(self):
        count = [0]
        def swapping(repo, head, prompt):
            count[0] += 1
            result = self.native_stub(repo, head, prompt)
            if count[0] > 1:
                result["checkpoint_sha256"] = "c" * 64
            return result
        with self.assertRaisesRegex(R4Error, "checkpoint changed"):
            self.exercise(native_runner=swapping)

    def test_forged_native_commit_cannot_be_scored(self):
        def forged(repo, head, prompt):
            value = self.native_stub(repo, head, prompt)
            value["source_commit"] = "a" * 40
            return value
        result = self.exercise(native_runner=forged)
        self.assertEqual(result["status"], "R4_NATIVE_CPU_INCOMPLETE_RUNTIME_FAILURE")
        self.assertIsNone(result["native_score"])

    def test_gold_reference_mutation_changes_digest(self):
        changed = copy.deepcopy(self.key)
        changed["answers"]["GW01"] = "DENY"
        original = verify_public_pilot(self.pack, self.key)
        altered = verify_public_pilot(self.pack, changed)
        self.assertNotEqual(original["reference_sha256"], altered["reference_sha256"])

    def test_mislabeled_blind_holdout_refused(self):
        changed = copy.deepcopy(self.pack)
        changed["split"] = "HIDDEN"
        with self.assertRaisesRegex(R4Error, "untrusted public"):
            probe(changed, self.key)

    def test_duplicate_and_too_long_cases_fail_closed(self):
        changed = copy.deepcopy(self.pack)
        changed["tasks"][1]["id"] = changed["tasks"][0]["id"]
        with self.assertRaisesRegex(R4Error, "duplicated"):
            verify_public_pilot(changed, self.key)
        changed = copy.deepcopy(self.pack)
        changed["tasks"][0]["prompt"] = "A" * 120
        with self.assertRaises(R4Error):
            verify_public_pilot(changed, self.key)

    def test_missing_reference_answer_fails_closed(self):
        changed = copy.deepcopy(self.key)
        changed["answers"].pop("GW01")
        with self.assertRaisesRegex(R4Error, "reference answers"):
            verify_public_pilot(self.pack, changed)

    def test_wrong_native_git_commit_refused_even_with_stub(self):
        with self.assertRaisesRegex(R4Error, "immutable CPU source pin"):
            self.exercise(native_head="f" * 40)


if __name__ == "__main__":
    unittest.main()
