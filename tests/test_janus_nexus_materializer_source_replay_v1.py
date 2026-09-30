# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.janus_nexus_materializer import NexusMaterializer


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class JanusNexusPinnedSourceReplayTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[NexusMaterializer, dict, Path]:
        sources = root / "sources"
        repo = sources / "1001"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "nexus-test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "JANUS Nexus Test"], check=True)
        (repo / "tracked.txt").write_text("pinned-source-bytes\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "pinned source"], check=True, stdout=subprocess.DEVNULL)
        sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"]).decode("ascii").strip()
        manifest = {
            "schema": "janus.nexus.manifest.v1",
            "artifact_id": "TEST-PINNED-SOURCE-REPLAY",
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
        materializer = NexusMaterializer(manifest, sources, output)
        materializer.materialize()
        self.assertTrue(materializer.verify()["ok"])
        return materializer, manifest, output

    def test_self_consistent_receipt_rewrite_cannot_replace_pinned_commit_truth(self) -> None:
        """A forged body may not become valid merely by rewriting its own receipts.

        This is the key distinction between a self-consistent archive and a replay
        against the manifest's historical Git commit authority.
        """
        with tempfile.TemporaryDirectory() as tmp:
            materializer, manifest, output = self._fixture(Path(tmp))
            face = output / "faces" / "public-1001"
            forged = b"forged-but-self-consistent\n"
            (face / "tracked.txt").write_bytes(forged)

            nexus_receipt = json.loads((output / "NEXUS_ID.json").read_text(encoding="utf-8"))
            source_row = nexus_receipt["sources"][0]
            file_row = source_row["files"][0]

            # Keep the declared Git blob identity and source commit pin, but rewrite
            # all self-reported byte digests to agree with the forged lab body.
            # A verifier grounded only in its own receipts can be fooled by this;
            # a pinned-source replay verifier must compare back to Git objects.
            file_row["bytes"] = len(forged)
            file_row["sha256"] = hashlib.sha256(forged).hexdigest()
            source_row["tree_sha256"] = _sha256_json(source_row["files"])

            (face / "SOURCE.json").write_text(
                json.dumps(source_row, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            identity_basis = {
                "schema": "janus.nexus.materialization_receipt.v1",
                "manifest_sha256": nexus_receipt["manifest_sha256"],
                "sources": [
                    {
                        "repository_id": source_row["repository_id"],
                        "sha": source_row["sha"],
                        "tree_sha256": source_row["tree_sha256"],
                    }
                ],
            }
            nexus_receipt["nexus_digest"] = _sha256_json(identity_basis)
            (output / "NEXUS_ID.json").write_text(
                json.dumps(nexus_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

            result = NexusMaterializer(manifest, materializer.sources_root, output).verify()
            self.assertFalse(result["ok"], result)
            self.assertIn("NEXUS_SOURCE_RECEIPT_PIN_MISMATCH:1001", result["errors"])


if __name__ == "__main__":
    unittest.main()
