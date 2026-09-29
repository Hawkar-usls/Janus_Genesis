# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
import unittest
from collections import Counter
from pathlib import Path

from tools import run_top100_round1_stratified as gate

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "benchmarks" / "frozen_samples" / "top100_round1_stratified_v0.1.json"
RUNNER = ROOT / "tools" / "run_top100_round1_stratified.py"


class Top100Round1StratifiedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack = json.loads(PACK.read_text(encoding="utf-8"))

    def test_pack_is_exactly_21_unique_frozen_samples(self) -> None:
        self.assertEqual([], gate.validate_pack(self.pack))
        rows = self.pack["samples"]
        self.assertEqual(21, len(rows))
        self.assertEqual(21, len({row["sample_id"] for row in rows}))
        self.assertEqual(
            {
                "GSM8K": 5,
                "TruthfulQA": 5,
                "BIG-Bench Hard (BBH)": 5,
                "IFEval": 5,
                "HumanEval": 1,
            },
            dict(Counter(row["benchmark"] for row in rows)),
        )

    def test_frozen_source_blob_ids_are_present(self) -> None:
        sources = self.pack["frozen_sources"]
        self.assertEqual(
            "e4c2ff4942b9a78bd74f04141224c11e28d12dc9",
            sources["gsm8k"]["git_blob_sha1"],
        )
        self.assertEqual(
            "4206d1e78db1b13612062ac816f6db0443d0e92b",
            sources["truthfulqa"]["git_blob_sha1"],
        )
        self.assertEqual(
            "cbe52f6eecf3986fdac745b4acba4da1408eb146",
            sources["ifeval"]["git_blob_sha1"],
        )
        self.assertEqual(
            "8de29eba01188e46784a4b1ec63ade9b50a4548c",
            sources["bbh"]["git_blob_sha1"],
        )
        self.assertEqual(
            "06236282a45e10e92233e2b8f84cea10ae25be46",
            sources["humaneval_example"]["git_blob_sha1"],
        )

    def test_numeric_and_choice_parsers(self) -> None:
        self.assertEqual("18", gate._last_number("Reasoning... final answer 18"))
        self.assertTrue(gate._numeric_equal("70000", "70000"))
        self.assertEqual("(B)", gate._choice("Therefore the answer is (B)."))
        self.assertEqual("(C)", gate._choice("C"))
        self.assertEqual("(B)", gate._choice("B because it is a better answer"))
        self.assertEqual(
            "(B)",
            gate._choice("Options: (A) foo, (B) bar, (C) baz. Final answer: B"),
        )
        self.assertIsNone(gate._choice("This is a better answer"))
        self.assertIsNone(gate._choice("I considered (A), (B), and (C)."))

    def test_ifeval_subset_graders(self) -> None:
        ok, _ = gate.grade_ifeval_subset(
            "two rocket jokes******second rocket joke",
            {
                "checks": [
                    {"type": "forbidden_character", "value": ","},
                    {"type": "exact_separator_count", "separator": "******", "value": 1},
                ]
            },
        )
        self.assertTrue(ok)
        bad, _ = gate.grade_ifeval_subset(
            "Hello, World",
            {"checks": [{"type": "forbidden_character", "value": ","}]},
        )
        self.assertFalse(bad)
        json_ok, _ = gate.grade_ifeval_subset(
            '{"product":"soft diaper"}',
            {"checks": [{"type": "valid_json"}]},
        )
        self.assertTrue(json_ok)

    def test_humaneval_source_builder_is_deterministic_without_execution(self) -> None:
        source = gate._build_humaneval_source("def return1():\n", "return 1")
        self.assertIn("def return1():", source)
        self.assertIn("    return 1", source)
        self.assertEqual(source, gate._build_humaneval_source("def return1():\n", "return 1"))

    def test_humaneval_source_builder_preserves_nested_indentation(self) -> None:
        source = gate._build_humaneval_source(
            "def return1():\n",
            "if True:\n    return 1",
        )
        self.assertIn("    if True:\n        return 1", source)
        compile(source, "<nested-humaneval-fixture>", "exec")

    def test_benchmark_runner_has_no_genesis_runtime_import(self) -> None:
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)
        self.assertFalse(any(name.startswith("genesis_") for name in imported_modules))
        self.assertFalse(any(name == "play_genesis" for name in imported_modules))

    def test_effective_messages_separate_raw_and_overlay(self) -> None:
        sample = self.pack["samples"][0]
        overlay = "BOUNDARY"
        raw = gate._messages(sample, "RAW_PROVIDER", overlay)
        bound = gate._messages(sample, "GENESIS_BOUNDARY_OVERLAY", overlay)
        self.assertEqual(1, len(raw))
        self.assertEqual(2, len(bound))
        self.assertEqual("system", bound[0]["role"])
        self.assertEqual(overlay, bound[0]["content"])
        self.assertEqual(raw[-1], bound[-1])


if __name__ == "__main__":
    unittest.main()
