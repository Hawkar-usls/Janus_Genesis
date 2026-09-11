#!/usr/bin/env python3
"""Append-only JANUS NEXUS variant lineage ledger.

This module is deliberately authority-neutral. It records immutable variant
facts and derives graph views; it does not execute variants, select winners,
mutate source repositories, or grant writeback permission.

A hash chain detects mutation/reordering of retained records. Detecting a
valid-prefix truncation requires an externally retained ``lineage_digest``
receipt and ``verify --expected-lineage-digest``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

RECORD_SCHEMA = "janus.nexus.variant_lineage.record.v1"
VARIANT_SCHEMA = "janus.nexus.variant_lineage.variant.v1"
RECEIPT_SCHEMA = "janus.nexus.variant_lineage.receipt.v1"
ZERO_DIGEST = "0" * 64
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

REQUIRED_PAYLOAD_KEYS = {
    "nexus_identity_digest",
    "parent_variant_ids",
    "source_repository_shas",
    "inherited_traits",
    "mutations",
    "test_suite",
    "metrics",
    "gate_results",
    "failure_reason_if_any",
    "receipt_digest",
    "selection_scope",
}


class LineageError(RuntimeError):
    """Fail-closed lineage validation error."""


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


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise LineageError(f"{field} must be a lowercase 64-hex digest")
    return value


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise LineageError(f"{field} must be an exact lowercase 40-hex Git SHA")
    return value


def validate_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LineageError("variant payload must be an object")
    keys = set(raw)
    if keys != REQUIRED_PAYLOAD_KEYS:
        missing = sorted(REQUIRED_PAYLOAD_KEYS - keys)
        extra = sorted(keys - REQUIRED_PAYLOAD_KEYS)
        raise LineageError(f"variant payload keys mismatch; missing={missing}; extra={extra}")

    _require_digest(raw["nexus_identity_digest"], "nexus_identity_digest")
    _require_digest(raw["receipt_digest"], "receipt_digest")

    parents = raw["parent_variant_ids"]
    if not isinstance(parents, list):
        raise LineageError("parent_variant_ids must be a unique list")
    for index, parent in enumerate(parents):
        _require_digest(parent, f"parent_variant_ids[{index}]")
    if len(parents) != len(set(parents)):
        raise LineageError("parent_variant_ids must be a unique list")

    sources = raw["source_repository_shas"]
    if not isinstance(sources, list) or not sources:
        raise LineageError("source_repository_shas must be a non-empty list")
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != {"repository_id", "sha"}:
            raise LineageError(
                f"source_repository_shas[{index}] must contain only repository_id and sha"
            )
        repository_id = source["repository_id"]
        if not isinstance(repository_id, str) or not REPOSITORY_ID.fullmatch(repository_id):
            raise LineageError(f"source_repository_shas[{index}].repository_id is invalid")
        if repository_id in source_ids:
            raise LineageError(f"duplicate repository_id: {repository_id}")
        source_ids.add(repository_id)
        _require_sha(source["sha"], f"source_repository_shas[{index}].sha")

    for field in ("inherited_traits", "mutations"):
        if not isinstance(raw[field], list):
            raise LineageError(f"{field} must be a list")
    for field in ("test_suite", "metrics", "gate_results"):
        if not isinstance(raw[field], dict):
            raise LineageError(f"{field} must be an object")

    failure = raw["failure_reason_if_any"]
    if failure is not None and (not isinstance(failure, str) or not failure.strip()):
        raise LineageError("failure_reason_if_any must be null or a non-empty string")

    scope = raw["selection_scope"]
    if not isinstance(scope, dict) or set(scope) != {"objective", "constraints", "dataset"}:
        raise LineageError("selection_scope must contain objective, constraints, and dataset")
    if not isinstance(scope["objective"], str) or not scope["objective"].strip():
        raise LineageError("selection_scope.objective must be a non-empty string")
    if not isinstance(scope["constraints"], list):
        raise LineageError("selection_scope.constraints must be a list")
    if not isinstance(scope["dataset"], str) or not scope["dataset"].strip():
        raise LineageError("selection_scope.dataset must be a non-empty string")

    try:
        normalized = json.loads(canonical_bytes(raw).decode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise LineageError(f"variant payload is not canonical JSON data: {exc}") from exc

    # Parents and source bindings are logical sets. Their input order must not
    # create a different variant identity for the same ancestry/source pins.
    normalized["parent_variant_ids"] = sorted(normalized["parent_variant_ids"])
    normalized["source_repository_shas"] = sorted(
        normalized["source_repository_shas"],
        key=lambda row: row["repository_id"],
    )
    return normalized


def variant_id_for(payload: dict[str, Any]) -> str:
    normalized = validate_payload(payload)
    return hashlib.sha256(
        b"JANUS_NEXUS_VARIANT_V1\x00" + canonical_bytes(normalized)
    ).hexdigest()


def _record_core(
    *,
    sequence: int,
    previous_digest: str,
    variant_id: str,
    generation: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": RECORD_SCHEMA,
        "event": "VARIANT_APPEND",
        "sequence": sequence,
        "previous_record_digest": previous_digest,
        "variant_id": variant_id,
        "generation": generation,
        "payload": payload,
    }


def _lineage_digest(record_digests: list[str], variant_ids: list[str]) -> str:
    return digest(
        {
            "schema": RECEIPT_SCHEMA,
            "record_count": len(record_digests),
            "head_record_digest": record_digests[-1] if record_digests else ZERO_DIGEST,
            "variant_ids": variant_ids,
        }
    )


def _require_no_follow_support() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise LineageError("this append-only ledger requires OS O_NOFOLLOW support")
    return int(nofollow)


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_real_existing_parent(path: Path) -> Path:
    absolute_parent = _absolute_lexical(path).parent
    if not absolute_parent.exists() or not absolute_parent.is_dir():
        raise LineageError("ledger parent directory must already exist")
    if absolute_parent.is_symlink():
        raise LineageError("ledger parent path must not contain symlinks")
    resolved_parent = Path(os.path.realpath(os.fspath(absolute_parent)))
    if resolved_parent != absolute_parent:
        raise LineageError("ledger parent path must not contain symlinks")
    for ancestor in absolute_parent.parents:
        if ancestor.is_symlink():
            raise LineageError("ledger parent path must not contain symlinks")
    return absolute_parent


def _safe_ledger_path(path: Path) -> Path:
    absolute = _absolute_lexical(path)
    _require_real_existing_parent(absolute)
    if absolute.is_symlink():
        raise LineageError("ledger path must not be a symlink")
    return absolute


def _read_regular_no_follow(path: Path) -> str | None:
    flags = os.O_RDONLY | _require_no_follow_support()
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LineageError(f"cannot open ledger without following links: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise LineageError("ledger path must be a regular file")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise LineageError(f"ledger is not valid UTF-8: {exc}") from exc
    finally:
        os.close(fd)


def _append_regular_no_follow(path: Path, encoded: bytes) -> None:
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | _require_no_follow_support()
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LineageError(f"cannot open ledger for append without following links: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise LineageError("ledger path must be a regular file")
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise LineageError("short/zero append write")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def verify_ledger(
    ledger: Path,
    *,
    expected_lineage_digest: str | None = None,
) -> dict[str, Any]:
    ledger = _safe_ledger_path(ledger)
    text = _read_regular_no_follow(ledger)
    if text is None:
        if expected_lineage_digest is not None:
            _require_digest(expected_lineage_digest, "expected_lineage_digest")
        empty_digest = _lineage_digest([], [])
        if expected_lineage_digest is not None and expected_lineage_digest != empty_digest:
            raise LineageError("lineage digest mismatch")
        return {
            "ok": True,
            "schema": RECEIPT_SCHEMA,
            "record_count": 0,
            "head_record_digest": ZERO_DIGEST,
            "lineage_digest": empty_digest,
            "variants": {},
        }

    if text and not text.endswith("\n"):
        raise LineageError("ledger ends with a partial/non-newline record")

    variants: dict[str, dict[str, Any]] = {}
    descendants: dict[str, list[str]] = {}
    record_digests: list[str] = []
    variant_ids: list[str] = []
    previous = ZERO_DIGEST

    for sequence, line in enumerate(text.splitlines()):
        if not line.strip():
            raise LineageError(f"blank record at sequence {sequence}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LineageError(f"invalid JSON at sequence {sequence}: {exc}") from exc
        if not isinstance(record, dict):
            raise LineageError(f"record {sequence} must be an object")
        if set(record) != {
            "schema",
            "event",
            "sequence",
            "previous_record_digest",
            "variant_id",
            "generation",
            "payload",
            "record_digest",
        }:
            raise LineageError(f"record {sequence} has unexpected fields")
        if record["schema"] != RECORD_SCHEMA or record["event"] != "VARIANT_APPEND":
            raise LineageError(f"record {sequence} schema/event mismatch")
        if record["sequence"] != sequence:
            raise LineageError(f"record {sequence} sequence mismatch")
        if record["previous_record_digest"] != previous:
            raise LineageError(f"record {sequence} hash-chain predecessor mismatch")

        payload = validate_payload(record["payload"])
        expected_variant_id = variant_id_for(payload)
        if record["payload"] != payload:
            raise LineageError(f"record {sequence} payload is not normalized canonical form")
        if record["variant_id"] != expected_variant_id:
            raise LineageError(f"record {sequence} variant_id mismatch")
        if expected_variant_id in variants:
            raise LineageError(f"duplicate variant_id at sequence {sequence}")

        parents = payload["parent_variant_ids"]
        missing = [parent for parent in parents if parent not in variants]
        if missing:
            raise LineageError(f"record {sequence} references non-prior parents: {missing}")
        expected_generation = (
            0
            if not parents
            else 1 + max(int(variants[parent]["generation"]) for parent in parents)
        )
        if record["generation"] != expected_generation:
            raise LineageError(f"record {sequence} generation mismatch")

        core = {key: value for key, value in record.items() if key != "record_digest"}
        expected_record_digest = digest(core)
        if record["record_digest"] != expected_record_digest:
            raise LineageError(f"record {sequence} digest mismatch")

        variants[expected_variant_id] = {
            "schema": VARIANT_SCHEMA,
            "variant_id": expected_variant_id,
            "generation": expected_generation,
            "parent_variant_ids": list(parents),
            "source_repository_shas": payload["source_repository_shas"],
            "inherited_traits": payload["inherited_traits"],
            "mutations": payload["mutations"],
            "test_suite": payload["test_suite"],
            "metrics": payload["metrics"],
            "gate_results": payload["gate_results"],
            "failure_reason_if_any": payload["failure_reason_if_any"],
            "receipt_digest": payload["receipt_digest"],
            "nexus_identity_digest": payload["nexus_identity_digest"],
            "selection_scope": payload["selection_scope"],
            "descendants": [],
        }
        descendants[expected_variant_id] = []
        for parent in parents:
            descendants[parent].append(expected_variant_id)

        previous = expected_record_digest
        record_digests.append(expected_record_digest)
        variant_ids.append(expected_variant_id)

    for variant_id, children in descendants.items():
        variants[variant_id]["descendants"] = sorted(children)

    lineage_digest = _lineage_digest(record_digests, variant_ids)
    if expected_lineage_digest is not None:
        _require_digest(expected_lineage_digest, "expected_lineage_digest")
        if expected_lineage_digest != lineage_digest:
            raise LineageError("lineage digest mismatch")

    return {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "record_count": len(record_digests),
        "head_record_digest": previous,
        "lineage_digest": lineage_digest,
        "variants": variants,
    }


def _lock_path(ledger: Path) -> Path:
    return ledger.with_name(ledger.name + ".append.lock")


def append_variant(ledger: Path, raw_payload: Any) -> dict[str, Any]:
    payload = validate_payload(raw_payload)
    ledger = _safe_ledger_path(ledger)

    lock = _lock_path(ledger)
    if lock.is_symlink():
        raise LineageError("append lock path must not be a symlink")
    lock_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | _require_no_follow_support()
    try:
        lock_fd = os.open(lock, lock_flags, 0o600)
    except FileExistsError as exc:
        raise LineageError("append lock already exists; reconcile instead of racing") from exc
    except OSError as exc:
        raise LineageError(f"cannot create append lock: {exc}") from exc

    try:
        os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_fd)
        state = verify_ledger(ledger)
        variant_id = variant_id_for(payload)
        if variant_id in state["variants"]:
            raise LineageError(f"variant already exists: {variant_id}")
        parents = payload["parent_variant_ids"]
        missing = [parent for parent in parents if parent not in state["variants"]]
        if missing:
            raise LineageError(f"unknown parent_variant_ids: {missing}")
        generation = (
            0
            if not parents
            else 1 + max(int(state["variants"][parent]["generation"]) for parent in parents)
        )
        core = _record_core(
            sequence=int(state["record_count"]),
            previous_digest=str(state["head_record_digest"]),
            variant_id=variant_id,
            generation=generation,
            payload=payload,
        )
        record = dict(core)
        record["record_digest"] = digest(core)
        encoded = canonical_bytes(record) + b"\n"
        _append_regular_no_follow(ledger, encoded)
        verified = verify_ledger(ledger)
        return {
            "ok": True,
            "schema": RECEIPT_SCHEMA,
            "event": "VARIANT_APPENDED",
            "variant_id": variant_id,
            "generation": generation,
            "record_digest": record["record_digest"],
            "lineage_digest": verified["lineage_digest"],
            "record_count": verified["record_count"],
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
            "source_writeback": False,
            "selection_authority_granted": False,
            "execution_authority_granted": False,
        }
    finally:
        os.close(lock_fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LineageError(f"cannot load input JSON: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="append one immutable variant record")
    append.add_argument("--ledger", required=True, type=Path)
    append.add_argument("--input", required=True, type=Path)

    verify = sub.add_parser("verify", help="verify hash chain and derive lineage graph")
    verify.add_argument("--ledger", required=True, type=Path)
    verify.add_argument("--expected-lineage-digest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "append":
            result = append_variant(args.ledger, _load_json(args.input))
        else:
            result = verify_ledger(
                args.ledger,
                expected_lineage_digest=args.expected_lineage_digest,
            )
    except LineageError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": RECEIPT_SCHEMA,
                    "error": str(exc),
                    "authority_delta": 0,
                    "source_writeback": False,
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
