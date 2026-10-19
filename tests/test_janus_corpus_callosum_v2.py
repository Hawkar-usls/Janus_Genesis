"""Deterministic adversarial tests for sequential JANUS Corpus Callosum v2.

Only simulated external inputs. Real git push tests use a disposable local bare
remote, never GitHub HOME. Existing v1 receipt validators are not weakened.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from genesis_beetle_model_consumption import ConsumptionError
from janus_corpus_callosum import _body_hash
from janus_corpus_callosum_v2 import (
    attest_roundtrip, roundtrip, SCHEMA, _validate_external,
)
from janus_corpus_v2_publisher import publish_v2, PublicationError
from tests.test_janus_corpus_git_publisher import GitPublisherTests, git
from tests.test_janus_corpus_callosum import PINNED


class SequentialProtocolTests(unittest.TestCase):
    def setUp(self):
        self.scenario = GitPublisherTests(
            methodName="test_real_git_commit_and_clean_worker_b_replay")
        self.scenario.setUp()
        self.addCleanup(self.scenario.doCleanups)
        self.home = self.scenario.home
        self.native = self.scenario.fixture.native
        self.env = {"JANUS_BICAMERAL_V2_OFFLINE": "1"}
        self.calls = []

    def adviser(self, challenge, *, stance="DISPUTES", text="A second hypothesis"):
        self.calls.append(("external", challenge))
        return {
            "mode": "OFFLINE_SIMULATED_EXTERNAL",
            "provider": "FIXTURE_ONLY_NOT_A_REAL_PROVIDER",
            "text": text, "stance": stance,
            "context_sha256": challenge["context_sha256"],
            "native_initial_sha256": challenge["native_initial_sha256"],
            "observed_context_ids": challenge["observed_context_ids"][:1],
        }

    def native_observed(self, repo, sha, prompt):
        self.calls.append(("native", prompt))
        return self.native(repo, sha, prompt)

    def infer(self, *, external=None, native=None):
        return roundtrip(
            self.home, self.env, execute=True,
            native_repo=Path("not-executed"), native_head=PINNED,
            native_runner=native or self.native_observed,
            external_simulator=external or self.adviser)

    def read_body(self):
        result = attest_roundtrip(
            self.home, baseline=self.scenario.baseline,
            expected_native_head=PINNED)
        return json.loads((self.home / result["receipt_path"]).read_text())

    def test_real_sequence_order_and_git_durability(self):
        outcome = self.infer()
        self.assertEqual(outcome["status"], "NATIVE_EXTERNAL_NATIVE__UNVERIFIED")
        self.assertEqual([x[0] for x in self.calls], ["native", "external", "native"])
        self.assertIn("REVIEW_UNTRUSTED", self.calls[2][1])
        self.assertIn("A second hypothesis", self.calls[2][1])
        body = self.read_body()
        self.assertEqual(body["disagreement"], "DISPUTE_REPORTED_NOT_ADJUDICATED")
        self.assertEqual(body["quality"], "NOT_EVALUATED")
        self.assertFalse(body["auto_training_allowed"])
        self.assertFalse(body["ack_advanced"])
        self.assertIsNotNone(body["native_review"])
        persisted = publish_v2(self.scenario.worker,
                               baseline=self.scenario.baseline,
                               expected_native_head=PINNED)
        self.assertEqual(persisted["status"], "SEQUENTIAL_DURABLE__NOT_MODEL_TRUTH")
        fresh = self.scenario.fresh_clone("sequential-replay")
        receipt = attest_roundtrip(fresh / "state/habitat_cloud_home",
                                   baseline=self.scenario.baseline,
                                   expected_native_head=PINNED)
        self.assertEqual(receipt["receipt_sha256"], persisted["receipt_sha256"])
        self.assertEqual(git("-C", fresh, "rev-parse", "HEAD"), persisted["commit"])
        self.assertEqual(publish_v2(self.scenario.worker,
                                    baseline=self.scenario.baseline)["status"],
                         "SEQUENTIAL_ALREADY_DURABLE")

    def test_native_only_on_simulator_failure(self):
        def down(_challenge):
            self.calls.append(("external", None))
            raise OSError("injected offline failure")
        result = self.infer(external=down)
        self.assertEqual(result["status"],
                         "NATIVE_ONLY__EXTERNAL_SIMULATOR_UNAVAILABLE")
        self.assertEqual([c[0] for c in self.calls], ["native", "external"])
        body = self.read_body()
        self.assertIsNone(body["external_simulated"])
        self.assertIsNone(body["native_review"])
        self.assertEqual(body["disagreement"], "NOT_MEASURED_NO_EXTERNAL")

    def test_review_failure_is_partial_not_complete(self):
        def native(repo, sha, prompt):
            if "REVIEW_UNTRUSTED" in prompt:
                raise OSError("CPU review crashed")
            return self.native(repo, sha, prompt)
        result = self.infer(native=native)
        self.assertEqual(result["status"], "NATIVE_EXTERNAL__REVIEW_UNAVAILABLE")
        self.assertIsNone(self.read_body()["native_review"])

    def test_no_live_provider_is_possible_without_injected_simulator(self):
        with self.assertRaisesRegex(ConsumptionError, "no external simulator"):
            roundtrip(self.home, self.env, execute=True,
                      native_repo=Path("native"), native_head=PINNED)
        self.assertFalse((self.home / "corpus_callosum_v2").exists())

    def test_dry_run_and_opt_in(self):
        result = roundtrip(self.home, {}, execute=False)
        self.assertEqual(result["status"], "SEQUENTIAL_DRY_RUN_NO_INFERENCE")
        with self.assertRaisesRegex(ConsumptionError, "opt-in"):
            roundtrip(self.home, {}, execute=True,
                      native_repo=Path("native"), native_head=PINNED,
                      external_simulator=self.adviser)
        self.assertFalse((self.home / "corpus_callosum_v2").exists())

    def test_native_failure_has_no_receipt_and_no_external_call(self):
        with self.assertRaises(OSError):
            self.infer(native=lambda *_args: (_ for _ in ()).throw(OSError("native down")))
        self.assertFalse(self.calls)
        self.assertFalse((self.home / "corpus_callosum_v2").exists())

    def test_simulator_cannot_claim_live_provider(self):
        def fake_live(challenge):
            value = self.adviser(challenge)
            value["mode"] = "REAL_PROVIDER_RESPONSE"
            return value
        result = self.infer(external=fake_live)
        self.assertEqual(result["status"], "NATIVE_ONLY__EXTERNAL_SIMULATOR_UNAVAILABLE")

    def test_no_false_consensus_if_simulated_external_supports(self):
        self.infer(external=lambda challenge: self.adviser(challenge, stance="SUPPORTS"))
        self.assertEqual(self.read_body()["disagreement"],
                         "NO_DISPUTE_REPORTED_NOT_CONSENSUS")

    def test_external_native_hash_spoof_rejected(self):
        def forged(challenge):
            value = self.adviser(challenge)
            value["native_initial_sha256"] = "f" * 64
            return value
        result = self.infer(external=forged)
        self.assertEqual(result["status"], "NATIVE_ONLY__EXTERNAL_SIMULATOR_UNAVAILABLE")

    def test_recomputed_receipt_hash_cannot_hide_wrong_review(self):
        outcome = self.infer()
        path = Path(outcome["receipt_path"])
        doc = json.loads(path.read_text())
        doc["native_review"]["generated_text"] = "forged"
        doc["receipt_sha256"] = _body_hash(doc)
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ConsumptionError, "lineage mismatch"):
            attest_roundtrip(self.home)

    def test_protected_state_mutation_blocks_durable_publication(self):
        self.infer()
        state = self.home / "STATE.json"
        state.write_text(state.read_text() + "\n")
        with self.assertRaisesRegex(ConsumptionError, "protected HOME state changed"):
            publish_v2(self.scenario.worker, baseline=self.scenario.baseline)

    def test_crash_before_push_not_durable(self):
        self.infer()
        with self.assertRaisesRegex(PublicationError, "before sequential push"):
            publish_v2(self.scenario.worker,
                       baseline=self.scenario.baseline, interrupt_at="after_commit")
        fresh = self.scenario.fresh_clone("before-crash")
        self.assertFalse((fresh / "state/habitat_cloud_home/corpus_callosum_v2").exists())

    def test_crash_after_push_recovers_from_independent_clone(self):
        self.infer()
        with self.assertRaisesRegex(PublicationError, "after sequential push"):
            publish_v2(self.scenario.worker,
                       baseline=self.scenario.baseline, interrupt_at="after_push")
        fresh = self.scenario.fresh_clone("after-crash")
        self.assertEqual(attest_roundtrip(
            fresh / "state/habitat_cloud_home")["status"],
            "SEQUENTIAL_RECEIPT_VALIDATED_NOT_TRUTH")

    def test_remote_move_fails_closed(self):
        self.infer()
        other = self.scenario.fresh_clone("concurrent")
        (other / "outside.txt").write_text("other worker")
        git("-C", other, "add", "outside.txt")
        git("-C", other, "-c", "user.name=test",
            "-c", "user.email=test@example.invalid",
            "commit", "-m", "concurrent HOME update")
        git("-C", other, "push", "origin",
            "HEAD:refs/heads/janus/habitat-cloud-state")
        with self.assertRaisesRegex(PublicationError, "remote moved"):
            publish_v2(self.scenario.worker, baseline=self.scenario.baseline)


if __name__ == "__main__":
    unittest.main()
