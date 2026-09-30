#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""No-delete local filesystem gateway for the operator-configured JANUS NAS root.

This module is deliberately not a network client. The configured NAS/share must
already be mounted by the operator. The gateway exposes only read/list/stat plus
create-new and append-only writes below one configured write prefix.

There is no delete, unlink, rmdir, rename, replace, truncate, chmod, chown,
symlink, hardlink, subprocess, shell, or arbitrary command operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MAX_READ_BYTES = 16 * 1024 * 1024
MAX_WRITE_BYTES = 16 * 1024 * 1024
MAX_PATH_PARTS = 32
MAX_PART_CHARS = 128


class NasGatewayError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parts(relative: str, *, allow_root: bool = False) -> tuple[str, ...]:
    if not isinstance(relative, str) or not relative:
        raise NasGatewayError("relative path must be non-empty text")
    if "\\" in relative or "\x00" in relative:
        raise NasGatewayError("path contains forbidden characters")
    p = PurePosixPath(relative)
    if p.is_absolute():
        raise NasGatewayError("absolute paths are forbidden")
    raw = p.parts
    if raw == (".",):
        if allow_root:
            return ()
        raise NasGatewayError("root path is not valid for this operation")
    if not raw and allow_root:
        return ()
    if not raw or len(raw) > MAX_PATH_PARTS:
        raise NasGatewayError("path depth invalid")
    for part in raw:
        if part in {"", ".", ".."} or len(part) > MAX_PART_CHARS or "/" in part or "\x00" in part:
            raise NasGatewayError("path part invalid")
    return tuple(raw)


class NasJanusNoDeleteGateway:
    """Capability-limited view over an already-mounted operator NAS root."""

    def __init__(self, root: str | os.PathLike[str], *, write_prefix: str = "beacon", max_read_bytes: int = MAX_READ_BYTES, max_write_bytes: int = MAX_WRITE_BYTES) -> None:
        self.root = Path(root)
        if self.root.is_symlink():
            raise NasGatewayError("configured root may not be a symlink")
        try:
            st = self.root.stat()
        except FileNotFoundError as exc:
            raise NasGatewayError("configured root does not exist") from exc
        if not stat.S_ISDIR(st.st_mode):
            raise NasGatewayError("configured root is not a directory")
        prefix_parts = _parts(write_prefix)
        if len(prefix_parts) != 1:
            raise NasGatewayError("write_prefix must be one existing directory name")
        self.write_prefix = prefix_parts[0]
        if isinstance(max_read_bytes, bool) or not isinstance(max_read_bytes, int) or max_read_bytes <= 0 or isinstance(max_write_bytes, bool) or not isinstance(max_write_bytes, int) or max_write_bytes <= 0:
            raise NasGatewayError("byte limits must be positive integers")
        self.max_read_bytes = max_read_bytes
        self.max_write_bytes = max_write_bytes
        fd = self._open_dir((self.write_prefix,))
        os.close(fd)

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "read_operations": ["LIST", "STAT", "READ"],
            "write_operations": ["CREATE_NEW", "APPEND"],
            "delete": False,
            "rename": False,
            "replace": False,
            "truncate": False,
            "directory_creation": False,
            "symlink_following": False,
            "arbitrary_command": False,
            "network_transport": False,
            "source_writeback": False,
        }

    def _open_root(self) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            return os.open(os.fspath(self.root), flags)
        except OSError as exc:
            raise NasGatewayError("cannot open configured root without following symlink") from exc

    def _open_dir(self, parts: tuple[str, ...]) -> int:
        current = self._open_root()
        try:
            for part in parts:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                nxt = os.open(part, flags, dir_fd=current)
                os.close(current)
                current = nxt
            return current
        except Exception:
            os.close(current)
            raise

    @staticmethod
    def _open_parent(root_opener, parts: tuple[str, ...]) -> tuple[int, str]:
        if not parts:
            raise NasGatewayError("file path required")
        parent = root_opener(parts[:-1])
        return parent, parts[-1]

    def _require_write_scope(self, parts: tuple[str, ...]) -> None:
        if len(parts) < 2 or parts[0] != self.write_prefix:
            raise NasGatewayError(f"writes are restricted below configured prefix {self.write_prefix!r}")

    def list_dir(self, relative: str = ".") -> list[dict[str, Any]]:
        parts = _parts(relative, allow_root=True)
        fd = self._open_dir(parts)
        try:
            rows = []
            for name in sorted(os.listdir(fd)):
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode):
                    kind = "SYMLINK_BLOCKED"
                elif stat.S_ISDIR(st.st_mode):
                    kind = "DIRECTORY"
                elif stat.S_ISREG(st.st_mode):
                    kind = "REGULAR_FILE"
                else:
                    kind = "SPECIAL_BLOCKED"
                rows.append({"name": name, "kind": kind, "size": st.st_size if kind == "REGULAR_FILE" else None})
            return rows
        finally:
            os.close(fd)

    def stat_path(self, relative: str) -> dict[str, Any]:
        parts = _parts(relative)
        parent, name = self._open_parent(self._open_dir, parts)
        try:
            st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode):
                kind = "SYMLINK_BLOCKED"
            elif stat.S_ISDIR(st.st_mode):
                kind = "DIRECTORY"
            elif stat.S_ISREG(st.st_mode):
                kind = "REGULAR_FILE"
            else:
                kind = "SPECIAL_BLOCKED"
            return {"path_sha256": _sha256(relative.encode("utf-8")), "kind": kind, "size": st.st_size if kind == "REGULAR_FILE" else None}
        finally:
            os.close(parent)

    def read_bytes(self, relative: str, *, max_bytes: int | None = None) -> bytes:
        parts = _parts(relative)
        parent, name = self._open_parent(self._open_dir, parts)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, dir_fd=parent)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    raise NasGatewayError("read target must be a regular file")
                ceiling = self.max_read_bytes if max_bytes is None else max_bytes
                if isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling <= 0 or ceiling > self.max_read_bytes:
                    raise NasGatewayError("max_bytes outside configured read ceiling")
                if st.st_size > ceiling:
                    raise NasGatewayError("file exceeds bounded read ceiling")
                chunks = []
                remaining = ceiling + 1
                while remaining > 0:
                    chunk = os.read(fd, min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
                if len(data) > ceiling:
                    raise NasGatewayError("read exceeded bounded ceiling")
                return data
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def _validate_write(self, relative: str, data: bytes) -> tuple[tuple[str, ...], bytes]:
        parts = _parts(relative)
        self._require_write_scope(parts)
        if not isinstance(data, (bytes, bytearray)):
            raise NasGatewayError("write data must be bytes")
        payload = bytes(data)
        if len(payload) > self.max_write_bytes:
            raise NasGatewayError("write exceeds configured byte ceiling")
        return parts, payload

    def create_new(self, relative: str, data: bytes) -> dict[str, Any]:
        parts, payload = self._validate_write(relative, data)
        parent, name = self._open_parent(self._open_dir, parts)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, 0o600, dir_fd=parent)
            try:
                view = memoryview(payload)
                written = 0
                while written < len(view):
                    written += os.write(fd, view[written:])
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        return self._write_receipt("CREATE_NEW", relative, payload)

    def append(self, relative: str, data: bytes) -> dict[str, Any]:
        parts, payload = self._validate_write(relative, data)
        parent, name = self._open_parent(self._open_dir, parts)
        try:
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, 0o600, dir_fd=parent)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    raise NasGatewayError("append target must be a regular file")
                view = memoryview(payload)
                written = 0
                while written < len(view):
                    written += os.write(fd, view[written:])
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        return self._write_receipt("APPEND", relative, payload)

    def create_versioned_json(self, logical_name: str, document: Mapping[str, Any]) -> dict[str, Any]:
        name_parts = _parts(logical_name)
        if len(name_parts) != 1:
            raise NasGatewayError("logical_name must be one safe file name")
        data = _canonical_bytes(document)
        digest = _sha256(data)
        relative = f"{self.write_prefix}/{name_parts[0]}.{digest}.json"
        return self.create_new(relative, data)

    @staticmethod
    def _write_receipt(operation: str, relative: str, payload: bytes) -> dict[str, Any]:
        result = {
            "operation": operation,
            "path_sha256": _sha256(relative.encode("utf-8")),
            "bytes": len(payload),
            "payload_sha256": _sha256(payload),
            "delete_capability": False,
            "rename_capability": False,
            "truncate_capability": False,
        }
        result["receipt_sha256"] = _sha256(_canonical_bytes(result))
        return result


