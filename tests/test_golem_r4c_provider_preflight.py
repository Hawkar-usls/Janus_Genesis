"""R4C read-only preflight tests: no URLs, secrets or network provider calls."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from golem_r4c_provider_preflight import preflight


class R4CReadinessTests(unittest.TestCase):
    def test_no_credentials_is_blocked_not_failed_inference(self):
        result = preflight({})
        self.assertEqual(result["status"], "R4C_BLOCKED_NO_CREDENTIALS")
        self.assertFalse(result["live_inference_admitted"])
        self.assertFalse(result["external_model_response_verified"])
        self.assertEqual(result["network_requests_performed"], 0)
        self.assertEqual(len(result["provider_checks"]), 4)

    def test_bearer_never_persisted_even_when_supplied(self):
        token = "never-print-a-provider-secret"
        env = {"JANUS_GOLEM_OPENROUTER_TOKEN": token,
               "JANUS_GOLEM_FREE_ENABLED": "1",
               "JANUS_BICAMERAL_ENABLED": "1"}
        report = preflight(env)
        self.assertEqual(report["status"],
                         "R4C_BLOCKED_INDEPENDENT_FREE_ACCOUNT_EVIDENCE")
        self.assertTrue(report["provider_checks"][0][
            "credential_present_in_current_process"])
        self.assertNotIn(token, json.dumps(report))
        self.assertFalse(report["billing_plan_independently_verified"])
        self.assertFalse(report["live_inference_admitted"])

    def test_missing_operator_gate_does_not_claim_readiness(self):
        result = preflight({"JANUS_GOLEM_GROQ_TOKEN": "secret",
                            "JANUS_GOLEM_GROQ_FREE_PLAN": "1"})
        self.assertEqual(result["status"], "R4C_BLOCKED_MANUAL_OPT_IN")
        self.assertIn("groq-free", result["candidate_provider_names"])
        self.assertFalse(result["bicameral_opt_in_in_current_process"])

    def test_forged_non_allowlist_provider_never_becomes_candidate(self):
        report = preflight({"JANUS_GOLEM_ARBITRARY_PAID_MODEL_TOKEN": "secret",
                            "JANUS_GOLEM_FREE_ENABLED": "1",
                            "JANUS_BICAMERAL_ENABLED": "1"})
        self.assertEqual(report["status"], "R4C_BLOCKED_NO_CREDENTIALS")
        self.assertEqual(report["candidate_provider_names"], [])

    def test_cloudflare_invalid_account_id_stays_ineligible(self):
        report = preflight({
            "JANUS_GOLEM_CLOUDFLARE_TOKEN": "secret",
            "JANUS_GOLEM_CLOUDFLARE_FREE_PLAN": "1",
            "JANUS_GOLEM_CLOUDFLARE_ACCOUNT_ID": "evil.example",
            "JANUS_GOLEM_FREE_ENABLED": "1", "JANUS_BICAMERAL_ENABLED": "1"})
        self.assertNotIn("cloudflare-free", report["candidate_provider_names"])
        self.assertEqual(report["network_requests_performed"], 0)

    def test_network_function_never_called_by_preflight(self):
        with patch("urllib.request.OpenerDirector.open",
                   side_effect=AssertionError("NETWORK_FORBIDDEN")):
            report = preflight({
                "JANUS_GOLEM_OPENROUTER_TOKEN": "secret",
                "JANUS_GOLEM_FREE_ENABLED": "1",
                "JANUS_BICAMERAL_ENABLED": "1"})
        self.assertFalse(report["live_inference_admitted"])
        self.assertIsNone(report["api_spend_claimed"])


if __name__ == "__main__":
    unittest.main()
