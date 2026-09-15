#!/usr/bin/env python3
"""Read-only JANUS source identity guard.

Capture endpoint source identity without publishing private source fingerprints.
Each local snapshot binds:
- exact Git HEAD commit,
- exact HEAD^{tree} object,
- deterministic non-.git worktree surface/bytes/modes/symlink targets.

Only fixed read-only ``git rev-parse`` queries are permitted. The guard does not
attribute causality: equal before/after snapshots show endpoint identity
stability, not proof that no transient write-and-restore occurred in between.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

CONFIG_SCHEMA = "janus.source_identity_guard.config.v1"
SNAPSHOT_SCHEMA = "janus.source_identity_guard.snapshot.v1"
COMPARE_SCHEMA = "janus.source_identity_guard.compare_receipt.v1"
PUBLIC_SCHEMA = "janus.source_identity_guard.public_projection.v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID = re.compile(r"^[0-9]{1,32}$")
CONFIG_KEYS = {"schema", "sources"}
SOURCE_KEYS = {"repository_id", "visibility"}
SNAPSHOT_KEYS = {
    "schema",
    "source_count",
    "sources",
    "snapshot_digest",
    "git_queries",
    "git_metadata_included_in_worktree_digest",
    "source_mutation_performed",
    "authority_delta",
    "mass_effect_budget_delta",
}
SNAPSHOT_SOURCE_KEYS = {
    "repository_id",
    "visibility",
    "head_commit",
    "head_tree",
    "worktree_digest",
    "worktree_entry_count",
}
COMPARE_KEYS = {
    "schema",
    "source_count",
    "before_snapshot_digest",
    "after_snapshot_digest",
    "source_identity_unchanged",
    "source_identity_drift_observed",
    "drifted_repository_ids",
    "writeback_attribution_made",
    "transient_write_and_restore_ruled_out",
    "source_mutation_performed_by_guard",
    "authority_delta",
    "mass_effect_budget_delta",
}
ALLOWED_VISIBILITY = {"public", "private"}
GIT_QUERY_RECEIPT = [
    "rev-parse --verify HEAD",
    "rev-parse --verify HEAD^{tree}",
]


class SourceIdentityGuardError(RuntimeError):
    """Fail-closed source identity guard error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require_exact_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceIdentityGuardError(f"{field} must be an object")
    if set(value) != expected:
        raise SourceIdentityGuardError(f"{field} fields invalid")
    return value


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise SourceIdentityGuardError(f"{field} must be lowercase 64-hex digest")
    return value


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise SourceIdentityGuardError(f"{field} must be lowercase 40-hex Git object id")
    return value


def _require_bool(value: Any, field: str, expected: bool | None = None) -> bool:
    if type(value) is not bool:
        raise SourceIdentityGuardError(f"{field} must be boolean")
    if expected is not None and value is not expected:
        raise SourceIdentityGuardError(f"{field} must be {expected}")
    return value


def _require_zero(value: Any, field: str) -> int:
    if type(value) is not int or value != 0:
        raise SourceIdentityGuardError(f"{field} must be integer zero")
    return 0


def validate_config(raw: Any) -> dict[str, Any]:
    value = _require_exact_keys(raw, CONFIG_KEYS, "config")
    if value.get("schema") != CONFIG_SCHEMA:
        raise SourceIdentityGuardError("config schema invalid")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourceIdentityGuardError("config sources required")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw_row in enumerate(sources):
        row = _require_exact_keys(raw_row, SOURCE_KEYS, f"config.sources[{index}]")
        repository_id = row.get("repository_id")
        visibility = row.get("visibility")
        if not isinstance(repository_id, str) or not OPAQUE_ID.fullmatch(repository_id):
            raise SourceIdentityGuardError("repository_id must be opaque numeric id")
        if repository_id in seen:
            raise SourceIdentityGuardError("duplicate repository_id")
        if visibility not in ALLOWED_VISIBILITY:
            raise SourceIdentityGuardError("visibility invalid")
        seen.add(repository_id)
        normalized.append({"repository_id": repository_id, "visibility": str(visibility)})
    normalized.sort(key=lambda item: item["repository_id"])
    return {"schema": CONFIG_SCHEMA, "sources": normalized}


