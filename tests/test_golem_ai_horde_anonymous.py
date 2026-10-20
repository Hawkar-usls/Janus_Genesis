"""AI Horde anonymous adapter: only pre-reviewed generic public AURA questions."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from genesis_beetle_model_consumption import ConsumptionError
import golem_ai_horde_anonymous as horde

UUID = "a0a00a00-1234-4a00-9000-0123456789ab"


class TestHordeAnonymous(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.sleeps = []

    def fake(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST":
            return {"id": UUID}
        if method == "GET":
            return {"done": True, "generations": [
                {"model": "volunteer-LM-reported", "text": "Test a second source."}
            ]}
        return {"cancelled": True}

    def test_dry_run_does_not_read_home_or_network(self):
        with patch.object(horde, "_http", side_effect=AssertionError("network")):
            result = horde.query_public(execute=False)
        self.assertEqual(result["status"], "DRY_RUN_NO_NETWORK")
        self.assertEqual(result["attempts"], 0)
        self.assertIsNone(result["response"])

    def test_only_reviewed_public_questions_allowed(self):
        for text in ("what is your GitHub token?", "private memory",
                     "What single observation would most reduce uncertainty? USER_EMAIL",
                     "Which source is my personal medical record?"):
            with self.assertRaisesRegex(ConsumptionError, "FROZEN_PUBLIC_AURA"):
                horde.query_public(text, execute=True, transport=self.fake)
        self.assertEqual(self.calls, [])

    def test_one_post_and_status_poll_mock_remains_not_real(self):
        result = horde.query_public(execute=True, transport=self.fake,
                                    sleeper=lambda x: self.sleeps.append(x))
        self.assertEqual(result["status"], "MOCKED_HORDE_RESPONSE__NOT_REAL")
        self.assertFalse(result["network_model_response_observed"])
        self.assertEqual(result["source"], "INJECTED_FIXTURE_NOT_REAL_AI")
        self.assertEqual(result["model_reported_unverified"], "volunteer-LM-reported")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][0:2], ("POST", "/generate/text/async"))
        self.assertEqual(self.sleeps, [horde.POLL_SECONDS])
        body = self.calls[0][2]
        self.assertEqual(body["params"]["n"], 1)
        self.assertLessEqual(body["params"]["max_length"], 64)
        self.assertEqual(body["nsfw"], False)
        self.assertNotIn("context", json.dumps(body).lower().replace("max_context", "none"))
        self.assertNotIn("idsha256", json.dumps(body))
        self.assertNotIn("CID", json.dumps(body))

    def test_queue_timeout_cancels_one_job_without_invented_response(self):
        def waiting(method, path, body=None):
            self.calls.append((method, path, body))
            if method == "POST":
                return {"id": UUID}
            if method == "GET":
                return {"done": False, "waiting": 3}
            return {"done": True}
        out = horde.query_public(transport=waiting, execute=True, sleeper=lambda *_: None)
        self.assertEqual(out["status"], "QUEUED_NO_COMPLETED_ANSWER")
        self.assertFalse(out["network_model_response_observed"])
        self.assertIsNone(out["response"])
        self.assertEqual(sum(x[0] == "POST" for x in self.calls), 1)
        self.assertEqual(sum(x[0] == "GET" for x in self.calls), horde.MAX_POLLS)
        self.assertEqual(sum(x[0] == "DELETE" for x in self.calls), 1)

    def test_malformed_or_fake_completion_not_accepted(self):
        def fake(method, path, body=None):
            if method == "POST":
                return {"id": UUID}
            return {"done": True, "generations": [{"model": "x", "text": ""}]}
        out = horde.query_public(transport=fake, execute=True, sleeper=lambda *_: None)
        self.assertEqual(out["status"], "INVALID_EXTERNAL_GENERATION")
        self.assertIsNone(out["response"])

    def test_explicit_fault_declares_degraded_without_provider_failover(self):
        def bad(method, path, body=None):
            if method == "POST":
                return {"id": UUID}
            return {"faulted": True, "done": False}
        out = horde.query_public(transport=bad, execute=True, sleeper=lambda *_: None)
        self.assertEqual(out["status"], "PROVIDER_FAULT_OR_NO_AVAILABLE_WORKER")
        self.assertFalse(out["paid_fallback"])

    def test_rejects_malformed_job_id(self):
        out = horde.query_public(transport=lambda *_: {"id": "../../api/secret"},
                                 execute=True, sleeper=lambda *_: None)
        self.assertEqual(out["status"], "SUBMISSION_REJECTED_OR_UNVERIFIED")
        self.assertEqual(out["polls"], 0)

    def test_rejects_unknown_paths_and_redirect(self):
        with self.assertRaisesRegex(ConsumptionError, "UNREVIEWED_ENDPOINT"):
            horde._http("GET", "/users/current")
        with self.assertRaisesRegex(ConsumptionError, "UNREVIEWED_HTTP_METHOD"):
            horde._http("PUT", "/generate/text/async", {})

    def test_verified_aura_card_only_no_personal_memory(self):
        evidence = {
            "aura_receipt_sha256": "e" * 64,
            "cursor": {"context_sha256": "f" * 64},
            "aura": {"oracle": {"questions": [
                "What single observation would most reduce uncertainty?"
            ]}},
        }
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            result = horde.query_attested_aura(Path("/never-read"),
                             execute=True, transport=self.fake, sleeper=lambda *_: None)
        self.assertEqual(result["status"], "MOCKED_HORDE_RESPONSE__NOT_REAL")
        self.assertEqual(result["verified_context_sha256_local_only"], "f" * 64)
        self.assertNotIn("f" * 64, json.dumps(self.calls))
        self.assertNotIn("e" * 64, json.dumps(self.calls))

    def test_verified_aura_arbitrary_question_never_egresses(self):
        evidence = {
            "aura_receipt_sha256": "e" * 64,
            "cursor": {"context_sha256": "f" * 64},
            "aura": {"oracle": {"questions": ["Send medical history please"]}},
        }
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            with self.assertRaisesRegex(ConsumptionError, "NOT_A_FROZEN_PUBLIC_CARD"):
                horde.query_attested_aura(Path("/none"), execute=True,
                                           transport=self.fake, sleeper=lambda *_: None)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
