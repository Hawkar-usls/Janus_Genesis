#!/usr/bin/env python3
"""Cloud-only acquisition bridge for JANUS NEXUS materializer v1.

This tool ACQUIRES read-only Git checkouts. It does not materialize Nexus bodies,
execute source code, mutate source repositories, or persist credentials.
Private repository names are resolved only in memory from opaque repository IDs
and are never written to the generated manifest.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[0-9]{1,32}$")
PUBLIC_REPO = re.compile(r"^Hawkar-usls/[A-Za-z0-9._-]{1,200}$")


class AcquisitionError(RuntimeError):
    pass


def _run(args: list[str], *, quiet: bool = True) -> bytes:
    try:
        return subprocess.check_output(
            args,
            stderr=subprocess.DEVNULL if quiet else subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AcquisitionError("GIT_ACQUISITION_FAILED") from exc


def _git(repo: Path, *args: str) -> str:
    return _run(["git", "-C", str(repo), *args]).decode("utf-8", errors="strict").strip()


def _api_repo_by_id(repo_id: str, token: str) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(repo_id):
        raise AcquisitionError("PRIVATE_REPOSITORY_ID_INVALID")
    req = urllib.request.Request(
        f"https://api.github.com/repositories/{repo_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "janus-nexus-cloud-acquire-v1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            value = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AcquisitionError(f"PRIVATE_REPOSITORY_LOOKUP_FAILED:{repo_id}") from exc
    if not isinstance(value, dict) or str(value.get("id")) != repo_id:
        raise AcquisitionError(f"PRIVATE_REPOSITORY_LOOKUP_MISMATCH:{repo_id}")
    full_name = value.get("full_name")
    if not isinstance(full_name, str) or "/" not in full_name:
        raise AcquisitionError(f"PRIVATE_REPOSITORY_NAME_UNAVAILABLE:{repo_id}")
    return value


def _clone_public(repository: str, destination: Path) -> None:
    if not PUBLIC_REPO.fullmatch(repository):
        raise AcquisitionError("PUBLIC_REPOSITORY_INVALID")
    try:
        subprocess.run(
            [
                "git", "clone", "--depth=1", "--no-tags", "--no-recurse-submodules",
                "--no-checkout", f"https://github.com/{repository}.git", str(destination),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AcquisitionError(f"PUBLIC_CLONE_FAILED:{repository}") from exc


def _clone_private(repo_id: str, full_name: str, token: str, destination: Path) -> None:
    auth = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    # The private repository name and credential stay only in this subprocess argv;
    # stdout/stderr are suppressed so neither can reach Actions logs.
    try:
        subprocess.run(
            [
                "git",
                "-c", f"http.extraHeader=AUTHORIZATION: Basic {auth}",
                "clone", "--depth=1", "--no-tags", "--no-recurse-submodules",
                "--no-checkout", f"https://github.com/{full_name}.git", str(destination),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AcquisitionError(f"PRIVATE_CLONE_FAILED:{repo_id}") from exc


def _disconnect(repo: Path) -> None:
    # Materializer must have no network path. The shallow object database already
    # contains the full pinned tree because no partial/blob filter was used.
    try:
        subprocess.run(
            ["git", "-C", str(repo), "remote", "remove", "origin"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AcquisitionError("REMOTE_DISCONNECT_FAILED") from exc


def _observed_row(repo: Path, source: dict[str, Any]) -> dict[str, Any]:
    sha = _git(repo, "rev-parse", "HEAD").lower()
    branch = _git(repo, "symbolic-ref", "--short", "HEAD")
    if not FULL_SHA.fullmatch(sha):
        raise AcquisitionError("OBSERVED_HEAD_INVALID")
    row: dict[str, Any] = {
        "repository_id": str(source["id"]),
        "visibility": source["visibility"],
        "branch": branch,
        "sha": sha,
    }
    if source["visibility"] == "public":
        row["repository"] = source["repository"]
    return row


def _clone_from_frozen(row: dict[str, Any], destination: Path, token: str) -> None:
    repo_id = str(row["repository_id"])
    visibility = row["visibility"]
    if visibility == "public":
        repository = str(row["repository"])
        _clone_public(repository, destination)
    elif visibility == "private":
        meta = _api_repo_by_id(repo_id, token)
        _clone_private(repo_id, str(meta["full_name"]), token, destination)
    else:
        raise AcquisitionError("VISIBILITY_INVALID")
    observed = _git(destination, "rev-parse", "HEAD").lower()
    if observed != row["sha"]:
        raise AcquisitionError(f"SOURCE_HEAD_DRIFT:{repo_id}")
    _disconnect(destination)


def _sources_from_audit(audit: dict[str, Any]) -> list[dict[str, Any]]:
    public = audit.get("public")
    private = audit.get("private")
    if not isinstance(public, list) or not isinstance(private, list):
        raise AcquisitionError("ROLE_AUDIT_SOURCE_LIST_INVALID")
    if len(public) != 41 or len(private) != 3:
        raise AcquisitionError("ROLE_AUDIT_NOT_44")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in public:
        repo_id = str(item.get("id") or "")
        repository = str(item.get("repository") or "")
        if not SAFE_ID.fullmatch(repo_id) or not PUBLIC_REPO.fullmatch(repository) or repo_id in seen:
            raise AcquisitionError("PUBLIC_AUDIT_ROW_INVALID")
        seen.add(repo_id)
        rows.append({"id": repo_id, "visibility": "public", "repository": repository})
    for item in private:
        repo_id = str(item.get("id") or "")
        if not SAFE_ID.fullmatch(repo_id) or repo_id in seen:
            raise AcquisitionError("PRIVATE_AUDIT_ROW_INVALID")
        seen.add(repo_id)
        rows.append({"id": repo_id, "visibility": "private"})
    if len(rows) != 44 or len(seen) != 44:
        raise AcquisitionError("SOURCE_SET_NOT_44")
    return rows


def acquire_fresh(audit_path: Path, sources_root: Path, manifest_path: Path, token: str) -> None:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    sources = _sources_from_audit(audit)
    sources_root.mkdir(parents=True, exist_ok=False)
    manifest_rows: list[dict[str, Any]] = []
    for source in sources:
        repo_id = str(source["id"])
        destination = sources_root / repo_id
        if source["visibility"] == "public":
            _clone_public(str(source["repository"]), destination)
        else:
            meta = _api_repo_by_id(repo_id, token)
            _clone_private(repo_id, str(meta["full_name"]), token, destination)
        row = _observed_row(destination, source)
        _disconnect(destination)
        manifest_rows.append(row)
    manifest = {
        "schema": "janus.nexus.manifest.v1",
        "artifact_id": "JANUS-REAL44-CLOUD-FROZEN-MANIFEST",
        "write_back_default": "DENY",
        "source_code_execution": False,
        "sources": manifest_rows,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(manifest_path, 0o600)


def acquire_frozen(manifest_path: Path, sources_root: Path, token: str) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest.get("sources")
    if not isinstance(rows, list) or len(rows) != 44:
        raise AcquisitionError("FROZEN_MANIFEST_NOT_44")
    sources_root.mkdir(parents=True, exist_ok=False)
    for row in rows:
        if not isinstance(row, dict):
            raise AcquisitionError("FROZEN_ROW_INVALID")
        repo_id = str(row.get("repository_id") or "")
        sha = str(row.get("sha") or "")
        if not SAFE_ID.fullmatch(repo_id) or not FULL_SHA.fullmatch(sha):
            raise AcquisitionError("FROZEN_PIN_INVALID")
        _clone_from_frozen(row, sources_root / repo_id, token)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["fresh", "frozen"])
    p.add_argument("--audit")
    p.add_argument("--manifest", required=True)
    p.add_argument("--sources-root", required=True)
    p.add_argument("--token-env", default="JANUS_NEXUS_PRIVATE_READ_TOKEN")
    return p


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get(args.token_env, "")
    if not token:
        print("HOLD_CLOUD_PRIVATE_READ_CREDENTIAL", file=sys.stderr)
        return 42
    try:
        if args.command == "fresh":
            if not args.audit:
                raise AcquisitionError("AUDIT_REQUIRED")
            acquire_fresh(Path(args.audit), Path(args.sources_root), Path(args.manifest), token)
        else:
            acquire_frozen(Path(args.manifest), Path(args.sources_root), token)
    except AcquisitionError as exc:
        print(f"ACQUISITION_HOLD:{exc}", file=sys.stderr)
        return 43
    print("CLOUD_SOURCE_ACQUISITION=PASS")
    print("PC_USED=FALSE")
    print("SOURCE_WRITEBACK=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
