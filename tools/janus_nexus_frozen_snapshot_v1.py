#!/usr/bin/env python3
"""Authenticated encrypted transfer of one REAL44 frozen Git source manifest.

Only encrypted, AEAD-authenticated bytes cross GitHub worker boundaries.
Private names, source SHA pins and manifest digest never enter public receipts.
The read-only PAT is used only as per-run KDF input, never persisted or logged.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any

SCHEMA = "janus.real44.encrypted_frozen_manifest.v1"
MANIFEST_SCHEMA = "janus.nexus.manifest.v1"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[0-9]{1,32}$")


class SnapshotHold(Exception):
    pass


def _manifest(blob: bytes) -> dict[str, Any]:
    try:
        body = json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SnapshotHold("FROZEN_MANIFEST_JSON_INVALID") from exc
    if not isinstance(body, dict) or body.get("schema") != MANIFEST_SCHEMA:
        raise SnapshotHold("FROZEN_MANIFEST_SCHEMA_INVALID")
    if body.get("source_code_execution") is not False or body.get("write_back_default") != "DENY":
        raise SnapshotHold("FROZEN_MANIFEST_AUTHORITY_INVALID")
    rows = body.get("sources")
    if not isinstance(rows, list) or len(rows) != 44:
        raise SnapshotHold("FROZEN_MANIFEST_COUNT_INVALID")
    seen: set[str] = set()
    vis = {"public": 0, "private": 0}
    for row in rows:
        if not isinstance(row, dict):
            raise SnapshotHold("FROZEN_MANIFEST_ROW_INVALID")
        id_ = str(row.get("repository_id") or "")
        sha = row.get("sha")
        visibility = row.get("visibility")
        if not SAFE_ID.fullmatch(id_) or id_ in seen or not isinstance(sha, str) or not FULL_SHA.fullmatch(sha):
            raise SnapshotHold("FROZEN_MANIFEST_PIN_INVALID")
        seen.add(id_)
        if visibility not in vis:
            raise SnapshotHold("FROZEN_MANIFEST_VISIBILITY_INVALID")
        vis[visibility] += 1
        if visibility == "private" and set(row) != {"repository_id", "visibility", "branch", "sha"}:
            raise SnapshotHold("FROZEN_PRIVATE_IDENTITY_FORBIDDEN")
        if visibility == "public" and set(row) != {"repository_id", "visibility", "repository", "branch", "sha"}:
            raise SnapshotHold("FROZEN_PUBLIC_ROW_FIELDS_INVALID")
        if not isinstance(row.get("branch"), str) or not row["branch"] or len(row["branch"]) > 240:
            raise SnapshotHold("FROZEN_BRANCH_INVALID")
    if vis != {"public": 41, "private": 3}:
        raise SnapshotHold("FROZEN_SOURCE_VISIBILITY_COUNT_INVALID")
    return body


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode(value: Any, length: int) -> bytes:
    if not isinstance(value, str) or len(value) > 100000:
        raise SnapshotHold("FROZEN_ENVELOPE_FIELD_INVALID")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SnapshotHold("FROZEN_ENVELOPE_FIELD_INVALID") from exc
    if len(raw) != length:
        raise SnapshotHold("FROZEN_ENVELOPE_LENGTH_INVALID")
    return raw


def _key(token: str, salt: bytes, run_id: str) -> bytes:
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=SHA256(), length=32, salt=salt,
                info=("JANUS_REAL44_FROZEN_A_B_V1:" + run_id).encode("ascii")).derive(token.encode("utf-8"))


def _aad(run_id: str) -> bytes:
    return (SCHEMA + ":Hawkar-usls/Janus_Genesis:" + run_id).encode("ascii")


def _atomic_private(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise SnapshotHold("FROZEN_DESTINATION_SYMLINK_REJECTED")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def seal(manifest_path: Path, output_path: Path, token: str, run_id: str) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    original = manifest_path.read_bytes()
    _manifest(original)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    cipher = AESGCM(_key(token, salt, run_id)).encrypt(nonce, original, _aad(run_id))
    envelope = {"schema": SCHEMA, "salt": _b64(salt),
                "nonce": _b64(nonce), "ciphertext": _b64(cipher)}
    _atomic_private(output_path, (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))


def open_snapshot(envelope_path: Path, output_path: Path, token: str, run_id: str) -> None:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        env = json.loads(envelope_path.read_text("ascii"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise SnapshotHold("FROZEN_ENVELOPE_UNREADABLE") from exc
    if not isinstance(env, dict) or set(env) != {"schema", "salt", "nonce", "ciphertext"} or env["schema"] != SCHEMA:
        raise SnapshotHold("FROZEN_ENVELOPE_SCHEMA_INVALID")
    salt, nonce = _decode(env["salt"], 16), _decode(env["nonce"], 12)
    encoded = env["ciphertext"]
    if not isinstance(encoded, str) or len(encoded) > 250000:
        raise SnapshotHold("FROZEN_ENVELOPE_SIZE_INVALID")
    try:
        ct = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SnapshotHold("FROZEN_ENVELOPE_CIPHERTEXT_INVALID") from exc
    try:
        clear = AESGCM(_key(token, salt, run_id)).decrypt(nonce, ct, _aad(run_id))
    except (InvalidTag, ValueError) as exc:
        raise SnapshotHold("FROZEN_ENVELOPE_AUTHENTICATION_FAILED") from exc
    _manifest(clear)
    _atomic_private(output_path, clear)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("seal", "open"))
    p.add_argument("--manifest", required=True)
    p.add_argument("--encrypted", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--token-env", default="JANUS_NEXUS_PRIVATE_READ_TOKEN")
    a = p.parse_args()
    token = os.environ.get(a.token_env, "")
    if not token or "\n" in token or "\r" in token:
        print("FROZEN_HOLD:READ_ONLY_CREDENTIAL_UNAVAILABLE", file=sys.stderr)
        return 42
    if not a.run_id.isdecimal() or len(a.run_id) > 32:
        print("FROZEN_HOLD:RUN_ID_INVALID", file=sys.stderr)
        return 43
    try:
        if a.action == "seal":
            seal(Path(a.manifest), Path(a.encrypted), token, a.run_id)
        else:
            open_snapshot(Path(a.encrypted), Path(a.manifest), token, a.run_id)
    except (SnapshotHold, OSError, ValueError, ImportError) as exc:
        code = str(exc) if isinstance(exc, SnapshotHold) else "FROZEN_CRYPTO_OR_IO_HOLD"
        print("FROZEN_HOLD:" + code, file=sys.stderr)
        return 43
    print("FROZEN_MANIFEST_" + ("SEALED" if a.action == "seal" else "OPENED") + "=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
