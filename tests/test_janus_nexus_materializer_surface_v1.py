# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.janus_nexus_materializer import NexusMaterializer


class JanusNexusExactSurfaceTests(unittest.TestCase):
    def _make_repo(self, root: Path) -> tuple[Path, str]:
        repo = root / "sources" / "1001"
        repo.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "nexus-test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "JANUS Nexus Test"],
            check=True,
        )
        (repo / "tracked.txt").write_text("committed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "fixture"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            stderr=subprocess.STDOUT,
        ).decode("ascii").strip()
        return repo, sha

    def _manifest(self, sha: str) -> dict:
        return {
            "schema": "janus.nexus.manifest.v1",
            "artifact_id": "TEST-NEXUS-EXACT-SURFACE",
            "write_back_default": "DENY",
            "source_code_execution": False,
            "sources": [
                {
                    "repository_id": "1001",
                    "visibility": "public",
                    "repository": "Hawkar-usls/Alpha",
                    "branch": "main",
                    "sha": sha,
                }
            ],
        }

    def _materialize(self, root: Path) -> tuple[NexusMaterializer, Path]:
        _, sha = self._make_repo(root)
        output = root / "nexus"
        materializer = NexusMaterializer(self._manifest(sha), root / "sources", output)
        materializer.materialize()
        self.assertTrue(materializer.verify()["ok"])
        return materializer, output

    def test_unreceipted_body_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            materializer, output = self._materialize(Path(tmp))
            extra = output / "faces" / "public-1001" / "extra.txt"
            extra.write_text("unreceipted\n", encoding="utf-8")

            result = materializer.verify()

            self.assertFalse(result["ok"])
            self.assertIn("NEXUS_BODY_SURFACE_MISMATCH:1001", result["errors"])

    def test_modified_source_receipt_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            materializer, output = self._materialize(Path(tmp))
            source_json = output / "faces" / "public-1001" / "SOURCE.json"
            receipt = json.loads(source_json.read_text(encoding="utf-8"))
            receipt["write_back_performed"] = True
            source_json.write_text(
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

            result = materializer.verify()

            self.assertFalse(result["ok"])
            self.assertIn("NEXUS_SOURCE_RECEIPT_MISMATCH:1001", result["errors"])

    def test_unexpected_root_artifact_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            materializer, output = self._materialize(Path(tmp))
            (output / "UNRECEIPTED.txt").write_text("unexpected\n", encoding="utf-8")

            result = materializer.verify()

            self.assertFalse(result["ok"])
            self.assertIn("NEXUS_ROOT_SURFACE_MISMATCH", result["errors"])


if __name__ == "__main__":
    unittest.main()
