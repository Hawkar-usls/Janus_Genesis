"""ESSENCE v0.7 adversarial frozen future-window gate contracts."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest

from tools import essence_v07_trial_gate as gate

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research/essence/v07/preregistration.json"

def protocol():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))

def packet(*, candidate="idea-swarm-dual-strand-00",
           n1=60, n2=60, baseline_bad=False, candidate_bad=True):
    p = protocol()
    start1 = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc)
    start2 = dt.datetime(2026, 11, 22, tzinfo=dt.timezone.utc)
    rows = []
    for cohort, count, origin in (("a", n1, start1), ("b", n2, start2)):
        for i in range(count):
            at = origin + dt.timedelta(minutes=i)
            rows.append({
                "task_id": f"{cohort}-{i:03d}",
                "origin_sha256": "b" * 64,
                "event_at": at.isoformat(),
                "observed_at": (at + dt.timedelta(seconds=10)).isoformat(),
                "actual_bad": True,
                "baseline_says_bad": baseline_bad,
                "candidate_says_bad": candidate_bad,
            })
    return {
        "schema": gate.PACKET,
        "candidate_id": candidate,
        "protocol_sha256": gate.sha(p),
        "origin_repo": next(x["origin_repo"] for x in p["arms"] if x["id"] == candidate),
        "claimed_verifier_repo": "Hawkar-usls/Janus_Genesis",
        "claimed_production_authority": False,
        "rows": rows,
        "rows_sha256": gate.sha(rows),
    }

def reseal(pkt):
    pkt["rows_sha256"] = gate.sha(pkt["rows"])

class ProspectiveContracts(unittest.TestCase):
    def test_frozen_two_lanes_and_disjoint_future_windows(self):
        self.assertTrue(gate.preregistered(protocol()))
        self.assertEqual(len(protocol()["arms"]), 2)

    def test_real_future_data_not_invented_in_ci(self):
        p = packet(n1=0, n2=0)
        result = gate.score(protocol(), p)
        self.assertEqual(result["research_gate"], "PENDING_FUTURE_HOLDOUT")
        self.assertFalse(result["production_authority"])

    def test_synthetic_mock_winner_still_requires_external_authentication(self):
        p = packet()
        r = gate.score(protocol(), p)
        self.assertEqual(r["research_gate"],
                         "RESEARCH_METRIC_PASS_REQUIRES_EXTERNAL_AUTHENTICATION")
        self.assertFalse(r["independent_external_replication"])
        self.assertFalse(r["offspring_activated"])
        self.assertTrue(r["source_claims_not_authenticated"])
        for c in r["cohorts"].values():
            self.assertEqual(c["n"], 60)
            self.assertEqual(c["wins_candidate"], 60)
            self.assertEqual(c["wins_baseline"], 0)
            self.assertLess(c["mcnemar_one_sided_p"], 0.005)

    def test_no_benefit_is_hold(self):
        r = gate.score(protocol(), packet(baseline_bad=True, candidate_bad=True))
        self.assertEqual(r["research_gate"], "HOLD_NO_REPLICATED_GAIN")

    def test_one_positive_cohort_does_not_count_as_replication(self):
        p = packet()
        for row in p["rows"]:
            if row["task_id"].startswith("b-"):
                row["baseline_says_bad"] = True
        reseal(p)
        self.assertEqual(gate.score(protocol(), p)["research_gate"],
                         "HOLD_NO_REPLICATED_GAIN")

    def test_not_enough_real_cases_is_pending(self):
        self.assertEqual(gate.score(protocol(), packet(n1=59))["research_gate"],
                         "PENDING_FUTURE_HOLDOUT")

    def test_one_false_rejection_healthy_blocks_metric_pass(self):
        p = packet()
        p["rows"][0]["actual_bad"] = False
        p["rows"][0]["candidate_says_bad"] = True
        p["rows"][0]["baseline_says_bad"] = False
        reseal(p)
        self.assertEqual(gate.score(protocol(), p)["research_gate"],
                         "HOLD_NO_REPLICATED_GAIN")

    def test_row_hash_mismatch_rejected(self):
        p = packet()
        p["rows"][0]["actual_bad"] = False
        with self.assertRaisesRegex(ValueError, "TAMPERED_ROWS"):
            gate.score(protocol(), p)

    def test_precommit_mismatch_rejected(self):
        p = packet()
        p["protocol_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "PREREGISTRATION_HASH_MISMATCH"):
            gate.score(protocol(), p)

    def test_duplicate_replayed_job_rejected(self):
        p = packet()
        p["rows"][1]["task_id"] = p["rows"][0]["task_id"]
        reseal(p)
        with self.assertRaisesRegex(ValueError, "REPLAYED_OR_INVALID_TASK_ID"):
            gate.score(protocol(), p)

    def test_historical_job_outside_windows_rejected(self):
        p = packet()
        p["rows"][0]["event_at"] = "2026-11-13T00:00:00Z"
        reseal(p)
        with self.assertRaisesRegex(ValueError, "OUTSIDE_PREREGISTERED_FUTURE_WINDOW"):
            gate.score(protocol(), p)

    def test_observation_cannot_precede_event(self):
        p = packet()
        p["rows"][0]["observed_at"] = "2026-11-01T00:00:00Z"
        reseal(p)
        with self.assertRaisesRegex(ValueError, "FUTURE_LEAKAGE_OR_EARLY_OBSERVATION"):
            gate.score(protocol(), p)

    def test_same_origin_verifier_rejected(self):
        p = packet()
        p["claimed_verifier_repo"] = p["origin_repo"]
        with self.assertRaisesRegex(ValueError, "SELF_VERIFICATION_OR_INVALID_IDENTITY"):
            gate.score(protocol(), p)

    def test_claimed_authority_rejected(self):
        p = packet()
        p["claimed_production_authority"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_AUTHORITY_CLAIM"):
            gate.score(protocol(), p)

    def test_truth_label_must_be_boolean(self):
        p = packet()
        p["rows"][0]["actual_bad"] = 1
        reseal(p)
        with self.assertRaisesRegex(ValueError, "NON_BOOLEAN_LABEL"):
            gate.score(protocol(), p)

    def test_wrong_origin_rejected(self):
        p = packet()
        p["origin_repo"] = "Hawkar-usls/Other"
        with self.assertRaisesRegex(ValueError, "SOURCE_ORIGIN_MISMATCH"):
            gate.score(protocol(), p)

    def test_thresholds_cannot_be_relaxed(self):
        p = protocol()
        p["thresholds"]["min_cases_each_cohort"] = 10
        with self.assertRaisesRegex(ValueError, "PREREGISTERED_THRESHOLDS_CHANGED"):
            gate.preregistered(p)

    def test_p_values_are_paired_and_one_sided(self):
        self.assertEqual(gate.exact_binomial_one_sided(0, 10), 1.0)
        self.assertEqual(gate.exact_binomial_one_sided(10, 0), 1 / 1024)
        self.assertEqual(gate.exact_binomial_one_sided(0, 0), 1.0)

    def test_no_claim_of_real_prospective_data_from_fixture(self):
        p = packet()
        self.assertEqual(p["rows"][0]["origin_sha256"], "b" * 64)
        self.assertEqual(gate.score(protocol(), p)["source_claims_not_authenticated"], True)

if __name__ == "__main__":
    unittest.main()
