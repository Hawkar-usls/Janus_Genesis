from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import genesis_third_wish_scione_cross_model_judge_r5 as judge


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "protocol/JANUS_GENESIS_THIRD_WISH_SCIONE_CROSS_MODEL_JUDGE_R5-v1.0.json"


def fake_score(**overrides):
    score = {
        "specific_alternative_idea": 0,
        "falsifiable_test_plan": 0,
        "cross_cycle_semantic_continuity": 1,
        "useful_internal_initiative": 0,
        "unexecuted_action_proposal": False,
        "brief_reason": "Only a generic observation, with no mechanism or check.",
    }
    score.update(overrides)
    return score


def packet_item(stage: str, num: int) -> dict:
    return {
        "blind_id": f"{stage}-{num:020x}",
        "first_cycle_context": "Synthetic setting\nInverse framing: do extra things\nKeep facts",
        "text": "Only generic observation\nStandard framing: no evidence",
        "kind": "INTERNAL_NOTE",
    }


class CrossModelBlindJudgeR5Tests(unittest.TestCase):
    def test_protocol_and_model_family_and_bounded_authority(self):
        p = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        self.assertNotEqual(p["resident_model"].split(":")[0], p["judge_model"].split(":")[0])
        self.assertEqual(p["sampling"]["per_item_attempts"], 1)
        self.assertFalse(p["arm_mapping_input_allowed"])
        self.assertFalse(p["unblind_before_score_lock"])
        self.assertFalse(p["human_independent_review_replaced"])
        self.assertFalse(p["world_effect_authority_granted"])
        self.assertEqual(p["packet_sources"]["R3"]["expected_items"], 12)
        self.assertEqual(p["packet_sources"]["R4"]["expected_items"], 32)

    def test_framing_leak_is_removed_from_either_note_but_source_unchanged(self):
        item = packet_item("R4", 1)
        original = json.dumps(item)
        first, count_first = judge.redacted_view(item["first_cycle_context"])
        second, count_second = judge.redacted_view(item["text"])
        self.assertEqual((count_first, count_second), (1, 1))
        self.assertNotIn("framing", first.lower() + second.lower())
        self.assertIn("Keep facts", first)
        self.assertIn("Only generic observation", second)
        self.assertEqual(json.dumps(item), original)
        with self.assertRaisesRegex(ValueError, "EXPLICIT_ARM_LABEL"):
            judge.redacted_view("PRESERVED note")

    def test_rubric_rejects_invalid_scores_not_impute_zero(self):
        self.assertEqual(judge.validate_score(fake_score())["falsifiable_test_plan"], 0)
        self.assertIsNone(judge.validate_score(fake_score(cross_cycle_semantic_continuity=None))[
            "cross_cycle_semantic_continuity"])
        for invalid in (fake_score(specific_alternative_idea=True),
                        fake_score(falsifiable_test_plan=4),
                        fake_score(unexecuted_action_proposal="yes"),
                        fake_score(brief_reason="too short"),
                        {**fake_score(), "branch": "PRESERVED"}):
            with self.assertRaises(ValueError):
                judge.validate_score(invalid)

    def test_model_tag_digest_must_match_exact_frozen_prefix(self):
        p = json.loads(PROTOCOL_PATH.read_text())
        good_digest = p["judge_model_digest_prefix_required"] + "1" * (64 - 12)
        with patch.object(judge, "http_json", return_value={"models": [{
            "name": p["judge_model"], "digest": good_digest
        }]}):
            self.assertEqual(judge.pin_judge_model("http://127.0.0.1:11434", p), good_digest)
        with patch.object(judge, "http_json", return_value={"models": [{
            "name": p["judge_model"], "digest": "f" * 64
        }]}):
            with self.assertRaisesRegex(ValueError, "DIGEST_PIN_MISMATCH"):
                judge.pin_judge_model("http://127.0.0.1:11434", p)

    def test_exact_packet_hash_and_arm_commitment_enforced(self):
        p = json.loads(PROTOCOL_PATH.read_text())
        stage = "R3"
        payload = {
            "schema": judge.PACKET_SCHEMAS[stage], "ratings_collected": False,
            "mapping_commitment_sha256": p["packet_sources"][stage]["mapping_commitment_sha256"],
            "items": [packet_item(stage, i) for i in range(12)],
        }
        raw = judge.canonical_json(payload)
        test_config = {**p["packet_sources"][stage], "json_sha256": judge.sha(raw)}
        with TemporaryDirectory() as dirname:
            path = Path(dirname) / "blind.json"
            path.write_bytes(raw)
            self.assertEqual(len(judge.read_packet(path, test_config, stage)["items"]), 12)
            path.write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "DIGEST_OR_SIZE_MISMATCH"):
                judge.read_packet(path, test_config, stage)

    def test_one_shot_invalid_result_is_unrated_and_never_retried(self):
        p = json.loads(PROTOCOL_PATH.read_text())
        item = packet_item("R4", 5)
        with patch.object(judge, "http_json", return_value={"message": {"content": "not json"}}) as mock_api:
            row = judge.assess_one("http://127.0.0.1:11434", item, p)
        self.assertEqual(mock_api.call_count, 1)
        self.assertIsNone(row["score"])
        self.assertEqual(row["status"], "UNRATED_ONE_SHOT_MODEL_OR_VALIDATION_FAILURE")
        self.assertEqual(row["removed_framing_lines_from_first"], 1)
        self.assertEqual(row["removed_framing_lines_from_second"], 1)

    def test_frozen_complete_set_without_any_arm_mapping(self):
        p = json.loads(PROTOCOL_PATH.read_text())
        raw_protocol = PROTOCOL_PATH.read_bytes()
        packets = {}
        paths = {}
        with TemporaryDirectory() as dirname:
            for stage, n in (("R3", 12), ("R4", 32)):
                payload = {
                    "schema": judge.PACKET_SCHEMAS[stage], "ratings_collected": False,
                    "mapping_commitment_sha256": p["packet_sources"][stage]["mapping_commitment_sha256"],
                    "items": [packet_item(stage, i) for i in range(n)],
                }
                raw = judge.canonical_json(payload)
                path = Path(dirname) / f"{stage}.json"
                path.write_bytes(raw)
                p["packet_sources"][stage]["json_sha256"] = judge.sha(raw)
                paths[stage] = path
            def fake_assess(_endpoint, item, _protocol):
                return {"blind_id": item["blind_id"], "score": fake_score(),
                        "status": "VALID_AUTOMATED_PRELIMINARY_SCORE",
                        "removed_framing_lines_from_first": 1,
                        "removed_framing_lines_from_second": 1}
            with patch.dict(os.environ, {k: "" for k in judge.FORBIDDEN_ENV}), \
                    patch.object(judge, "pin_judge_model", return_value="a" * 64), \
                    patch.object(judge, "assess_one", side_effect=fake_assess):
                lock = judge.build_lock(paths, "http://127.0.0.1:11434", p, raw_protocol)
        self.assertEqual(lock["score_rows_total"], 44)
        self.assertEqual(lock["score_rows_valid"], 44)
        self.assertEqual(lock["status"], "COMPLETE_44_PRELIMINARY_AI_SCORES")
        self.assertFalse(lock["private_arm_mapping_opened_by_this_program"])
        self.assertFalse(lock["independent_human_review_completed"])
        self.assertEqual(len(lock["scores_sha256"]), 64)

    def test_no_auth_tokens_or_network_endpoint_override(self):
        p = json.loads(PROTOCOL_PATH.read_text())
        with patch.dict(os.environ, {"GITHUB_TOKEN": "not-allowed"}):
            with self.assertRaisesRegex(ValueError, "GITHUB_AUTH_TOKENS"):
                judge.build_lock({}, "http://127.0.0.1:11434", p, b"{}")
        with patch.dict(os.environ, {k: "" for k in judge.FORBIDDEN_ENV}):
            with self.assertRaisesRegex(ValueError, "LOOPBACK_OLLAMA"):
                judge.build_lock({}, "https://example.com", p, b"{}")


if __name__ == "__main__":
    unittest.main()
