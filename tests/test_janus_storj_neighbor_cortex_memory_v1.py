from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from janus_storj_neighbor_cortex_memory import (  # noqa: E402
    CortexClosedError,
    CortexConfigurationError,
    CortexFlushError,
    CortexMemoryError,
    JanusCortexMemory,
    JanusTwoFacedBrain,
)


class JanusStorjNeighborCortexMemoryTests(unittest.IsolatedAsyncioTestCase):
    def make_memory(self, root: Path, **kwargs) -> JanusCortexMemory:
        options = {
            "db_path": root / "janus_data" / "janus_cortex.db",
            "batch_size": 500,
            "max_buffer_bytes": 1024 * 1024,
            "max_record_bytes": 64 * 1024,
            "flush_timeout": 10.0,
            "enable_fts": False,
        }
        options.update(kwargs)
        return JanusCortexMemory(**options)

    async def test_compatibility_name_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            brain = JanusTwoFacedBrain(
                Path(directory) / "cortex.db",
                enable_fts=False,
            )
            self.assertIsInstance(brain, JanusCortexMemory)
            await brain.close()

    async def test_db_parent_created_and_wal_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = self.make_memory(root)
            self.assertTrue(memory.db_path.parent.is_dir())
            with sqlite3.connect(memory.db_path) as conn:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                indexes = {
                    row[1]
                    for row in conn.execute("PRAGMA index_list('memories')").fetchall()
                }
            self.assertEqual(str(mode).lower(), "wal")
            self.assertIn("idx_memories_tag", indexes)
            self.assertIn("idx_memories_timestamp", indexes)
            self.assertNotIn("idx_content", indexes)
            await memory.close()

    async def test_batch_count_bound_flushes(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), batch_size=3)
            await memory.remember("alpha", "one")
            await memory.remember("alpha", "two")
            self.assertEqual(await memory.count_durable_rows(), 0)
            await memory.remember("alpha", "three")
            self.assertEqual(memory.buffered_rows, 0)
            self.assertEqual(await memory.count_durable_rows(), 3)
            await memory.close()

    async def test_byte_bound_flushes_before_count_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(
                Path(directory),
                batch_size=500,
                max_buffer_bytes=20,
                max_record_bytes=1024,
            )
            await memory.remember("t", "x" * 25)
            self.assertEqual(await memory.count_durable_rows(), 1)
            self.assertEqual(memory.buffered_rows, 0)
            await memory.close()

    async def test_idle_timeout_flushes_without_another_remember(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), flush_timeout=0.05)
            await memory.remember("idle", "flush me without a second remember")
            self.assertEqual(await memory.count_durable_rows(), 0)
            await asyncio.sleep(0.18)
            self.assertEqual(await memory.count_durable_rows(), 1)
            self.assertEqual(memory.buffered_rows, 0)
            await memory.close()

    async def test_new_remember_resets_idle_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), flush_timeout=0.08)
            await memory.remember("idle", "first")
            await asyncio.sleep(0.05)
            await memory.remember("idle", "second resets deadline")
            await asyncio.sleep(0.045)
            self.assertEqual(await memory.count_durable_rows(), 0)
            await asyncio.sleep(0.08)
            self.assertEqual(await memory.count_durable_rows(), 2)
            await memory.close()

    async def test_flush_disk_io_does_not_block_event_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), batch_size=1)
            original = memory._persist_batch_sync

            def slow_persist(batch):
                time.sleep(0.12)
                original(batch)

            memory._persist_batch_sync = slow_persist  # type: ignore[method-assign]
            ticks = 0

            async def ticker():
                nonlocal ticks
                stop = asyncio.get_running_loop().time() + 0.10
                while asyncio.get_running_loop().time() < stop:
                    ticks += 1
                    await asyncio.sleep(0.01)

            await asyncio.gather(memory.remember("thread", "disk is slow"), ticker())
            self.assertGreaterEqual(ticks, 5)
            self.assertEqual(await memory.count_durable_rows(), 1)
            await memory.close()

    async def test_failed_flush_requeues_rows_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), batch_size=1)
            original = memory._persist_batch_sync
            calls = 0

            def fail_once(batch):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise sqlite3.OperationalError("synthetic disk failure")
                original(batch)

            memory._persist_batch_sync = fail_once  # type: ignore[method-assign]
            with self.assertRaises(CortexFlushError):
                await memory.remember("retry", "must survive failed disk flush")
            self.assertEqual(memory.buffered_rows, 1)
            self.assertIn("OperationalError", memory.last_flush_error or "")
            receipt = await memory.force_save()
            self.assertEqual(receipt.rows, 1)
            self.assertEqual(memory.buffered_rows, 0)
            self.assertIsNone(memory.last_flush_error)
            self.assertEqual(await memory.count_durable_rows(), 1)
            await memory.close()

    async def test_close_waits_for_active_idle_disk_worker_without_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), flush_timeout=0.03)
            original = memory._persist_batch_sync
            started = threading.Event()
            release = threading.Event()

            def blocked_persist(batch):
                started.set()
                if not release.wait(2.0):
                    raise RuntimeError("test did not release disk worker")
                original(batch)

            memory._persist_batch_sync = blocked_persist  # type: ignore[method-assign]
            await memory.remember("shutdown-race", "exactly once")
            self.assertTrue(await asyncio.to_thread(started.wait, 1.0))

            close_task = asyncio.create_task(memory.close())
            await asyncio.sleep(0.04)
            self.assertFalse(
                close_task.done(),
                "close must join an active SQLite worker instead of cancelling it",
            )
            release.set()
            receipt = await asyncio.wait_for(close_task, timeout=2.0)
            self.assertEqual(receipt.rows, 0)
            self.assertEqual(memory.buffered_rows, 0)
            self.assertEqual(await memory.count_durable_rows(), 1)

    async def test_failed_close_is_retryable_and_retains_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), flush_timeout=10.0)
            original = memory._persist_batch_sync
            calls = 0

            def fail_once(batch):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise sqlite3.OperationalError("synthetic close failure")
                original(batch)

            memory._persist_batch_sync = fail_once  # type: ignore[method-assign]
            await memory.remember("close-retry", "must remain after failed close")
            with self.assertRaises(CortexFlushError):
                await memory.close()
            self.assertEqual(memory.buffered_rows, 1)
            self.assertFalse(memory._closed)
            self.assertFalse(memory._closing)
            receipt = await memory.close()
            self.assertEqual(receipt.rows, 1)
            self.assertEqual(await memory.count_durable_rows(), 1)

    async def test_recall_combines_ram_and_hdd_with_one_global_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), batch_size=3)
            await memory.remember("story", "Janus durable first")
            await asyncio.sleep(0.002)
            await memory.remember("story", "Janus durable second")
            await asyncio.sleep(0.002)
            await memory.remember("story", "Janus durable third")
            await asyncio.sleep(0.002)
            await memory.remember("story", "Janus RAM fourth")
            await asyncio.sleep(0.002)
            await memory.remember("story", "Janus RAM fifth")

            hits = await memory.recall_hits("Janus", limit=3)
            self.assertEqual(len(hits), 3)
            self.assertEqual(
                [hit.content for hit in hits[:2]],
                ["Janus RAM fifth", "Janus RAM fourth"],
            )
            self.assertEqual(hits[2].content, "Janus durable third")
            self.assertEqual([hit.source for hit in hits], ["RAM", "RAM", "HDD"])
            formatted = await memory.recall("Janus", limit=2)
            self.assertEqual(len(formatted), 2)
            self.assertTrue(formatted[0].startswith("[RAM]"))
            await memory.close()

    async def test_like_fallback_treats_percent_and_underscore_literally(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), batch_size=1, enable_fts=False)
            await memory.remember("literal", "marker 100%_real")
            await memory.remember("literal", "marker 100Xreal")
            hits = await memory.recall_hits("%_", limit=10)
            self.assertEqual([hit.content for hit in hits], ["marker 100%_real"])
            await memory.close()

    async def test_timestamp_is_utc_aware(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory))
            await memory.remember("utc", "timestamp")
            self.assertEqual(memory.buffered_rows, 1)
            self.assertTrue(memory._buffer[0].iso_date.endswith("+00:00"))
            await memory.close()

    async def test_record_size_is_bounded_before_ram_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory), max_record_bytes=32)
            with self.assertRaises(CortexMemoryError):
                await memory.remember("tag", "x" * 100)
            self.assertEqual(memory.buffered_rows, 0)
            self.assertEqual(await memory.count_durable_rows(), 0)
            await memory.close()

    async def test_active_db_inside_storj_root_is_rejected_but_sibling_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storj = root / "storj-storage"
            storj.mkdir()
            with self.assertRaises(CortexConfigurationError):
                JanusCortexMemory(
                    storj / "janus_cortex.db",
                    storj_roots=[storj],
                    enable_fts=False,
                )
            memory = JanusCortexMemory(
                root / "janus-data" / "janus_cortex.db",
                storj_roots=[storj],
                enable_fts=False,
            )
            await memory.close()

    async def test_close_flushes_buffer_and_prevents_new_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = self.make_memory(Path(directory))
            await memory.remember("shutdown", "save me")
            receipt = await memory.close()
            self.assertEqual(receipt.rows, 1)
            self.assertEqual(await memory.count_durable_rows(), 1)
            with self.assertRaises(CortexClosedError):
                await memory.remember("shutdown", "too late")
            second = await memory.close()
            self.assertEqual(second.rows, 0)

    async def test_fts5_auto_mode_is_optional_and_recall_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = JanusCortexMemory(
                Path(directory) / "fts" / "cortex.db",
                batch_size=1,
                enable_fts="auto",
            )
            await memory.remember("oracle", "black cat remembers the threshold")
            hits = await memory.recall_hits("black cat", limit=5)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].content, "black cat remembers the threshold")
            await memory.close()


if __name__ == "__main__":
    unittest.main()
