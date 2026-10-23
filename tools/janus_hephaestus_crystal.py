#!/usr/bin/env python3
"""JANUS Hephaestus Crystal v2.

A bounded, metadata-only filesystem analyzer descended from the historical
``hephaestus_crystal.py`` JANUS module dated 2026-01-24.

The historical module mixed three different concepts:

* Shannon entropy of the file-size distribution;
* filesystem tail-slack modelling;
* a fictional/simulated ``Quantum-P=NP / Perfect Fit`` ideal.

This revision deliberately separates them.  It does not read file contents,
measure extents, defragment data, execute a quantum algorithm, or claim a proof
about P versus NP.

Core laws:

    SIZE_DISTRIBUTION_ENTROPY != FILESYSTEM_FRAGMENTATION
    TAIL_SLACK_MODEL != OBSERVED_PHYSICAL_LAYOUT
    PERFECT_BYTE_STREAM_LOWER_BOUND != P_EQUALS_NP_PROOF
    SIMULATED_CONVERGENCE != COMPLEXITY_CLASS_PROOF
    HARDCODED_COUNTS != EXPERIMENTAL_EVIDENCE

The optional SQLite receipt is disabled by default and stores only the
privacy-safe report; file names and the scanned target path are never included
in the report payload.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import sqlite3
import stat
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping

logger = logging.getLogger("JANUS_HEPHAESTUS")

DEFAULT_MAX_FILES = 1_000_000
DEFAULT_MAX_DEPTH = 64
DEFAULT_FALLBACK_ALLOCATION_UNIT = 4096

HISTORICAL_LINEAGE = {
    "origin_date": "2026-01-24",
    "legacy_module": "hephaestus_crystal.py",
    "legacy_success_simulation": "quantum_success_sim.py",
    "legacy_label": "Quantum-P=NP / Perfect Fit",
    "legacy_claim_preserved": True,
    "legacy_claim_classification": "HISTORICAL_SIMULATION_CLAIM_ONLY",
    "p_equals_np_proven": False,
    "quantum_algorithm_executed_by_this_module": False,
}


class HephaestusError(RuntimeError):
    """Base fail-closed analyzer error."""


class UnsafeScanTargetError(HephaestusError):
    """The requested scan root is not an admitted concrete directory."""


class InvalidConfigurationError(HephaestusError):
    """Analyzer configuration is invalid."""


@dataclass(frozen=True)
class CrystalReport:
    schema: str
    status: str
    scan_complete: bool
    scan_truncated: bool
    file_count: int
    positive_size_file_count: int
    zero_size_file_count: int
    directory_count: int
    symlink_entries_skipped: int
    special_entries_skipped: int
    cross_device_entries_skipped: int
    inaccessible_entries: int
    logical_bytes: int
    size_distribution_entropy_bits: float
    allocation_unit_model_bytes: int
    allocation_unit_source: str
    modeled_tail_slack_bytes: int
    modeled_tail_slack_fraction_of_modeled_allocation: float
    observed_allocation_supported_file_count: int
    observed_logical_bytes_for_allocation_sample: int
    observed_allocated_bytes_namespace_sum: int
    observed_allocated_minus_logical_bytes: int
    hardlink_entries_observed: int
    theoretical_perfect_byte_stream_tail_slack_bytes: int
    modeled_tail_slack_recovery_upper_bound_bytes: int
    fragmentation_measured: bool
    extent_layout_measured: bool
    seek_locality_measured: bool
    p_equals_np_proven: bool
    quantum_algorithm_executed: bool
    verdict: str
    snapshot_atomic: bool
    report_sha256: str
    lineage: Mapping[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrystalOptimizer:
    """Bounded metadata-only filesystem analyzer.

    The implementation intentionally keeps aggregate counters rather than a
    list of file paths.  This makes the memory footprint bounded by traversal
    bookkeeping rather than by the number or names of files.
    """

    def __init__(
        self,
        target_path: str = "/app",
        *,
        allocation_unit_bytes: int | None = None,
        max_files: int = DEFAULT_MAX_FILES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        same_filesystem_only: bool = True,
    ) -> None:
        if not isinstance(target_path, str) or not target_path:
            raise InvalidConfigurationError("TARGET_PATH_REQUIRED")
        if type(max_files) is not int or max_files <= 0:
            raise InvalidConfigurationError("MAX_FILES_MUST_BE_POSITIVE_INT")
        if type(max_depth) is not int or max_depth < 0:
            raise InvalidConfigurationError("MAX_DEPTH_MUST_BE_NONNEGATIVE_INT")
        if allocation_unit_bytes is not None and (
            type(allocation_unit_bytes) is not int or allocation_unit_bytes <= 0
        ):
            raise InvalidConfigurationError("ALLOCATION_UNIT_MUST_BE_POSITIVE_INT")

        self.target_path = os.path.abspath(target_path)
        self._configured_allocation_unit = allocation_unit_bytes
        self.max_files = max_files
        self.max_depth = max_depth
        self.same_filesystem_only = bool(same_filesystem_only)
        self._reset()

    def _reset(self) -> None:
        self.file_count = 0
        self.positive_size_file_count = 0
        self.zero_size_file_count = 0
        self.directory_count = 0
        self.symlink_entries_skipped = 0
        self.special_entries_skipped = 0
        self.cross_device_entries_skipped = 0
        self.inaccessible_entries = 0
        self.logical_bytes = 0
        self._size_log2_weight_sum = 0.0
        self.modeled_tail_slack_bytes = 0
        self.observed_allocation_supported_file_count = 0
        self.observed_logical_bytes_for_allocation_sample = 0
        self.observed_allocated_bytes_namespace_sum = 0
        self.hardlink_entries_observed = 0
        self.scan_truncated = False
        self._allocation_unit_bytes = DEFAULT_FALLBACK_ALLOCATION_UNIT
        self._allocation_unit_source = "FALLBACK_MODEL_4096"
        self._scan_duration_seconds = 0.0

    def _validate_root(self) -> os.stat_result:
        try:
            root_stat = os.lstat(self.target_path)
        except OSError as exc:
            raise UnsafeScanTargetError("SCAN_ROOT_INACCESSIBLE") from exc
        if stat.S_ISLNK(root_stat.st_mode):
            raise UnsafeScanTargetError("SCAN_ROOT_SYMLINK_REJECTED")
        if not stat.S_ISDIR(root_stat.st_mode):
            raise UnsafeScanTargetError("SCAN_ROOT_NOT_DIRECTORY")
        return root_stat

    def _select_allocation_unit(self) -> None:
        if self._configured_allocation_unit is not None:
            self._allocation_unit_bytes = self._configured_allocation_unit
            self._allocation_unit_source = "EXPLICIT_MODEL_PARAMETER"
            return
        try:
            vfs = os.statvfs(self.target_path)
        except (AttributeError, OSError):
            return
        fragment = int(getattr(vfs, "f_frsize", 0) or 0)
        block = int(getattr(vfs, "f_bsize", 0) or 0)
        if fragment > 0:
            self._allocation_unit_bytes = fragment
            self._allocation_unit_source = "STATVFS_F_FRSIZE_MODEL_HINT"
        elif block > 0:
            self._allocation_unit_bytes = block
            self._allocation_unit_source = "STATVFS_F_BSIZE_MODEL_HINT"

    async def scan_filesystem(self) -> None:
        """Scan filesystem metadata in a worker thread.

        No regular-file content is opened or read.  Symlinks are not followed.
        The scan is not an atomic filesystem snapshot; concurrent modifications
        remain possible and are declared in the resulting report.
        """
        self._reset()
        start = time.monotonic()
        await asyncio.to_thread(self._sync_scan)
        self._scan_duration_seconds = max(0.0, time.monotonic() - start)

    def _sync_scan(self) -> None:
        root_stat = self._validate_root()
        root_device = root_stat.st_dev
        self._select_allocation_unit()
        stack: list[tuple[str, int]] = [(self.target_path, 0)]

        while stack:
            current, depth = stack.pop()
            try:
                iterator = os.scandir(current)
            except OSError:
                self.inaccessible_entries += 1
                continue

            try:
                with iterator:
                    for entry in iterator:
                        if self.file_count >= self.max_files:
                            self.scan_truncated = True
                            return
                        try:
                            entry_stat = entry.stat(follow_symlinks=False)
                        except OSError:
                            self.inaccessible_entries += 1
                            continue

                        mode = entry_stat.st_mode
                        if stat.S_ISLNK(mode):
                            self.symlink_entries_skipped += 1
                            continue

                        if self.same_filesystem_only and entry_stat.st_dev != root_device:
                            self.cross_device_entries_skipped += 1
                            continue

                        if stat.S_ISDIR(mode):
                            self.directory_count += 1
                            if depth < self.max_depth:
                                stack.append((entry.path, depth + 1))
                            else:
                                self.scan_truncated = True
                            continue

                        if not stat.S_ISREG(mode):
                            self.special_entries_skipped += 1
                            continue

                        self._observe_regular_file(entry_stat)
            except OSError:
                self.inaccessible_entries += 1

    def _observe_regular_file(self, file_stat: os.stat_result) -> None:
        size = max(0, int(file_stat.st_size))
        self.file_count += 1
        self.logical_bytes += size
        if size > 0:
            self.positive_size_file_count += 1
            self._size_log2_weight_sum += size * math.log2(size)
        else:
            self.zero_size_file_count += 1

        remainder = size % self._allocation_unit_bytes
        if remainder:
            self.modeled_tail_slack_bytes += self._allocation_unit_bytes - remainder

        blocks = getattr(file_stat, "st_blocks", None)
        if isinstance(blocks, int) and blocks >= 0:
            self.observed_allocation_supported_file_count += 1
            self.observed_logical_bytes_for_allocation_sample += size
            # POSIX st_blocks is expressed in 512-byte units.  This is observed
            # namespace allocation, not a unique-extent physical-space proof.
            self.observed_allocated_bytes_namespace_sum += blocks * 512

        if int(getattr(file_stat, "st_nlink", 1) or 1) > 1:
            self.hardlink_entries_observed += 1

    def calculate_size_distribution_entropy(self) -> float:
        """Shannon entropy of the byte-weighted file-size distribution.

        For positive file sizes s_i and total S:
            H = -sum((s_i/S) * log2(s_i/S))
              = log2(S) - sum(s_i*log2(s_i))/S

        This statistic says nothing by itself about extent fragmentation or seek
        locality.
        """
        if self.logical_bytes <= 0:
            return 0.0
        entropy = math.log2(self.logical_bytes) - (
            self._size_log2_weight_sum / self.logical_bytes
        )
        # Floating-point cancellation can produce a tiny negative value.
        return max(0.0, entropy)

    def build_report(self) -> CrystalReport:
        entropy = self.calculate_size_distribution_entropy()
        modeled_allocation = self.logical_bytes + self.modeled_tail_slack_bytes
        tail_fraction = (
            self.modeled_tail_slack_bytes / modeled_allocation
            if modeled_allocation > 0
            else 0.0
        )
        observed_delta = (
            self.observed_allocated_bytes_namespace_sum
            - self.observed_logical_bytes_for_allocation_sample
        )

        payload: dict[str, Any] = {
            "schema": "janus.hephaestus_crystal.v2",
            "status": "ANALYSIS_COMPLETE" if not self.scan_truncated else "ANALYSIS_TRUNCATED",
            "scan_complete": not self.scan_truncated,
            "scan_truncated": self.scan_truncated,
            "file_count": self.file_count,
            "positive_size_file_count": self.positive_size_file_count,
            "zero_size_file_count": self.zero_size_file_count,
            "directory_count": self.directory_count,
            "symlink_entries_skipped": self.symlink_entries_skipped,
            "special_entries_skipped": self.special_entries_skipped,
            "cross_device_entries_skipped": self.cross_device_entries_skipped,
            "inaccessible_entries": self.inaccessible_entries,
            "logical_bytes": self.logical_bytes,
            "size_distribution_entropy_bits": entropy,
            "allocation_unit_model_bytes": self._allocation_unit_bytes,
            "allocation_unit_source": self._allocation_unit_source,
            "modeled_tail_slack_bytes": self.modeled_tail_slack_bytes,
            "modeled_tail_slack_fraction_of_modeled_allocation": tail_fraction,
            "observed_allocation_supported_file_count": self.observed_allocation_supported_file_count,
            "observed_logical_bytes_for_allocation_sample": self.observed_logical_bytes_for_allocation_sample,
            "observed_allocated_bytes_namespace_sum": self.observed_allocated_bytes_namespace_sum,
            "observed_allocated_minus_logical_bytes": observed_delta,
            "hardlink_entries_observed": self.hardlink_entries_observed,
            "theoretical_perfect_byte_stream_tail_slack_bytes": 0,
            "modeled_tail_slack_recovery_upper_bound_bytes": self.modeled_tail_slack_bytes,
            "fragmentation_measured": False,
            "extent_layout_measured": False,
            "seek_locality_measured": False,
            "p_equals_np_proven": False,
            "quantum_algorithm_executed": False,
            "verdict": "MEASUREMENT_COMPLETE_FRAGMENTATION_NOT_MEASURED",
            "snapshot_atomic": False,
            "lineage": dict(HISTORICAL_LINEAGE),
        }
        digest_payload = dict(payload)
        canonical = json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        payload["report_sha256"] = hashlib.sha256(canonical).hexdigest()
        return CrystalReport(**payload)

    async def analyze(self) -> CrystalReport:
        await self.scan_filesystem()
        return self.build_report()


def _setting(settings: Any, key: str, default: Any) -> Any:
    if isinstance(settings, Mapping):
        return settings.get(key, default)
    getter = getattr(settings, "get", None)
    if callable(getter):
        return getter(key, default)
    return default


def _persist_report_sync(db_path: str, target_id: str, report: CrystalReport) -> None:
    payload = report.public_dict()
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS janus_hephaestus_reports_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                report_sha256 TEXT NOT NULL,
                file_count INTEGER NOT NULL,
                logical_bytes INTEGER NOT NULL,
                size_distribution_entropy_bits REAL NOT NULL,
                modeled_tail_slack_bytes INTEGER NOT NULL,
                fragmentation_measured INTEGER NOT NULL,
                p_equals_np_proven INTEGER NOT NULL,
                report_json TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            INSERT INTO janus_hephaestus_reports_v2
            (target_id, report_sha256, file_count, logical_bytes,
             size_distribution_entropy_bits, modeled_tail_slack_bytes,
             fragmentation_measured, p_equals_np_proven, report_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_id,
                report.report_sha256,
                report.file_count,
                report.logical_bytes,
                report.size_distribution_entropy_bits,
                report.modeled_tail_slack_bytes,
                int(report.fragmentation_measured),
                int(report.p_equals_np_proven),
                encoded,
            ),
        )
        db.commit()


async def persist_report(
    db_path: str,
    target_id: str,
    report: CrystalReport,
) -> None:
    """Persist a privacy-safe report after explicit caller admission."""
    if not isinstance(db_path, str) or not db_path:
        raise InvalidConfigurationError("DB_PATH_REQUIRED")
    if not isinstance(target_id, str) or not target_id:
        raise InvalidConfigurationError("TARGET_ID_REQUIRED")
    await asyncio.to_thread(_persist_report_sync, db_path, target_id, report)


async def run(core: Any) -> dict[str, Any]:
    """JANUS integration entry point.

    Analysis is metadata-only.  Local SQLite persistence is opt-in via
    ``hephaestus_persist_report=true``; it is never silently enabled.
    """
    settings = getattr(core, "settings", {})
    target = _setting(settings, "hephaestus_scan_target", "/app")
    allocation_unit = _setting(settings, "hephaestus_allocation_unit_bytes", None)
    max_files = _setting(settings, "hephaestus_max_files", DEFAULT_MAX_FILES)
    max_depth = _setting(settings, "hephaestus_max_depth", DEFAULT_MAX_DEPTH)
    same_fs = _setting(settings, "hephaestus_same_filesystem_only", True)

    analyzer = CrystalOptimizer(
        target,
        allocation_unit_bytes=allocation_unit,
        max_files=max_files,
        max_depth=max_depth,
        same_filesystem_only=same_fs,
    )
    report = await analyzer.analyze()

    persisted = False
    if _setting(settings, "hephaestus_persist_report", False) is True:
        db_path = _setting(settings, "hephaestus_db_path", "janus.db")
        target_id = _setting(settings, "hephaestus_target_id", "default")
        await persist_report(db_path, target_id, report)
        persisted = True

    logger.info(
        "Hephaestus Crystal v2 files=%d logical_bytes=%d entropy=%.6f "
        "modeled_tail_slack=%d fragmentation_measured=%s persisted=%s",
        report.file_count,
        report.logical_bytes,
        report.size_distribution_entropy_bits,
        report.modeled_tail_slack_bytes,
        report.fragmentation_measured,
        persisted,
    )
    return {
        "status": "success",
        "report": report.public_dict(),
        "persisted": persisted,
    }
