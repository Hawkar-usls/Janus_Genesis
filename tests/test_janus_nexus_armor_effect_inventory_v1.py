# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import unittest

from tools import audit_armor_effect_drift_v18_7_50 as armor_drift


MATERIALIZER = armor_drift.ROOT / "tools" / "janus_nexus_materializer.py"
ALLOWED_GIT_QUERY_SUBCOMMANDS = frozenset({"rev-parse", "ls-tree", "cat-file"})
FORBIDDEN_GIT_EFFECT_SUBCOMMANDS = frozenset(
    {"clone", "fetch", "push", "pull", "remote", "ls-remote", "send-pack", "receive-pack"}
)


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


class JanusNexusProcessShapeTests(unittest.TestCase):
    def test_materializer_direct_process_surface_stays_narrow(self) -> None:
        rows = armor_drift.scan(MATERIALIZER)
        self.assertTrue(rows)
        self.assertEqual(
            {str(row["call"]) for row in rows},
            {"subprocess.check_output"},
        )

    def test_materializer_git_helper_uses_only_static_read_query_subcommands(self) -> None:
        tree = ast.parse(MATERIALIZER.read_text(encoding="utf-8"), filename=str(MATERIALIZER))
        helper = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "_git"
            ),
            None,
        )
        self.assertIsNotNone(helper)
        assert helper is not None

        process_calls = [
            node
            for node in ast.walk(helper)
            if isinstance(node, ast.Call) and _dotted(node.func) == "subprocess.check_output"
        ]
        self.assertEqual(len(process_calls), 1)

        query_subcommands: set[str] = set()
        dynamic_query_calls: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _dotted(node.func) != "_git":
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                dynamic_query_calls.append(int(getattr(node, "lineno", 0)))
                continue
            command = node.args[1].value
            if not isinstance(command, str):
                dynamic_query_calls.append(int(getattr(node, "lineno", 0)))
                continue
            query_subcommands.add(command)

        self.assertFalse(
            dynamic_query_calls,
            f"dynamic Git subcommand selection is outside the producer contract: {dynamic_query_calls}",
        )
        self.assertTrue(query_subcommands)
        self.assertTrue(query_subcommands <= ALLOWED_GIT_QUERY_SUBCOMMANDS)
        self.assertFalse(query_subcommands & FORBIDDEN_GIT_EFFECT_SUBCOMMANDS)


if __name__ == "__main__":
    unittest.main()
