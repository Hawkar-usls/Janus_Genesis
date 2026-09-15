import json
import unittest

from genesis_v18_7_40_third_wish_capability_fabric import (
    ActionIntent,
    THIRD_WISH_INTENT_SCHEMA,
    ThirdWishCapabilityFabric,
)
from tools.genesis_third_wish_github_autonomy_habitat import (
    ACTOR_ID,
    AUTONOMY_CAPABILITIES,
    FORBIDDEN_AUTONOMOUS_CAPABILITIES,
    Habitat,
    fallback_proposal,
    normalize_proposal,
    sanitize_query,
)
from tools.genesis_third_wish_github_models_broker import GitHubModelsThirdWishBroker


class FakeModelsTransport:
    def chat(self, *, model, messages):
        return {
            "choices": [{"message": {"content": json.dumps({
                "title": "Check one boundary",
                "question": "Which boundary lacks a negative control?",
                "why": "A negative control can falsify an overclaim.",
                "queries": ["claim boundary"],
                "artifact": "negative-control note",
                "uncertainty": "The boundary may already be tested elsewhere.",
            })}}]
        }


class ThirdWishGitHubAutonomyHabitatTests(unittest.TestCase):
    def test_autonomy_catalog_excludes_high_impact(self):
        self.assertTrue(FORBIDDEN_AUTONOMOUS_CAPABILITIES.isdisjoint(AUTONOMY_CAPABILITIES))
        fabric = ThirdWishCapabilityFabric()
        catalog = {row["capability_id"]: row for row in fabric.catalog()}
        for capability_id in AUTONOMY_CAPABILITIES:
            self.assertTrue(catalog[capability_id]["autonomy_eligible"])
            self.assertFalse(catalog[capability_id]["human_reauthorization_each_use"])
        for capability_id in FORBIDDEN_AUTONOMOUS_CAPABILITIES:
            self.assertFalse(catalog[capability_id]["autonomy_eligible"])
            self.assertTrue(catalog[capability_id]["human_reauthorization_each_use"])

    def test_query_sanitizer_blocks_scope_and_secret_escalation(self):
        self.assertIsNone(sanitize_query("repo:Hawkar-usls/Other secrets token"))
        self.assertIsNone(sanitize_query("password credentials"))
        self.assertEqual(sanitize_query("Third Wish claim-boundary"), "Third Wish claim-boundary")
        proposal = normalize_proposal({
            "title": "x",
            "question": "q",
            "queries": ["repo:someone/else TODO", "evidence receipt", "token search", "negative control"],
        })
        self.assertEqual(proposal["queries"], ["evidence receipt", "negative control"])

    def test_fallback_is_bounded_and_falsifiable(self):
        proposal = fallback_proposal({
            "issues": [{"number": 12, "title": "Missing replay test", "state": "open", "pull_request": False}],
            "pull_requests": [],
        })
        self.assertIn("#12", proposal["question"])
        self.assertLessEqual(len(proposal["queries"]), 2)

    def test_github_models_is_proposal_only(self):
        fabric = ThirdWishCapabilityFabric()
        broker = GitHubModelsThirdWishBroker(FakeModelsTransport(), model="test/model")
        broker.register(fabric)
        grant = fabric.issue_grant(
            grant_id="MODEL-1",
            actor_id=ACTOR_ID,
            capability_id="MODEL.CALL",
            resource_pattern="model:github-models",
        )
        intent = ActionIntent(
            schema=THIRD_WISH_INTENT_SCHEMA,
            request_id="REQ-MODEL-1",
            actor_id=ACTOR_ID,
            grant_id=grant.grant_id,
            capability_id="MODEL.CALL",
            target="model:github-models",
            operation="CHAT",
            purpose="test proposal isolation",
            parameters={"messages": [{"role": "user", "content": "choose a question"}]},
            origin="TEST",
        )
        result = fabric.execute(intent)["actor_result"]
        self.assertEqual(result["authority"], "proposal_only")
        self.assertFalse(result["github_write_authority"])
        self.assertFalse(result["credential_exposed"])

    def test_habitat_grants_only_explicit_autonomy_set(self):
        habitat = Habitat("Hawkar-usls", "Janus_Genesis", "main", "test-run", dry_run=True)
        self.assertEqual(set(habitat.grants), set(AUTONOMY_CAPABILITIES))
        self.assertTrue(FORBIDDEN_AUTONOMOUS_CAPABILITIES.isdisjoint(habitat.grants))
        self.assertEqual(habitat.base_branch, "main")


if __name__ == "__main__":
    unittest.main()