def _git_readonly(repo: Path, query: str) -> str:
    commands = {
        "HEAD": ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        "HEAD_TREE": ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD^{tree}"],
    }
    command = commands.get(query)
    if command is None:
        raise SourceIdentityGuardError("unsupported git identity query")
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceIdentityGuardError(f"read-only Git identity query failed:{query}") from exc
    try:
        value = output.decode("ascii", errors="strict").strip().lower()
    except UnicodeDecodeError as exc:
        raise SourceIdentityGuardError("Git identity query returned non-ASCII output") from exc
    return _require_sha(value, f"git.{query}")


def _safe_name(name: str) -> str:
    try:
        name.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise SourceIdentityGuardError("non-UTF8-compatible worktree path rejected") from exc
    return name


def _stat_stability_tuple(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stream_file_no_follow(path: Path) -> tuple[str, int, int]:
    """Hash a regular file without following links or buffering the whole file."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise SourceIdentityGuardError("O_NOFOLLOW support required")
    flags = os.O_RDONLY | int(nofollow)
    if hasattr(os, "O_CLOEXEC"):
        flags |= int(os.O_CLOEXEC)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SourceIdentityGuardError("cannot read worktree file without following links") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise SourceIdentityGuardError("worktree entry changed type during capture")
        hasher = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            total += len(chunk)
        after = os.fstat(fd)
        if _stat_stability_tuple(before) != _stat_stability_tuple(after):
            raise SourceIdentityGuardError("worktree file changed during capture")
        if total != after.st_size:
            raise SourceIdentityGuardError("worktree file size changed during capture")
        return hasher.hexdigest(), total, stat.S_IMODE(after.st_mode)
    finally:
        os.close(fd)


def _stable_symlink_record(path: Path, rel_text: str, initial: os.stat_result) -> dict[str, Any]:
    before_tuple = _stat_stability_tuple(initial)
    try:
        target = os.readlink(path)
        after = os.lstat(path)
    except OSError as exc:
        raise SourceIdentityGuardError("worktree symlink read failed") from exc
    if not stat.S_ISLNK(after.st_mode) or before_tuple != _stat_stability_tuple(after):
        raise SourceIdentityGuardError("worktree symlink changed during capture")
    _safe_name(target)
    return {
        "path": rel_text,
        "type": "symlink",
        "mode": stat.S_IMODE(after.st_mode),
        "target": target,
    }


def _worktree_surface(checkout: Path) -> tuple[str, int]:
    records: list[dict[str, Any]] = []

    def walk(directory: Path, prefix: Path) -> None:
        try:
            directory_before = os.lstat(directory)
        except OSError as exc:
            raise SourceIdentityGuardError("worktree directory unreadable") from exc
        if not stat.S_ISDIR(directory_before.st_mode):
            raise SourceIdentityGuardError("worktree directory changed type during capture")

        # Include the worktree root and every nested directory mode in the
        # endpoint surface while deliberately excluding .git contents.
        records.append(
            {
                "path": "." if prefix == Path(".") else prefix.as_posix(),
                "type": "directory",
                "mode": stat.S_IMODE(directory_before.st_mode),
            }
        )

        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise SourceIdentityGuardError("worktree directory scan failed") from exc

        for entry in entries:
            if prefix == Path(".") and entry.name == ".git":
                continue
            name = _safe_name(entry.name)
            rel = Path(name) if prefix == Path(".") else prefix / name
            rel_text = rel.as_posix()
            try:
                item_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise SourceIdentityGuardError("worktree entry lstat failed") from exc
            path = Path(entry.path)
            if stat.S_ISDIR(item_stat.st_mode):
                walk(path, rel)
            elif stat.S_ISREG(item_stat.st_mode):
                sha256_hex, byte_count, opened_mode = _stream_file_no_follow(path)
                records.append(
                    {
                        "path": rel_text,
                        "type": "file",
                        "mode": opened_mode,
                        "bytes": byte_count,
                        "sha256": sha256_hex,
                    }
                )
            elif stat.S_ISLNK(item_stat.st_mode):
                records.append(_stable_symlink_record(path, rel_text, item_stat))
            else:
                raise SourceIdentityGuardError(
                    f"unsupported special worktree entry type:{rel_text}"
                )

        try:
            directory_after = os.lstat(directory)
        except OSError as exc:
            raise SourceIdentityGuardError("worktree directory disappeared during capture") from exc
        if _stat_stability_tuple(directory_before) != _stat_stability_tuple(directory_after):
            raise SourceIdentityGuardError("worktree directory changed during capture")

    walk(checkout, Path("."))
    records.sort(key=lambda item: (item["path"], item["type"]))
    return digest({"surface": records}), len(records)


def _checkout(root: Path, repository_id: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise SourceIdentityGuardError("sources_root must be a real directory")
    checkout = root / repository_id
    if checkout.is_symlink() or not checkout.is_dir():
        raise SourceIdentityGuardError(f"source checkout invalid:{repository_id}")
    try:
        checkout.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise SourceIdentityGuardError(f"source checkout escapes sources_root:{repository_id}") from exc
    return checkout


def capture(config_raw: Any, sources_root: Path) -> dict[str, Any]:
    config = validate_config(config_raw)
    root = Path(sources_root)
    rows: list[dict[str, Any]] = []
    for row in config["sources"]:
        repository_id = row["repository_id"]
        checkout = _checkout(root, repository_id)

        head_commit_before = _git_readonly(checkout, "HEAD")
        head_tree_before = _git_readonly(checkout, "HEAD_TREE")
        worktree_digest, entry_count = _worktree_surface(checkout)
        head_commit_after = _git_readonly(checkout, "HEAD")
        head_tree_after = _git_readonly(checkout, "HEAD_TREE")

        if head_commit_before != head_commit_after or head_tree_before != head_tree_after:
            raise SourceIdentityGuardError(
                f"Git identity changed during capture:{repository_id}"
            )

        rows.append(
            {
                "repository_id": repository_id,
                "visibility": row["visibility"],
                "head_commit": head_commit_after,
                "head_tree": head_tree_after,
                "worktree_digest": worktree_digest,
                "worktree_entry_count": entry_count,
            }
        )

    basis = {"schema": SNAPSHOT_SCHEMA, "source_count": len(rows), "sources": rows}
    return {
        **basis,
        "snapshot_digest": digest(basis),
        "git_queries": list(GIT_QUERY_RECEIPT),
        "git_metadata_included_in_worktree_digest": False,
        "source_mutation_performed": False,
        "authority_delta": 0,
        "mass_effect_budget_delta": 0,
    }


def validate_snapshot(raw: Any) -> dict[str, Any]:
    value = _require_exact_keys(raw, SNAPSHOT_KEYS, "snapshot")
    if value.get("schema") != SNAPSHOT_SCHEMA:
        raise SourceIdentityGuardError("snapshot schema invalid")
    source_count = value.get("source_count")
    if type(source_count) is not int or source_count <= 0:
        raise SourceIdentityGuardError("snapshot source_count invalid")
    sources = value.get("sources")
    if not isinstance(sources, list) or len(sources) != source_count:
        raise SourceIdentityGuardError("snapshot source count mismatch")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_row in enumerate(sources):
        row = _require_exact_keys(raw_row, SNAPSHOT_SOURCE_KEYS, f"snapshot.sources[{index}]")
        repository_id = row.get("repository_id")
        if not isinstance(repository_id, str) or not OPAQUE_ID.fullmatch(repository_id):
            raise SourceIdentityGuardError("snapshot repository_id invalid")
        if repository_id in seen:
            raise SourceIdentityGuardError("snapshot duplicate repository_id")
        visibility = row.get("visibility")
        if visibility not in ALLOWED_VISIBILITY:
            raise SourceIdentityGuardError("snapshot visibility invalid")
        entry_count = row.get("worktree_entry_count")
        if type(entry_count) is not int or entry_count <= 0:
            raise SourceIdentityGuardError("snapshot worktree_entry_count invalid")
        normalized.append(
            {
                "repository_id": repository_id,
                "visibility": visibility,
                "head_commit": _require_sha(row.get("head_commit"), "snapshot.head_commit"),
                "head_tree": _require_sha(row.get("head_tree"), "snapshot.head_tree"),
                "worktree_digest": _require_digest(row.get("worktree_digest"), "snapshot.worktree_digest"),
                "worktree_entry_count": entry_count,
            }
        )
        seen.add(repository_id)
    normalized.sort(key=lambda item: item["repository_id"])
    if normalized != sources:
        raise SourceIdentityGuardError("snapshot sources not normalized")
    if value.get("git_queries") != GIT_QUERY_RECEIPT:
        raise SourceIdentityGuardError("snapshot git query contract invalid")
    _require_bool(
        value.get("git_metadata_included_in_worktree_digest"),
        "snapshot.git_metadata_included",
        False,
    )
    _require_bool(
        value.get("source_mutation_performed"),
        "snapshot.source_mutation_performed",
        False,
    )
    _require_zero(value.get("authority_delta"), "snapshot.authority_delta")
    _require_zero(
        value.get("mass_effect_budget_delta"), "snapshot.mass_effect_budget_delta"
    )
    basis = {"schema": SNAPSHOT_SCHEMA, "source_count": source_count, "sources": normalized}
    expected_digest = digest(basis)
    if value.get("snapshot_digest") != expected_digest:
        raise SourceIdentityGuardError("snapshot digest mismatch")
    return {**value, "sources": normalized, "snapshot_digest": expected_digest}


def compare(before_raw: Any, after_raw: Any) -> dict[str, Any]:
    before = validate_snapshot(before_raw)
    after = validate_snapshot(after_raw)
    before_rows = {row["repository_id"]: row for row in before["sources"]}
    after_rows = {row["repository_id"]: row for row in after["sources"]}
    if set(before_rows) != set(after_rows):
        raise SourceIdentityGuardError("before/after source set mismatch")
    drifted = [
        repository_id
        for repository_id in sorted(before_rows)
        if before_rows[repository_id] != after_rows[repository_id]
    ]
    unchanged = not drifted and before["snapshot_digest"] == after["snapshot_digest"]
    return {
        "schema": COMPARE_SCHEMA,
        "source_count": len(before_rows),
        "before_snapshot_digest": before["snapshot_digest"],
        "after_snapshot_digest": after["snapshot_digest"],
        "source_identity_unchanged": unchanged,
        "source_identity_drift_observed": bool(drifted),
        "drifted_repository_ids": drifted,
        "writeback_attribution_made": False,
        "transient_write_and_restore_ruled_out": False,
        "source_mutation_performed_by_guard": False,
        "authority_delta": 0,
        "mass_effect_budget_delta": 0,
    }


def validate_compare_receipt(raw: Any) -> dict[str, Any]:
    value = _require_exact_keys(raw, COMPARE_KEYS, "compare_receipt")
    if value.get("schema") != COMPARE_SCHEMA:
        raise SourceIdentityGuardError("compare receipt schema invalid")
    source_count = value.get("source_count")
    if type(source_count) is not int or source_count <= 0:
        raise SourceIdentityGuardError("compare source_count invalid")
    before_digest = _require_digest(
        value.get("before_snapshot_digest"), "compare.before_snapshot_digest"
    )
    after_digest = _require_digest(
        value.get("after_snapshot_digest"), "compare.after_snapshot_digest"
    )
    unchanged = _require_bool(
        value.get("source_identity_unchanged"), "compare.source_identity_unchanged"
    )
    drift = _require_bool(
        value.get("source_identity_drift_observed"),
        "compare.source_identity_drift_observed",
    )
    if unchanged == drift:
        raise SourceIdentityGuardError("compare unchanged/drift flags inconsistent")
    if unchanged != (before_digest == after_digest):
        raise SourceIdentityGuardError("compare digest/identity flags inconsistent")

    drifted_ids = value.get("drifted_repository_ids")
    if not isinstance(drifted_ids, list):
        raise SourceIdentityGuardError("compare drifted_repository_ids invalid")
    cleaned_ids: list[str] = []
    for item in drifted_ids:
        if not isinstance(item, str) or not OPAQUE_ID.fullmatch(item):
            raise SourceIdentityGuardError("compare drifted_repository_ids invalid")
        cleaned_ids.append(item)
    if cleaned_ids != sorted(set(cleaned_ids)):
        raise SourceIdentityGuardError("compare drifted_repository_ids not normalized")
    if drift != bool(cleaned_ids):
        raise SourceIdentityGuardError("compare drift flag/list inconsistent")

    _require_bool(
        value.get("writeback_attribution_made"),
        "compare.writeback_attribution_made",
        False,
    )
    _require_bool(
        value.get("transient_write_and_restore_ruled_out"),
        "compare.transient_write_and_restore_ruled_out",
        False,
    )
    _require_bool(
        value.get("source_mutation_performed_by_guard"),
        "compare.source_mutation_performed_by_guard",
        False,
    )
    _require_zero(value.get("authority_delta"), "compare.authority_delta")
    _require_zero(
        value.get("mass_effect_budget_delta"), "compare.mass_effect_budget_delta"
    )
    return {
        **value,
        "before_snapshot_digest": before_digest,
        "after_snapshot_digest": after_digest,
        "drifted_repository_ids": cleaned_ids,
    }


def public_projection(compare_raw: Any) -> dict[str, Any]:
    value = validate_compare_receipt(compare_raw)
    return {
        "schema": PUBLIC_SCHEMA,
        "source_count": value["source_count"],
        "source_identity_unchanged": value["source_identity_unchanged"],
        "source_identity_drift_observed": value["source_identity_drift_observed"],
        "local_source_fingerprints_published": False,
        "drifted_repository_ids_published": False,
        "writeback_attribution_made": False,
        "transient_write_and_restore_ruled_out": False,
        "source_mutation_performed_by_guard": False,
        "authority_delta": 0,
        "mass_effect_budget_delta": 0,
        "claim_ceiling": (
            "This public projection reports endpoint source identity stability only. "
            "It publishes no local source fingerprints or drifted source IDs and does not "
            "attribute writeback causality or rule out a transient write-and-restore."
        ),
    }


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceIdentityGuardError(f"cannot load {label} JSON") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture_cmd = sub.add_parser("capture")
    capture_cmd.add_argument("--config", required=True, type=Path)
    capture_cmd.add_argument("--sources-root", required=True, type=Path)
    compare_cmd = sub.add_parser("compare")
    compare_cmd.add_argument("--before", required=True, type=Path)
    compare_cmd.add_argument("--after", required=True, type=Path)
    public_cmd = sub.add_parser("public-project")
    public_cmd.add_argument("--compare", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capture":
            result = capture(_load_json(args.config, "config"), args.sources_root)
        elif args.command == "compare":
            result = compare(
                _load_json(args.before, "before snapshot"),
                _load_json(args.after, "after snapshot"),
            )
        else:
            result = public_projection(_load_json(args.compare, "compare receipt"))
    except SourceIdentityGuardError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "source_mutation_performed_by_guard": False,
                    "authority_delta": 0,
                    "mass_effect_budget_delta": 0,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
