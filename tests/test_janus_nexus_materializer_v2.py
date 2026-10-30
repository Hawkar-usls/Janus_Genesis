"""Offline fail-closed tests for inert symlink/gitlink Nexus source materialization."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "janus_nexus_materializer_v2.py"
spec = importlib.util.spec_from_file_location("janus_nexus_materializer_v2_test", MODULE)
assert spec and spec.loader
materializer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = materializer
spec.loader.exec_module(materializer)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args],
                                   stderr=subprocess.DEVNULL, text=True).strip()


@unittest.skipUnless(os.name == "posix", "requires POSIX symlink semantics")
class InertGitSourceTests(unittest.TestCase):
    GITLINK_SHA = "a" * 40

    def test_live_git_tree_symlink_and_gitlink_are_inert_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sources" / "123"
            source.mkdir(parents=True)
            subprocess.run(["git", "init", "-b", "main", str(source)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            git(source, "config", "user.name", "JANUS TEST")
            git(source, "config", "user.email", "test@example.invalid")
            (source / "hello.txt").write_text("hello from pinned Git\n", encoding="utf-8")
            os.symlink("../../sensitive/location", source / "external-link")
            git(source, "add", "hello.txt", "external-link")
            git(source, "update-index", "--add", "--cacheinfo",
                f"160000,{self.GITLINK_SHA},vendor/opaque")
            git(source, "commit", "-m", "inert tree contract")
            original_head = git(source, "rev-parse", "HEAD")
            manifest = {
                "schema": "janus.nexus.manifest.v1",
                "artifact_id": "INERT-TEST",
                "write_back_default": "DENY",
                "source_code_execution": False,
                "sources": [{
                    "repository_id": "123", "visibility": "public",
                    "repository": "Hawkar-usls/inert-fixture",
                    "branch": "main", "sha": original_head,
                }],
            }
            nexus = root / "nexus"
            instance = materializer.NexusMaterializer(manifest, root / "sources", nexus)
            created = instance.materialize()
            self.assertEqual(created["source_count"], 1)
            self.assertTrue(instance.verify()["ok"])

            body = nexus / "faces" / "public-123"
            link = body / "external-link"
            self.assertTrue(link.is_file())
            self.assertFalse(link.is_symlink())
            self.assertEqual(link.read_bytes(), b"../../sensitive/location")
            gitlink = body / "vendor" / "opaque"
            self.assertTrue(gitlink.is_file())
            self.assertFalse(gitlink.is_symlink())
            self.assertEqual(
                gitlink.read_bytes(),
                b"JANUS_INERT_GITLINK_V1\n" + self.GITLINK_SHA.encode("ascii") + b"\n",
            )
            receipt = json.loads((nexus / "NEXUS_ID.json").read_text())
            rows = {r["path"]: r for r in receipt["sources"][0]["files"]}
            self.assertEqual(rows["external-link"]["git_mode"], "120000")
            self.assertEqual(rows["vendor/opaque"]["git_mode"], "160000")
            self.assertEqual(
                rows["external-link"]["inert_representation"],
                "SYMLINK_TARGET_BLOB_BYTES_NOT_FOLLOWED",
            )
            self.assertEqual(
                rows["vendor/opaque"]["inert_representation"],
                "GITLINK_COMMIT_REF_ONLY_NO_RECURSIVE_FETCH",
            )
            self.assertFalse(receipt["network_access_performed"])
            self.assertFalse(receipt["source_code_executed"])
            self.assertFalse(receipt["source_write_back_performed"])
            self.assertEqual(git(source, "rev-parse", "HEAD"), original_head)

            # An altered inert link target must break the read-back receipt.
            link.write_bytes(b"../../modified")
            result = instance.verify()
            self.assertFalse(result["ok"])
            self.assertIn("NEXUS_BODY_FILE_DIGEST_MISMATCH:123", result["errors"])


if __name__ == "__main__":
    unittest.main()
