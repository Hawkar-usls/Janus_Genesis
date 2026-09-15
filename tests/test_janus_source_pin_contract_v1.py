# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from janus_source_pin_contract import (  # noqa: E402
    GIT_COMMIT_SHA1,
    OPAQUE_VERSION_TOKEN,
    SourcePinContractError,
    adapt_legacy_source_pins,
    pinset_digest,
    public_projection,
    require_exact_git_replay,
    validate_pinset,
)


SHA_A = "a" * 40
SHA_B = "b" * 40


def pinset(rows, pinset_id="TEST-PINSET"):
    return {
        "schema": "janus.source_pin_set.v1",
        "pinset_id": pinset_id,
        "sources": rows,
    }


def row(source_id, value, *, visibility="public", kind=GIT_COMMIT_SHA1, source_kind="GIT_REPOSITORY"):
    return {
        "source_id": source_id,
        "visibility": visibility,
        "source_kind": source_kind,
        "pin": {"kind": kind, "value": value},
    }


class JanusSourcePinContractTests(unittest.TestCase):
    def test_exact_lowercase_git_commit_is_admitted(self):
        value = pinset([row("1089782172", SHA_A)])
        normalized = require_exact_git_replay(value)
        self.assertEqual(normalized["sources"][0]["pin"]["value"], SHA_A)

    def test_uppercase_git_commit_is_rejected(self):
        with self.assertRaisesRegex(
            SourcePinContractError,
            "GIT_COMMIT_SHA1_MUST_BE_LOWERCASE_40_HEX",
        ):
            validate_pinset(pinset([row("1089782172", "A" * 40)]))

    def test_sha_shaped_opaque_token_is_not_inferred_as_git_commit(self):
        value = pinset(
            [
                row(
                    "opaque-task",
                    SHA_A,
                    kind=OPAQUE_VERSION_TOKEN,
                    source_kind="GIT_REPOSITORY",
                )
            ]
        )
        normalized = validate_pinset(value)
        self.assertEqual(normalized["sources"][0]["pin"]["kind"], OPAQUE_VERSION_TOKEN)
        with self.assertRaisesRegex(
            SourcePinContractError,
            "EXACT_GIT_REPLAY_REQUIRES_GIT_COMMIT_SHA1:opaque-task",
        ):
            require_exact_git_replay(value)

    def test_exact_git_replay_rejects_non_git_source_kind(self):
        value = pinset(
            [row("artifact", SHA_A, source_kind="OPAQUE_RESOURCE")]
        )
        with self.assertRaisesRegex(
            SourcePinContractError,
            "EXACT_GIT_REPLAY_SOURCE_KIND_INVALID:artifact",
        ):
            require_exact_git_replay(value)

    def test_adapter_requires_explicit_complete_visibility_mapping(self):
        with self.assertRaisesRegex(
            SourcePinContractError,
            "LEGACY_ADAPTER_VISIBILITY_SET_MISMATCH",
        ):
            adapt_legacy_source_pins(
                {"1089782172": SHA_A, "1103537693": SHA_B},
                pin_kind=GIT_COMMIT_SHA1,
                source_kind="GIT_REPOSITORY",
                visibility_by_source={"1089782172": "public"},
                pinset_id="LEGACY",
            )

    def test_adapter_does_not_infer_opaque_40hex_as_git(self):
        adapted = adapt_legacy_source_pins(
            {"task": SHA_A},
            pin_kind=OPAQUE_VERSION_TOKEN,
            source_kind="GIT_REPOSITORY",
            visibility_by_source={"task": "public"},
            pinset_id="LEGACY-OPAQUE",
        )
        self.assertEqual(adapted["sources"][0]["pin"]["kind"], OPAQUE_VERSION_TOKEN)
        with self.assertRaises(SourcePinContractError):
            require_exact_git_replay(adapted)

    def test_canonical_digest_is_order_independent_for_source_rows(self):
        first = pinset(
            [
                row("b-source", SHA_B),
                row("a-source", SHA_A),
            ]
        )
        second = pinset(
            [
                row("a-source", SHA_A),
                row("b-source", SHA_B),
            ]
        )
        self.assertEqual(pinset_digest(first), pinset_digest(second))

    def test_duplicate_source_id_is_rejected(self):
        with self.assertRaisesRegex(
            SourcePinContractError,
            "SOURCE_PIN_SOURCE_ID_DUPLICATE",
        ):
            validate_pinset(
                pinset(
                    [
                        row("same", SHA_A),
                        row("same", SHA_B),
                    ]
                )
            )

    def test_private_source_id_must_be_opaque_numeric(self):
        with self.assertRaisesRegex(
            SourcePinContractError,
            "PRIVATE_SOURCE_ID_MUST_BE_OPAQUE_NUMERIC",
        ):
            validate_pinset(
                pinset(
                    [
                        row(
                            "private-repository-name",
                            SHA_B,
                            visibility="private",
                        )
                    ]
                )
            )

    def test_private_projection_omits_exact_value_whole_digest_and_local_id(self):
        secret_pinset_id = "PRIVATE-REPOSITORY-NAME-MUST-NOT-LEAK"
        value = pinset(
            [
                row("1089782172", SHA_A, visibility="public"),
                row("1112728873", SHA_B, visibility="private"),
            ],
            pinset_id=secret_pinset_id,
        )
        projected = public_projection(value)
        serialized = json.dumps(projected, sort_keys=True)
        self.assertIn(SHA_A, serialized)
        self.assertNotIn(SHA_B, serialized)
        self.assertNotIn(secret_pinset_id, serialized)
        self.assertNotIn("pinset_digest", projected)
        self.assertNotIn("pinset_id", projected)
        self.assertFalse(projected["local_pinset_id_published"])
        self.assertFalse(projected["whole_pinset_digest_published"])
        private = next(
            item for item in projected["sources"] if item["visibility"] == "private"
        )
        self.assertNotIn("pin_value", private)
        self.assertFalse(private["pin_value_public"])
        self.assertTrue(private["local_pin_validated"])
        self.assertTrue(private["exact_git_replay_eligible_locally"])

    def test_opaque_version_token_rejects_whitespace(self):
        with self.assertRaisesRegex(
            SourcePinContractError,
            "OPAQUE_VERSION_TOKEN_INVALID",
        ):
            validate_pinset(
                pinset(
                    [
                        row(
                            "task",
                            "version token with spaces",
                            kind=OPAQUE_VERSION_TOKEN,
                            source_kind="OPAQUE_RESOURCE",
                        )
                    ]
                )
            )


if __name__ == "__main__":
    unittest.main()
