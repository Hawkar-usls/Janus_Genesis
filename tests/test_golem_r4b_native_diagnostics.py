"""R4B fixture-only protocol tests: fake runners MUST NOT become real measurements."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from janus_corpus_callosum import NATIVE_ID
from golem_r4b_native_diagnostics import (
    run_diagnostics, validate, measured_excerpt, R4BDiagnosticError,
    PACK_SCHEMA, KEY_SCHEMA,
)
from golem_bicameral_r4_native_probe import PINNED

ROOT = Path(__file__).resolve().parents[1]
PACK = json.loads((ROOT / "benchmarks/golem_r4b_public_diagnostics.json").read_text())
KEY = json.loads((ROOT / "benchmarks/golem_r4b_public_diagnostics_key.json").read_text())


class R4BDiagnosticsTests(unittest.TestCase):
    def native(self, repo, sha, prompt):
        output = "YES" if "YES" in prompt else (
            "NO" if "NO" in prompt else "a bounded continuation")
        return {
            "hemisphere": "NATIVE", "model": NATIVE_ID,
            "source_repository": "Hawkar-usls/Janus-Demiurge",
            "source_commit": PINNED, "checkpoint_sha256": "d" * 64,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "generated_text": output, "inference_attested_by": "PINNED_LOCAL_SUBPROCESS",
            "external_llm": False,
        }

    def run_fixture(self, native=None):
        with tempfile.TemporaryDirectory() as temp:
            return run_diagnostics(PACK, KEY, Path(temp), execute=True,
                                   native_runner=native or self.native)

    def test_frozen_public_pilot_three_independent_strata(self):
        meta = validate(PACK, KEY)
        self.assertEqual(meta["tasks"], 9)
        self.assertEqual(set(meta["strata"].values()), {3})
        self.assertTrue(meta["public_only"])

    def test_dry_run_wont_invent_scores(self):
        r = run_diagnostics(PACK, KEY)
        self.assertEqual(r["status"], "R4B_NOT_EXECUTED")
        self.assertIsNone(r["groups"])
        self.assertEqual(r["external"], "NOT_EXECUTED")

    def test_fixture_is_never_real_cpu_evidence(self):
        r = self.run_fixture()
        self.assertEqual(r["status"], "R4B_SYNTHETIC_NATIVE_DIAGNOSTIC__NOT_EVIDENCE")
        self.assertEqual(r["source_type"], "TEST_FIXTURE__NOT_REAL_CPU")
        self.assertEqual(len(r["records"]), 9)
        self.assertFalse(r["improvement_claim_admitted"])
        self.assertFalse(r["raw_generated_text_is_training_data"])
        self.assertEqual(r["groups"]["CONTINUATION"]["exact_matches"], None)
        self.assertEqual(r["groups"]["INSTRUCTION"]["tasks"], 3)

    def test_model_failure_does_not_score_remaining_tasks_as_wrong(self):
        count = [0]
        def stop(repo, sha, prompt):
            count[0] += 1
            if count[0] == 2:
                raise OSError("simulated crash")
            return self.native(repo, sha, prompt)
        r = self.run_fixture(native=stop)
        self.assertEqual(r["status"], "R4B_INCOMPLETE_NATIVE_FAILURE")
        self.assertIsNone(r["groups"])
        self.assertEqual(len(r["records"]), 1)

    def test_midstream_checkpoint_mutation_fails_closed(self):
        count = [0]
        def mutated(repo, sha, prompt):
            count[0] += 1
            value = self.native(repo, sha, prompt)
            if count[0] >= 2:
                value["checkpoint_sha256"] = "f" * 64
            return value
        with self.assertRaisesRegex(R4BDiagnosticError, "checkpoint changed"):
            self.run_fixture(native=mutated)

    def test_raw_excerpt_is_bounded_and_control_chars_scrubbed(self):
        text = "A" * 180 + "\x00B"
        excerpt = measured_excerpt(text)
        self.assertEqual(len(excerpt), 160)
        self.assertNotIn("\x00", excerpt)
        self.assertEqual(measured_excerpt("a\x00b"), "a\uFFFDb")

    def test_prompt_drift_or_answer_key_drift_refused(self):
        bad = copy.deepcopy(PACK)
        bad["prompts"][0]["prompt"] = "X" * 128
        with self.assertRaises(R4BDiagnosticError):
            validate(bad, KEY)
        bad_key = copy.deepcopy(KEY)
        bad_key["expected"]["IN01"] = "MAYBE"
        with self.assertRaisesRegex(R4BDiagnosticError, "instruction key"):
            validate(PACK, bad_key)

    def test_retrofit_r4a_label_is_not_admitted(self):
        altered = copy.deepcopy(PACK)
        altered["split"] = "PUBLIC_NATIVE_CPU_PILOT_NOT_HOLDOUT"
        with self.assertRaisesRegex(R4BDiagnosticError, "invalid R4B"):
            validate(altered, KEY)

    def test_wrong_native_source_is_reported_incomplete(self):
        def forged(repo, sha, prompt):
            value = self.native(repo, sha, prompt)
            value["source_commit"] = "a" * 40
            return value
        r = self.run_fixture(native=forged)
        self.assertEqual(r["status"], "R4B_INCOMPLETE_NATIVE_FAILURE")


if __name__ == "__main__":
    unittest.main()
