#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JANUS Storj-neighbor Cortex memory v1.

A bounded episodic/search persistence backend derived from the user's
``JanusTwoFacedBrain`` RAM-buffer + SQLite WAL concept.

This module is deliberately *not* canonical Genesis world/player state and is
not the Third-Wish provenance journal. It is an HDD-friendly cache/index layer:
RAM absorbs small bursts, SQLite receives ordered batch inserts, and recall can
search recent RAM plus durable rows without granting truth or command authority.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, Sequence


CORTEX_SCHEMA = "janus.cortex.memory.v1"
DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_BUFFER_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_RECORD_BYTES = 256 * 1024
DEFAULT_FLUSH_TIMEOUT = 300.0
DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_WAL_AUTOCHECKPOINT_PAGES = 2048
DEFAULT_JOURNAL_SIZE_LIMIT_BYTES = 64 * 1024 * 1024
DEFAULT_CACHE_SIZE_KIB = 8192
MAX_TAG_CHARS = 256
MAX_RECALL_LIMIT = 200


class CortexMemoryError(RuntimeError):
    """Base error for the bounded Cortex backend."""


class CortexConfigurationError(CortexMemoryError):
    pass


class CortexFlushError(CortexMemoryError):
    pass


class CortexClosedError(CortexMemoryError):
    pass


@dataclass(frozen=True)
class MemoryRow:
    timestamp: float
    iso_date: str
    tag: str
    content: str

    @property
    def payload_bytes(self) -> int:
        return len(self.tag.encode("utf-8")) + len(self.content.encode("utf-8"))


@dataclass(frozen=True)
class MemoryHit:
    source: Literal["RAM", "HDD"]
    timestamp: float
    iso_date: str
    tag: str
    content: str


@dataclass(frozen=True)
class FlushReceipt:
    rows: int
    elapsed_seconds: float
    reason: str


