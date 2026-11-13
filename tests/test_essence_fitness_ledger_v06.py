"""Adversarial contracts for ESSENCE v0.6 evidence-based inheritance (offline)."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest

from tools import essence_fitness_ledger_v06 as e

REFERENCE = Path(__file__).parent / "fixtures" / "essence_r2_real_duration_20261113.json"
FREEZE = dt.datetime(2026, 11, 13, 0, 0, tzinfo=dt.timezone.utc)

def r2():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))

def future(n=60, *, candidate=95.0, baseline=120.0):
    rows = []
    for i in range(n):
        start = FREEZE + dt.timedelta(hours=2, seconds=i * 200)
        predicted = start - dt.timedelta(seconds=10)
        end = start + dt.timedelta(seconds=100)
        rows.append({
            "repo": "Hawkar-usls/Janus_Genesis",
            "job_id": 9000 + i,
            "predicted_at": predicted.isoformat(),
            "started_at": start.isoformat(),
            "completed_at": end.isoformat(),
            "actual_duration_s": 100.0,
            "candidate_prediction_s": candidate,
            "baseline_prediction_s": baseline,
        })
    return {
        "schema": e.FUTURE_SCHEMA,
        "origin_repo": "Hawkar-usls/Janus_Genesis",
        "verifier_repo": "Hawkar-usls/Janus-Demiurge",
        "frozen_checkpoint_sha256": "e" * 64,
        "frozen_at": FREEZE.isoformat(),
        "claimed_production_authority": False,
        "rows": rows,
        "rows_sha256": e.sha(rows),
    }

class RealEvidenceContracts(unittest.TestCase):
    def test_actual_r2_rejects_weak_model(self):
        event = e.historical_r2(r2())
        self.assertEqual(event["holdout_n"], 60)
        self.assertLess(event["relative_gain"], 0)
        self.assertAlmostEqual(event["baseline_mae_s"], 24.41667)
        self.assertAlmostEqual(event["candidate_mae_s"], 26.32281)
        self.assertEqual(event["research_gate"], "HOLD_NO_INDEPENDENT_GAIN")
        self.assertFalse(event["raw_rows_bound"])
        self.assertFalse(event["production_authority"])

    def test_negative_receipt_immutably_enters_memory(self):
        state = e.initial_state()
        updated = e.add_evidence(state, e.historical_r2(r2()))
        self.assertEqual(len(state["entries"]), 0)
        self.assertEqual(len(updated["entries"]), 1)
        self.assertTrue(e.verify_state(updated))
        self.assertNotEqual(state["state_sha256"], updated["state_sha256"])

    def test_idempotent_repeat_not_a_second_independent_trial(self):
        event = e.historical_r2(r2())
        state = e.add_evidence(e.initial_state(), event)
        self.assertEqual(e.add_evidence(state, event), state)

    def test_tampered_receipt_rejected(self):
        state = e.add_evidence(e.initial_state(), e.historical_r2(r2()))
        corrupted = copy.deepcopy(state)
        corrupted["entries"][0]["candidate_mae_s"] = 0.01
        with self.assertRaisesRegex(ValueError, "LEDGER_TAMPERED"):
            e.verify_state(corrupted)

    def test_cannot_claim_promoted_weights(self):
        record = r2()
        record["production_weights_promoted"] = True
        with self.assertRaisesRegex(ValueError, "SOURCE_AUTHORITY_CONTRADICTION"):
            e.historical_r2(record)

    def test_r2_not_mislabelled_as_future(self):
        record = r2()
        record["dataset"]["heldout_procedure"] = "Prospective"
        with self.assertRaisesRegex(ValueError, "NOT_RETROSPECTIVE_R2"):
            e.historical_r2(record)

    def test_future_good_raw_scores_still_not_authorized(self):
        ev = e.future_packet(future())
        self.assertEqual(ev["holdout_n"], 60)
        self.assertAlmostEqual(ev["candidate_mae_s"], 5)
        self.assertAlmostEqual(ev["baseline_mae_s"], 20)
        self.assertEqual(ev["research_gate"], "RESEARCH_CANDIDATE_PENDING_EXTERNAL_AUTHENTICATION")
        self.assertFalse(ev["external_authentication_completed"])
        self.assertFalse(ev["production_authority"])
        self.assertFalse(ev["offspring_activation"])

    def test_future_negative_is_hold(self):
        ev = e.future_packet(future(candidate=140.0))
        self.assertEqual(ev["research_gate"], "HOLD_NO_INDEPENDENT_GAIN")

    def test_provenance_hash_detects_row_tamper(self):
        sample = future()
        sample["rows"][0]["candidate_prediction_s"] = 1
        with self.assertRaisesRegex(ValueError, "ROWS_HASH_MISMATCH"):
            e.future_packet(sample)

    def test_rejects_leakage_from_future(self):
        sample = future()
        sample["rows"][0]["predicted_at"] = sample["rows"][0]["completed_at"]
        sample["rows_sha256"] = e.sha(sample["rows"])
        with self.assertRaisesRegex(ValueError, "FUTURE_ORDERING_VIOLATION"):
            e.future_packet(sample)

    def test_freeze_embargo_is_real(self):
        sample = future()
        sample["rows"][0]["started_at"] = (FREEZE + dt.timedelta(minutes=10)).isoformat()
        sample["rows"][0]["predicted_at"] = (FREEZE + dt.timedelta(minutes=9)).isoformat()
        sample["rows"][0]["completed_at"] = (FREEZE + dt.timedelta(minutes=11, seconds=40)).isoformat()
        sample["rows_sha256"] = e.sha(sample["rows"])
        with self.assertRaisesRegex(ValueError, "FUTURE_EMBARGO_VIOLATION"):
            e.future_packet(sample)

    def test_falsified_observation_is_not_an_independent_trial(self):
        sample = future()
        sample["rows"][0]["actual_duration_s"] = 1
        sample["rows_sha256"] = e.sha(sample["rows"])
        with self.assertRaisesRegex(ValueError, "UNMATCHED_OBSERVED_DURATION"):
            e.future_packet(sample)

    def test_duplicate_job_rejected(self):
        sample = future()
        sample["rows"][1]["job_id"] = sample["rows"][0]["job_id"]
        sample["rows_sha256"] = e.sha(sample["rows"])
        with self.assertRaisesRegex(ValueError, "INVALID_OR_DUPLICATE_JOB"):
            e.future_packet(sample)

    def test_self_verification_forbidden(self):
        sample = future()
        sample["verifier_repo"] = sample["origin_repo"]
        with self.assertRaisesRegex(ValueError, "SELF_VERIFICATION_FORBIDDEN"):
            e.future_packet(sample)

    def test_no_small_handpicked_holdout(self):
        sample = future(59)
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_OR_UNBOUNDED_FUTURE_ROWS"):
            e.future_packet(sample)

    def test_no_authority_from_attestation_claim(self):
        sample = future()
        sample["claimed_production_authority"] = True
        with self.assertRaisesRegex(ValueError, "CLAIMED_PRODUCTION_AUTHORITY"):
            e.future_packet(sample)

    def test_bad_ledger_chain_detected_with_rehashed_envelope(self):
        state = e.add_evidence(e.initial_state(), e.historical_r2(r2()))
        changed = copy.deepcopy(state)
        changed["entries"][0]["previous_sha256"] = "1" * 64
        changed["entries"][0]["receipt_sha256"] = e.sha({
            k: v for k, v in changed["entries"][0].items() if k != "receipt_sha256"})
        changed["head_sha256"] = changed["entries"][0]["receipt_sha256"]
        changed["state_sha256"] = e.sha({k: v for k, v in changed.items()
                                        if k != "state_sha256"})
        with self.assertRaisesRegex(ValueError, "BROKEN_LEDGER_CHAIN"):
            e.verify_state(changed)

if __name__ == "__main__":
    unittest.main()
