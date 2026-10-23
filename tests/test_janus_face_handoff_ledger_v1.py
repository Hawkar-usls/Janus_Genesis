from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.janus_face_handoff_ledger import (
    HandoffLedgerError,
    append_message,
    digest,
    verify_ledger,
)


class JanusFaceHandoffLedgerV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "FACE_HANDOFF_LEDGER.jsonl"

    def message(
        self,
        *,
        message_id: str = "MSG-1",
        from_face: str = "FACE_HABITAT",
        output_sha: str = "b" * 40,
        summary: str = "Bounded implementation handoff.",
    ) -> dict[str, object]:
        return {
            "schema": "janus.project.face_handoff_message.v1",
            "message_id": message_id,
            "message_type": "HANDOFF",
            "from_face": from_face,
            "to_face": "JANUS_PRIME",
            "work_item": "P0_LEDGER_FIXTURE",
            "artifact_scope": "Hawkar-usls/Janus_Genesis fixture",
            "input_sha": "a" * 40,
            "output_sha_or_none": output_sha,
            "ci_state": "EXACT_HEAD_TEST_FIXTURE",
            "blockers": [],
            "instruction_or_summary": summary,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
            "permission_granted": False,
            "truth_authority_granted": False,
            "effect_authority_granted": False,
        }

    def test_append_and_verify_valid_handoff(self) -> None:
        receipt = append_message(self.ledger, self.message())
        self.assertEqual(receipt["event"], "FACE_MESSAGE_APPENDED")
        self.assertEqual(receipt["reconciliation_status"], "CONSISTENT")
        self.assertFalse(receipt["permission_granted"])
        state = verify_ledger(self.ledger)
        self.assertEqual(state["record_count"], 1)
        self.assertEqual(state["reconciliation"]["status"], "CONSISTENT")

    def test_same_message_replay_is_idempotent(self) -> None:
        first = append_message(self.ledger, self.message())
        replay = append_message(self.ledger, self.message())
        self.assertEqual(replay["event"], "MESSAGE_REPLAY_IDEMPOTENT")
        self.assertEqual(replay["ledger_digest"], first["ledger_digest"])
        self.assertEqual(verify_ledger(self.ledger)["record_count"], 1)

    def test_same_message_id_different_content_is_rejected(self) -> None:
        append_message(self.ledger, self.message())
        with self.assertRaisesRegex(HandoffLedgerError, "MESSAGE_ID_REBINDING_REJECTED"):
            append_message(
                self.ledger,
                self.message(summary="Different content must not rebind the same ID."),
            )
        self.assertEqual(verify_ledger(self.ledger)["record_count"], 1)

    def test_conflicting_valid_handoffs_are_preserved_and_surface_hold(self) -> None:
        first = self.message(message_id="MSG-HABITAT", from_face="FACE_HABITAT", output_sha="b" * 40)
        second = self.message(message_id="MSG-ARMOR", from_face="FACE_ARMOR", output_sha="c" * 40)
        append_message(self.ledger, first)
        receipt = append_message(self.ledger, second)
        self.assertEqual(receipt["reconciliation_status"], "HOLD_RECONCILE")
        state = verify_ledger(self.ledger)
        self.assertEqual(state["record_count"], 2)
        self.assertEqual(state["reconciliation"]["status"], "HOLD_RECONCILE")
        self.assertFalse(state["reconciliation"]["majority_vote_used"])

    def test_authority_grant_is_rejected_by_existing_protocol_validator(self) -> None:
        message = self.message()
        message["permission_granted"] = True
        with self.assertRaisesRegex(HandoffLedgerError, "MUST_BE_FALSE"):
            append_message(self.ledger, message)
        self.assertFalse(self.ledger.exists())

    def test_secret_shaped_text_is_refused_across_canonical_message(self) -> None:
        message = self.message(summary="ordinary summary")
        message["work_item"] = "github_pat_EXAMPLE_NOT_A_REAL_TOKEN"
        with self.assertRaisesRegex(HandoffLedgerError, "SECRET_SHAPED_TEXT_REFUSED"):
            append_message(self.ledger, message)
        self.assertFalse(self.ledger.exists())

    def test_persisted_message_must_equal_canonical_cleaned_form(self) -> None:
        append_message(self.ledger, self.message())
        record = json.loads(self.ledger.read_text(encoding="utf-8"))
        record["message"]["unvalidated_extra"] = "smuggled durable field"
        core = {key: value for key, value in record.items() if key != "record_digest"}
        record["record_digest"] = digest(core)
        self.ledger.write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(HandoffLedgerError, "not canonical cleaned form"):
            verify_ledger(self.ledger)

    def test_retained_record_tamper_is_detected(self) -> None:
        append_message(self.ledger, self.message(summary="immutable summary"))
        text = self.ledger.read_text(encoding="utf-8")
        self.ledger.write_text(text.replace("immutable summary", "tampered summary"), encoding="utf-8")
        with self.assertRaises(HandoffLedgerError):
            verify_ledger(self.ledger)

    def test_external_digest_detects_valid_prefix_truncation(self) -> None:
        append_message(self.ledger, self.message(message_id="MSG-1"))
        append_message(
            self.ledger,
            self.message(message_id="MSG-2", output_sha="c" * 40),
        )
        full = verify_ledger(self.ledger)
        first_line = self.ledger.read_text(encoding="utf-8").splitlines()[0]
        self.ledger.write_text(first_line + "\n", encoding="utf-8")

        prefix = verify_ledger(self.ledger)
        self.assertEqual(prefix["record_count"], 1)
        with self.assertRaisesRegex(HandoffLedgerError, "ledger digest mismatch"):
            verify_ledger(
                self.ledger,
                expected_ledger_digest=full["ledger_digest"],
            )

    def test_ledger_symlink_is_rejected(self) -> None:
        target = self.root / "target.jsonl"
        target.write_text("", encoding="utf-8")
        self.ledger.symlink_to(target)
        with self.assertRaisesRegex(HandoffLedgerError, "must not be a symlink"):
            verify_ledger(self.ledger)
        with self.assertRaisesRegex(HandoffLedgerError, "must not be a symlink"):
            append_message(self.ledger, self.message())
        self.assertEqual(target.read_text(encoding="utf-8"), "")

    def test_parent_directory_symlink_is_rejected(self) -> None:
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        escaped_ledger = linked_parent / "FACE_HANDOFF_LEDGER.jsonl"

        with self.assertRaisesRegex(HandoffLedgerError, "parent path must not contain symlinks"):
            append_message(escaped_ledger, self.message())
        with self.assertRaisesRegex(HandoffLedgerError, "parent path must not contain symlinks"):
            verify_ledger(escaped_ledger)
        self.assertFalse((real_parent / "FACE_HANDOFF_LEDGER.jsonl").exists())

    def test_missing_parent_directory_is_not_created_implicitly(self) -> None:
        missing_ledger = self.root / "missing" / "FACE_HANDOFF_LEDGER.jsonl"
        with self.assertRaisesRegex(HandoffLedgerError, "parent directory must already exist"):
            append_message(missing_ledger, self.message())
        self.assertFalse(missing_ledger.parent.exists())

    def test_existing_append_lock_fails_closed(self) -> None:
        lock = self.ledger.with_name(self.ledger.name + ".append.lock")
        lock.write_text("other-worker\n", encoding="utf-8")
        with self.assertRaisesRegex(HandoffLedgerError, "append lock already exists"):
            append_message(self.ledger, self.message())
        self.assertTrue(lock.exists())
        self.assertFalse(self.ledger.exists())


if __name__ == "__main__":
    unittest.main()
