"""Offline safety tests for the existing Genesis receiver recovery job."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import genesis_beetle_receiver_recovery as m

NOW = datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def fixture(count=2, seq=1):
    entries = [{"batch_id": f"batch-{i}", "sha256": SHA} for i in range(1, count + 1)]
    q = {"schema": "janus.beetle.delivery_queue.v1",
         "target_repository": m.REPOSITORY,
         "entries": entries, "next_sequence": count + 1}
    a = {"schema": "janus.beetle.inbox_ack.v1", "target_repository": m.REPOSITORY,
         "status": m.ACK_STATUS, "scientific_authority_delta": 0,
         "last_sequence": seq, "sha256": SHA, "batch_id": f"batch-{seq}"}
    return q, a


def run(age=240, *, status="completed", conclusion="success", event="schedule"):
    return {"id": 12345, "path": m.WORKFLOW, "head_branch": "main",
            "head_repository": {"full_name": m.REPOSITORY},
            "event": event, "status": status, "conclusion": conclusion,
            "created_at": (NOW - timedelta(minutes=age)).strftime("%Y-%m-%dT%H:%M:%SZ")}


class Tests(unittest.TestCase):
    def test_behind_old_run_admits_only_one_bounded_wake(self):
        q, a = fixture()
        d = m.decide(q, a, {"workflow_runs": [run()]}, NOW)
        self.assertEqual(d, {"action": "RECOVER_MISSED_RECEIVER", "dispatch": True, "pending": 1})

    def test_fully_acked_skips_without_extra_jobs(self):
        q, a = fixture(seq=2)
        d = m.decide(q, a, {"workflow_runs": []}, NOW)
        self.assertEqual(d["action"], "CURRENT_ACK")
        self.assertFalse(d["dispatch"])

    def test_active_and_recent_runs_are_not_duplicated(self):
        q, a = fixture()
        for history, status in [
            ([run(status="in_progress")], "HOLD_ACTIVE_RECEIVER"),
            ([run(age=10)], "HOLD_RECENT_RECEIVER_ATTEMPT"),
            ([run(age=85)], "HOLD_RECENT_RECEIVER_SUCCESS"),
        ]:
            self.assertEqual(m.decide(q, a, {"workflow_runs": history}, NOW)["action"], status)

    def test_corrupt_ack_or_rebound_sender_held(self):
        q, a = fixture()
        for q2, a2 in [
            ({**q, "target_repository": "other/repo"}, a),
            (q, {**a, "sha256": "b"*64}),
            (q, {**a, "last_sequence": 5}),
            (q, {**a, "scientific_authority_delta": 1}),
            ({**q, "next_sequence": 99}, a),
        ]:
            with self.assertRaises(m.Hold):
                m.decide(q2, a2, {"workflow_runs": [run()]}, NOW)

    def test_missing_untrusted_run_history_never_dispatches(self):
        q, a = fixture()
        for rows in ({"workflow_runs": []}, {"workflow_runs": [run(event="pull_request")]},
                     {"workflow_runs": [run(status="unsafe")]},
                     {"workflow_runs": [run(age=-100)]}):
            with self.assertRaises(m.Hold):
                m.decide(q, a, rows, NOW)

    def test_workflow_reuses_one_existing_job_and_not_a_feedback_cycle(self):
        flow = (Path(__file__).resolve().parents[1] /
                ".github/workflows/janus-habitat-cloud-home-bounded-recovery.yml").read_text()
        self.assertIn("janus-beetle-memory-receiver.yml/runs?per_page=100", flow)
        self.assertIn("steps.receiver_gate.outputs.dispatch == 'true'", flow)
        self.assertIn("steps.receiver_gate.outputs.dispatch != 'true'", flow)
        self.assertIn("ref: beetle-memory", flow)
        self.assertIn("github.event_name != 'pull_request'", flow)
        self.assertNotIn("workflow_run:", flow)
        self.assertNotIn("ROWAN_API_KEY", flow)


if __name__ == "__main__":
    unittest.main()
