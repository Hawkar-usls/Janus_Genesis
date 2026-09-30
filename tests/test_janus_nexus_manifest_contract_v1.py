# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.janus_nexus_materializer import NexusMaterializerError, validate_manifest


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "protocol" / "JANUS_NEXUS_MANIFEST-v1.0.schema.json"


def _valid_manifest() -> dict:
    return {
        "schema": "janus.nexus.manifest.v1",
        "artifact_id": "TEST-NEXUS-MANIFEST-CONTRACT",
        "write_back_default": "DENY",
        "source_code_execution": False,
        "sources": [
            {
                "repository_id": "1001",
                "visibility": "public",
                "repository": "Hawkar-usls/Alpha",
                "branch": "main",
                "sha": "a" * 40,
            },
            {
                "repository_id": "1002",
                "visibility": "private",
                "branch": "private/main",
                "sha": "b" * 40,
            },
        ],
    }


class JanusNexusManifestContractTests(unittest.TestCase):
    def test_runtime_accepts_canonical_manifest(self) -> None:
        self.assertEqual(validate_manifest(_valid_manifest())["schema"], "janus.nexus.manifest.v1")

    def test_runtime_rejects_unknown_top_level_metadata(self) -> None:
        manifest = _valid_manifest()
        manifest["private_repository_name"] = "must-not-have-a-public-manifest-surface"
        with self.assertRaisesRegex(
            NexusMaterializerError,
            "NEXUS_MANIFEST_TOP_LEVEL_FIELD_INVALID",
        ):
            validate_manifest(manifest)

    def test_runtime_rejects_invalid_artifact_id(self) -> None:
        for artifact_id in ("", "x" * 201, 123):
            with self.subTest(artifact_id=artifact_id):
                manifest = _valid_manifest()
                manifest["artifact_id"] = artifact_id
                with self.assertRaisesRegex(
                    NexusMaterializerError,
                    "NEXUS_MANIFEST_ARTIFACT_ID_INVALID",
                ):
                    validate_manifest(manifest)

    def test_runtime_rejects_unknown_public_source_field(self) -> None:
        manifest = _valid_manifest()
        manifest["sources"][0]["secret_note"] = "not-part-of-the-contract"
        with self.assertRaisesRegex(
            NexusMaterializerError,
            "NEXUS_SOURCE_FIELD_INVALID:1001",
        ):
            validate_manifest(manifest)

    def test_runtime_rejects_unknown_private_source_field(self) -> None:
        manifest = _valid_manifest()
        manifest["sources"][1]["secret_note"] = "private-name-or-url-could-hide-here"
        with self.assertRaisesRegex(
            NexusMaterializerError,
            "NEXUS_SOURCE_FIELD_INVALID:1002",
        ):
            validate_manifest(manifest)

    def test_runtime_rejects_duplicate_repository_id(self) -> None:
        manifest = _valid_manifest()
        manifest["sources"][1]["repository_id"] = "1001"
        with self.assertRaisesRegex(
            NexusMaterializerError,
            "NEXUS_SOURCE_REPOSITORY_ID_INVALID",
        ):
            validate_manifest(manifest)

    def test_schema_top_level_is_closed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIs(schema.get("additionalProperties"), False)

    def test_schema_source_rows_are_closed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIs(schema["$defs"]["publicSource"].get("additionalProperties"), False)
        self.assertIs(schema["$defs"]["privateSource"].get("additionalProperties"), False)

    def test_schema_branch_rule_matches_runtime_dotdot_rejection(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        pattern = schema["$defs"]["branch"]["pattern"]
        compiled = re.compile(pattern)
        self.assertIsNotNone(compiled.fullmatch("feature/nexus-v1"))
        self.assertIsNone(compiled.fullmatch("feature/../hidden"))

    def test_schema_declares_semantic_repository_id_uniqueness(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["sources"].get("x-janus-uniqueBy"), "repository_id")


if __name__ == "__main__":
    unittest.main()
