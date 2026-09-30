#!/usr/bin/env python3
from __future__ import annotations

import ast
import asyncio
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.janus_hephaestus_crystal import (
    CrystalOptimizer,
    UnsafeScanTargetError,
    persist_report,
    run,
)


class _Core:
    def __init__(self, settings):
        self.settings = settings


class HephaestusCrystalV2Tests(unittest.TestCase):
    def _write_sizes(self, root: Path, sizes: list[int]) -> None:
        for index, size in enumerate(sizes):
            (root / f"f{index}.bin").write_bytes(b"x" * size)

    def test_constructor_is_real_dunder_init(self):
        with tempfile.TemporaryDirectory() as td:
            analyzer = CrystalOptimizer(td, allocation_unit_bytes=4096)
            self.assertEqual(analyzer.file_count, 0)
            self.assertEqual(analyzer.logical_bytes, 0)

    def test_equal_file_sizes_have_expected_shannon_entropy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_sizes(root, [10, 10, 10, 10])
            report = asyncio.run(
                CrystalOptimizer(td, allocation_unit_bytes=4096).analyze()
            )
            self.assertAlmostEqual(report.size_distribution_entropy_bits, 2.0, places=12)
            self.assertFalse(report.fragmentation_measured)
            self.assertEqual(
                report.verdict,
                "MEASUREMENT_COMPLETE_FRAGMENTATION_NOT_MEASURED",
            )

    def test_tail_slack_model_is_exact_for_declared_model_unit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_sizes(root, [1, 4096, 4097])
            report = asyncio.run(
                CrystalOptimizer(td, allocation_unit_bytes=4096).analyze()
            )
            self.assertEqual(report.logical_bytes, 8194)
            self.assertEqual(report.modeled_tail_slack_bytes, 8190)
            self.assertEqual(report.modeled_tail_slack_recovery_upper_bound_bytes, 8190)
            self.assertEqual(report.theoretical_perfect_byte_stream_tail_slack_bytes, 0)

    def test_perfect_stream_is_not_promoted_to_p_equals_np(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a").write_bytes(b"abc")
            report = asyncio.run(CrystalOptimizer(td).analyze())
            self.assertFalse(report.p_equals_np_proven)
            self.assertFalse(report.quantum_algorithm_executed)
            self.assertEqual(
                report.lineage["legacy_claim_classification"],
                "HISTORICAL_SIMULATION_CLAIM_ONLY",
            )
            self.assertFalse(report.lineage["p_equals_np_proven"])

    def test_empty_directory_is_valid_zero_entropy_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            report = asyncio.run(CrystalOptimizer(td).analyze())
            self.assertEqual(report.file_count, 0)
            self.assertEqual(report.logical_bytes, 0)
            self.assertEqual(report.size_distribution_entropy_bits, 0.0)
            self.assertEqual(report.modeled_tail_slack_bytes, 0)

    def test_scan_is_bounded_by_max_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_sizes(root, [1] * 10)
            report = asyncio.run(
                CrystalOptimizer(td, max_files=3, allocation_unit_bytes=4096).analyze()
            )
            self.assertEqual(report.file_count, 3)
            self.assertTrue(report.scan_truncated)
            self.assertFalse(report.scan_complete)
            self.assertEqual(report.status, "ANALYSIS_TRUNCATED")

    def test_depth_limit_is_fail_visible(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "one" / "two"
            nested.mkdir(parents=True)
            (nested / "deep.bin").write_bytes(b"x")
            report = asyncio.run(CrystalOptimizer(td, max_depth=0).analyze())
            self.assertTrue(report.scan_truncated)
            self.assertEqual(report.file_count, 0)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_file_is_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside.bin"
            outside.write_bytes(b"secret-data")
            link = root / "link.bin"
            link.symlink_to(outside)
            report = asyncio.run(CrystalOptimizer(td).analyze())
            self.assertEqual(report.file_count, 1)
            self.assertEqual(report.symlink_entries_skipped, 1)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            real = base / "real"
            real.mkdir()
            link = base / "root-link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(UnsafeScanTargetError):
                asyncio.run(CrystalOptimizer(str(link)).analyze())

    def test_report_does_not_publish_target_path_or_file_names(self):
        with tempfile.TemporaryDirectory() as td:
            secret_name = "PRIVATE_LOCAL_FILENAME_987654321.bin"
            Path(td, secret_name).write_bytes(b"x" * 10)
            report = asyncio.run(CrystalOptimizer(td).analyze())
            encoded = json.dumps(report.public_dict(), sort_keys=True)
            self.assertNotIn(td, encoded)
            self.assertNotIn(secret_name, encoded)

    def test_report_digest_is_deterministic_for_same_aggregates(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            self._write_sizes(Path(td1), [5, 7, 11])
            self._write_sizes(Path(td2), [11, 5, 7])
            r1 = asyncio.run(
                CrystalOptimizer(td1, allocation_unit_bytes=4096).analyze()
            )
            r2 = asyncio.run(
                CrystalOptimizer(td2, allocation_unit_bytes=4096).analyze()
            )
            # Platform allocation observations may vary only if the fixture resides
            # on different filesystems.  These temporary directories share one.
            self.assertEqual(r1.report_sha256, r2.report_sha256)

    def test_observed_allocation_delta_is_not_called_tail_slack(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.bin").write_bytes(b"x" * 123)
            report = asyncio.run(CrystalOptimizer(td).analyze())
            self.assertIn("observed_allocated_minus_logical_bytes", report.public_dict())
            self.assertIn("modeled_tail_slack_bytes", report.public_dict())
            self.assertFalse(report.extent_layout_measured)
            self.assertFalse(report.seek_locality_measured)

    def test_default_run_does_not_persist(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a").write_bytes(b"x")
            result = asyncio.run(run(_Core({"hephaestus_scan_target": td})))
            self.assertEqual(result["status"], "success")
            self.assertFalse(result["persisted"])

    def test_explicit_sqlite_persistence_stores_only_safe_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "scan"
            root.mkdir()
            secret_name = "LOCAL_PRIVATE_NAME.bin"
            (root / secret_name).write_bytes(b"hello")
            db_path = str(Path(td) / "janus.db")
            report = asyncio.run(CrystalOptimizer(str(root)).analyze())
            asyncio.run(persist_report(db_path, "OPAQUE_TARGET_01", report))
            with sqlite3.connect(db_path) as db:
                row = db.execute(
                    "SELECT target_id, p_equals_np_proven, report_json "
                    "FROM janus_hephaestus_reports_v2"
                ).fetchone()
            self.assertEqual(row[0], "OPAQUE_TARGET_01")
            self.assertEqual(row[1], 0)
            self.assertNotIn(str(root), row[2])
            self.assertNotIn(secret_name, row[2])

    def test_opt_in_run_persistence_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "scan"
            root.mkdir()
            (root / "a").write_bytes(b"abc")
            db_path = str(Path(td) / "report.db")
            result = asyncio.run(
                run(
                    _Core(
                        {
                            "hephaestus_scan_target": str(root),
                            "hephaestus_persist_report": True,
                            "hephaestus_db_path": db_path,
                            "hephaestus_target_id": "OPAQUE_TARGET_02",
                        }
                    )
                )
            )
            self.assertTrue(result["persisted"])
            self.assertTrue(Path(db_path).exists())

    def test_source_has_no_file_content_open_network_or_subprocess_surface(self):
        source_path = Path(__file__).resolve().parents[1] / "tools" / "janus_hephaestus_crystal.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden_import_roots = {
            "socket",
            "subprocess",
            "requests",
            "httpx",
            "urllib",
            "ftplib",
            "paramiko",
        }
        forbidden_calls = {
            "open",
            "os.open",
            "os.remove",
            "os.unlink",
            "os.rename",
            "os.replace",
            "os.rmdir",
            "shutil.rmtree",
            "shutil.move",
        }
        imports = set()
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    calls.add(func.id)
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    calls.add(f"{func.value.id}.{func.attr}")
        self.assertFalse(imports & forbidden_import_roots)
        self.assertFalse(calls & forbidden_calls)

    def test_contract_language_does_not_equate_entropy_with_fragmentation(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_sizes(Path(td), [1, 2, 4, 8, 16])
            report = asyncio.run(CrystalOptimizer(td).analyze())
            self.assertGreater(report.size_distribution_entropy_bits, 0.0)
            self.assertFalse(report.fragmentation_measured)


if __name__ == "__main__":
    unittest.main()
