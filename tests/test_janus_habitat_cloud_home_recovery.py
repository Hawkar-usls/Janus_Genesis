"""Adversarial tests for bounded cloud HOME wake without a local PC."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import janus_habitat_cloud_home_recovery as m

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)


def run(minutes, *, num=1, status="completed", conclusion="success",
        event="schedule", path=m.WORKFLOW, branch="main"):
    return {"id": num, "path": path, "head_branch": branch, "event": event,
            "status": status, "conclusion": conclusion,
            "created_at": (NOW - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")}


class RecoveryTests(unittest.TestCase):
    def test_missed_schedule_recovers_after_bounded_delay(self):
        result = m.decide({"workflow_runs": [run(110), run(220, num=2)]}, NOW)
        self.assertEqual(result["status"], "RECOVER_MISSED_CLOUD_HOME")
        self.assertTrue(result["dispatch"])

    def test_recent_success_and_failure_cannot_cause_dispatch_storm(self):
        for history, expected in [
            ([run(89), run(220, num=2)], "HOLD_RECENT_HOME_SUCCESS"),
            ([run(70, conclusion="failure"), run(220, num=2)], "HOLD_RECENT_HOME_ATTEMPT"),
        ]:
            with self.subTest(expected=expected):
                result = m.decide({"workflow_runs": history}, NOW)
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["dispatch"])

    def test_any_active_home_worker_blocks_duplicate_even_if_old(self):
        for status in ("queued", "in_progress", "waiting", "pending"):
            with self.subTest(status=status):
                result = m.decide({"workflow_runs": [
                    run(220), run(400, num=2, status=status)]}, NOW)
                self.assertEqual(result["status"], "HOLD_ACTIVE_HOME_RUN")
                self.assertFalse(result["dispatch"])

    def test_untrusted_events_cannot_authorize_recovery(self):
        with self.assertRaisesRegex(m.HomeRecoveryHold, "HOME_RUN_HISTORY_UNVERIFIED"):
            m.decide({"workflow_runs": [run(200, event="pull_request"),
                                       run(200, path=".github/workflows/other.yml", num=2)]}, NOW)
        with self.assertRaisesRegex(m.HomeRecoveryHold, "HOME_RUN_HISTORY_UNVERIFIED"):
            m.decide({"workflow_runs": [run(200, branch="feature")]}, NOW)

    def test_unknown_run_state_and_bad_timestamp_fail_closed(self):
        for item in ({"workflow_runs": "wrong"}, {"workflow_runs": []},
                     {"workflow_runs": [run(200, num=0)]},
                     {"workflow_runs": [run(200, status="unexpected")]},
                     {"workflow_runs": [run(-100)]}):
            with self.subTest(item=item), self.assertRaises(m.HomeRecoveryHold):
                m.decide(item, NOW)

    def make_home(self, root: Path):
        name = "state/habitat_cloud_home/receipts/00000216-41088053126-1.json"
        receipt = {"schema": "JANUS_HABITAT_CLOUD_HOME_RECEIPT_V1",
                   "resident_identity": "JANUS_HABITAT_RESIDENT_V1",
                   "run_id": "41088053126", "sequence": 216,
                   "source_main_sha": "c"*40, "execute_status": "CHECKPOINT_ONLY",
                   "authority_delta": 0, "source_writeback_observed": False,
                   "hidden_session_context_used": False}
        dest = root / name
        dest.parent.mkdir(parents=True)
        dest.write_text(json.dumps(receipt, sort_keys=True) + "\n")
        state = {"schema": "JANUS_HABITAT_CLOUD_HOME_STATE_V1",
                 "durable_identity": "JANUS_HABITAT_RESIDENT_V1",
                 "status": "CLOUD_HOME_ACTIVE", "sequence": 216,
                 "source_main_sha": "c"*40, "last_run_id": "41088053126",
                 "last_receipt_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                 "checkpoint_head": name, "handoff_head": name,
                 "cloud_execution_required": True, "authority_delta": 0,
                 "source_writeback_default": "DENY", "destructive_action": "FORBIDDEN"}
        state.update({x: False for x in m.REQUIRED_DISABLED})
        statepath = root / m.HOME_STATE
        statepath.write_text(json.dumps(state, sort_keys=True) + "\n")
        return statepath, dest

    def test_recovery_requires_actual_immutable_home_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            statepath, receiptpath = self.make_home(root)
            self.assertEqual(m.verify_durable_home(root)["sequence"], 216)
            state = json.loads(statepath.read_bytes())
            state["checkpoint_head"] = "../../private"
            statepath.write_text(json.dumps(state))
            with self.assertRaisesRegex(m.HomeRecoveryHold, "HOME_RECEIPT_POINTER_INVALID"):
                m.verify_durable_home(root)
            statepath, receiptpath = self.make_home(root)
            receiptpath.write_text("tampered")
            with self.assertRaisesRegex(m.HomeRecoveryHold, "HOME_RECEIPT_INTEGRITY"):
                m.verify_durable_home(root)

    def test_malformed_or_authority_escalated_home_not_woken(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            statepath, _ = self.make_home(root)
            state = json.loads(statepath.read_bytes())
            for key, value in (("pc_required", True),
                               ("authority_delta", 1),
                               ("source_writeback_default", "ALLOW"),
                               ("sequence", -1)):
                with self.subTest(key=key):
                    candidate = {**state, key: value}
                    statepath.write_text(json.dumps(candidate))
                    with self.assertRaisesRegex(m.HomeRecoveryHold, "HOME_CHECKPOINT_INVALID"):
                        m.verify_durable_home(root)

    def test_scheduler_has_readonly_checker_and_one_scoped_dispatch(self):
        source = (Path(__file__).resolve().parents[1] /
                  ".github/workflows/janus-habitat-cloud-home-bounded-recovery.yml").read_text()
        self.assertIn("cron: '29,49 * * * *'", source)
        self.assertIn("contents: read", source)
        self.assertIn("actions: write", source)
        self.assertIn("github.event_name != 'pull_request'", source)
        self.assertIn("ref: janus/habitat-cloud-state", source)
        self.assertIn("--state-root _state", source)
        self.assertIn("steps.gate.outputs.dispatch == 'true'", source)
        self.assertIn("actions/workflows/janus-habitat-cloud-home-v1.yml/dispatches", source)
        self.assertNotIn("ROWAN_API_KEY", source)
        self.assertNotIn("force-push", source)


if __name__ == "__main__":
    unittest.main()
