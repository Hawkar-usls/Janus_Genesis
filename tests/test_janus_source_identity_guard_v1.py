from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.janus_source_identity_guard import (
    SourceIdentityGuardError,
    capture,
    compare,
    public_projection,
    validate_config,
)


class JanusSourceIdentityGuardV1Tests(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.STDOUT
        ).decode("ascii").strip()

    def _make_repo(self, root: Path, repo_id: str, text: str = "alpha\n") -> Path:
        repo = root / repo_id
        repo.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "guard@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "JANUS Guard Test"],
            check=True,
        )
        (repo / "tracked.txt").write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "fixture"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return repo

    def _config(self, *repo_ids: str) -> dict[str, object]:
        return {
            "schema": "janus.source_identity_guard.config.v1",
            "sources": [
                {
                    "repository_id": repo_id,
                    "visibility": "private" if repo_id.startswith("9") else "public",
                }
                for repo_id in repo_ids
            ],
        }

    def test_unchanged_endpoint_identity_compares_equal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            self._make_repo(root, "1001")
            config = self._config("1001")
            before = capture(config, root)
            after = capture(config, root)
            receipt = compare(before, after)
            self.assertTrue(receipt["source_identity_unchanged"])
            self.assertFalse(receipt["source_identity_drift_observed"])
            self.assertEqual(
                receipt["before_snapshot_digest"], receipt["after_snapshot_digest"]
            )
            self.assertFalse(receipt["writeback_attribution_made"])
            self.assertFalse(receipt["transient_write_and_restore_ruled_out"])

    def test_tracked_worktree_byte_change_is_detected_even_without_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "1001")
            config = self._config("1001")
            before = capture(config, root)
            original_head = self._git(repo, "rev-parse", "HEAD")
            (repo / "tracked.txt").write_text(
                "mutated but uncommitted\n", encoding="utf-8"
            )
            after = capture(config, root)
            self.assertEqual(original_head, self._git(repo, "rev-parse", "HEAD"))
            receipt = compare(before, after)
            self.assertFalse(receipt["source_identity_unchanged"])
            self.assertEqual(receipt["drifted_repository_ids"], ["1001"])

    def test_untracked_addition_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "1001")
            config = self._config("1001")
            before = capture(config, root)
            (repo / "untracked.bin").write_bytes(b"new local bytes")
            after = capture(config, root)
            self.assertTrue(compare(before, after)["source_identity_drift_observed"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_target_change_is_detected_without_following_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "1001")
            (repo / "pointer").symlink_to("tracked.txt")
            config = self._config("1001")
            before = capture(config, root)
            (repo / "pointer").unlink()
            (repo / "pointer").symlink_to("other-target")
            after = capture(config, root)
            self.assertTrue(compare(before, after)["source_identity_drift_observed"])

    def test_new_commit_changes_head_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "1001")
            config = self._config("1001")
            before = capture(config, root)
            (repo / "tracked.txt").write_text("new committed bytes\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-m", "second"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            after = capture(config, root)
            self.assertNotEqual(
                before["sources"][0]["head_commit"],
                after["sources"][0]["head_commit"],
            )
            self.assertTrue(compare(before, after)["source_identity_drift_observed"])

    def test_git_identity_change_during_capture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            self._make_repo(root, "1001")
            with patch(
                "tools.janus_source_identity_guard._git_readonly",
                side_effect=["a" * 40, "b" * 40, "c" * 40, "b" * 40],
            ):
                with self.assertRaisesRegex(
                    SourceIdentityGuardError, "Git identity changed during capture"
                ):
                    capture(self._config("1001"), root)

    def test_git_metadata_noise_is_excluded_from_worktree_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "1001")
            config = self._config("1001")
            before = capture(config, root)
            (repo / ".git" / "JANUS_GUARD_NOISE").write_text(
                "metadata only\n", encoding="utf-8"
            )
            after = capture(config, root)
            self.assertEqual(before["snapshot_digest"], after["snapshot_digest"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_source_checkout_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "sources"
            real = parent / "real"
            self._make_repo(real, "1001")
            root.mkdir()
            (root / "1001").symlink_to(real / "1001", target_is_directory=True)
            with self.assertRaisesRegex(SourceIdentityGuardError, "source checkout invalid"):
                capture(self._config("1001"), root)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO support required")
    def test_special_worktree_file_is_rejected_without_opening_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "1001")
            os.mkfifo(repo / "pipe")
            with self.assertRaisesRegex(
                SourceIdentityGuardError, "unsupported special worktree"
            ):
                capture(self._config("1001"), root)

    def test_config_is_closed_and_repository_ids_are_opaque_numeric(self) -> None:
        bad = self._config("1001")
        bad["sources"][0]["repository_name"] = "private-name"  # type: ignore[index]
        with self.assertRaisesRegex(SourceIdentityGuardError, "fields invalid"):
            validate_config(bad)
        with self.assertRaisesRegex(SourceIdentityGuardError, "opaque numeric"):
            validate_config(self._config("private-repo-name"))

    def test_config_order_does_not_change_snapshot_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            self._make_repo(root, "1001", "one\n")
            self._make_repo(root, "9002", "two\n")
            left = capture(self._config("9002", "1001"), root)
            right = capture(self._config("1001", "9002"), root)
            self.assertEqual(left["snapshot_digest"], right["snapshot_digest"])

    def test_public_projection_hides_local_fingerprints_and_drift_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            repo = self._make_repo(root, "9002")
            config = self._config("9002")
            before = capture(config, root)
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            after = capture(config, root)
            local = compare(before, after)
            projected = public_projection(local)
            serialized = json.dumps(projected, sort_keys=True)
            self.assertNotIn(local["before_snapshot_digest"], serialized)
            self.assertNotIn(local["after_snapshot_digest"], serialized)
            self.assertNotIn("9002", serialized)
            self.assertFalse(projected["local_source_fingerprints_published"])
            self.assertFalse(projected["drifted_repository_ids_published"])

    def test_snapshot_tamper_is_rejected_before_compare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            self._make_repo(root, "1001")
            snapshot = capture(self._config("1001"), root)
            snapshot["sources"][0]["worktree_digest"] = "0" * 64
            with self.assertRaisesRegex(SourceIdentityGuardError, "snapshot digest mismatch"):
                compare(snapshot, capture(self._config("1001"), root))

    def test_forged_compare_flags_are_rejected_before_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sources"
            self._make_repo(root, "1001")
            snapshot = capture(self._config("1001"), root)
            receipt = compare(snapshot, snapshot)
            receipt["after_snapshot_digest"] = "0" * 64
            with self.assertRaisesRegex(
                SourceIdentityGuardError, "digest/identity flags inconsistent"
            ):
                public_projection(receipt)

            receipt = compare(snapshot, snapshot)
            receipt["source_identity_unchanged"] = False
            receipt["source_identity_drift_observed"] = True
            receipt["drifted_repository_ids"] = []
            with self.assertRaises(SourceIdentityGuardError):
                public_projection(receipt)


if __name__ == "__main__":
    unittest.main()
