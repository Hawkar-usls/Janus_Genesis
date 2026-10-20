"""No-network AURA Oracle ↔ Corpus v2 tests, with separate real-repo CI gate."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from genesis_beetle_model_consumption import ConsumptionError, compact, sha256
from janus_corpus_callosum import _body_hash, _safe_native_env
from janus_corpus_callosum_v2 import roundtrip
from janus_corpus_home_handoff import protected_snapshot
from janus_corpus_aura_oracle import (
    AURA_HEAD, attest_oracle, consult_oracle, real_local_aura,
)
from tests.test_janus_corpus_callosum import PINNED
from tests.test_janus_corpus_git_publisher import GitPublisherTests


class CorpusAuraTests(unittest.TestCase):
    def setUp(self):
        self.fixture = GitPublisherTests(
            methodName="test_real_git_commit_and_clean_worker_b_replay")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home = self.fixture.home
        self.baseline = protected_snapshot(self.home)
        self.calls = 0
        def external(challenge):
            return {
                "mode": "OFFLINE_SIMULATED_EXTERNAL",
                "provider": "FIXTURE_ONLY_NOT_A_REAL_PROVIDER",
                "text": "Which independent witness would challenge the first idea?",
                "stance": "DISPUTES",
                "context_sha256": challenge["context_sha256"],
                "native_initial_sha256": challenge["native_initial_sha256"],
                "observed_context_ids": challenge["observed_context_ids"][:1],
            }
        v2 = roundtrip(self.home, {"JANUS_BICAMERAL_V2_OFFLINE": "1"},
                       execute=True, native_repo=Path("test-only"),
                       native_head=PINNED, native_runner=self.fixture.fixture.native,
                       external_simulator=external)
        self.assertEqual(v2["status"], "NATIVE_EXTERNAL_NATIVE__UNVERIFIED")

    def fake_oracle(self, _repo, _sha, req):
        self.calls += 1
        return {
            "schema": "aura.oracle.shabitat_heuristic_response.v1",
            "status": "HEURISTIC_ONLY",
            "request_id": req["request_id"],
            "engine": "AURA_SHABITAT_REFLECTIVE_V1",
            "deterministic_request_sha256": sha256(compact(req)),
            "cards": [{
                "id": "THREAD", "name": "Thread",
                "lens": "Trace provenance",
                "question": "What independent source can verify it?",
                "caution": "Repeated claims are not proof.",
            }],
            "heuristics": ["Seek a separate independent control."],
            "questions": ["What would disconfirm the claim?"],
            "cautions": ["Symbolic cards are not evidence."],
            "decision_authority": "CALLER_RETAINS_CHOICE",
            "permission_granted": False, "evidence_upgrade": False,
            "verification_claim": False, "prediction_claim": False,
            "professional_advice": False, "world_effect_requested": False,
            "authority_delta": 0, "mass_effect_budget_delta": 0,
            "may_be_ignored": True,
            "claim_ceiling":
            "AURA_HEURISTIC_IS_REFLECTIVE_INPUT_NOT_EVIDENCE_COMMAND_PERMISSION_OR_PREDICTION",
        }

    def consult(self, runner=None):
        return consult_oracle(
            self.home, {"JANUS_CORPUS_AURA_ENABLED": "1"},
            execute=True, aura_repo=Path("/test-only"),
            aura_head=AURA_HEAD, native_head=PINNED,
            oracle_runner=runner or self.fake_oracle)

    def test_dry_run_never_executes_aura(self):
        result = consult_oracle(self.home, {}, execute=False)
        self.assertEqual(result["status"], "AURA_REFLECTIVE_PEER_DRY_RUN_NO_PROCESS")
        self.assertEqual(self.calls, 0)
        self.assertFalse((self.home / "corpus_aura_oracle").exists())

    def test_v2_receipt_bind_and_no_reexecution(self):
        result = self.consult()
        self.assertEqual(result["oracle_source_type"], "MOCKED_AURA_TEST_ONLY")
        witness = attest_oracle(self.home, baseline=self.baseline,
                                native_head=PINNED)
        content = json.loads(Path(witness["path"]).read_text())
        self.assertEqual(content["oracle_commit"], AURA_HEAD)
        self.assertEqual(content["oracle"]["cards"][0]["id"], "THREAD")
        self.assertFalse(content["oracle_is_model"])
        self.assertFalse(content["forecast_claimed"])
        self.assertEqual(content["scientific_authority_delta"], 0)
        self.assertFalse(content["ack_advanced"])
        self.assertEqual(protected_snapshot(self.home), self.baseline)
        again = self.consult(runner=lambda *_: self.fail("should not run twice"))
        self.assertEqual(again["status"], "AURA_ALREADY_RECEIPTED_NO_REEXECUTION")
        self.assertEqual(self.calls, 1)

    def test_no_opt_in_no_receipt(self):
        with self.assertRaisesRegex(ConsumptionError, "OPT_IN"):
            consult_oracle(self.home, {}, execute=True,
                           aura_repo=Path("."), oracle_runner=self.fake_oracle)
        self.assertFalse((self.home / "corpus_aura_oracle").exists())

    def test_wrong_source_pin_refused(self):
        with self.assertRaisesRegex(ConsumptionError, "OPT_IN_AND_PINNED"):
            consult_oracle(self.home, {"JANUS_CORPUS_AURA_ENABLED": "1"},
                           execute=True, aura_repo=Path("."),
                           aura_head="f"*40, oracle_runner=self.fake_oracle)

    def test_authority_claim_fails_closed(self):
        def forged(repo, head, req):
            doc = self.fake_oracle(repo, head, req)
            doc["permission_granted"] = True
            return doc
        with self.assertRaisesRegex(Exception, "FALSE_REQUIRED"):
            self.consult(forged)
        self.assertFalse((self.home / "corpus_aura_oracle").exists())

    def test_forecast_claim_fails_closed(self):
        def forged(repo, head, req):
            doc = self.fake_oracle(repo, head, req)
            doc["prediction_claim"] = True
            return doc
        with self.assertRaisesRegex(Exception, "FALSE_REQUIRED"):
            self.consult(forged)

    def test_wrong_request_hash_fails_closed(self):
        def forged(repo, head, req):
            doc = self.fake_oracle(repo, head, req)
            doc["deterministic_request_sha256"] = "f"*64
            return doc
        with self.assertRaisesRegex(ConsumptionError, "REQUEST_HASH"):
            self.consult(forged)

    def test_tampered_oracle_flags_rejected_even_with_rehashed_digest(self):
        self.consult()
        path = Path(attest_oracle(self.home)["path"])
        body = json.loads(path.read_text())
        body["oracle"]["evidence_upgrade"] = True
        body["oracle_sha256"] = sha256(compact(body["oracle"]))
        body["receipt_sha256"] = _body_hash(body)
        path.write_text(json.dumps(body))
        with self.assertRaises(Exception):
            attest_oracle(self.home)

    def test_broken_upstream_v2_cannot_invoke_aura(self):
        path = next((self.home / "corpus_callosum_v2").glob("*.json"))
        doc = json.loads(path.read_text())
        doc["native_initial"]["generated_text"] = "tampered"
        path.write_text(json.dumps(doc))
        with self.assertRaises(ConsumptionError):
            self.consult(runner=lambda *_: self.fail("AURA must not run"))

    def test_subprocess_environment_does_not_inherit_tokens(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "never-ever-log",
                                     "JANUS_GOLEM_OPENROUTER_TOKEN": "secret"}):
            env = _safe_native_env()
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("JANUS_GOLEM_OPENROUTER_TOKEN", env)

    def test_unpinned_local_oracle_refused_before_process_start(self):
        with self.assertRaisesRegex(ConsumptionError, "SOURCE_NOT_APPROVED"):
            real_local_aura(Path("/no-aura-checkout"), "a"*40, {})


if __name__ == "__main__":
    unittest.main()
