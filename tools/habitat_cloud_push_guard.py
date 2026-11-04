#!/usr/bin/env python3
"""Bounded, fail-closed publication of a prepared Cloud HOME checkpoint.

A temporary GitHub push failure must not strand a valid worker-A receipt.
Never rebase, force-push, duplicate the receipt, or accept an unrelated head.
A failed push can have succeeded remotely; reread the exact target ref first.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time

REMOTE = "origin"
TARGET = "refs/heads/janus/habitat-cloud-state"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_ATTEMPTS = 4


class PublicationHold(RuntimeError):
    """A conflict or unavailable remote prevents an attested handoff."""


def _command(argv, run):
    return run(argv, capture_output=True, text=True, check=False, timeout=30)


def _sha(argv, run):
    response = _command(argv, run)
    value = response.stdout.strip()
    if response.returncode != 0 or not HEX40.fullmatch(value):
        raise PublicationHold("CLOUD_HOME_INVALID_LOCAL_COMMIT")
    return value


def _remote_head(run):
    response = _command(["git", "ls-remote", "--exit-code", REMOTE, TARGET], run)
    # Do not interpret a missing branch, invalid response, or network error as an
    # empty state that can be overwritten.
    if response.returncode != 0:
        raise PublicationHold("CLOUD_HOME_REMOTE_HEAD_UNKNOWN")
    lines = response.stdout.strip().splitlines()
    if len(lines) != 1:
        raise PublicationHold("CLOUD_HOME_REMOTE_HEAD_AMBIGUOUS")
    columns = lines[0].split()
    if len(columns) != 2 or columns[1] != TARGET or not HEX40.fullmatch(columns[0]):
        raise PublicationHold("CLOUD_HOME_REMOTE_HEAD_MALFORMED")
    return columns[0]


def publish(run=subprocess.run, sleep=time.sleep, attempts=MAX_ATTEMPTS):
    """Publish the same immutable commit only while remote HEAD == its parent.

    Returns the exact local commit SHA only when the remote advertises it.
    On a transient push error retry the *same* commit (not a new sequence).
    If another writer advances the target, HOLD without rebase or force-push.
    """
    if not isinstance(attempts, int) or not 1 <= attempts <= MAX_ATTEMPTS:
        raise ValueError("CLOUD_HOME_UNBOUNDED_RETRY")
    local = _sha(["git", "rev-parse", "HEAD"], run)
    parent = _sha(["git", "rev-parse", "HEAD^"], run)
    if local == parent:
        raise PublicationHold("CLOUD_HOME_IDENTICAL_PARENT")
    for attempt in range(attempts):
        remote = _remote_head(run)
        if remote == local:
            return local  # Prior push succeeded despite lost acknowledgment.
        if remote != parent:
            raise PublicationHold("CLOUD_HOME_REMOTE_HEAD_DRIFT")
        result = _command(["git", "push", REMOTE, f"HEAD:{TARGET}"], run)
        # A zero exit alone is insufficient: verify what the remote advertises.
        # A nonzero exit can also mean that GitHub accepted but dropped its ACK.
        try:
            visible = _remote_head(run)
        except PublicationHold as exc:
            if attempt == attempts - 1:
                raise PublicationHold("CLOUD_HOME_PUSH_UNVERIFIED") from exc
            sleep(min(2 ** attempt, 4))
            continue
        if visible == local:
            return local
        if visible != parent:
            raise PublicationHold("CLOUD_HOME_REMOTE_HEAD_DRIFT")
        if attempt < attempts - 1:
            sleep(min(2 ** attempt, 4))
    raise PublicationHold("CLOUD_HOME_PUSH_RETRY_EXHAUSTED")


def main():
    try:
        sha = publish()
    except PublicationHold as exc:
        print("::error::" + str(exc), file=sys.stderr)
        return 1
    print("CLOUD_HOME_ATTESTED_STATE_COMMIT=" + sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
