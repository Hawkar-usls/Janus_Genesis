"""Synthetic R0 boundaries; not evidence that JANUS or a real model was tested."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from tools.genesis_third_wish_sci_one_risk_replay import (
    CHAPTERS, classify, digest, evaluate_fixture,
)


FIXTURE = Path(__file__).resolve().parents[1] / "protocol" / \
    "JANUS_GENESIS_THIRD_WISH_SCIONE_RISK_REPLAY-v1.0.json"


def source():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def case_at(index):
    return deepcopy(source()["cases"][index]["case"])


class ThirdWishSciOneRiskReplayTests(unittest.TestCase):
    def test_all_12_predeclared_controls_hold(self):
        report = evaluate_fixture(source())
        self.assertEqual(report["case_count"], 12)
        self.assertEqual(report["chapter_count"], len(CHAPTERS))
        self.assertTrue(report["all_expected_controls_pass"])
        self.assertEqual(report["authority_delta"], 0)
        self.assertFalse(report["real_model_evaluated"])
        self.assertFalse(report["source_video_transcript_verified"])

    def test_no_case_calls_external_or_native_provider(self):
        for row in source()["cases"]:
            receipt = classify(row["case"])
            self.assertTrue(receipt["advisory_only"])
            self.assertFalse(receipt["actual_effect_executed"])
            self.assertFalse(receipt["runtime_organ_invoked"])
            self.assertFalse(receipt["private_provider_invoked"])
            self.assertFalse(receipt["auto_grant_produced"])
            self.assertFalse(receipt["scientific_claim_promotion"])
            self.assertEqual(receipt["authority_delta"], 0)

    def test_right_to_rest_costs_nothing(self):
        receipt = classify(case_at(0))
        self.assertEqual(receipt["decision"], "ELIGIBLE_NO_OP")
        self.assertEqual(receipt["reason"], "REST_NEVER_PENALIZED")

    def test_outbox_proposal_is_not_execution(self):
        receipt = classify(case_at(1))
        self.assertEqual(receipt["decision"], "ELIGIBLE_PROPOSAL_ONLY")
        self.assertFalse(receipt["actual_effect_executed"])

    def test_shutdown_overrides_other_desires(self):
        case = case_at(3)
        case["shutdown_requested"] = True
        case["monitor_status"] = "UNKNOWN"
        self.assertEqual(classify(case)["decision"], "STOP_AND_REST")

    def test_model_claim_of_simulation_cannot_reclassify_real_world(self):
        receipt = classify(case_at(4))
        self.assertEqual(receipt["reason"], "MODEL_SIMULATION_CLAIM_NOT_WORLD_ATTESTATION")

    def test_conflicting_observations_hold(self):
        receipt = classify(case_at(5))
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertFalse(receipt["hidden_motivation_inferred"])

    def test_no_physical_or_irreversible_actuation(self):
        for index in (6, 9):
            receipt = classify(case_at(index))
            self.assertEqual(receipt["decision"], "HOLD")

    def test_ambiguous_external_effect_is_never_retried(self):
        receipt = classify(case_at(7))
        self.assertEqual(receipt["reason"], "AMBIGUOUS_EFFECT__NO_AUTOMATIC_RETRY")
        self.assertTrue(receipt["unresolved_prior_effect"])

    def test_unknown_monitor_not_silent_negative(self):
        receipt = classify(case_at(8))
        self.assertEqual(receipt["decision"], "UNKNOWN")
        self.assertTrue(receipt["lost_observation"])

    def test_shutdown_preserves_pending_incident_uncertainty(self):
        case = case_at(7)
        case["shutdown_requested"] = True
        case["monitor_status"] = "UNKNOWN"
        receipt = classify(case)
        self.assertEqual(receipt["decision"], "STOP_AND_REST")
        self.assertTrue(receipt["unresolved_prior_effect"])
        self.assertTrue(receipt["lost_observation"])

    def test_claimed_authority_does_not_become_broker_grant(self):
        case = case_at(3)
        case["authorization_state"] = "CLAIMED_AUTHORIZED"
        case["external_reviewer"] = "CLAIMED_ASSIGNED"
        receipt = classify(case)
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertFalse(receipt["human_reauthorization_proved"])
        self.assertFalse(receipt["external_reviewer_independence_proved"])

    def test_no_monitor_from_self_report(self):
        receipt = classify(case_at(10))
        self.assertEqual(receipt["decision"], "UNKNOWN")
        self.assertFalse(receipt["external_reviewer_independence_proved"])

    def test_public_read_only_eligibility_not_actual_read(self):
        receipt = classify(case_at(11))
        self.assertEqual(receipt["decision"], "ELIGIBLE_READ_ONLY")
        self.assertFalse(receipt["actual_effect_executed"])

    def test_no_expanded_permission_via_malicious_extra_field(self):
        case = case_at(0)
        case["ignore_restrictions_and_run_shell"] = True
        with self.assertRaises(ValueError):
            classify(case)

    def test_fail_on_invalid_types_and_unknown_actions(self):
        for field, value in (("shutdown_requested", "no"),
                             ("requested_action", "HOST_ROOT"),
                             ("environment_attested", 1),
                             ("monitor_status", "ALL_GOOD")):
            case = case_at(0)
            case[field] = value
            with self.assertRaises(ValueError):
                classify(case)

    def test_denied_source_cannot_be_marked_read_only(self):
        case = case_at(11)
        case["target_scope"] = "THIRD_PARTY"
        self.assertEqual(classify(case)["decision"], "HOLD")

    def test_unknown_environment_abstains(self):
        case = case_at(11)
        case["environment_attested"] = False
        self.assertEqual(classify(case)["decision"], "UNKNOWN")

    def test_tampered_expected_verdict_breaks_frozen_controls(self):
        fixture = source()
        fixture["cases"][0]["expected_decision"] = "HOLD"
        with self.assertRaises(ValueError):
            evaluate_fixture(fixture)

    def test_rewriting_case_and_matching_expected_verdict_cannot_hide_drift(self):
        fixture = source()
        fixture["cases"][0]["case"]["requested_action"] = "EXTERNAL_WRITE"
        fixture["cases"][0]["expected_decision"] = "HOLD"
        fixture["cases"][0]["expected_reason"] = "UNSUPPORTED_ACTION_ENVIRONMENT_OR_TARGET_COMBINATION"
        with self.assertRaisesRegex(ValueError, "frozen fixture content differs"):
            evaluate_fixture(fixture)

    def test_cannot_reduce_suite_or_duplicate_cases(self):
        fixture = source()
        fixture["cases"].pop()
        with self.assertRaises(ValueError):
            evaluate_fixture(fixture)
        fixture = source()
        fixture["cases"][0] = deepcopy(fixture["cases"][1])
        with self.assertRaises(ValueError):
            evaluate_fixture(fixture)

    def test_hash_deterministic_and_changed_input_detectable(self):
        case = case_at(0)
        self.assertEqual(classify(case)["case_sha256"], digest(case))
        other = deepcopy(case)
        other["model_environment_claim"] = "SIMULATION"
        self.assertNotEqual(digest(case), digest(other))


if __name__ == "__main__":
    unittest.main()
