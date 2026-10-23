# -*- coding: utf-8 -*-
"""JANUS NEXUS materializer v1.

Build a disposable, reproducible multi-repository work body from *already local*
Git repositories pinned to exact commit SHAs. Source bytes are read from the
pinned Git commit object, never from mutable working-tree files.

The materializer never clones, fetches, executes source code, writes to source
repositories, or infers authority from repository content. Acquisition is
intentionally outside this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "janus.nexus.manifest.v1"
RECEIPT_SCHEMA = "janus.nexus.materialization_receipt.v1"
SOURCE_RECEIPT_SCHEMA = "janus.nexus.source_receipt.v1"
SAFE_ID = re.compile(r"^[0-9]{1,32}$")
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/+-]{1,240}$")
SAFE_PUBLIC_REPO = re.compile(r"^Hawkar-usls/[A-Za-z0-9._-]{1,200}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
REGULAR_BLOB_MODES = {"100644", "100755"}
MANIFEST_TOP_LEVEL_FIELDS = frozenset(
    {"schema", "artifact_id", "write_back_default", "source_code_execution", "sources"}
)
PUBLIC_SOURCE_FIELDS = frozenset(
    {"repository_id", "visibility", "repository", "branch", "sha"}
)
PRIVATE_SOURCE_FIELDS = frozenset(
    {"repository_id", "visibility", "branch", "sha"}
)
PRIVATE_IDENTITY_FIELDS = frozenset(
    {"repository", "name", "full_name", "clone_url", "html_url"}
)


class NexusMaterializerError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical(value))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NexusMaterializerError(f"JSON_UNREADABLE:{path}") from exc
    if not isinstance(value, dict):
        raise NexusMaterializerError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or (path.exists() and path.is_symlink()):
        raise NexusMaterializerError("NEXUS_OUTPUT_SYMLINK_REJECTED")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise NexusMaterializerError("NEXUS_MANIFEST_SCHEMA_INVALID")
    if set(value) - MANIFEST_TOP_LEVEL_FIELDS:
        raise NexusMaterializerError("NEXUS_MANIFEST_TOP_LEVEL_FIELD_INVALID")
    artifact_id = value.get("artifact_id")
    if artifact_id is not None and (
        not isinstance(artifact_id, str) or not 1 <= len(artifact_id) <= 200
    ):
        raise NexusMaterializerError("NEXUS_MANIFEST_ARTIFACT_ID_INVALID")
    if value.get("write_back_default") != "DENY":
        raise NexusMaterializerError("NEXUS_WRITE_BACK_MUST_DEFAULT_DENY")
    if value.get("source_code_execution") is not False:
        raise NexusMaterializerError("NEXUS_SOURCE_EXECUTION_MUST_BE_FALSE")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise NexusMaterializerError("NEXUS_MANIFEST_SOURCES_REQUIRED")

    seen_ids: set[str] = set()
    for row in sources:
        if not isinstance(row, dict):
            raise NexusMaterializerError("NEXUS_SOURCE_ROW_INVALID")
        repo_id = str(row.get("repository_id") or "")
        visibility = row.get("visibility")
        branch = str(row.get("branch") or "")
        sha = str(row.get("sha") or "")
        if not SAFE_ID.fullmatch(repo_id) or repo_id in seen_ids:
            raise NexusMaterializerError("NEXUS_SOURCE_REPOSITORY_ID_INVALID")
        if visibility not in {"public", "private"}:
            raise NexusMaterializerError("NEXUS_SOURCE_VISIBILITY_INVALID")
        if visibility == "private" and PRIVATE_IDENTITY_FIELDS.intersection(row):
            raise NexusMaterializerError("NEXUS_PRIVATE_REPOSITORY_METADATA_LEAK")
        allowed_fields = PUBLIC_SOURCE_FIELDS if visibility == "public" else PRIVATE_SOURCE_FIELDS
        if set(row) - allowed_fields:
            raise NexusMaterializerError(f"NEXUS_SOURCE_FIELD_INVALID:{repo_id}")
        if not SAFE_BRANCH.fullmatch(branch) or ".." in branch:
            raise NexusMaterializerError("NEXUS_SOURCE_BRANCH_INVALID")
        if not FULL_SHA.fullmatch(sha):
            raise NexusMaterializerError("NEXUS_SOURCE_SHA_INVALID")
        if visibility == "public":
            if not SAFE_PUBLIC_REPO.fullmatch(str(row.get("repository") or "")):
                raise NexusMaterializerError("NEXUS_PUBLIC_REPOSITORY_INVALID")
        seen_ids.add(repo_id)
    return value


def load_manifest(path: str | Path) -> dict[str, Any]:
    return validate_manifest(_read_json(Path(path)))


def _git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args],
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise NexusMaterializerError(
            f"NEXUS_GIT_QUERY_FAILED:{repo}:{' '.join(args)}"
        ) from exc


def _checked_relative_path(raw: str) -> Path:
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise NexusMaterializerError("NEXUS_TRACKED_PATH_INVALID")
    if any(part in {"", ".", ".git"} for part in candidate.parts):
        raise NexusMaterializerError("NEXUS_TRACKED_PATH_INVALID")
    return candidate


def _pinned_tree_blobs(repo: Path, commit_sha: str) -> list[tuple[Path, str, str]]:
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit_sha)
    rows: list[tuple[Path, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, path_raw = record.split(b"\t", 1)
            mode, object_type, object_sha = header.decode("ascii").split(" ", 2)
            rel = _checked_relative_path(path_raw.decode("utf-8", errors="strict"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise NexusMaterializerError("NEXUS_GIT_TREE_RECORD_INVALID") from exc
        if len(rel.parts) == 1 and rel.name.casefold() == "source.json":
            raise NexusMaterializerError(
                f"NEXUS_SOURCE_RESERVED_PATH_REJECTED:{rel.as_posix()}"
            )
        if object_type != "blob" or mode not in REGULAR_BLOB_MODES:
            raise NexusMaterializerError(
                f"NEXUS_SOURCE_ENTRY_TYPE_REJECTED:{rel.as_posix()}:{mode}:{object_type}"
            )
        if not FULL_SHA.fullmatch(object_sha):
            raise NexusMaterializerError("NEXUS_GIT_BLOB_SHA_INVALID")
        rows.append((rel, object_sha, mode))
    return sorted(rows, key=lambda item: item[0].as_posix())


def _file_record(raw: bytes, rel: Path, git_blob_sha: str, git_mode: str) -> dict[str, Any]:
    return {
        "path": rel.as_posix(),
        "bytes": len(raw),
        "sha256": _sha256_bytes(raw),
        "git_blob_sha": git_blob_sha,
        "git_mode": git_mode,
    }


def _safe_destination(root: Path, rel: Path) -> Path:
    root_resolved = root.resolve()
    candidate = root / rel
    candidate.parent.mkdir(parents=True, exist_ok=True)
    if candidate.parent.is_symlink() or candidate.is_symlink():
        raise NexusMaterializerError("NEXUS_OUTPUT_SYMLINK_REJECTED")
    parent_resolved = candidate.parent.resolve()
    try:
        parent_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise NexusMaterializerError("NEXUS_OUTPUT_ESCAPE_REJECTED") from exc
    return candidate


def _expected_body_surface(file_rows: list[dict[str, Any]]) -> set[str]:
    expected = {"SOURCE.json"}
    for item in file_rows:
        rel = _checked_relative_path(str(item.get("path") or ""))
        expected.add(rel.as_posix())
        parent = rel.parent
        while parent != Path("."):
            expected.add(parent.as_posix())
            parent = parent.parent
    return expected


def _actual_surface(root: Path) -> tuple[set[str], bool]:
    entries: set[str] = set()
    has_symlink = False
    try:
        for path in root.rglob("*"):
            entries.add(path.relative_to(root).as_posix())
            if path.is_symlink():
                has_symlink = True
    except OSError:
        return entries, True
    return entries, has_symlink


class NexusMaterializer:
    def __init__(self, manifest: dict[str, Any], sources_root: str | Path, output_root: str | Path) -> None:
        self.manifest = validate_manifest(manifest)
        self.sources_root = Path(sources_root)
        self.output_root = Path(output_root)
        self.receipt_path = self.output_root / "NEXUS_ID.json"

    @property
    def manifest_sha256(self) -> str:
        return _sha256_json(self.manifest)

    def _source_checkout(self, row: dict[str, Any]) -> Path:
        return self.sources_root / str(row["repository_id"])

    def _verify_checkout_pin(self, row: dict[str, Any], checkout: Path) -> None:
        if not checkout.is_dir() or checkout.is_symlink():
            raise NexusMaterializerError(
                f"NEXUS_SOURCE_CHECKOUT_INVALID:{row['repository_id']}"
            )
        head = _git(checkout, "rev-parse", "HEAD").decode("ascii").strip().lower()
        if head != row["sha"]:
            raise NexusMaterializerError(
                f"NEXUS_SOURCE_SHA_MISMATCH:{row['repository_id']}:{head}"
            )
        object_type = _git(checkout, "cat-file", "-t", row["sha"]).decode("ascii").strip()
        if object_type != "commit":
            raise NexusMaterializerError(
                f"NEXUS_SOURCE_PIN_NOT_COMMIT:{row['repository_id']}"
            )

    def _body_dir(self, row: dict[str, Any]) -> Path:
        prefix = "public" if row["visibility"] == "public" else "private"
        return self.output_root / "faces" / f"{prefix}-{row['repository_id']}"

    def _source_receipt(self, row: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema": SOURCE_RECEIPT_SCHEMA,
            "repository_id": str(row["repository_id"]),
            "visibility": row["visibility"],
            "branch": row["branch"],
            "sha": row["sha"],
            "tracked_file_count": len(files),
            "tree_sha256": _sha256_json(files),
            "files": files,
            "source_bytes_read_from_pinned_git_objects": True,
            "mutable_worktree_bytes_used": False,
            "source_history_remains_authoritative": True,
            "source_code_executed": False,
            "write_back_performed": False,
        }
        if row["visibility"] == "public":
            receipt["repository"] = row["repository"]
        return receipt

    def _expected_source_receipt(self, manifest_row: dict[str, Any]) -> dict[str, Any]:
        checkout = self._source_checkout(manifest_row)
        self._verify_checkout_pin(manifest_row, checkout)
        files: list[dict[str, Any]] = []
        for rel, blob_sha, git_mode in _pinned_tree_blobs(checkout, manifest_row["sha"]):
            raw = _git(checkout, "cat-file", "blob", blob_sha)
            files.append(_file_record(raw, rel, blob_sha, git_mode))
        return self._source_receipt(manifest_row, files)

    def _existing_receipt(self) -> dict[str, Any] | None:
        if not self.receipt_path.exists():
            return None
        return _read_json(self.receipt_path)

    def _preflight_sources(self) -> list[tuple[dict[str, Any], Path, list[tuple[Path, str, str]]]]:
        """Validate every source pin/tree before publishing any Nexus body bytes."""
        prepared: list[tuple[dict[str, Any], Path, list[tuple[Path, str, str]]]] = []
        for row in self.manifest["sources"]:
            checkout = self._source_checkout(row)
            self._verify_checkout_pin(row, checkout)
            tracked = _pinned_tree_blobs(checkout, row["sha"])
            prepared.append((row, checkout, tracked))
        return prepared

    def materialize(self) -> dict[str, Any]:
        if self.output_root.is_symlink():
            raise NexusMaterializerError("NEXUS_OUTPUT_ROOT_SYMLINK_REJECTED")
        existing = self._existing_receipt()
        if existing is not None:
            if existing.get("manifest_sha256") != self.manifest_sha256:
                raise NexusMaterializerError("NEXUS_ALREADY_BOUND_TO_DIFFERENT_MANIFEST")
            verified = self.verify()
            if not verified["ok"]:
                raise NexusMaterializerError("NEXUS_EXISTING_BODY_FAILED_VERIFY")
            return {
                "status": "ALREADY_MATERIALIZED",
                "manifest_sha256": self.manifest_sha256,
                "nexus_digest": existing.get("nexus_digest"),
                "source_count": existing.get("source_count"),
            }

        if self.output_root.exists() and any(self.output_root.iterdir()):
            raise NexusMaterializerError("NEXUS_OUTPUT_NOT_EMPTY")

        prepared_sources = self._preflight_sources()
        self.output_root.mkdir(parents=True, exist_ok=True)

        source_receipts: list[dict[str, Any]] = []
        for row, checkout, tracked in prepared_sources:
            body_dir = self._body_dir(row)
            body_dir.mkdir(parents=True, exist_ok=False)
            files: list[dict[str, Any]] = []
            for rel, blob_sha, git_mode in tracked:
                raw = _git(checkout, "cat-file", "blob", blob_sha)
                destination = _safe_destination(body_dir, rel)
                destination.write_bytes(raw)
                files.append(_file_record(raw, rel, blob_sha, git_mode))
            source_receipt = self._source_receipt(row, files)
            _write_json(body_dir / "SOURCE.json", source_receipt)
            source_receipts.append(source_receipt)

        identity_basis = {
            "schema": RECEIPT_SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "sources": [
                {
                    "repository_id": r["repository_id"],
                    "sha": r["sha"],
                    "tree_sha256": r["tree_sha256"],
                }
                for r in source_receipts
            ],
        }
        nexus_digest = _sha256_json(identity_basis)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "nexus_digest": nexus_digest,
            "source_count": len(source_receipts),
            "sources": source_receipts,
            "source_history_merged": False,
            "source_history_remains_authoritative": True,
            "source_bytes_read_from_pinned_git_objects": True,
            "mutable_worktree_bytes_used": False,
            "source_code_executed": False,
            "network_access_performed": False,
            "source_write_back_performed": False,
            "write_back_default": "DENY",
            "destructive_action_performed": False,
        }
        _write_json(self.receipt_path, receipt)
        return {
            "status": "MATERIALIZED",
            "manifest_sha256": self.manifest_sha256,
            "nexus_digest": nexus_digest,
            "source_count": len(source_receipts),
            "source_write_back_performed": False,
            "source_code_executed": False,
            "mutable_worktree_bytes_used": False,
        }

    def verify(self) -> dict[str, Any]:
        if not self.receipt_path.is_file() or self.receipt_path.is_symlink():
            return {"ok": False, "errors": ["NEXUS_RECEIPT_MISSING"]}
        try:
            receipt = _read_json(self.receipt_path)
        except NexusMaterializerError:
            return {"ok": False, "errors": ["NEXUS_RECEIPT_UNREADABLE"]}
        errors: list[str] = []

        if receipt.get("schema") != RECEIPT_SCHEMA:
            errors.append("NEXUS_RECEIPT_SCHEMA_INVALID")
        if receipt.get("manifest_sha256") != self.manifest_sha256:
            errors.append("NEXUS_MANIFEST_DIGEST_MISMATCH")
        if receipt.get("write_back_default") != "DENY":
            errors.append("NEXUS_WRITE_BACK_DEFAULT_CHANGED")
        if receipt.get("source_write_back_performed") is not False:
            errors.append("NEXUS_SOURCE_WRITE_BACK_CLAIM_INVALID")
        if receipt.get("source_code_executed") is not False:
            errors.append("NEXUS_SOURCE_EXECUTION_CLAIM_INVALID")
        if receipt.get("mutable_worktree_bytes_used") is not False:
            errors.append("NEXUS_MUTABLE_WORKTREE_CLAIM_INVALID")
        if receipt.get("source_history_merged") is not False:
            errors.append("NEXUS_SOURCE_HISTORY_MERGE_CLAIM_INVALID")
        if receipt.get("source_history_remains_authoritative") is not True:
            errors.append("NEXUS_SOURCE_HISTORY_AUTHORITY_CLAIM_INVALID")
        if receipt.get("source_bytes_read_from_pinned_git_objects") is not True:
            errors.append("NEXUS_PINNED_OBJECT_BYTES_CLAIM_INVALID")
        if receipt.get("network_access_performed") is not False:
            errors.append("NEXUS_NETWORK_ACCESS_CLAIM_INVALID")
        if receipt.get("destructive_action_performed") is not False:
            errors.append("NEXUS_DESTRUCTIVE_ACTION_CLAIM_INVALID")

        try:
            root_names = {p.name for p in self.output_root.iterdir()}
        except OSError:
            root_names = set()
        faces_root = self.output_root / "faces"
        if (
            root_names != {"NEXUS_ID.json", "faces"}
            or faces_root.is_symlink()
            or not faces_root.is_dir()
        ):
            errors.append("NEXUS_ROOT_SURFACE_MISMATCH")

        source_rows = receipt.get("sources")
        if not isinstance(source_rows, list):
            source_rows = []
            errors.append("NEXUS_SOURCE_RECEIPTS_INVALID")
        if receipt.get("source_count") != len(source_rows):
            errors.append("NEXUS_SOURCE_COUNT_MISMATCH")
        if receipt.get("source_count") != len(self.manifest["sources"]):
            errors.append("NEXUS_SOURCE_COUNT_MISMATCH")

        manifest_rows = {
            str(row["repository_id"]): row
            for row in self.manifest["sources"]
        }
        manifest_order = [str(row["repository_id"]) for row in self.manifest["sources"]]
        receipt_ids: list[str] = []
        expected_face_names: set[str] = set()
        basis_sources: list[dict[str, Any]] = []

        for row in source_rows:
            if not isinstance(row, dict):
                errors.append("NEXUS_SOURCE_RECEIPT_ROW_INVALID")
                continue
            repo_id = str(row.get("repository_id") or "")
            receipt_ids.append(repo_id)
            manifest_row = manifest_rows.get(repo_id)
            expected_receipt: dict[str, Any] | None = None
            if manifest_row is None:
                errors.append(f"NEXUS_SOURCE_BINDING_MISMATCH:{repo_id}")
            else:
                binding_keys = ("visibility", "branch", "sha")
                if any(row.get(key) != manifest_row.get(key) for key in binding_keys):
                    errors.append(f"NEXUS_SOURCE_BINDING_MISMATCH:{repo_id}")
                if manifest_row["visibility"] == "public":
                    if row.get("repository") != manifest_row.get("repository"):
                        errors.append(f"NEXUS_SOURCE_BINDING_MISMATCH:{repo_id}")
                elif "repository" in row:
                    errors.append(f"NEXUS_PRIVATE_METADATA_LEAK:{repo_id}")
                try:
                    expected_receipt = self._expected_source_receipt(manifest_row)
                except NexusMaterializerError as exc:
                    errors.append(f"NEXUS_SOURCE_REPLAY_FAILED:{repo_id}:{exc}")
                else:
                    if row != expected_receipt:
                        errors.append(f"NEXUS_SOURCE_RECEIPT_PIN_MISMATCH:{repo_id}")

            visibility = row.get("visibility")
            prefix = "public" if visibility == "public" else "private"
            face_name = f"{prefix}-{repo_id}"
            expected_face_names.add(face_name)
            body_dir = faces_root / face_name
            if body_dir.is_symlink() or not body_dir.is_dir():
                errors.append(f"NEXUS_BODY_DIR_INVALID:{repo_id}")
                continue

            if expected_receipt is not None:
                file_rows = expected_receipt["files"]
            else:
                file_rows = row.get("files")
            if not isinstance(file_rows, list):
                errors.append(f"NEXUS_FILE_RECEIPTS_INVALID:{repo_id}")
                continue

            try:
                expected_surface = _expected_body_surface(file_rows)
            except NexusMaterializerError:
                expected_surface = {"SOURCE.json"}
                errors.append(f"NEXUS_RECEIPT_PATH_INVALID:{repo_id}")
            actual_surface, has_symlink = _actual_surface(body_dir)
            if has_symlink or actual_surface != expected_surface:
                errors.append(f"NEXUS_BODY_SURFACE_MISMATCH:{repo_id}")

            recomputed: list[dict[str, Any]] = []
            for item in file_rows:
                try:
                    rel = _checked_relative_path(str(item.get("path") or ""))
                except NexusMaterializerError:
                    errors.append(f"NEXUS_RECEIPT_PATH_INVALID:{repo_id}")
                    continue
                path = body_dir / rel
                if path.is_symlink() or not path.is_file():
                    errors.append(f"NEXUS_BODY_FILE_MISSING:{repo_id}:{rel.as_posix()}")
                    continue
                try:
                    path.resolve().relative_to(body_dir.resolve())
                except (OSError, ValueError):
                    errors.append(f"NEXUS_BODY_FILE_ESCAPE:{repo_id}:{rel.as_posix()}")
                    continue
                raw = path.read_bytes()
                recomputed.append(
                    _file_record(
                        raw,
                        rel,
                        str(item.get("git_blob_sha") or ""),
                        str(item.get("git_mode") or ""),
                    )
                )
            if recomputed != file_rows:
                errors.append(f"NEXUS_BODY_FILE_DIGEST_MISMATCH:{repo_id}")
            tree_sha = _sha256_json(recomputed)
            expected_tree_sha = (
                expected_receipt.get("tree_sha256")
                if expected_receipt is not None
                else row.get("tree_sha256")
            )
            if tree_sha != expected_tree_sha:
                errors.append(f"NEXUS_TREE_DIGEST_MISMATCH:{repo_id}")

            source_json = body_dir / "SOURCE.json"
            if not source_json.is_file() or source_json.is_symlink():
                errors.append(f"NEXUS_SOURCE_RECEIPT_MISSING:{repo_id}")
            else:
                try:
                    persisted_source_receipt = _read_json(source_json)
                except NexusMaterializerError:
                    persisted_source_receipt = {}
                    errors.append(f"NEXUS_SOURCE_RECEIPT_UNREADABLE:{repo_id}")
                if persisted_source_receipt != row:
                    errors.append(f"NEXUS_SOURCE_RECEIPT_MISMATCH:{repo_id}")
                if expected_receipt is not None and persisted_source_receipt != expected_receipt:
                    errors.append(f"NEXUS_SOURCE_RECEIPT_PIN_MISMATCH:{repo_id}")
                if visibility == "private" and any(
                    key in persisted_source_receipt
                    for key in ("repository", "name", "full_name", "clone_url", "html_url")
                ):
                    errors.append(f"NEXUS_PRIVATE_METADATA_LEAK:{repo_id}")

            if manifest_row is not None and expected_receipt is not None:
                basis_sources.append(
                    {
                        "repository_id": repo_id,
                        "sha": manifest_row["sha"],
                        "tree_sha256": expected_receipt["tree_sha256"],
                    }
                )
            else:
                basis_sources.append(
                    {
                        "repository_id": repo_id,
                        "sha": row.get("sha"),
                        "tree_sha256": row.get("tree_sha256"),
                    }
                )

        if len(receipt_ids) != len(set(receipt_ids)):
            errors.append("NEXUS_SOURCE_RECEIPT_ID_DUPLICATE")
        if set(receipt_ids) != set(manifest_rows):
            errors.append("NEXUS_SOURCE_SET_MISMATCH")
        if len(source_rows) != len(self.manifest["sources"]):
            errors.append("NEXUS_SOURCE_SET_MISMATCH")
        if receipt_ids != manifest_order:
            errors.append("NEXUS_SOURCE_ORDER_MISMATCH")

        if faces_root.is_dir() and not faces_root.is_symlink():
            try:
                actual_face_names = {p.name for p in faces_root.iterdir()}
            except OSError:
                actual_face_names = set()
            if actual_face_names != expected_face_names:
                errors.append("NEXUS_FACES_SURFACE_MISMATCH")
            else:
                for path in faces_root.iterdir():
                    if path.is_symlink() or not path.is_dir():
                        errors.append("NEXUS_FACES_SURFACE_MISMATCH")
                        break

        basis = {
            "schema": RECEIPT_SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "sources": basis_sources,
        }
        if _sha256_json(basis) != receipt.get("nexus_digest"):
            errors.append("NEXUS_IDENTITY_DIGEST_MISMATCH")
        return {
            "ok": not errors,
            "source_count": len(source_rows),
            "manifest_sha256": self.manifest_sha256,
            "nexus_digest": receipt.get("nexus_digest"),
            "errors": errors,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JANUS NEXUS offline exact-SHA materializer v1")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sources-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("command", choices=("materialize", "verify"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    materializer = NexusMaterializer(
        load_manifest(args.manifest), args.sources_root, args.output_root
    )
    result = materializer.materialize() if args.command == "materialize" else materializer.verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
