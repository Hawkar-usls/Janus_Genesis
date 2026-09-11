# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.janus_nexus_materializer import NexusMaterializer


class JanusNexusPinnedObjectTests(unittest.TestCase):
    def test_dirty_worktree_cannot_change_materialized_pinned_commit_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            repo = sources / "1001"
            repo.mkdir(parents=True)
            subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "nexus-test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "JANUS Nexus Test"], check=True)
            tracked = repo / "tracked.txt"
            tracked.write_text("committed\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "fixture"], check=True, stdout=subprocess.DEVNULL)
            sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"]).decode("ascii").strip()

            # HEAD remains the exact declared pin, but mutable worktree bytes diverge.
            tracked.write_text("dirty-uncommitted\n", encoding="utf-8")
            manifest = {
                "schema": "janus.nexus.manifest.v1",
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
            output = root / "nexus"
            result = NexusMaterializer(manifest, sources, output).materialize()
            self.assertEqual(result["status"], "MATERIALIZED")
            self.assertFalse(result["mutable_worktree_bytes_used"])
            copied = output / "faces" / "public-1001" / "tracked.txt"
            self.assertEqual(copied.read_text(encoding="utf-8"), "committed\n")
            self.assertNotEqual(copied.read_text(encoding="utf-8"), tracked.read_text(encoding="utf-8"))
            self.assertTrue(NexusMaterializer(manifest, sources, output).verify()["ok"])


if __name__ == "__main__":
    unittest.main()
