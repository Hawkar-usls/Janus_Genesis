"""AI Horde anonymous adapter: only pre-reviewed generic public AURA questions."""
from __future__ import annotations

import json
import io
from contextlib import redirect_stdout
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
        evidence["home_baseline"] = "BASELINE"
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            with patch.object(horde, "protected_snapshot", return_value="BASELINE"):
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

    def test_identifies_official_client_with_public_contact(self):
        class Refused:
            def open(self, req, timeout):
                self.req = req
                raise horde.error.HTTPError(req.full_url, 403, "Forbidden",
                                            {}, io.BytesIO(b'{}'))
        client = Refused()
        with patch.object(horde.request, "build_opener", return_value=client):
            with self.assertRaises(ConsumptionError):
                horde._http("POST", "/generate/text/async", {"prompt": "public"})
        agent = client.req.get_header("Client-agent")
        self.assertTrue(agent.startswith("JANUS-AURA-GOLEM:0.2:"))
        self.assertIn("github.com/Hawkar-usls/Janus_Genesis/issues", agent)
        self.assertIn("JANUS-AURA-GOLEM/0.2", client.req.get_header("User-agent"))

    def test_403_official_refusal_code_is_safely_classified(self):
        class Refused:
            def open(self, request, timeout):
                raise horde.error.HTTPError(
                    request.full_url, 403, "Forbidden", {},
                    io.BytesIO(b'{"rc":"AnonForbidden","message":"DO_NOT_ECHO_MARKER"}'))
        with patch.object(horde.request, "build_opener", return_value=Refused()):
            with self.assertRaises(ConsumptionError) as caught:
                horde._http("POST", "/generate/text/async", {"prompt": "public"})
        self.assertEqual(str(caught.exception), "HORDE_HTTP_403_AnonForbidden")
        self.assertNotIn("DO_NOT_ECHO_MARKER", str(caught.exception))

    def test_403_untrusted_return_code_never_reaches_public_log(self):
        class Refused:
            def open(self, request, timeout):
                raise horde.error.HTTPError(
                    request.full_url, 403, "Forbidden", {},
                    io.BytesIO(b'{"rc":"DO_NOT_ECHO_MARKER","message":"secret"}'))
        with patch.object(horde.request, "build_opener", return_value=Refused()):
            with self.assertRaises(ConsumptionError) as caught:
                horde._http("POST", "/generate/text/async", {"prompt": "public"})
        self.assertEqual(str(caught.exception), "HORDE_HTTP_403")

    def test_strict_live_cli_rejects_false_green_without_second_attempt(self):
        refused = {
            "status": "PROVIDER_UNAVAILABLE__NO_RESPONSE",
            "network_model_response_observed": False,
            "source": "ACTUAL_ANONYMOUS_HTTP",
            "model_reported_unverified": None,
            "failure_class": "HORDE_HTTP_403",
        }
        with patch.object(horde, "query_public", return_value=refused) as client:
            with patch.object(sys, "argv", [
                    "horde", "--execute-public-demo", "--require-real-answer"]):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(horde.main(), 2)
        self.assertEqual(client.call_count, 1)
        self.assertIn('"failure_class": "HORDE_HTTP_403"', output.getvalue())

    def test_strict_live_cli_passes_only_real_observed_text(self):
        answer = "One independently testable hypothesis."
        received = {
            "status": "REAL_ANONYMOUS_RESPONSE__UNVERIFIED",
            "network_model_response_observed": True,
            "source": "ACTUAL_ANONYMOUS_HTTP",
            "prompt_sent": True, "attempts": 1,
            "model_reported_unverified": "reported-model",
            "response": answer,
            "response_sha256": horde.sha256(answer.encode("utf-8")),
            "failure_class": None,
        }
        with patch.object(horde, "query_public", return_value=received):
            with patch.object(sys, "argv", [
                    "horde", "--execute-public-demo", "--require-real-answer"]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(horde.main(), 0)


    def test_http_403_may_have_disclosed_prompt_even_without_job(self):
        class Refused:
            def open(self, req, timeout):
                raise horde.error.HTTPError(req.full_url, 403, "Forbidden",
                                            {}, io.BytesIO(b'{}'))
        with patch.object(horde.request, "build_opener", return_value=Refused()):
            result = horde.query_public(execute=True)
        self.assertEqual(result["failure_class"], "HORDE_HTTP_403")
        self.assertEqual(result["status"], "PROVIDER_UNAVAILABLE__NO_RESPONSE")
        self.assertIsNone(result["prompt_sent"])
        self.assertEqual(result["attempts"], 1)
        self.assertFalse(result["network_model_response_observed"])


    def test_whitespace_or_control_only_external_reply_cannot_pass_canary(self):
        for bad_text in (" \t\n ", "\x00\x01", "\r\t\n"):
            def blank_generation(method, path, body=None):
                if method == "POST":
                    return {"id": UUID}
                return {"done": True, "generations": [
                    {"model": "provider-model", "text": bad_text}
                ]}
            result = horde.query_public(execute=True, transport=blank_generation,
                                        sleeper=lambda *_: None)
            self.assertEqual(result["status"], "INVALID_EXTERNAL_GENERATION")
            self.assertFalse(result["network_model_response_observed"])
            self.assertIsNone(result["response"])



    def test_strict_real_canary_rejects_forged_model_response_or_digest(self):
        answer = "A small independent test is needed."
        good = {
            "status": "REAL_ANONYMOUS_RESPONSE__UNVERIFIED",
            "network_model_response_observed": True,
            "source": "ACTUAL_ANONYMOUS_HTTP",
            "prompt_sent": True, "attempts": 1,
            "response": answer,
            "response_sha256": horde.sha256(answer.encode()),
            "model_reported_unverified": "observed-model",
        }
        self.assertTrue(horde.real_answer_observed(good))
        for patch_value in (
            {"response_sha256": "0" * 64},
            {"response": "   \n"},
            {"prompt_sent": None},
            {"attempts": 2},
            {"source": "INJECTED_FIXTURE_NOT_REAL_AI"},
            {"model_reported_unverified": ""},
            {"network_model_response_observed": False},
        ):
            with self.subTest(patch_value=patch_value):
                self.assertFalse(horde.real_answer_observed({**good, **patch_value}))

    def test_native_head_mismatch_rejected_before_external_post(self):
        evidence = {
            "home_baseline": "BASELINE",
            "aura_receipt_sha256": "e" * 64,
            "cursor": {"context_sha256": "f" * 64},
            "aura": {"oracle_source_type": "PINNED_LOCAL_AURA_CLI",
                     "oracle": {"questions": [
                         "What single observation would most reduce uncertainty?"
                     ]}},
            "v2": {"native_initial": {
                "source_commit": "a" * 40, "checkpoint_sha256": "b" * 64}},
        }
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            with self.assertRaisesRegex(ConsumptionError, "HORDE_NATIVE_COMMIT"):
                horde.query_attested_aura(Path("/never-read"),
                    execute=True, transport=self.fake, sleeper=lambda *_: None,
                    native_repo=Path("/missing"), native_head="c" * 40)
        self.assertEqual(self.calls, [])

    def test_pinned_checkout_preflight_failure_before_external_post(self):
        evidence = {
            "home_baseline": "BASELINE",
            "aura_receipt_sha256": "e" * 64,
            "cursor": {"context_sha256": "f" * 64},
            "aura": {"oracle_source_type": "PINNED_LOCAL_AURA_CLI",
                     "oracle": {"questions": [
                         "What single observation would most reduce uncertainty?"
                     ]}},
            "v2": {"native_initial": {
                "source_commit": "a" * 40, "checkpoint_sha256": "b" * 64}},
        }
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            with patch.object(horde, "preflight_native_checkout",
                              side_effect=ConsumptionError("PREFLIGHT_STOP")):
                with self.assertRaisesRegex(ConsumptionError, "PREFLIGHT_STOP"):
                    horde.query_attested_aura(Path("/never-read"),
                        execute=True, transport=self.fake,
                        native_repo=Path("/missing"), native_head="a" * 40)
        self.assertEqual(self.calls, [])

    def test_private_home_drift_rejected_before_and_after_external(self):
        evidence = {
            "home_baseline": "BASELINE",
            "aura_receipt_sha256": "e" * 64,
            "cursor": {"context_sha256": "f" * 64},
            "aura": {"oracle_source_type": "PINNED_LOCAL_AURA_CLI",
                     "oracle": {"questions": [
                         "What single observation would most reduce uncertainty?"
                     ]}},
        }
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            with patch.object(horde, "protected_snapshot", return_value="DRIFT"):
                with self.assertRaisesRegex(ConsumptionError, "BEFORE_EGRESS"):
                    horde.query_attested_aura(Path("/never-read"),
                        execute=True, transport=self.fake)
            self.assertEqual(self.calls, [])
            with patch.object(horde, "protected_snapshot",
                              side_effect=["BASELINE", "DRIFT"]):
                with self.assertRaisesRegex(ConsumptionError, "AFTER_EGRESS"):
                    horde.query_attested_aura(Path("/never-read"),
                        execute=True, transport=self.fake, sleeper=lambda *_: None)
        self.assertEqual(sum(c[0] == "POST" for c in self.calls), 1)

    def test_mock_aura_cannot_be_used_for_live_public_external_egress(self):
        evidence = {
            "home_baseline": "BASELINE",
            "aura": {"oracle_source_type": "MOCKED_AURA_TEST_ONLY",
                     "oracle": {"questions": [
                         "What single observation would most reduce uncertainty?"
                     ]}},
        }
        with patch("janus_corpus_aura_golem_live.load_aura_evidence",
                   return_value=evidence):
            with patch.object(horde, "query_public",
                              side_effect=AssertionError("No real external egress")):
                with self.assertRaisesRegex(ConsumptionError,
                                            "REAL_EGRESS_REQUIRES_REAL_PINNED_AURA"):
                    horde.query_attested_aura(Path("/never-read"), execute=True)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