class BeaconNasMemoryAdapter:
    """Persist Beacon forecasts/outcomes and immutable state snapshots via gateway."""

    def __init__(self, gateway: NasJanusNoDeleteGateway) -> None:
        self.gateway = gateway

    @staticmethod
    def _line(record: Mapping[str, Any]) -> bytes:
        return _canonical_bytes(record) + b"\n"

    def persist_forecast(self, forecast: Mapping[str, Any]) -> dict[str, Any]:
        return self.gateway.append(f"{self.gateway.write_prefix}/beacon_forecasts.jsonl", self._line(forecast))

    def persist_outcome(self, outcome: Mapping[str, Any]) -> dict[str, Any]:
        return self.gateway.append(f"{self.gateway.write_prefix}/beacon_outcomes.jsonl", self._line(outcome))

    def checkpoint(self, state: Mapping[str, Any]) -> dict[str, Any]:
        sequence = state.get("state_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise NasGatewayError("Beacon state_sequence invalid")
        data = _canonical_bytes(state)
        digest = _sha256(data)
        relative = f"{self.gateway.write_prefix}/beacon_state_{sequence:012d}_{digest}.json"
        return self.gateway.create_new(relative, data)

    def load_latest_state(self) -> dict[str, Any] | None:
        rows = self.gateway.list_dir(self.gateway.write_prefix)
        candidates = [row["name"] for row in rows if row["kind"] == "REGULAR_FILE" and row["name"].startswith("beacon_state_") and row["name"].endswith(".json")]
        if not candidates:
            return None

        def sequence(name: str) -> int:
            parts = name.split("_", 3)
            if len(parts) < 4:
                return -1
            try:
                return int(parts[2])
            except ValueError:
                return -1

        latest = max(candidates, key=lambda name: (sequence(name), name))
        raw = self.gateway.read_bytes(f"{self.gateway.write_prefix}/{latest}")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NasGatewayError("latest Beacon state is invalid JSON") from exc
        if not isinstance(value, dict):
            raise NasGatewayError("latest Beacon state must be an object")
        return value
