"""Real pinned CPU Demiurge + fake external GOLEM + local bare-Git HOME tests.

This is *not* a hosted model / live external API test. A separate checkout at
a reviewed immutable Demiurge SHA is required. CI sets REQUIRE_REAL_NATIVE=1,
so missing setup fails instead of silently skipping. All model receipts are
written to a disposable local bare Git repository, never production HOME.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from janus_corpus_callosum import _safe_native_env, bridge
from janus_corpus_git_publisher import publish
from janus_corpus_home_handoff import attest, protected_snapshot
from tests.test_janus_corpus_git_publisher import GitPublisherTests, git


# Source code is reviewed at this immutable PR commit. This SHA contains
# weights_only=True; it is not an automatic endorsement or promotion of PR #301.
REVIEWED_DEMIURGE_SHA = "8873e5121a67daac5c8afb8ff297d6565dc87c32"


class RealNativeBicameralCPU(unittest.TestCase):
    def setUp(self):
        directory = os.environ.get("JANUS_NATIVE_DEMIURGE_CHECKOUT")
        required = os.environ.get("JANUS_REQUIRE_REAL_NATIVE") == "1"
        if not directory:
            if required:
                self.fail("REAL_NATIVE_CPU_SMOKE_NOT_CONFIGURED")
            self.skipTest("pin native checkout to run opt-in CPU integration")
        self.native_repo = Path(directory).resolve()
        self.assertEqual(git("-C", self.native_repo, "rev-parse", "HEAD"),
                         REVIEWED_DEMIURGE_SHA, "native code must be pinned")
        self.assertEqual(git("-C", self.native_repo, "status", "--porcelain"),
                         "", "native repo must be clean")
        checkpoint = self.native_repo / "janus_model/checkpoints/promoted.pt"
        self.assertTrue(checkpoint.is_file())
        self.checkpoint_before = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        self.assertEqual(len(self.checkpoint_before), 64)
        self.scenario = GitPublisherTests(
            methodName="test_real_git_commit_and_clean_worker_b_replay")
        self.scenario.setUp()
        self.addCleanup(self.scenario.doCleanups)
        self.home = self.scenario.home
        self.core_before = protected_snapshot(self.home)
        self.assertEqual(self.core_before, self.scenario.baseline)

    def _assert_recovered(self, name, expected_state, expect_external):
        pushed = publish(self.scenario.worker, baseline=self.core_before,
                         expected_native_head=REVIEWED_DEMIURGE_SHA)
        self.assertEqual(pushed["status"],
                         "BICAMERAL_RECEIPT_COMMITTED__NOT_MODEL_TRUTH")
        fresh = self.scenario.fresh_clone(name)
        recovered = attest(fresh / "state/habitat_cloud_home",
                           baseline=self.core_before, require_receipt=True,
                           expected_native_head=REVIEWED_DEMIURGE_SHA)
        self.assertEqual(recovered["receipt_sha256"], pushed["receipt_sha256"])
        self.assertEqual(bool(recovered["referenced_external"]), expect_external)
        self.assertFalse(recovered["ack_advanced"])
        self.assertFalse(recovered["self_modification_authorized"])
        self.assertEqual(recovered["scientific_authority_delta"], 0)
        self.assertEqual(git("-C", fresh, "rev-parse", "HEAD"), pushed["commit"])
        body = __import__("json").loads(
            (fresh / "state/habitat_cloud_home" / recovered["receipt_path"]).read_text())
        self.assertEqual(body["state"], expected_state)
        self.assertEqual(body["hemispheres"]["native"]["source_commit"],
                         REVIEWED_DEMIURGE_SHA)
        self.assertEqual(body["hemispheres"]["native"]["checkpoint_sha256"],
                         self.checkpoint_before)
        self.assertFalse(body["trained_from_external_outputs"])
        self.assertFalse(body["feedback_for_native"]["training_use_permitted"])
        self.assertEqual(protected_snapshot(self.home), self.core_before)
        self.assertEqual(hashlib.sha256(
            (self.native_repo / "janus_model/checkpoints/promoted.pt").read_bytes()
        ).hexdigest(), self.checkpoint_before)
        return body

    def test_true_cpu_native_and_mock_external_join_survive_runner_restart(self):
        # No live HTTP is permitted. A deterministic fake response exercises
        # the same provider parsing/receipt validation as the free gateway.
        with patch("urllib.request.OpenerDirector.open",
                   side_effect=AssertionError("NETWORK_REQUEST_FORBIDDEN")):
            result = bridge(
                self.home, dict(self.scenario.fixture.env), execute=True,
                native_repo=self.native_repo,
                native_head=REVIEWED_DEMIURGE_SHA,
                external_transport=self.scenario.fixture.external)
        self.assertEqual(result["status"],
                         "BICAMERAL_PAIR_OBSERVED__UNVERIFIED")
        body = self._assert_recovered(
            "clean-second-runner", "BICAMERAL_PAIR_OBSERVED__UNVERIFIED", True)
        self.assertEqual(body["hemispheres"]["external"]["provider"],
                         "openrouter-free")
        self.assertEqual(body["hemispheres"]["external"]["model_reported"],
                         "free-external")
        self.assertFalse(body["scientific_consensus_claimed"])
        self.assertNotIn("NEVER_LOG_SECRET", str(body))
        self.assertEqual(publish(self.scenario.worker, baseline=self.core_before)[
            "status"], "BICAMERAL_ALREADY_DURABLE__NO_PUSH")

    def test_external_rate_limit_keeps_real_native_and_durable_fallback(self):
        def fake_429(*_args):
            # Mimics quota or network failure; does not send requests.
            raise URLError("injected external outage")
        with patch("urllib.request.OpenerDirector.open",
                   side_effect=AssertionError("NETWORK_REQUEST_FORBIDDEN")):
            result = bridge(
                self.home, dict(self.scenario.fixture.env), execute=True,
                native_repo=self.native_repo, native_head=REVIEWED_DEMIURGE_SHA,
                external_transport=fake_429)
        self.assertEqual(result["status"], "NATIVE_ONLY__EXTERNAL_UNAVAILABLE")
        body = self._assert_recovered(
            "offline-second-runner", "NATIVE_ONLY__EXTERNAL_UNAVAILABLE", False)
        self.assertIsNone(body["hemispheres"]["external"])
        self.assertIsNotNone(body["hemispheres"]["native"])

    def test_v2_two_actual_native_cpu_passes_with_simulated_external_reply(self):
        from janus_corpus_callosum_v2 import roundtrip, attest_roundtrip
        from janus_corpus_v2_publisher import publish_v2

        seen = []
        def simulator(challenge):
            seen.append(challenge)
            return {
                "mode": "OFFLINE_SIMULATED_EXTERNAL",
                "provider": "FIXTURE_ONLY_NOT_A_REAL_PROVIDER",
                "text": "Independent mock challenges the initial speculation.",
                "stance": "DISPUTES",
                "context_sha256": challenge["context_sha256"],
                "native_initial_sha256": challenge["native_initial_sha256"],
                "observed_context_ids": challenge["observed_context_ids"][:1],
            }

        with patch("urllib.request.OpenerDirector.open",
                   side_effect=AssertionError("NETWORK_REQUEST_FORBIDDEN")):
            result = roundtrip(
                self.home, {"JANUS_BICAMERAL_V2_OFFLINE": "1"}, execute=True,
                native_repo=self.native_repo, native_head=REVIEWED_DEMIURGE_SHA,
                external_simulator=simulator)
        self.assertEqual(result["status"], "NATIVE_EXTERNAL_NATIVE__UNVERIFIED")
        self.assertEqual(len(seen), 1)
        verified = attest_roundtrip(self.home, baseline=self.core_before,
                                    expected_native_head=REVIEWED_DEMIURGE_SHA)
        body = __import__("json").loads(
            (self.home / verified["receipt_path"]).read_text())
        self.assertEqual(body["native_initial"]["checkpoint_sha256"],
                         self.checkpoint_before)
        self.assertEqual(body["native_review"]["checkpoint_sha256"],
                         self.checkpoint_before)
        self.assertNotEqual(body["native_review"]["prompt_sha256"],
                            body["native_initial"]["prompt_sha256"])
        self.assertEqual(body["disagreement"], "DISPUTE_REPORTED_NOT_ADJUDICATED")
        pushed = publish_v2(self.scenario.worker, baseline=self.core_before,
                            expected_native_head=REVIEWED_DEMIURGE_SHA)
        fresh = self.scenario.fresh_clone("v2-real-native-replay")
        check = attest_roundtrip(fresh / "state/habitat_cloud_home",
                                 baseline=self.core_before,
                                 expected_native_head=REVIEWED_DEMIURGE_SHA)
        self.assertEqual(check["receipt_sha256"], pushed["receipt_sha256"])
        self.assertEqual(hashlib.sha256(
            (self.native_repo / "janus_model/checkpoints/promoted.pt").read_bytes()
        ).hexdigest(), self.checkpoint_before)

    def test_rejected_candidate_leaves_last_verified_native_checkpoint_intact(self):
        # Distinct from a real model update/rollback: a corrupt candidate is
        # rejected; the active last verified checkpoint never changes.
        candidate = self.scenario.root / "candidate.pt"
        candidate.write_bytes(b"corrupted untrusted checkpoint")
        command = [sys.executable, "-m", "janus_model.cli", "inspect",
                   "--checkpoint", str(candidate),
                   "--expected-sha256", self.checkpoint_before]
        result = subprocess.run(command, cwd=self.native_repo,
                                env=_safe_native_env(), capture_output=True,
                                text=True, timeout=25, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("JANUS_CHECKPOINT_SHA256_MISMATCH", result.stderr)
        checkpoint = self.native_repo / "janus_model/checkpoints/promoted.pt"
        self.assertEqual(hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                         self.checkpoint_before)


if __name__ == "__main__":
    unittest.main()