class JanusCortexMemory:
    """Async facade over an HDD-friendly SQLite/WAL episodic memory.

    Important semantics:
    - SQLite I/O is executed through ``asyncio.to_thread`` after construction.
    - the idle timer is real: buffered rows flush after ``flush_timeout`` even
      when no later ``remember`` call arrives;
    - a failed flush is requeued in front of newer RAM rows before the exception
      escapes, preserving data for retry;
    - count *and* byte ceilings bound ordinary RAM buffering;
    - shutdown never cancels an active SQLite worker; it wakes and joins the
      idle task before one serialized final flush/checkpoint;
    - this memory is observational/episodic only and has no canonical world or
      command authority.
    """

    def __init__(
        self,
        db_path: str | Path = "janus_data/janus_cortex.db",
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES,
        max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
        flush_timeout: float = DEFAULT_FLUSH_TIMEOUT,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        synchronous: Literal["NORMAL", "FULL"] = "NORMAL",
        wal_autocheckpoint_pages: int = DEFAULT_WAL_AUTOCHECKPOINT_PAGES,
        journal_size_limit_bytes: int = DEFAULT_JOURNAL_SIZE_LIMIT_BYTES,
        cache_size_kib: int = DEFAULT_CACHE_SIZE_KIB,
        enable_fts: bool | Literal["auto"] = "auto",
        storj_roots: Iterable[str | Path] = (),
    ) -> None:
        self.db_path = Path(db_path).expanduser().absolute()
        self.batch_size = self._positive_int("batch_size", batch_size)
        self.max_buffer_bytes = self._positive_int(
            "max_buffer_bytes", max_buffer_bytes
        )
        self.max_record_bytes = self._positive_int(
            "max_record_bytes", max_record_bytes
        )
        self.flush_timeout = self._positive_float("flush_timeout", flush_timeout)
        self.busy_timeout_ms = self._positive_int(
            "busy_timeout_ms", busy_timeout_ms
        )
        if synchronous not in {"NORMAL", "FULL"}:
            raise CortexConfigurationError("synchronous must be NORMAL or FULL")
        self.synchronous = synchronous
        self.wal_autocheckpoint_pages = self._positive_int(
            "wal_autocheckpoint_pages", wal_autocheckpoint_pages
        )
        self.journal_size_limit_bytes = self._positive_int(
            "journal_size_limit_bytes", journal_size_limit_bytes
        )
        self.cache_size_kib = self._positive_int("cache_size_kib", cache_size_kib)
        if enable_fts not in {True, False, "auto"}:
            raise CortexConfigurationError("enable_fts must be true, false, or auto")
        self.enable_fts = enable_fts
        self._assert_not_inside_storj_roots(storj_roots)

        self._buffer: list[MemoryRow] = []
        self._buffer_bytes = 0
        self._buffer_lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._idle_task: asyncio.Task[None] | None = None
        self._idle_wakeup = asyncio.Event()
        self._last_append_monotonic = time.monotonic()
        self._last_flush_monotonic = time.monotonic()
        self._closing = False
        self._closed = False
        self._last_flush_error: str | None = None

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_enabled = self._init_db()

    @staticmethod
    def _positive_int(name: str, value: int) -> int:
        value = int(value)
        if value <= 0:
            raise CortexConfigurationError(f"{name} must be > 0")
        return value

    @staticmethod
    def _positive_float(name: str, value: float) -> float:
        value = float(value)
        if value <= 0:
            raise CortexConfigurationError(f"{name} must be > 0")
        return value

    def _assert_not_inside_storj_roots(
        self, storj_roots: Iterable[str | Path]
    ) -> None:
        """Reject placing the active SQLite files inside a Storj-managed tree.

        Sharing one physical disk is allowed. What is rejected is putting the
        live DB *inside* a directory that Storj itself owns/manages.
        """
        db = self.db_path.resolve(strict=False)
        for root_raw in storj_roots:
            root = Path(root_raw).expanduser().absolute().resolve(strict=False)
            try:
                db.relative_to(root)
            except ValueError:
                continue
            raise CortexConfigurationError(
                "active Cortex DB must not be inside a Storj-managed storage root"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000.0,
        )
        conn.execute(f"PRAGMA synchronous={self.synchronous}")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        conn.execute(f"PRAGMA wal_autocheckpoint={self.wal_autocheckpoint_pages}")
        conn.execute(f"PRAGMA journal_size_limit={self.journal_size_limit_bytes}")
        conn.execute(f"PRAGMA cache_size={-self.cache_size_kib}")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def _init_db(self) -> bool:
        with sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000.0,
        ) as conn:
            mode = str(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
            if mode != "wal":
                raise CortexConfigurationError(
                    f"SQLite WAL unavailable for Cortex DB: journal_mode={mode}"
                )
            conn.execute(f"PRAGMA synchronous={self.synchronous}")
            conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            conn.execute(
                f"PRAGMA wal_autocheckpoint={self.wal_autocheckpoint_pages}"
            )
            conn.execute(
                f"PRAGMA journal_size_limit={self.journal_size_limit_bytes}"
            )
            conn.execute(f"PRAGMA cache_size={-self.cache_size_kib}")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    iso_date TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_tag ON memories(tag)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_timestamp "
                "ON memories(timestamp DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cortex_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO cortex_meta(key, value) VALUES (?, ?)",
                ("schema", CORTEX_SCHEMA),
            )
            fts_enabled = self._init_fts(conn)
            conn.execute(
                "INSERT OR REPLACE INTO cortex_meta(key, value) VALUES (?, ?)",
                ("fts_enabled", "1" if fts_enabled else "0"),
            )
            conn.commit()
            return fts_enabled

    def _init_fts(self, conn: sqlite3.Connection) -> bool:
        if self.enable_fts is False:
            return False
        existed = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='memories_fts' LIMIT 1"
            ).fetchone()
            is not None
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content,
                    tag,
                    content='memories',
                    content_rowid='id',
                    tokenize='unicode61'
                )
                """
            )
            conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, tag)
                    VALUES (new.id, new.content, new.tag);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tag)
                    VALUES ('delete', old.id, old.content, old.tag);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tag)
                    VALUES ('delete', old.id, old.content, old.tag);
                    INSERT INTO memories_fts(rowid, content, tag)
                    VALUES (new.id, new.content, new.tag);
                END;
                """
            )
            if not existed:
                conn.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
            return True
        except sqlite3.OperationalError:
            if self.enable_fts is True:
                raise CortexConfigurationError("SQLite FTS5 was explicitly required")
            return False

    @property
    def buffered_rows(self) -> int:
        return len(self._buffer)

    @property
    def buffered_bytes(self) -> int:
        return self._buffer_bytes

    @property
    def last_flush_error(self) -> str | None:
        return self._last_flush_error

    def _validate_memory(self, tag: str, content: str) -> MemoryRow:
        if not isinstance(tag, str) or not tag.strip():
            raise CortexMemoryError("tag must be a non-empty string")
        if len(tag) > MAX_TAG_CHARS:
            raise CortexMemoryError(f"tag exceeds {MAX_TAG_CHARS} characters")
        if not isinstance(content, str) or not content:
            raise CortexMemoryError("content must be a non-empty string")
        payload_bytes = len(tag.encode("utf-8")) + len(content.encode("utf-8"))
        if payload_bytes > self.max_record_bytes:
            raise CortexMemoryError(
                f"memory record exceeds max_record_bytes={self.max_record_bytes}"
            )
        now = datetime.now(timezone.utc)
        return MemoryRow(
            timestamp=now.timestamp(),
            iso_date=now.isoformat(),
            tag=tag,
            content=content,
        )

    def _require_open_for_write(self) -> None:
        if self._closing or self._closed:
            raise CortexClosedError("Cortex memory is closing or closed")

    async def remember(self, tag: str, content: str) -> None:
        """Append one episodic row to RAM and flush when a bound is reached."""
        self._require_open_for_write()
        row = self._validate_memory(tag, content)
        should_flush = False
        async with self._buffer_lock:
            self._require_open_for_write()
            self._buffer.append(row)
            self._buffer_bytes += row.payload_bytes
            self._last_append_monotonic = time.monotonic()
            self._idle_wakeup.set()
            self._ensure_idle_task_locked()
            should_flush = (
                len(self._buffer) >= self.batch_size
                or self._buffer_bytes >= self.max_buffer_bytes
            )
        if should_flush:
            await self.flush(reason="buffer-bound")

    def _ensure_idle_task_locked(self) -> None:
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.create_task(
                self._idle_flush_loop(),
                name="janus-cortex-idle-flush",
            )

    async def _wait_for_idle_wakeup(self, timeout: float) -> bool:
        """Return True when explicitly woken, False when the deadline expires."""
        if timeout <= 0:
            return False
        try:
            await asyncio.wait_for(self._idle_wakeup.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def _idle_flush_loop(self) -> None:
        while True:
            async with self._buffer_lock:
                if self._closing or self._closed or not self._buffer:
                    return
                deadline = self._last_append_monotonic + self.flush_timeout
                self._idle_wakeup.clear()

            delay = max(0.0, deadline - time.monotonic())
            if await self._wait_for_idle_wakeup(delay):
                continue

            async with self._buffer_lock:
                if self._closing or self._closed or not self._buffer:
                    return
                idle_for = time.monotonic() - self._last_append_monotonic
            if idle_for < self.flush_timeout:
                continue

            try:
                await self.flush(reason="idle-timeout")
            except CortexFlushError:
                # The failed batch is already restored to RAM. Wait for either
                # a close/new-memory wakeup or one retry interval.
                async with self._buffer_lock:
                    if self._closing or self._closed:
                        return
                    self._idle_wakeup.clear()
                await self._wait_for_idle_wakeup(self.flush_timeout)

    async def flush(self, *, reason: str = "explicit") -> FlushReceipt:
        """Serialize one disk flush without holding the RAM lock during I/O."""
        async with self._flush_lock:
            async with self._buffer_lock:
                if not self._buffer:
                    return FlushReceipt(rows=0, elapsed_seconds=0.0, reason=reason)
                batch = self._buffer
                batch_bytes = self._buffer_bytes
                self._buffer = []
                self._buffer_bytes = 0

            started = time.monotonic()
            try:
                await asyncio.to_thread(self._persist_batch_sync, batch)
            except Exception as exc:
                async with self._buffer_lock:
                    self._buffer = batch + self._buffer
                    self._buffer_bytes = batch_bytes + self._buffer_bytes
                self._last_flush_error = f"{type(exc).__name__}: {exc}"
                raise CortexFlushError(
                    "Cortex batch flush failed; rows retained in RAM"
                ) from exc

            elapsed = time.monotonic() - started
            self._last_flush_monotonic = time.monotonic()
            self._last_flush_error = None
            return FlushReceipt(rows=len(batch), elapsed_seconds=elapsed, reason=reason)

    def _persist_batch_sync(self, batch: Sequence[MemoryRow]) -> None:
        rows = [
            (row.timestamp, row.iso_date, row.tag, row.content)
            for row in batch
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO memories(timestamp, iso_date, tag, content) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    async def force_save(self) -> FlushReceipt:
        """Durably flush all currently buffered rows."""
        return await self.flush(reason="force-save")

    async def checkpoint(
        self, mode: Literal["PASSIVE", "FULL"] = "PASSIVE"
    ) -> tuple[int, int, int]:
        """Request an explicit WAL checkpoint; not performed after every batch."""
        if mode not in {"PASSIVE", "FULL"}:
            raise CortexMemoryError("checkpoint mode must be PASSIVE or FULL")
        return await asyncio.to_thread(self._checkpoint_sync, mode)

    def _checkpoint_sync(self, mode: str) -> tuple[int, int, int]:
        with self._connect() as conn:
            row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    @staticmethod
    def _literal_like_pattern(keyword: str) -> str:
        escaped = (
            keyword.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        return f"%{escaped}%"

    @staticmethod
    def _fts_literal_query(keyword: str) -> str:
        return '"' + keyword.replace('"', '""') + '"'

    def _search_disk_sync(self, keyword: str, limit: int) -> list[MemoryHit]:
        with self._connect() as conn:
            if self.fts_enabled:
                rows = conn.execute(
                    """
                    SELECT m.timestamp, m.iso_date, m.tag, m.content
                    FROM memories_fts AS f
                    JOIN memories AS m ON m.id = f.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY m.id DESC
                    LIMIT ?
                    """,
                    (self._fts_literal_query(keyword), limit),
                ).fetchall()
            else:
                pattern = self._literal_like_pattern(keyword)
                rows = conn.execute(
                    """
                    SELECT timestamp, iso_date, tag, content
                    FROM memories
                    WHERE content LIKE ? ESCAPE '\\' COLLATE NOCASE
                       OR tag LIKE ? ESCAPE '\\' COLLATE NOCASE
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, limit),
                ).fetchall()
        return [
            MemoryHit(
                source="HDD",
                timestamp=float(row[0]),
                iso_date=str(row[1]),
                tag=str(row[2]),
                content=str(row[3]),
            )
            for row in rows
        ]

    async def recall_hits(self, keyword: str, limit: int = 5) -> list[MemoryHit]:
        """Search RAM + SQLite and enforce one global newest-first result limit."""
        if not isinstance(keyword, str) or not keyword:
            raise CortexMemoryError("keyword must be a non-empty string")
        limit = max(1, min(MAX_RECALL_LIMIT, int(limit)))
        folded = keyword.casefold()
        async with self._buffer_lock:
            ram = [
                MemoryHit(
                    source="RAM",
                    timestamp=row.timestamp,
                    iso_date=row.iso_date,
                    tag=row.tag,
                    content=row.content,
                )
                for row in self._buffer
                if folded in row.content.casefold() or folded in row.tag.casefold()
            ]
        disk = await asyncio.to_thread(self._search_disk_sync, keyword, limit * 2)
        merged = sorted(ram + disk, key=lambda item: item.timestamp, reverse=True)
        seen: set[tuple[str, str, str]] = set()
        results: list[MemoryHit] = []
        for hit in merged:
            key = (hit.iso_date, hit.tag, hit.content)
            if key in seen:
                continue
            seen.add(key)
            results.append(hit)
            if len(results) >= limit:
                break
        return results

    async def recall(self, keyword: str, limit: int = 5) -> list[str]:
        """Compatibility output matching the original JanusTwoFacedBrain style."""
        hits = await self.recall_hits(keyword, limit=limit)
        return [f"[{hit.source}] {hit.content}" for hit in hits]

    async def count_durable_rows(self) -> int:
        return await asyncio.to_thread(self._count_durable_rows_sync)

    def _count_durable_rows_sync(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0])

    async def close(self) -> FlushReceipt:
        """Wake/join the idle task, flush RAM, then checkpoint without cancellation."""
        async with self._close_lock:
            if self._closed:
                return FlushReceipt(
                    rows=0,
                    elapsed_seconds=0.0,
                    reason="already-closed",
                )

            async with self._buffer_lock:
                self._closing = True
                self._idle_wakeup.set()
            idle = self._idle_task
            if idle is not None and idle is not asyncio.current_task() and not idle.done():
                await idle

            try:
                receipt = await self.flush(reason="close")
                await self.checkpoint("PASSIVE")
            except Exception:
                # A failed close is retryable. Flush already restores failed
                # batches to RAM, so reopen lifecycle admission and restart the
                # idle timer if there is data to protect.
                async with self._buffer_lock:
                    self._closing = False
                    self._idle_wakeup.set()
                    if self._buffer:
                        self._ensure_idle_task_locked()
                raise

            async with self._buffer_lock:
                self._closed = True
                self._closing = False
                self._idle_wakeup.set()
            return receipt

    async def __aenter__(self) -> "JanusCortexMemory":
        if self._closed:
            raise CortexClosedError("Cortex memory is closed")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


class JanusTwoFacedBrain(JanusCortexMemory):
    """Backward-compatible name for the user's original two-faced memory idea."""


CORTEX_MEMORY_CLAIMS = {
    "schema": CORTEX_SCHEMA,
    "ram_buffered": True,
    "sqlite_wal": True,
    "real_idle_timeout_flush": True,
    "sqlite_io_runs_outside_event_loop_after_init": True,
    "failed_batch_retained_for_retry": True,
    "buffer_bounded_by_count_and_payload_bytes": True,
    "failed_flush_may_temporarily_exceed_ordinary_ram_bound_to_preserve_rows": True,
    "utc_timestamps": True,
    "fts5_optional_with_literal_like_fallback": True,
    "shutdown_cancels_active_sqlite_worker": False,
    "shutdown_waits_for_active_flush": True,
    "failed_close_is_retryable": True,
    "active_db_inside_storj_managed_root_allowed": False,
    "same_physical_disk_as_storj_forbidden": False,
    "canonical_world_authority": False,
    "canonical_player_authority": False,
    "third_wish_provenance_authority": False,
    "recall_result_is_truth": False,
    "memory_row_is_command": False,
    "network_access": False,
}
