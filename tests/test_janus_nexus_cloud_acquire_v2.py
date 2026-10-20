"""Fail-closed, network-free security contracts for REAL44 cloud acquire v2."""
from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "janus_nexus_cloud_acquire_v2.py"
spec = importlib.util.spec_from_file_location("janus_real44_acquire_v2_test", MODULE)
assert spec and spec.loader
acquire = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = acquire
spec.loader.exec_module(acquire)


class TestCloudAcquirerV2Security(unittest.TestCase):
    def test_git_private_auth_not_present_in_argv_or_persistent_remote(self):
        token = "synthetic_test_secret_not_real"
        intercepted = []

        def run(argv, **kwargs):
            intercepted.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        with patch.object(acquire.subprocess, "run", side_effect=run):
            acquire._clone_private("123", "org/opaque", token, Path("/tmp/opaque"))
        self.assertEqual(len(intercepted), 1)
        argv, options = intercepted[0]
        self.assertNotIn(token, " ".join(argv))
        self.assertNotIn("extraHeader", " ".join(argv))
        self.assertNotIn(token, repr(argv))
        self.assertEqual(options["env"]["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(options["env"]["GIT_CONFIG_KEY_0"], "http.extraHeader")
        self.assertIn("AUTHORIZATION: Basic", options["env"]["GIT_CONFIG_VALUE_0"])
        self.assertNotIn(token, options["env"]["GIT_CONFIG_VALUE_0"])
        self.assertEqual(options["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(options["stdout"], subprocess.DEVNULL)
        self.assertEqual(options["stderr"], subprocess.DEVNULL)

    def test_reject_newline_or_untrusted_clone_path(self):
        with patch.object(acquire.subprocess, "run") as run:
            for token in ("bad\ntoken", "bad\rtoken", ""):
                with self.assertRaises(acquire.AcquisitionError):
                    acquire._clone_private("123", "org/opaque", token, Path("/tmp/nope"))
            with self.assertRaises(acquire.AcquisitionError):
                acquire._clone_private("123", "../../evil", "dummy", Path("/tmp/nope"))
        run.assert_not_called()

    def test_private_api_response_must_be_private_exact_id(self):
        class Response:
            def __init__(self, result):
                import json
                self.content = json.dumps(result).encode()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, maxbytes): return self.content

        class Opener:
            def __init__(self, body): self.body = body
            def open(self, req, timeout): return Response(self.body)

        for body in (
            {"id": 123, "private": False, "full_name": "org/opaque"},
            {"id": 124, "private": True, "full_name": "org/opaque"},
        ):
            with patch.object(acquire.urllib.request, "build_opener", return_value=Opener(body)):
                with self.assertRaisesRegex(acquire.AcquisitionError, "PRIVATE_REPOSITORY_LOOKUP_MISMATCH"):
                    acquire._api_repo_by_id("123", "synthetic_test_secret_not_real")
        with patch.object(acquire.urllib.request, "build_opener", return_value=Opener(
                {"id": 123, "private": True, "full_name": "org/opaque"})):
            result = acquire._api_repo_by_id("123", "synthetic_test_secret_not_real")
        self.assertEqual(result["id"], 123)

    def test_errors_do_not_include_private_identifier(self):
        with patch.object(acquire.subprocess, "run", side_effect=subprocess.CalledProcessError(
                1, ["git", "clone", "private-external-path"])):
            with self.assertRaises(acquire.AcquisitionError) as error:
                acquire._clone_private("123", "org/opaque", "dummy", Path("/tmp/nope"))
        self.assertEqual(str(error.exception), "PRIVATE_CLONE_FAILED")
        self.assertNotIn("org/opaque", str(error.exception))

    def test_workflow_requires_trusted_dispatch_for_private_workers(self):
        workflow = (ROOT / ".github/workflows/janus-real44-cloud-materialization-v2.yml").read_text()
        head, jobs = workflow.split("\\njobs:\\n", 1)
        self.assertNotIn("secrets.JANUS_NEXUS_PRIVATE_READ_TOKEN", head)
        self.assertIn("  offline-contract:", jobs)
        a = jobs.split("  worker-a:\\n", 1)[1].split("  worker-b:\\n", 1)[0]
        b = jobs.split("  worker-b:\\n", 1)[1].split("  verdict:\\n", 1)[0]
        for worker in (a, b):
            self.assertIn("github.event_name == 'workflow_dispatch'", worker)
            self.assertIn("github.ref == 'refs/heads/main'", worker)
            self.assertIn("github.repository == 'Hawkar-usls/Janus_Genesis'", worker)
        self.assertIn("if: always()", jobs.split("  verdict:\\n", 1)[1])
        self.assertNotIn("secrets.JANUS_NEXUS_PRIVATE_READ_TOKEN", jobs.split("  offline-contract:\\n", 1)[1].split("  worker-a:\\n", 1)[0])
        self.assertIn("persist-credentials: false", a)
        self.assertIn("persist-credentials: false", b)

    def test_no_credential_fails_closed_before_network(self):
        with patch.dict(os.environ, {"JANUS_NEXUS_PRIVATE_READ_TOKEN": ""}):
            with patch.object(sys, "argv", ["acquire", "fresh", "--manifest", "/tmp/test",
                                            "--sources-root", "/tmp/test-sources", "--audit", "/tmp/audit"]):
                with patch.object(acquire, "acquire_fresh", side_effect=AssertionError("network")):
                    with patch("builtins.print"):
                        self.assertEqual(acquire.main(), 42)


if __name__ == "__main__":
    unittest.main()
