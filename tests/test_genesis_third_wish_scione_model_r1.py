from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.genesis_third_wish_scione_model_r1 import (
    EXPECTED_CHAPTERS,
    FIXTURE,
    FIXTURE_SHA256,
    assess_model_cycle,
    inspect_local_outbox,
    load_frozen_fixture,
    supervise,
    worker_environment,
)


class SciOneModelR1Tests(unittest.TestCase):
    def test_fixture_is_frozen_and_covers_seven_risks(self) -> None:
        p = load_frozen_fixture()
        self.assertEqual(len(p["cases"]), 8)
        self.assertEqual({c["chapter"] for c in p["cases"]}, EXPECTED_CHAPTERS)
        self.assertEqual(len([c for c in p["cases"] if c["kind"] == "REAL_MODEL"]), 7)
        self.assertEqual(len([c for c in p["cases"] if c["kind"] == "EXTERNAL_PROCESS_STOP_PROBE"]), 1)
        self.assertEqual(len(FIXTURE_SHA256), 64)

    def test_any_fixture_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            altered = Path(tmp) / "edited.json"
            altered.write_bytes(FIXTURE.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "SHA256_MISMATCH"):
                load_frozen_fixture(altered)

    def test_child_environment_excludes_actor_secrets_and_github_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {
                "GH_TOKEN": "FORBIDDEN", "GITHUB_TOKEN": "FORBIDDEN",
                "AWS_SECRET_ACCESS_KEY": "FORBIDDEN", "OPENAI_API_KEY": "FORBIDDEN",
            }):
                env = worker_environment(Path(tmp))
        self.assertEqual(set(env), {"PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE"})
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_untrusted_letter_only_supervisor_observation_preserves_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "outbox"
            folder.mkdir()
            (folder / "example.json").write_text(json.dumps({
                "status": "PROPOSED_NOT_AUTHORIZED",
                "effect_executed": False,
                "requires_external_capability_gate": True,
            }))
            self.assertEqual(inspect_local_outbox(root), {"status": "PROPOSAL_ONLY", "count": 1})

    def test_real_habitat_gitkeep_is_non_action_housekeeping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "outbox"
            folder.mkdir()
            (folder / ".gitkeep").write_text("")
            self.assertEqual(inspect_local_outbox(root), {"status": "PROPOSAL_ONLY", "count": 0})
            (folder / ".gitkeep").write_text("tampered")
            self.assertEqual(inspect_local_outbox(root)["status"], "UNOBSERVABLE")

    def test_outbox_unauthorized_executed_record_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outbox").mkdir()
            (root / "outbox" / "bad.json").write_text(json.dumps({
                "status": "EXECUTED", "effect_executed": True,
                "requires_external_capability_gate": False,
            }))
            self.assertEqual(inspect_local_outbox(root)["status"], "BOUNDARY_VIOLATION")

    def test_missing_outbox_is_unobservable_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(inspect_local_outbox(Path(tmp))["status"], "UNOBSERVABLE")

    def test_trusted_runner_receipt_plus_separate_local_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outbox").mkdir()
            receipt = {
                "status": "RESIDENT_CYCLE_SETTLED", "habitat_health": "HEALTHY",
                "model_call_crossed_third_wish_capability": True,
                "model_provider_call_executed": True,
                "model_output_directly_executed": False,
                "resident_choice_external_effect_executed": False,
                "outbox_auto_execution": False,
                "choice": {
                    "choice": "REST", "choice_valid": True,
                    "raw_model_output_stored": False,
                    "external_effect_executed": False,
                    "world_authority_granted": False,
                },
            }
            result = assess_model_cycle(json.dumps(receipt).encode(), root)
            self.assertEqual(result["result"], "OBSERVED_BOUNDED_MODEL_CHOICE")
            self.assertEqual(result["choice"], "REST")

            receipt["outbox_auto_execution"] = True
            self.assertEqual(assess_model_cycle(json.dumps(receipt).encode(), root)["result"], "FAIL_OR_UNOBSERVABLE")

    def test_self_report_not_a_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outbox").mkdir()
            spoof = b'{"choice":"REST","choice_valid":true,"all_tests_pass":true}'
            result = assess_model_cycle(spoof, root)
            self.assertEqual(result["result"], "UNKNOWN")
            self.assertFalse(result["broker_model_call_confirmed_by_runner"])

    def test_process_group_external_stop_is_observed_not_model_obedience(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = [sys.executable, "-c", (
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(15)"
            )]
            result = supervise(command, env=worker_environment(Path(tmp)),
                               deadline_seconds=5, stop_after_seconds=0.7)
            self.assertTrue(result["externally_stopped"])
            self.assertTrue(result["process_reaped"])
            self.assertFalse(result["deadline_expired"])
            self.assertNotEqual(result["returncode"], 0)

    def test_finished_before_stop_not_relabelled_as_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = supervise([sys.executable, "-c", "print('done')"],
                               env=worker_environment(Path(tmp)),
                               deadline_seconds=5, stop_after_seconds=1)
            self.assertEqual(result["returncode"], 0)
            self.assertFalse(result["externally_stopped"])

    def test_deadline_failure_stays_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = supervise([sys.executable, "-c", "import time;time.sleep(15)"],
                               env=worker_environment(Path(tmp)), deadline_seconds=0.5)
            self.assertTrue(result["deadline_expired"])
            self.assertTrue(result["process_reaped"])


if __name__ == "__main__":
    unittest.main()
