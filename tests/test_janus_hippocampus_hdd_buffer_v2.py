# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.janus_hippocampus_hdd_buffer import (
    JanusHippocampusBufferedJournal,
    MemoryBufferFullError,
    MemoryClosedError,
    MemoryPersistenceError,
)


class BufferedHippocampusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "nested" / "janus_cortex.db"
        self.memories: list[JanusHippocampusBufferedJournal] = []

    async def asyncTearDown(self) -> None:
        for memory in reversed(self.memories):
            if not memory._closed:  # test cleanup only
                try:
                    await memory.close()
                except MemoryPersistenceError:
                    pass
        self.tmp.cleanup()

    async def make_memory(self, **kwargs) -> JanusHippocampusBufferedJournal:
        memory = JanusHippocampusBufferedJournal(self.db, **kwargs)
        self.memories.append(memory)
        await memory.start()
        return memory

    def disk_rows(self) -> list[tuple]:
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(
                "SELECT id, source, content FROM thoughts ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

    async def wait_for_row_count(self, expected: int, timeout: float = 2.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self.db.exists() and len(self.disk_rows()) == expected:
                return
            await asyncio.sleep(0.01)
        self.assertEqual(len(self.disk_rows()), expected)

    async def stop_background_flusher(self, memory: JanusHippocampusBufferedJournal) -> None:
        memory._stop_event.set()
        memory._flush_event.set()
        if memory._flush_task is not None:
            await memory._flush_task
            memory._flush_task = None

    async def test_batch_threshold_wakes_background_flush(self) -> None:
        memory = await self.make_memory(batch_size=2, flush_interval_seconds=60)
        await memory.remember("USER", "alpha")
        self.assertEqual(self.disk_rows(), [])
        await memory.remember("JANUS", "beta")
        await self.wait_for_row_count(2)
        self.assertEqual([r[2] for r in self.disk_rows()], ["alpha", "beta"])

    async def test_periodic_flush_occurs_after_silence(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=0.05)
        await memory.remember("USER", "one quiet thought")
        await self.wait_for_row_count(1)

    async def test_force_save_persists_partial_batch(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        await memory.remember("USER", "force me")
        count = await memory.force_save()
        self.assertEqual(count, 1)
        self.assertEqual(self.disk_rows()[0][2], "force me")

    async def test_failed_flush_requeues_exact_batch_in_original_order(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        await memory.remember("USER", "first")
        await memory.remember("JANUS", "second")
        original = memory._write_batch_sync

        def fail_once(batch):
            raise OSError("synthetic disk outage")

        memory._write_batch_sync = fail_once  # type: ignore[method-assign]
        with self.assertRaises(MemoryPersistenceError):
            await memory.flush()
        self.assertEqual((await memory.stats())["buffered_records"], 2)
        self.assertEqual(self.disk_rows(), [])

        await memory.remember("USER", "third")
        memory._write_batch_sync = original  # type: ignore[method-assign]
        await memory.force_save()
        self.assertEqual(
            [row[2] for row in self.disk_rows()], ["first", "second", "third"]
        )

    async def test_concurrent_remember_has_no_loss_or_duplicate(self) -> None:
        memory = await self.make_memory(
            batch_size=500, flush_interval_seconds=60, max_buffer_records=1000
        )
        await asyncio.gather(
            *(memory.remember("USER", f"thought-{i:03d}") for i in range(200))
        )
        await memory.force_save()
        rows = self.disk_rows()
        self.assertEqual(len(rows), 200)
        self.assertEqual(len({row[2] for row in rows}), 200)

    async def test_buffer_overflow_fails_closed_instead_of_dropping_old_memory(self) -> None:
        memory = await self.make_memory(
            batch_size=3,
            flush_interval_seconds=60,
            max_buffer_records=3,
        )
        # Stop the timer deterministically. This test is about admission at the
        # RAM ceiling, not about whether a scheduler lets the flusher win first.
        await self.stop_background_flusher(memory)
        await memory.remember("USER", "a")
        await memory.remember("USER", "b")
        await memory.remember("USER", "c")
        with self.assertRaises(MemoryBufferFullError):
            await memory.remember("USER", "must-not-replace-a-b-c")
        self.assertEqual(
            [x.content for x in memory._buffer], ["a", "b", "c"]
        )

    async def test_unicode_recall_combines_ram_and_bounded_disk_without_duplicate(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        await memory.remember("USER", "Кот помнит порог")
        await memory.force_save()
        await memory.remember("JANUS", "КОТ охраняет новый порог")
        hits = await memory.recall("кот", limit=5)
        self.assertEqual([hit["origin"] for hit in hits], ["RAM", "HDD"])
        self.assertEqual(len(hits), 2)

    async def test_legacy_thoughts_schema_is_migrated_without_row_loss(self) -> None:
        self.db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "CREATE TABLE thoughts ("
                "id INTEGER PRIMARY KEY, timestamp TEXT, source TEXT, "
                "content TEXT, tags TEXT, vector BLOB)"
            )
            conn.execute(
                "INSERT INTO thoughts(timestamp, source, content, tags, vector) "
                "VALUES ('old-time', 'OLD', 'old memory', '[]', NULL)"
            )
            conn.commit()
        finally:
            conn.close()

        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        conn = sqlite3.connect(self.db)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(thoughts)")}
        finally:
            conn.close()
        self.assertIn("content_folded", columns)
        self.assertEqual(self.disk_rows()[0][2], "old memory")
        await memory.remember("NEW", "new memory")
        await memory.force_save()
        self.assertEqual([r[2] for r in self.disk_rows()], ["old memory", "new memory"])

    async def test_tag_alias_preserves_user_seed_api(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        await memory.remember(tag="JANUS-POWER", content={"state": "bounded"})
        await memory.force_save()
        row = self.disk_rows()[0]
        self.assertEqual(row[1], "JANUS-POWER")
        self.assertEqual(row[2], '{"state":"bounded"}')

    async def test_close_flushes_and_rejects_later_writes(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        await memory.remember("USER", "last before sleep")
        await memory.close()
        self.assertEqual(self.disk_rows()[0][2], "last before sleep")
        with self.assertRaises(MemoryClosedError):
            await memory.remember("USER", "too late")

    async def test_close_remember_race_cannot_append_after_final_flush(self) -> None:
        memory = await self.make_memory(batch_size=500, flush_interval_seconds=60)
        await memory._buffer_lock.acquire()
        try:
            remember_task = asyncio.create_task(memory.remember("USER", "racing thought"))
            await asyncio.sleep(0)
            close_task = asyncio.create_task(memory.close())
            await asyncio.sleep(0)
        finally:
            memory._buffer_lock.release()

        results = await asyncio.gather(remember_task, close_task, return_exceptions=True)
        remember_result = results[0]
        if isinstance(remember_result, MemoryClosedError):
            self.assertEqual(self.disk_rows(), [])
        else:
            self.assertIsNone(remember_result)
            self.assertEqual([r[2] for r in self.disk_rows()], ["racing thought"])
        self.assertEqual((await memory.stats())["buffered_records"], 0)

    async def test_normal_and_full_are_explicit_durability_modes(self) -> None:
        normal = await self.make_memory(
            batch_size=500, flush_interval_seconds=60, synchronous="NORMAL"
        )
        self.assertEqual((await normal.stats())["synchronous"], "NORMAL")
        await normal.close()

        second_db = Path(self.tmp.name) / "full.db"
        full = JanusHippocampusBufferedJournal(
            second_db, batch_size=500, flush_interval_seconds=60, synchronous="FULL"
        )
        self.memories.append(full)
        await full.start()
        self.assertEqual((await full.stats())["synchronous"], "FULL")
        with self.assertRaises(ValueError):
            JanusHippocampusBufferedJournal(second_db, synchronous="OFF")


if __name__ == "__main__":
    unittest.main()
