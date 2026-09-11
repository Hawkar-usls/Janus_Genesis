#!/usr/bin/env python3
"""Durable append-only ledger for validated JANUS project-face handoffs.

The existing ``janus_project_face_handoff`` module owns envelope semantics and
conflict reconciliation. This module adds persistence only. Recording an
envelope never executes it and never grants command, truth, merge, source
writeback, or external-effect authority.

Retained-record mutation/reordering is hash-chained. Detecting truncation to an
older valid prefix requires an externally retained ``ledger_digest`` receipt.
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
from typing import Any, Iterator

from tools.janus_project_face_handoff import (
    FaceHandoffError,
    reconcile_messages,
    validate_message,
)

RECORD_SCHEMA = "janus.project.face_handoff_ledger.record.v1"
RECEIPT_SCHEMA = "janus.project.face_handoff_ledger.receipt.v1"
ZERO_DIGEST = "0" * 64
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Persistence-specific canary. This is intentionally conservative and is not a
# claim that all possible credentials can be detected from text.
_SECRET_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "GITHUB_PAT_",
    "GHP_",
    "GHU_",
    "GHS_",
    "GHR_",
    "AKIA",
    "AUTHORIZATION: BEARER ",
)


class HandoffLedgerError(RuntimeError):
    """Fail-closed durable-ledger validation error."""


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
        raise HandoffLedgerError(f"{field} must be a lowercase 64-hex digest")
    return value


def _require_no_follow_support() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise HandoffLedgerError("durable handoff ledger requires OS O_NOFOLLOW support")
    return int(nofollow)


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_real_existing_parent(path: Path) -> Path:
    absolute_parent = _absolute_lexical(path).parent
    if not absolute_parent.exists() or not absolute_parent.is_dir():
        raise HandoffLedgerError("ledger parent directory must already exist")
    if absolute_parent.is_symlink():
        raise HandoffLedgerError("ledger parent path must not contain symlinks")
    resolved_parent = Path(os.path.realpath(os.fspath(absolute_parent)))
    if resolved_parent != absolute_parent:
        raise HandoffLedgerError("ledger parent path must not contain symlinks")
    for ancestor in absolute_parent.parents:
        if ancestor.is_symlink():
            raise HandoffLedgerError("ledger parent path must not contain symlinks")
    return absolute_parent


def _safe_ledger_path(path: Path) -> Path:
    absolute = _absolute_lexical(path)
    _require_real_existing_parent(absolute)
    if absolute.is_symlink():
        raise HandoffLedgerError("ledger path must not be a symlink")
    return absolute


def _read_regular_no_follow(path: Path) -> str | None:
    flags = os.O_RDONLY | _require_no_follow_support()
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise HandoffLedgerError(f"cannot open ledger without following links: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise HandoffLedgerError("ledger path must be a regular file")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise HandoffLedgerError(f"ledger is not valid UTF-8: {exc}") from exc
    finally:
        os.close(fd)


def _append_regular_no_follow(path: Path, encoded: bytes) -> None:
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | _require_no_follow_support()
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise HandoffLedgerError(f"cannot open ledger for append without following links: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise HandoffLedgerError("ledger path must be a regular file")
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise HandoffLedgerError("short/zero append write")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)


def _reject_secret_shaped_text(message: dict[str, Any]) -> None:
    for text in _iter_strings(message):
        upper = text.upper()
        if any(marker in upper for marker in _SECRET_MARKERS):
            raise HandoffLedgerError("SECRET_SHAPED_TEXT_REFUSED_FOR_DURABLE_PERSISTENCE")


def _clean_message(raw: Any) -> dict[str, Any]:
    try:
        cleaned = validate_message(raw)
    except FaceHandoffError as exc:
        raise HandoffLedgerError(f"FACE_HANDOFF_INVALID:{exc}") from exc
    _reject_secret_shaped_text(cleaned)
    return cleaned


def _record_core(
    *,
    sequence: int,
    previous_record_digest: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": RECORD_SCHEMA,
        "event": "FACE_MESSAGE_APPEND",
        "sequence": sequence,
        "previous_record_digest": previous_record_digest,
        "message_id": message["message_id"],
        "message_sha256": message["message_sha256"],
        "message": message,
    }


def _ledger_digest(record_digests: list[str], messages: list[dict[str, Any]]) -> str:
    return digest(
        {
            "schema": RECEIPT_SCHEMA,
            "record_count": len(record_digests),
            "head_record_digest": record_digests[-1] if record_digests else ZERO_DIGEST,
            "message_ids": [item["message_id"] for item in messages],
            "message_sha256s": [item["message_sha256"] for item in messages],
        }
    )


def verify_ledger(
    ledger: Path,
    *,
    expected_ledger_digest: str | None = None,
) -> dict[str, Any]:
    ledger = _safe_ledger_path(ledger)
    text = _read_regular_no_follow(ledger)
    if text is None:
        empty_digest = _ledger_digest([], [])
        if expected_ledger_digest is not None:
            _require_digest(expected_ledger_digest, "expected_ledger_digest")
            if expected_ledger_digest != empty_digest:
                raise HandoffLedgerError("ledger digest mismatch")
        return {
            "ok": True,
            "schema": RECEIPT_SCHEMA,
            "record_count": 0,
            "head_record_digest": ZERO_DIGEST,
            "ledger_digest": empty_digest,
            "message_index": {},
            "reconciliation": {
                "status": "EMPTY",
                "majority_vote_used": False,
                "authority_delta": 0,
                "mass_effect_budget_delta": 0,
            },
        }
    if text and not text.endswith("\n"):
        raise HandoffLedgerError("ledger ends with a partial/non-newline record")

    previous = ZERO_DIGEST
    record_digests: list[str] = []
    messages: list[dict[str, Any]] = []
    message_index: dict[str, dict[str, Any]] = {}

    for sequence, line in enumerate(text.splitlines()):
        if not line.strip():
            raise HandoffLedgerError(f"blank record at sequence {sequence}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HandoffLedgerError(f"invalid JSON at sequence {sequence}: {exc}") from exc
        if not isinstance(record, dict) or set(record) != {
            "schema",
            "event",
            "sequence",
            "previous_record_digest",
            "message_id",
            "message_sha256",
            "message",
            "record_digest",
        }:
            raise HandoffLedgerError(f"record {sequence} shape invalid")
        if record["schema"] != RECORD_SCHEMA or record["event"] != "FACE_MESSAGE_APPEND":
            raise HandoffLedgerError(f"record {sequence} schema/event mismatch")
        if record["sequence"] != sequence:
            raise HandoffLedgerError(f"record {sequence} sequence mismatch")
        if record["previous_record_digest"] != previous:
            raise HandoffLedgerError(f"record {sequence} predecessor mismatch")

        cleaned = _clean_message(record["message"])
        if record["message"] != cleaned:
            raise HandoffLedgerError(f"record {sequence} message is not canonical cleaned form")
        if record["message_id"] != cleaned["message_id"]:
            raise HandoffLedgerError(f"record {sequence} message_id mismatch")
        if record["message_sha256"] != cleaned["message_sha256"]:
            raise HandoffLedgerError(f"record {sequence} message_sha256 mismatch")
        message_id = str(cleaned["message_id"])
        if message_id in message_index:
            raise HandoffLedgerError(f"duplicate persisted message_id: {message_id}")

        core = {key: value for key, value in record.items() if key != "record_digest"}
        expected_record_digest = digest(core)
        if record["record_digest"] != expected_record_digest:
            raise HandoffLedgerError(f"record {sequence} digest mismatch")

        message_index[message_id] = {
            "message_sha256": cleaned["message_sha256"],
            "sequence": sequence,
            "record_digest": expected_record_digest,
        }
        messages.append(cleaned)
        record_digests.append(expected_record_digest)
        previous = expected_record_digest

    try:
        reconciliation = reconcile_messages(messages)
    except FaceHandoffError as exc:
        raise HandoffLedgerError(f"persisted message reconciliation invalid:{exc}") from exc

    ledger_digest = _ledger_digest(record_digests, messages)
    if expected_ledger_digest is not None:
        _require_digest(expected_ledger_digest, "expected_ledger_digest")
        if expected_ledger_digest != ledger_digest:
            raise HandoffLedgerError("ledger digest mismatch")

    return {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "record_count": len(record_digests),
        "head_record_digest": previous,
        "ledger_digest": ledger_digest,
        "message_index": message_index,
        "reconciliation": reconciliation,
    }


def _lock_path(ledger: Path) -> Path:
    return ledger.with_name(ledger.name + ".append.lock")


def append_message(ledger: Path, raw_message: Any) -> dict[str, Any]:
    cleaned = _clean_message(raw_message)
    ledger = _safe_ledger_path(ledger)

    lock = _lock_path(ledger)
    if lock.is_symlink():
        raise HandoffLedgerError("append lock path must not be a symlink")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | _require_no_follow_support()
    try:
        lock_fd = os.open(lock, flags, 0o600)
    except FileExistsError as exc:
        raise HandoffLedgerError("append lock already exists; HOLD_RECONCILE instead of racing") from exc
    except OSError as exc:
        raise HandoffLedgerError(f"cannot create append lock: {exc}") from exc

    try:
        os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_fd)
        state = verify_ledger(ledger)
        message_id = str(cleaned["message_id"])
        existing = state["message_index"].get(message_id)
        if existing is not None:
            if existing["message_sha256"] != cleaned["message_sha256"]:
                raise HandoffLedgerError("MESSAGE_ID_REBINDING_REJECTED")
            return {
                "ok": True,
                "schema": RECEIPT_SCHEMA,
                "event": "MESSAGE_REPLAY_IDEMPOTENT",
                "message_id": message_id,
                "message_sha256": cleaned["message_sha256"],
                "record_count": state["record_count"],
                "head_record_digest": state["head_record_digest"],
                "ledger_digest": state["ledger_digest"],
                "reconciliation_status": state["reconciliation"]["status"],
                "permission_granted": False,
                "truth_authority_granted": False,
                "effect_authority_granted": False,
                "authority_delta": 0,
                "mass_effect_budget_delta": 0,
            }

        core = _record_core(
            sequence=int(state["record_count"]),
            previous_record_digest=str(state["head_record_digest"]),
            message=cleaned,
        )
        record = dict(core)
        record["record_digest"] = digest(core)
        _append_regular_no_follow(ledger, canonical_bytes(record) + b"\n")
        verified = verify_ledger(ledger)
        return {
            "ok": True,
            "schema": RECEIPT_SCHEMA,
            "event": "FACE_MESSAGE_APPENDED",
            "message_id": message_id,
            "message_sha256": cleaned["message_sha256"],
            "record_digest": record["record_digest"],
            "record_count": verified["record_count"],
            "head_record_digest": verified["head_record_digest"],
            "ledger_digest": verified["ledger_digest"],
            "reconciliation_status": verified["reconciliation"]["status"],
            "permission_granted": False,
            "truth_authority_granted": False,
            "effect_authority_granted": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
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
        raise HandoffLedgerError(f"cannot load input JSON: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append")
    append.add_argument("--ledger", required=True, type=Path)
    append.add_argument("--input", required=True, type=Path)

    verify = sub.add_parser("verify")
    verify.add_argument("--ledger", required=True, type=Path)
    verify.add_argument("--expected-ledger-digest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "append":
            result = append_message(args.ledger, _load_json(args.input))
        else:
            result = verify_ledger(
                args.ledger,
                expected_ledger_digest=args.expected_ledger_digest,
            )
    except HandoffLedgerError as exc:
        result = {
            "ok": False,
            "schema": RECEIPT_SCHEMA,
            "error": str(exc),
            "permission_granted": False,
            "truth_authority_granted": False,
            "effect_authority_granted": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        }
        print(json.dumps(result, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
