#!/usr/bin/env python3
"""V2-only compare-and-swap Git publisher for a validated sequential receipt.

Writes to a disposable or explicitly provisioned HOME checkout; no automatic
GitHub Action calls it. No inference and no credential handling is performed.
"""
from __future__ import annotations

import json
from pathlib import Path

from genesis_beetle_model_consumption import ConsumptionError
from janus_corpus_callosum_v2 import attest_roundtrip
from janus_corpus_git_publisher import (
    PublicationError, _git, _paths, _remote_head, STATE_REF, STATE_SUBDIR,
)

ALLOWED_PREFIX = STATE_SUBDIR + "/corpus_callosum_v2/"


def publish_v2(repo: Path, *, baseline: dict,
               expected_native_head: str | None = None,
               interrupt_at: str | None = None) -> dict:
    if repo.is_symlink() or not (repo / ".git").is_dir():
        raise PublicationError("sequential publisher requires normal Git checkout")
    home = repo / STATE_SUBDIR
    witness = attest_roundtrip(home, baseline=baseline,
                               expected_native_head=expected_native_head)
    base = _git(repo, "rev-parse", "HEAD")
    if base != _remote_head(repo):
        raise PublicationError("sequential HOME remote moved before commit")
    expected = STATE_SUBDIR + "/" + witness["receipt_path"]
    tracked = _paths(repo, "diff", "--name-only") + _paths(repo, "diff", "--cached", "--name-only")
    untracked = _paths(repo, "ls-files", "--others", "--exclude-standard")
    changed = set(tracked + untracked)
    if changed - {expected}:
        raise PublicationError("unexpected modified or untracked path in sequential checkout")
    if not expected.startswith(ALLOWED_PREFIX) or not (repo / expected).is_file():
        raise PublicationError("sequential receipt path not allowed")
    _git(repo, "add", "--", expected)
    staged = _paths(repo, "diff", "--cached", "--name-only")
    if staged not in ([], [expected]):
        raise PublicationError("unexpected staged sequential file")
    if not staged:
        if base != _remote_head(repo):
            raise PublicationError("sequential remote advanced during replay")
        return {"status": "SEQUENTIAL_ALREADY_DURABLE", "commit": base,
                "scientific_authority_delta": 0, "ack_advanced": False}
    attest_roundtrip(home, baseline=baseline, expected_native_head=expected_native_head)
    _git(repo, "-c", "user.name=janus-sequential[bot]",
         "-c", "user.email=janus-sequential[bot]@users.noreply.github.com",
         "commit", "-m", "JANUS sequential v2 unverified receipt")
    commit = _git(repo, "rev-parse", "HEAD")
    if interrupt_at == "after_commit":
        raise PublicationError("simulated death before sequential push")
    _git(repo, "push", "origin", f"HEAD:{STATE_REF}")
    if interrupt_at == "after_push":
        raise PublicationError("simulated death after sequential push")
    if _remote_head(repo) != commit:
        raise PublicationError("sequential push not confirmed")
    return {"status": "SEQUENTIAL_DURABLE__NOT_MODEL_TRUTH", "commit": commit,
            "receipt_sha256": witness["receipt_sha256"],
            "scientific_authority_delta": 0, "ack_advanced": False}
