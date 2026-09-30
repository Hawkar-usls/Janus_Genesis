# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.janus_nexus_materializer import NexusMaterializer, NexusMaterializerError


def _init_repo(root: Path, filename: str = "tracked.txt") -> tuple[Path, str]:
    sources = root / "sources"
    repo = sources / "1001"
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
    (repo / filename).write_text("historical-source-bytes\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "reserved path fixture"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        stderr=subprocess.STDOUT,
    ).decode("ascii").strip()
    return repo, sha


def _manifest(sha: str) -> dict:
    return {
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


class JanusNexusReservedPathTests(unittest.TestCase):
    def test_source_root_source_json_cannot_collide_with_nexus_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, sha = _init_repo(root, "SOURCE.json")

            with self.assertRaisesRegex(
                NexusMaterializerError,
                "NEXUS_SOURCE_RESERVED_PATH_REJECTED:SOURCE.json",
            ):
                NexusMaterializer(_manifest(sha), root / "sources", root / "nexus").materialize()

            # Fail before any source blob can be represented under a path that is
            # also owned by the Nexus receipt namespace.
            self.assertFalse((root / "nexus" / "faces" / "public-1001" / "SOURCE.json").exists())

    def test_output_root_symlink_cannot_redirect_writes_into_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, sha = _init_repo(root)

            # An empty untracked directory inside the source checkout would pass
            # the old output-root emptiness check. A symlinked Nexus root could
            # therefore redirect supposedly disposable output into source state.
            redirected = repo / "nexus-output"
            redirected.mkdir()
            output_link = root / "nexus"
            output_link.symlink_to(redirected, target_is_directory=True)

            with self.assertRaisesRegex(
                NexusMaterializerError,
                "NEXUS_OUTPUT_ROOT_SYMLINK_REJECTED",
            ):
                NexusMaterializer(_manifest(sha), root / "sources", output_link).materialize()

            self.assertEqual(list(redirected.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
