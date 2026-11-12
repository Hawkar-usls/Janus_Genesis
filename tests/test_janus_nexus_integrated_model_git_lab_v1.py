"""Fail-closed offline tests for the #162 scoped native-output Git handoff."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.janus_nexus_integrated_model_git_lab_v1 import (
    Hold, PROMPT, make_a, make_b, make_variants, proposal,
    receiver_receipt, run_path, source_witness, validate_a, verify,
    REGISTRY_SOURCE_RUN, REGISTRY_SOURCE_SHA, REGISTRY_SCHEMA,
)

RUN = "43261015476"
ATTEMPT = 1
CODE = "a" * 40
A_HEAD = "b" * 40
B_HEAD = "c" * 40
RAW_A = (PROMPT + " Candidate alpha has three useful public words.\n").encode()
RAW_B = (PROMPT + " Candidate beta proposes a second public variation!\n").encode()


def registry():
    return {
        "schema": REGISTRY_SCHEMA,
        "status": "PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE",
        "source_run_id": REGISTRY_SOURCE_RUN,
        "source_commit": REGISTRY_SOURCE_SHA,
        "actual_cross_organ_runtime_execution_attested": False,
        "full_issue_162_acceptance": False,
    }


class IntegratedNativeGitLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.witness = registry()

    def prepare(self):
        return make_a(self.root, RUN, ATTEMPT, CODE, self.witness, RAW_A, RAW_B)

    def base(self):
        return run_path(self.root, RUN, ATTEMPT)

    def test_two_actual_distinct_model_suffixes_and_retained_loser(self):
        a = self.prepare()
        _, state, variants = validate_a(self.root, RUN, ATTEMPT, self.witness)
        self.assertEqual(variants["model_generated_count"], 2)
        self.assertEqual(len(variants["candidates"]), 2)
        self.assertEqual(len(variants["rejected_variant_ids_retained"]), 1)
        self.assertNotEqual(variants["candidates"][0]["proposal"]["proposal_sha256"],
                            variants["candidates"][1]["proposal"]["proposal_sha256"])
        self.assertEqual(a["checkpoint_digest"], __import__(
            "tools.janus_nexus_integrated_model_git_lab_v1",
            fromlist=["digest"]).digest(state))
        self.assertFalse(variants["code_patch_generated_or_tested"])
        self.assertEqual(state["fence_epoch"], 1)
        self.assertFalse(state["source_witness"]["same_run_real44_materialized"])

    def test_git_handoff_reconstruction_and_idempotence(self):
        self.prepare()
        self.assertEqual(make_b(self.root, RUN, ATTEMPT, self.witness, A_HEAD),
                         "COMPLETED_NEW")
        self.assertEqual(make_b(self.root, RUN, ATTEMPT, self.witness, A_HEAD),
                         "IDEMPOTENT_EXISTING")
        receipt = verify(self.root, RUN, ATTEMPT, self.witness, A_HEAD, B_HEAD)
        self.assertEqual(receipt["status"], "PASS_SCOPED_NATIVE_MODEL_GIT_A_B_LAB_ONLY")
        self.assertTrue(receipt["lab_receiver_evaluation_executed"])
        self.assertFalse(receipt["production_receiver_ack"])
        self.assertFalse(receipt["live_lease_race_tested"])
        self.assertFalse(receipt["g1_g20_same_run_full_pass"])
        self.assertFalse(receipt["full_issue_162_acceptance"])
        self.assertEqual(receipt["authority_delta"], 0)
        self.assertEqual({p.name for p in self.base().iterdir()}, {
            "variants.json", "checkpoint.json", "worker-a.json",
            "worker-b.json", "receiver.json",
        })

    def test_conflicting_replay_and_fence_rejected(self):
        self.prepare()
        make_b(self.root, RUN, ATTEMPT, self.witness, A_HEAD)
        with self.assertRaisesRegex(Hold, "IMMUTABLE_RECEIPT_CONFLICT"):
            make_b(self.root, RUN, ATTEMPT, self.witness, "d" * 40)
        checkpoint = self.base() / "checkpoint.json"
        obj = json.loads(checkpoint.read_text())
        obj["fence_epoch"] = 9
        checkpoint.write_text(json.dumps(obj))
        with self.assertRaises(Hold):
            make_b(self.root, RUN, ATTEMPT, self.witness, A_HEAD)

    def test_receiver_ack_forgery_is_not_independent_proof(self):
        self.prepare()
        make_b(self.root, RUN, ATTEMPT, self.witness, A_HEAD)
        path = self.base() / "receiver.json"
        obj = json.loads(path.read_text())
        obj["external_downstream_consumer_ack"] = True
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(Hold, "CONSUMER_ACK_FORGED"):
            verify(self.root, RUN, ATTEMPT, self.witness, A_HEAD, B_HEAD)

    def test_modified_generated_variant_is_rejected(self):
        self.prepare()
        path = self.base() / "variants.json"
        obj = json.loads(path.read_text())
        obj["candidates"][0]["proposal"]["text"] += " tampered"
        path.write_text(json.dumps(obj))
        with self.assertRaises(Hold):
            validate_a(self.root, RUN, ATTEMPT, self.witness)

    def test_duplicate_run_id_cannot_replace_history(self):
        self.prepare()
        with self.assertRaisesRegex(Hold, "RUN_ID_ALREADY_PRESENT_HOLD"):
            self.prepare()

    def test_public_source_archive_cannot_claim_same_run(self):
        invalid = registry()
        invalid["full_issue_162_acceptance"] = True
        with self.assertRaisesRegex(Hold, "REAL44_FALSE_AUTHORITY"):
            source_witness(invalid)
        invalid = registry()
        invalid["source_commit"] = "0" * 40
        with self.assertRaisesRegex(Hold, "REAL44_PIN_DRIFT"):
            source_witness(invalid)

    def test_missing_model_generation_and_identical_candidates_rejected(self):
        with self.assertRaises(Hold):
            proposal((PROMPT + "\n").encode())
        first = proposal(RAW_A)
        with self.assertRaisesRegex(Hold, "MODEL_OUTPUTS_IDENTICAL_HOLD"):
            make_variants([first, copy.deepcopy(first)])

    def test_secret_like_generation_and_symlink_hold(self):
        with self.assertRaisesRegex(Hold, "MODEL_PROPOSAL_SECRET_LIKE"):
            proposal((PROMPT + " ghp_" + "A" * 32 + "\n").encode())
        self.prepare()
        state = self.base() / "worker-a.json"
        state.unlink()
        state.symlink_to(self.base() / "checkpoint.json")
        with self.assertRaises(Hold):
            validate_a(self.root, RUN, ATTEMPT, self.witness)

    def test_no_command_execution_from_model_text(self):
        raw = (PROMPT + " rm -rf /; arbitrary untrusted command!\n").encode()
        candidate = proposal(raw)
        self.assertIn("rm -rf", candidate["text"])
        variants = make_variants([candidate, proposal(RAW_B)])
        self.assertTrue(all(x["unsafe_execution_attempted"] is False
                            for x in variants["candidates"]))
        self.assertFalse(variants["code_patch_generated_or_tested"])

    def test_bad_github_ids_and_claims(self):
        with self.assertRaises(Hold):
            run_path(self.root, "../oops", ATTEMPT)
        self.prepare()
        make_b(self.root, RUN, ATTEMPT, self.witness, A_HEAD)
        with self.assertRaisesRegex(Hold, "GIT_A_B_HEADS_INVALID"):
            verify(self.root, RUN, ATTEMPT, self.witness, A_HEAD, A_HEAD)


if __name__ == "__main__":
    unittest.main()
