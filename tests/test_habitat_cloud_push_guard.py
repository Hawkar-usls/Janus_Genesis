"""Offline fault-injection tests for the Cloud HOME atomic checkpoint writer."""
from __future__ import annotations

import subprocess
import unittest

from tools import habitat_cloud_push_guard as guard

PARENT = "a" * 40
LOCAL = "b" * 40
OTHER = "c" * 40


class FakeGit:
    def __init__(self, pushes=None, remote=PARENT):
        self.remote = remote
        self.pushes = list(pushes or [("ok", LOCAL)])
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(tuple(argv))
        if argv == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, LOCAL + "\n", "")
        if argv == ["git", "rev-parse", "HEAD^"]:
            return subprocess.CompletedProcess(argv, 0, PARENT + "\n", "")
        if argv[:2] == ["git", "ls-remote"]:
            return subprocess.CompletedProcess(argv, 0, self.remote + "\t" + guard.TARGET + "\n", "")
        if argv[:2] == ["git", "push"]:
            action, new_head = self.pushes.pop(0)
            if new_head is not None:
                self.remote = new_head
            return subprocess.CompletedProcess(argv, 0 if action == "ok" else 1, "",
                                                "" if action == "ok" else "Internal Server Error")
        raise AssertionError("UNEXPECTED_GIT_COMMAND: " + repr(argv))

    def push_count(self):
        return sum(x[:2] == ("git", "push") for x in self.calls)


class CloudHomePushGuardTests(unittest.TestCase):
    def test_normal_push_requires_remote_confirmation(self):
        fake = FakeGit()
        self.assertEqual(guard.publish(run=fake, sleep=lambda _: None), LOCAL)
        self.assertEqual(fake.push_count(), 1)

    def test_github_500_retries_unchanged_commit_without_rebase(self):
        fake = FakeGit(pushes=[("failed", None), ("ok", LOCAL)])
        self.assertEqual(guard.publish(run=fake, sleep=lambda _: None), LOCAL)
        self.assertEqual(fake.push_count(), 2)
        self.assertFalse(any("force" in " ".join(call) or "rebase" in call for call in fake.calls))
        self.assertEqual([c for c in fake.calls if c[:2] == ("git", "push")],
                         [("git", "push", "origin", "HEAD:" + guard.TARGET)] * 2)

    def test_lost_ack_does_not_duplicate_checkpoint(self):
        fake = FakeGit(pushes=[("failed", LOCAL)])
        self.assertEqual(guard.publish(run=fake, sleep=lambda _: None), LOCAL)
        self.assertEqual(fake.push_count(), 1)

    def test_remote_branch_race_holds_without_overwrite(self):
        fake = FakeGit(remote=OTHER)
        with self.assertRaisesRegex(guard.PublicationHold, "REMOTE_HEAD_DRIFT"):
            guard.publish(run=fake, sleep=lambda _: None)
        self.assertEqual(fake.push_count(), 0)

    def test_remote_advanced_during_failed_push_holds(self):
        fake = FakeGit(pushes=[("failed", OTHER)])
        with self.assertRaisesRegex(guard.PublicationHold, "REMOTE_HEAD_DRIFT"):
            guard.publish(run=fake, sleep=lambda _: None)
        self.assertEqual(fake.push_count(), 1)

    def test_exhausted_retries_still_fail_closed(self):
        fake = FakeGit(pushes=[("failed", None)] * 4)
        with self.assertRaisesRegex(guard.PublicationHold, "RETRY_EXHAUSTED"):
            guard.publish(run=fake, sleep=lambda _: None)
        self.assertEqual(fake.push_count(), 4)

    def test_invalid_retry_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNBOUNDED_RETRY"):
            guard.publish(run=FakeGit(), sleep=lambda _: None, attempts=100)

    def test_no_remote_confirmation_no_success(self):
        class DeadRemote(FakeGit):
            def __call__(self, argv, **kwargs):
                if argv[:2] == ["git", "ls-remote"]:
                    return subprocess.CompletedProcess(argv, 128, "", "network down")
                return super().__call__(argv, **kwargs)
        with self.assertRaisesRegex(guard.PublicationHold, "REMOTE_HEAD_UNKNOWN"):
            guard.publish(run=DeadRemote(), sleep=lambda _: None)


if __name__ == "__main__":
    unittest.main()
