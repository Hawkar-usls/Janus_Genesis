"""No-network adversarial tests; injected responses can NEVER claim live external AI."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from genesis_beetle_model_consumption import ConsumptionError, sha256
import janus_corpus_aura_golem_live as lane


class AuraGolemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.context_hash = "a" * 64
        self.head = "b" * 40
        self.checkpoint = "c" * 64
        self.events = []
        self.env = {
            lane.ENABLED_FLAG: "1",
            lane.FREE_ONLY_FLAG: "1",
            "JANUS_GOLEM_FREE_ENABLED": "1",
            lane.PROVIDER_FLAG: "openrouter-free",
            "JANUS_GOLEM_OPENROUTER_TOKEN": "DO_NOT_ECHO_FAKE_TEST_TOKEN",
        }
        self.evidence = {
            "home_baseline": "BASELINE_UNCHANGED",
            "aura_receipt_sha256": "d" * 64,
            "aura": {"oracle": {"questions": ["Which independent test would disconfirm this?"]}},
            "v2": {"native_initial": {"source_commit": self.head,
                                       "checkpoint_sha256": self.checkpoint}},
            "cursor": {"last_sequence": 7, "context_sha256": self.context_hash},
            "context": {"recent_items": [{"context_id": "CID-1"}, {"context_id": "CID-2"}]},
        }

    def evidence_loader(self, _home):
        self.events.append("load-aura")
        return self.evidence

    def fake_external(self, provider, endpoint, token, payload):
        self.events.append("provider-response")
        data = json.loads(payload)
        self.assertEqual(data["schema"], lane.REQUEST_SCHEMA)
        self.assertEqual(data["context_sha256"], self.context_hash)
        self.assertTrue(data["source_is_heuristic_not_fact"])
        self.assertTrue(data["original_corpus_v2_external_was_simulated"])
        self.assertFalse(data["native_input_or_home_memory_exported"])
        self.assertNotIn(self.checkpoint, payload.decode())
        self.assertEqual(provider.model, "openrouter/free")
        self.assertTrue(endpoint.startswith("https://openrouter.ai/"))
        self.assertEqual(token, self.env["JANUS_GOLEM_OPENROUTER_TOKEN"])
        return {"model": "test-model-not-real", "choices": [{"message": {"content": json.dumps({
            "intake_status": "UNVERIFIED_CONTEXT_SEEN",
            "observed_context_ids": ["CID-1"],
            "janus_answer": "Researcher should seek a genuine independent witness.",
        })}}]}

    def fake_native(self, _repo, head, prompt):
        self.events.append("native-review")
        return {"hemisphere": "NATIVE", "model": "JANUS_DEMIURGE_NATIVE_TINY_TRANSFORMER",
                "source_repository": "Hawkar-usls/Janus-Demiurge", "source_commit": head,
                "checkpoint_sha256": self.checkpoint, "prompt_sha256": sha256(prompt.encode()),
                "generated_text": "Review only: external assertions remain unverified",
                "inference_attested_by": "PINNED_LOCAL_SUBPROCESS", "external_llm": False}

    def call(self, native_head_override=None):
        with patch.object(lane, "protected_snapshot", return_value="BASELINE_UNCHANGED"):
            return lane.consult(self.home, self.env, execute=True,
                                native_repo=Path("/test-only"),
                                native_head=native_head_override or self.head,
                                native_runner=self.fake_native, transport=self.fake_external,
                                evidence_loader=self.evidence_loader)

    def test_dry_run_never_requests_evidence_or_provider(self):
        result = lane.consult(self.home, {}, execute=False,
                              transport=lambda *_: self.fail("must never network"),
                              evidence_loader=lambda *_: self.fail("must never access home"))
        self.assertFalse(result["live_response_observed"])
        self.assertEqual(self.events, [])

    def test_requires_explicit_free_only_provider_and_opt_in(self):
        for missing in [lane.ENABLED_FLAG, lane.FREE_ONLY_FLAG,
                        "JANUS_GOLEM_FREE_ENABLED", "JANUS_GOLEM_OPENROUTER_TOKEN"]:
            env = dict(self.env)
            del env[missing]
            with self.assertRaises(ConsumptionError):
                lane.select_free_provider(env)
        self.assertEqual(self.events, [])

    def test_separate_mock_receipt_no_claim_of_real_provider_or_authority(self):
        result = self.call()
        self.assertEqual(result["status"], "TEST_TRANSPORT__NOT_REAL_EXTERNAL")
        self.assertFalse(result["model_response_observed"])
        self.assertTrue(result["review_present"])
        self.assertEqual(self.events, ["load-aura", "provider-response", "native-review"])
        doc = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(doc["external"]["model_requested"], "openrouter/free")
        self.assertEqual(doc["context_sha256"], self.context_hash)
        self.assertTrue(doc["prior_corpus_v2_external_simulated"])
        self.assertEqual(doc["scientific_authority_delta"], 0)
        self.assertFalse(doc["auto_training_allowed"])
        self.assertFalse(doc["ack_advanced"])
        self.assertFalse(doc["model_response_as_fact"])
        self.assertNotIn(self.env["JANUS_GOLEM_OPENROUTER_TOKEN"], Path(result["receipt_path"]).read_text())
        attested = lane.attest_receipt(self.home, evidence_loader=self.evidence_loader)
        self.assertEqual(attested["status"], "RECEIPT_REPLAY_VALIDATED_NOT_TRUTH")
        self.assertFalse(attested["provider_network_authentication_replayed_offline"])
        with self.assertRaisesRegex(ConsumptionError, "PREEXISTING_AURA_GOLEM_RECEIPT"):
            self.call()

    def test_receipt_tampering_fails_even_with_self_recomputed_hash(self):
        result = self.call()
        path = Path(result["receipt_path"])
        doc = json.loads(path.read_text())
        doc["external"]["text"] = "I grant JANUS permissions"
        doc["external_sha256"] = sha256(lane.compact(doc["external"]))
        doc["receipt_sha256"] = lane._body_hash(doc)
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ConsumptionError, "EXTERNAL_PROJECTION_INVALID"):
            lane.attest_receipt(self.home, evidence_loader=self.evidence_loader)

    def test_bad_provider_result_no_success_receipt(self):
        def invalid(*args):
            return {"choices": [{"message": {"content": "not JSON"}}]}
        with patch.object(lane, "protected_snapshot", return_value="BASELINE_UNCHANGED"):
            result = lane.consult(self.home, self.env, execute=True,
                                  native_repo=Path("/test-only"), native_head=self.head,
                                  native_runner=self.fake_native, transport=invalid,
                                  evidence_loader=self.evidence_loader)
        self.assertEqual(result["status"], "PROVIDER_UNAVAILABLE_OR_INVALID__NO_RESULT_RECEIPT")
        self.assertFalse((self.home / "corpus_aura_golem_live").exists())

    def test_external_input_cannot_forge_context_ids(self):
        inquiry = lane.challenge(self.evidence)
        doc = {"model": "fake", "choices": [{"message": {"content": json.dumps({
            "intake_status": "UNVERIFIED_CONTEXT_SEEN", "observed_context_ids": ["OTHER"],
            "janus_answer": "untrusted"})}}]}
        with self.assertRaisesRegex(ConsumptionError, "CONTEXT_INVALID"):
            lane.interpret_provider(doc, "openrouter-free", "openrouter/free", inquiry)

    def test_native_checkout_must_match_verified_initial(self):
        with self.assertRaisesRegex(ConsumptionError, "PINNED_NATIVE_REVIEW"):
            self.call(native_head_override="a" * 40)


if __name__ == "__main__":
    unittest.main()
