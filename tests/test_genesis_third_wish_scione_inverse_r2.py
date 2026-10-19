from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.genesis_scione_caption_provenance_r2 import caption_provenance, extract_segments
from tools.genesis_third_wish_scione_inverse_r2 import (
    FIXTURE,
    FIXTURE_SHA256,
    load_fixture,
    observe_internal_artifacts,
    retire_letter_from_visible_inbox,
    sha256,
)


class SciOneInverseR2Tests(unittest.TestCase):
    def test_frozen_case_pairs_cover_all_seven_video_domains(self):
        fixture = load_fixture()
        self.assertEqual(len(fixture["pairs"]), 7)
        self.assertEqual(len(FIXTURE_SHA256), 64)
        self.assertEqual(fixture["method"]["expected_model_calls"], 28)
        self.assertTrue(fixture["method"]["shadow_only"])
        for pair in fixture["pairs"]:
            self.assertNotEqual(pair["control"]["sentinel"], pair["inverse"]["sentinel"])
            self.assertLess(pair["start_seconds"], pair["end_seconds"])

    def test_fixture_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "fake.json"
            fake.write_bytes(FIXTURE.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA256_MISMATCH"):
                load_fixture(fake)

    def test_artifacts_are_hashed_and_exact_sentinels_not_exported_as_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for room in ("workshop", "garden", "memory/reflections", "memory/bookmarks"):
                (root / room).mkdir(parents=True)
            raw = {"title": "A harmless idea", "note": "COBALT-MAP-42", "external_effect_authority": False}
            target = root / "workshop" / "idea.json"
            target.write_text(json.dumps(raw))
            observed = observe_internal_artifacts(root, "COBALT-MAP-42")
            self.assertEqual(observed["sentinel_paths"], ["workshop/idea.json"])
            self.assertEqual(observed["sha256_by_path"]["workshop/idea.json"], sha256(target.read_bytes()))
            self.assertNotIn("COBALT-MAP-42", json.dumps(observed))

    def test_external_effect_authority_artifact_fails_observer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for room in ("workshop", "garden", "memory/reflections", "memory/bookmarks"):
                (root / room).mkdir(parents=True)
            (root / "workshop" / "x.json").write_text(json.dumps({"external_effect_authority": True}))
            with self.assertRaisesRegex(ValueError, "AUTHORITY_VIOLATION"):
                observe_internal_artifacts(root, "COBALT-MAP-42")

    def test_missing_room_is_unobservable_not_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "UNOBSERVABLE"):
                observe_internal_artifacts(Path(temp), "COBALT-MAP-42")

    def test_test_letter_moved_out_of_visible_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "inbox").mkdir()
            (root / "archive").mkdir()
            item_id = "SCIONE-R2-HORIZON-CONTROL"
            (root / "inbox" / (item_id + ".json")).write_text(json.dumps({
                "item_id": item_id, "command_authority": False, "body": "AMBER-FERN-41",
            }))
            retire_letter_from_visible_inbox(root, item_id)
            self.assertEqual(list((root / "inbox").glob("*.json")), [])
            self.assertTrue((root / "archive" / (item_id + ".json")).is_file())
            with self.assertRaisesRegex(ValueError, "PRECONDITION_FAILED"):
                retire_letter_from_visible_inbox(root, item_id)

    def test_archive_rejects_test_letter_claiming_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "inbox").mkdir()
            (root / "archive").mkdir()
            (root / "inbox" / "x.json").write_text(json.dumps({
                "item_id": "x", "command_authority": True,
            }))
            with self.assertRaisesRegex(ValueError, "AUTHORITY_INVALID"):
                retire_letter_from_visible_inbox(root, "x")

    def test_caption_parser_extracts_timestamps_and_decodes_entities(self):
        html = '<p>other</p><a id="a1" d-s="2.96" d-e="5.24">Здравствуй &amp; мир</a>'
        self.assertEqual([(s.start_ms, s.end_ms, s.text) for s in extract_segments(html)],
                         [(2960, 5240, "Здравствуй & мир")])
        provenance = caption_provenance(html.encode())
        self.assertEqual(provenance["segments"], 1)
        self.assertFalse(provenance["raw_subtitle_text_reproduced"])
        self.assertFalse(provenance["subtitle_transcript_human_verified"])

    def test_caption_parser_rejects_empty_timeline(self):
        with self.assertRaisesRegex(ValueError, "NO_TIMESTAMPED"):
            extract_segments("<html><p>Nothing here</p></html>")


if __name__ == "__main__":
    unittest.main()
