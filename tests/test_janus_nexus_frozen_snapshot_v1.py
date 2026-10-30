"""Source-safe frozen manifest transfer and moving-HEAD replay regressions."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


snapshot = module("janus_nexus_frozen_snapshot_v1", "tools/janus_nexus_frozen_snapshot_v1.py")
acquire = module("janus_nexus_cloud_acquire_v2_replay_test", "tools/janus_nexus_cloud_acquire_v2.py")


def _manifest():
    rows = [{
        "repository_id": str(1_000_000_000 + i),
        "visibility": "public",
        "repository": f"Hawkar-usls/fixture-{i}",
        "branch": "main",
        "sha": f"{i+1:040x}",
    } for i in range(41)]
    rows += [{
        "repository_id": str(2_000_000_000 + i),
        "visibility": "private", "branch": "main",
        "sha": f"{i+101:040x}",
    } for i in range(3)]
    return {"schema": "janus.nexus.manifest.v1",
            "artifact_id": "FROZEN-TEST",
            "write_back_default": "DENY",
            "source_code_execution": False,
            "sources": rows}


class FrozenSnapshotTests(unittest.TestCase):
    TOKEN = "fake-only-unit-test-secret-" * 4

    def test_authenticated_snapshot_no_private_names_or_pins_in_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clear = root / "manifest.json"
            sealed = root / "manifest.aead.json"
            restored = root / "restored.json"
            manifest = _manifest()
            clear.write_text(json.dumps(manifest), encoding="utf-8")
            snapshot.seal(clear, sealed, self.TOKEN, "41040048498")
            raw = sealed.read_text("ascii")
            self.assertNotIn("private", raw)
            self.assertNotIn("Hawkar-usls", raw)
            self.assertNotIn(manifest["sources"][41]["repository_id"], raw)
            self.assertNotIn(manifest["sources"][41]["sha"], raw)
            snapshot.open_snapshot(sealed, restored, self.TOKEN, "41040048498")
            self.assertEqual(json.loads(restored.read_text()), manifest)
            self.assertEqual(restored.stat().st_mode & 0o077, 0)

            with self.assertRaises(snapshot.SnapshotHold):
                snapshot.open_snapshot(sealed, root / "different-run.json", self.TOKEN, "41040048499")
            with self.assertRaises(snapshot.SnapshotHold):
                snapshot.open_snapshot(sealed, root / "different-token.json", self.TOKEN+"bad", "41040048498")
            changed = json.loads(raw)
            ciphertext = changed["ciphertext"]
            changed["ciphertext"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
            sealed.write_text(json.dumps(changed))
            with self.assertRaises(snapshot.SnapshotHold):
                snapshot.open_snapshot(sealed, root / "tampered.json", self.TOKEN, "41040048498")

    def test_private_name_in_manifest_rejected_before_encryption(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            m = _manifest()
            m["sources"][-1]["repository"] = "private/name-must-not-export"
            original = root / "in.json"
            original.write_text(json.dumps(m))
            with self.assertRaises(snapshot.SnapshotHold):
                snapshot.seal(original, root / "out.aead.json", self.TOKEN, "22")
            self.assertFalse((root / "out.aead.json").exists())

    def test_no_authority_or_missing_sources_can_be_sealed(self):
        for change in (lambda m: m.update(write_back_default="ALLOW"),
                       lambda m: m["sources"].pop(),
                       lambda m: m["sources"][2].update(sha="invalid")):
            m = _manifest()
            change(m)
            with self.assertRaises(snapshot.SnapshotHold):
                snapshot._manifest(json.dumps(m).encode())


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args],
                                   text=True, stderr=subprocess.DEVNULL).strip()


class FrozenReplayTests(unittest.TestCase):
    def test_b_uses_original_sha_after_remote_head_moves(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            origin = root / "origin"
            origin.mkdir()
            subprocess.run(["git", "init", "-b", "main", str(origin)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            git(origin, "config", "user.name", "JANUS-TEST")
            git(origin, "config", "user.email", "unit@example.invalid")
            (origin / "f.txt").write_text("VERSION-A\n")
            git(origin, "add", "f.txt")
            git(origin, "commit", "-m", "source frozen at A")
            frozen_sha = git(origin, "rev-parse", "HEAD")
            (origin / "f.txt").write_text("VERSION-B\n")
            git(origin, "commit", "-am", "source advances during worker A")
            latest_sha = git(origin, "rev-parse", "HEAD")

            def local_clone(repository, destination):
                subprocess.run([
                    "git", "clone", "--depth=1", "--no-checkout",
                    "--no-recurse-submodules", "file://" + str(origin), str(destination),
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            dest = root / "worker-b"
            row = {"repository_id": "12345", "visibility": "public",
                   "repository": "Hawkar-usls/fixture", "branch": "main",
                   "sha": frozen_sha}
            with patch.object(acquire, "_clone_public", side_effect=local_clone):
                acquire._clone_from_frozen(row, dest, "fake-not-used")
            self.assertEqual(git(dest, "rev-parse", "HEAD"), frozen_sha)
            self.assertNotEqual(frozen_sha, latest_sha)
            self.assertEqual(git(dest, "show", "HEAD:f.txt"), "VERSION-A")
            with self.assertRaises(subprocess.CalledProcessError):
                git(dest, "remote", "get-url", "origin")
            self.assertFalse((dest / "f.txt").exists())


if __name__ == "__main__":
    unittest.main()
