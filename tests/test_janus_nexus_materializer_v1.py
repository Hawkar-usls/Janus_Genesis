# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.janus_nexus_materializer import (
    NexusMaterializer,
    NexusMaterializerError,
    validate_manifest,
)


class JanusNexusMaterializerTests(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.STDOUT
        ).decode("utf-8").strip()

    def _make_repo(self, root: Path, repo_id: str, files: dict[str, str]) -> tuple[Path, str]:
        repo = root / repo_id
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "nexus-test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "JANUS Nexus Test"], check=True)
        for rel, text in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "--all"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "fixture"], check=True, stdout=subprocess.DEVNULL)
        return repo, self._git(repo, "rev-parse", "HEAD")

    def _manifest(self, public_sha: str, private_sha: str | None = None) -> dict:
        sources = [
            {
                "repository_id": "1001",
                "visibility": "public",
                "repository": "Hawkar-usls/Alpha",
                "branch": "main",
                "sha": public_sha,
            }
        ]
        if private_sha is not None:
            sources.append(
                {
                    "repository_id": "2002",
                    "visibility": "private",
                    "branch": "main",
                    "sha": private_sha,
                }
            )
        return {
            "schema": "janus.nexus.manifest.v1",
            "artifact_id": "TEST-NEXUS-MANIFEST",
            "write_back_default": "DENY",
            "source_code_execution": False,
            "sources": sources,
        }

    def test_materializes_exact_pins_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            _, public_sha = self._make_repo(
                sources,
                "1001",
                {"README.md": "alpha\n", "src/value.txt": "one\n"},
            )
            _, private_sha = self._make_repo(
                sources,
                "2002",
                {"private.txt": "opaque body\n"},
            )
            output = root / "nexus"
            materializer = NexusMaterializer(self._manifest(public_sha, private_sha), sources, output)
            result = materializer.materialize()
            self.assertEqual(result["status"], "MATERIALIZED")
            self.assertEqual(result["source_count"], 2)
            self.assertFalse(result["source_write_back_performed"])
            self.assertFalse(result["source_code_executed"])
            self.assertTrue(materializer.verify()["ok"])
            self.assertFalse((output / "faces" / "public-1001" / ".git").exists())
            private_receipt = json.loads(
                (output / "faces" / "private-2002" / "SOURCE.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("repository", private_receipt)
            self.assertNotIn("name", private_receipt)

    def test_same_manifest_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            _, sha = self._make_repo(sources, "1001", {"a.txt": "same\n"})
            manifest = self._manifest(sha)
            output = root / "nexus"
            first = NexusMaterializer(manifest, sources, output).materialize()
            second = NexusMaterializer(manifest, sources, output).materialize()
            self.assertEqual(first["status"], "MATERIALIZED")
            self.assertEqual(second["status"], "ALREADY_MATERIALIZED")
            self.assertEqual(first["nexus_digest"], second["nexus_digest"])

    def test_independent_rebuilds_have_same_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            _, sha = self._make_repo(
                sources,
                "1001",
                {"a.txt": "alpha\n", "dir/b.txt": "beta\n"},
            )
            manifest = self._manifest(sha)
            left = NexusMaterializer(manifest, sources, root / "left").materialize()
            right = NexusMaterializer(manifest, sources, root / "right").materialize()
            self.assertEqual(left["nexus_digest"], right["nexus_digest"])

    def test_wrong_source_sha_fails_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            self._make_repo(sources, "1001", {"a.txt": "alpha\n"})
            manifest = self._manifest("0" * 40)
            output = root / "nexus"
            with self.assertRaisesRegex(NexusMaterializerError, "NEXUS_SOURCE_SHA_MISMATCH"):
                NexusMaterializer(manifest, sources, output).materialize()
            self.assertFalse((output / "faces").exists())

    def test_late_wrong_source_sha_fails_before_any_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            _, public_sha = self._make_repo(sources, "1001", {"a.txt": "alpha\n"})
            self._make_repo(sources, "2002", {"private.txt": "opaque\n"})
            manifest = self._manifest(public_sha, "0" * 40)
            output = root / "nexus"
            with self.assertRaisesRegex(NexusMaterializerError, "NEXUS_SOURCE_SHA_MISMATCH"):
                NexusMaterializer(manifest, sources, output).materialize()
            self.assertFalse(output.exists())
            self.assertFalse((output / "faces").exists())
            self.assertFalse((output / "NEXUS_ID.json").exists())

    def test_changed_manifest_cannot_replace_bound_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            _, sha = self._make_repo(sources, "1001", {"a.txt": "alpha\n"})
            manifest = self._manifest(sha)
            output = root / "nexus"
            NexusMaterializer(manifest, sources, output).materialize()
            changed = dict(manifest)
            changed["artifact_id"] = "DIFFERENT-MANIFEST"
            with self.assertRaisesRegex(
                NexusMaterializerError, "NEXUS_ALREADY_BOUND_TO_DIFFERENT_MANIFEST"
            ):
                NexusMaterializer(changed, sources, output).materialize()

    def test_private_repository_metadata_is_rejected(self) -> None:
        manifest = {
            "schema": "janus.nexus.manifest.v1",
            "write_back_default": "DENY",
            "source_code_execution": False,
            "sources": [
                {
                    "repository_id": "2002",
                    "visibility": "private",
                    "repository": "Hawkar-usls/SecretName",
                    "branch": "main",
                    "sha": "a" * 40,
                }
            ],
        }
        with self.assertRaisesRegex(NexusMaterializerError, "NEXUS_PRIVATE_REPOSITORY_METADATA_LEAK"):
            validate_manifest(manifest)

    def test_tampered_materialized_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root / "sources"
            _, sha = self._make_repo(sources, "1001", {"a.txt": "original\n"})
            manifest = self._manifest(sha)
            output = root / "nexus"
            materializer = NexusMaterializer(manifest, sources, output)
            materializer.materialize()
            (output / "faces" / "public-1001" / "a.txt").write_text("tampered\n", encoding="utf-8")
            result = materializer.verify()
            self.assertFalse(result["ok"])
            self.assertIn("NEXUS_BODY_FILE_DIGEST_MISMATCH:1001", result["errors"])


if __name__ == "__main__":
    unittest.main()
