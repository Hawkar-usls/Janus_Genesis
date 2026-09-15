# -*- coding: utf-8 -*-
"""Hardened canonical entrypoint for the Round-2.1 capability admission gate.

The canonical entrypoint binds admission to four immutable inputs:

* the Round-2.1 config;
* the frozen Round-1 sample pack;
* the frozen Round-2 critical projection; and
* the exact prior Round-2 report, stored as deterministic gzip bytes encoded
  in base64 for text-safe Git storage.

Every run reconstructs the prior report, verifies its encoded/gzip/raw
identities, derives every FP16_RAW PASS record again, and requires that derived
projection to equal the frozen critical reference exactly.  Candidate outcomes
therefore cannot create, delete, or reweight critical membership.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from tools import run_top100_round2_1_capability_admission as gate
from tools import run_top100_round1_stratified as r1


PROVENANCE_STATUS = "VERIFIED_AGAINST_ACTUAL_CONSUMED_BYTES"
DERIVATION_STATUS = "REPLAYED_FROM_FROZEN_ROUND2_RECEIPT"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROUND2_REPORT_SCHEMA = "janus.genesis.top100.round2_quantization_routing_report.v1"


def git_blob_sha1_bytes(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def git_blob_sha1(path: Path) -> str:
    return git_blob_sha1_bytes(path.read_bytes())


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repo_relative(path: Path) -> str:
    """Represent a consumed path relative to this repository, independent of cwd."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_cli_input_path(path: Path) -> Path:
    """Resolve repository-relative CLI input paths independently of process cwd."""
    if path.is_absolute():
        return path.resolve()
    if ".." in path.parts:
        raise ValueError("relative CLI input path must be repository-relative and non-traversing")
    resolved = (REPOSITORY_ROOT / path).resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError("relative CLI input path escapes repository root") from exc
    return resolved


def _source_path_from_config(config: dict[str, Any]) -> Path:
    declared = str(config.get("round2_source_report_encoded") or "")
    if not declared:
        raise ValueError("round2_source_report_encoded is required")
    declared_path = Path(declared)
    if declared_path.is_absolute() or ".." in declared_path.parts:
        raise ValueError("round2 source report path must be repository-relative and non-traversing")
    source_path = (REPOSITORY_ROOT / declared_path).resolve()
    if _repo_relative(source_path) != declared:
        raise ValueError("round2 source report path does not resolve to its declared repository identity")
    return source_path


def _decode_round2_source_report(
    config: dict[str, Any],
    critical: dict[str, Any],
    encoded_bytes: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if config.get("round2_source_report_encoding") != "base64_gzip_mtime0":
        raise ValueError("unsupported Round-2 source report encoding")

    observed_encoded_blob = git_blob_sha1_bytes(encoded_bytes)
    expected_encoded_blob = str(config.get("round2_source_report_encoded_git_blob_sha1") or "")
    if observed_encoded_blob != expected_encoded_blob:
        raise ValueError(
            f"Round-2 encoded source Git blob mismatch: {observed_encoded_blob} != {expected_encoded_blob}"
        )

    try:
        gzip_bytes = base64.b64decode(encoded_bytes, validate=True)
    except Exception as exc:  # binascii.Error varies by interpreter detail
        raise ValueError("Round-2 source base64 decode failed") from exc

    observed_gzip_sha256 = _sha256_bytes(gzip_bytes)
    expected_gzip_sha256 = str(config.get("round2_source_report_gzip_sha256") or "")
    if observed_gzip_sha256 != expected_gzip_sha256:
        raise ValueError(
            f"Round-2 source gzip SHA-256 mismatch: {observed_gzip_sha256} != {expected_gzip_sha256}"
        )

    try:
        raw_bytes = gzip.decompress(gzip_bytes)
    except Exception as exc:
        raise ValueError("Round-2 source gzip decompression failed") from exc

    observed_raw_sha256 = _sha256_bytes(raw_bytes)
    expected_raw_sha256 = str(config.get("round2_source_report_json_sha256") or "")
    if observed_raw_sha256 != expected_raw_sha256:
        raise ValueError(
            f"Round-2 report JSON SHA-256 mismatch: {observed_raw_sha256} != {expected_raw_sha256}"
        )
    critical_source = critical.get("source")
    if not isinstance(critical_source, dict):
        raise ValueError("critical reference source must be an object")
    if observed_raw_sha256 != str(critical_source.get("round2_report_json_sha256") or ""):
        raise ValueError("critical reference is not bound to the reconstructed Round-2 report")

    observed_raw_git_blob = git_blob_sha1_bytes(raw_bytes)
    expected_raw_git_blob = str(config.get("round2_source_report_raw_git_blob_sha1") or "")
    if observed_raw_git_blob != expected_raw_git_blob:
        raise ValueError(
            f"Round-2 report raw Git blob mismatch: {observed_raw_git_blob} != {expected_raw_git_blob}"
        )

    try:
        report = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Round-2 source report JSON parse failed") from exc
    if report.get("schema") != ROUND2_REPORT_SCHEMA:
        raise ValueError("Round-2 source report schema mismatch")

    return report, {
        "encoding": "base64_gzip_mtime0",
        "observed_encoded_git_blob_sha1": observed_encoded_blob,
        "observed_gzip_sha256": observed_gzip_sha256,
        "observed_report_json_sha256": observed_raw_sha256,
        "observed_report_raw_git_blob_sha1": observed_raw_git_blob,
        "raw_report_byte_count": len(raw_bytes),
        "identity_channels_verified": 4,
    }


def _derive_critical_projection(round2_report: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    records = round2_report.get("records")
    if not isinstance(records, list):
        raise ValueError("Round-2 source records must be a list")
    if len(records) != int(round2_report.get("execution_record_count", -1)):
        raise ValueError("Round-2 execution_record_count mismatch")

    fp16_rows = [row for row in records if row.get("config_id") == "FP16_RAW"]
    if len(fp16_rows) != 21:
        raise ValueError(f"Round-2 source must contain exactly 21 FP16_RAW records, got {len(fp16_rows)}")
    pass_rows = [row for row in fp16_rows if row.get("status") == "PASS"]

    projection = [
        {
            "sample_id": str(row["sample_id"]),
            "benchmark": row["benchmark"],
            "domain": row["domain"],
            "grader": row["grader"],
            "effective_input_sha256": row["effective_input_sha256"],
            "reference_output_sha256": row["output_sha256"],
            "reference_grader_detail": row["grader_detail"],
            "reference_status": "PASS",
        }
        for row in pass_rows
    ]
    projection.sort(key=lambda row: row["sample_id"])
    return projection, len(fp16_rows)


def validate_critical_derivation(
    config: dict[str, Any],
    critical: dict[str, Any],
    round2_report: dict[str, Any],
) -> dict[str, Any]:
    projection, fp16_count = _derive_critical_projection(round2_report)
    frozen_projection = critical.get("critical_set")
    if not isinstance(frozen_projection, list):
        raise ValueError("critical_set must be a list")

    summaries = round2_report.get("summaries")
    fp16_summary = summaries.get("FP16_RAW") if isinstance(summaries, dict) else None
    if not isinstance(fp16_summary, dict):
        raise ValueError("Round-2 FP16_RAW summary missing")
    if int(fp16_summary.get("samples", -1)) != fp16_count:
        raise ValueError("Round-2 FP16_RAW summary sample count mismatch")
    if int(fp16_summary.get("pass", -1)) != len(projection):
        raise ValueError("Round-2 FP16_RAW summary PASS count mismatch")

    source = critical["source"]
    model = round2_report.get("models", {}).get("FP16")
    if not isinstance(model, dict):
        raise ValueError("Round-2 FP16 model receipt missing")
    if model.get("tag") != source.get("reference_model_tag"):
        raise ValueError("Round-2 FP16 model tag mismatch against critical source")
    if model.get("digest") != source.get("reference_model_digest"):
        raise ValueError("Round-2 FP16 model digest mismatch against critical source")
    if round2_report.get("sample_pack_sha256") != source.get("round1_pack_canonical_sha256"):
        raise ValueError("Round-2 source report is not bound to the critical source Round-1 pack")

    expected_count = int(critical.get("source_fp16_pass_count", -1))
    if len(projection) != expected_count or len(projection) != int(critical.get("critical_set_count", -1)):
        raise ValueError("derived FP16 PASS count does not equal frozen critical count")
    if projection != frozen_projection:
        raise ValueError("derived FP16 PASS projection does not equal frozen critical_set")

    canonical_hash = r1.canonical_sha256(projection)
    if canonical_hash != critical.get("critical_set_canonical_sha256"):
        raise ValueError("derived critical projection canonical hash mismatch against critical reference")
    if canonical_hash != config.get("critical_set_canonical_sha256"):
        raise ValueError("derived critical projection canonical hash mismatch against config")

    return {
        "status": DERIVATION_STATUS,
        "source_selector": "config_id == FP16_RAW and status == PASS",
        "source_fp16_record_count": fp16_count,
        "derived_pass_count": len(projection),
        "derived_sample_ids": [row["sample_id"] for row in projection],
        "derived_canonical_sha256": canonical_hash,
        "equals_frozen_critical_projection": True,
        "candidate_results_consulted": False,
    }


def validate_provenance(
    config: dict[str, Any],
    critical: dict[str, Any],
    *,
    config_path: Path,
    critical_path: Path,
    pack_path: Path,
    source_path: Path | None = None,
    config_bytes: bytes | None = None,
    critical_bytes: bytes | None = None,
    pack_bytes: bytes | None = None,
    source_encoded_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Validate declarations against the exact byte snapshot used by execution."""
    if config_bytes is None:
        config_bytes = config_path.read_bytes()
    if critical_bytes is None:
        critical_bytes = critical_path.read_bytes()
    if pack_bytes is None:
        pack_bytes = pack_path.read_bytes()
    if source_path is None:
        source_path = _source_path_from_config(config)
    if source_encoded_bytes is None:
        source_encoded_bytes = source_path.read_bytes()

    observed_config_blob = git_blob_sha1_bytes(config_bytes)
    observed_pack_blob = git_blob_sha1_bytes(pack_bytes)
    observed_critical_blob = git_blob_sha1_bytes(critical_bytes)
    observed_source_blob = git_blob_sha1_bytes(source_encoded_bytes)
    observed_pack_path = _repo_relative(pack_path)
    observed_critical_path = _repo_relative(critical_path)
    observed_source_path = _repo_relative(source_path)

    declared_pack_path = str(config.get("round1_pack") or "")
    declared_critical_path = str(config.get("critical_reference") or "")
    declared_source_path = str(config.get("round2_source_report_encoded") or "")
    if declared_pack_path != observed_pack_path:
        raise ValueError(
            f"config round1_pack path mismatch: {declared_pack_path!r} != {observed_pack_path!r}"
        )
    if declared_critical_path != observed_critical_path:
        raise ValueError(
            f"config critical_reference path mismatch: {declared_critical_path!r} != {observed_critical_path!r}"
        )
    if declared_source_path != observed_source_path:
        raise ValueError(
            f"config Round-2 source path mismatch: {declared_source_path!r} != {observed_source_path!r}"
        )

    declared_pack_blob = str(config.get("round1_pack_git_blob_sha1") or "")
    declared_critical_blob = str(config.get("critical_reference_git_blob_sha1") or "")
    declared_source_blob = str(config.get("round2_source_report_encoded_git_blob_sha1") or "")
    if declared_pack_blob != observed_pack_blob:
        raise ValueError(
            f"config round1 pack blob mismatch: {declared_pack_blob} != {observed_pack_blob}"
        )
    if declared_critical_blob != observed_critical_blob:
        raise ValueError(
            f"config critical reference blob mismatch: {declared_critical_blob} != {observed_critical_blob}"
        )
    if declared_source_blob != observed_source_blob:
        raise ValueError(
            f"config Round-2 source blob mismatch: {declared_source_blob} != {observed_source_blob}"
        )

    source = critical.get("source")
    if not isinstance(source, dict):
        raise ValueError("critical reference source must be an object")
    source_pack_path = str(source.get("round1_pack_path") or "")
    source_pack_blob = str(source.get("round1_pack_git_blob_sha1") or "")
    if source_pack_path != declared_pack_path:
        raise ValueError(
            f"critical source round1 pack path mismatch: {source_pack_path!r} != {declared_pack_path!r}"
        )
    if source_pack_blob != observed_pack_blob:
        raise ValueError(
            f"critical source round1 pack blob mismatch: {source_pack_blob} != {observed_pack_blob}"
        )

    declared_critical_set_hash = str(config.get("critical_set_canonical_sha256") or "")
    source_critical_set_hash = str(critical.get("critical_set_canonical_sha256") or "")
    if declared_critical_set_hash != source_critical_set_hash:
        raise ValueError(
            "config and critical reference disagree on critical_set_canonical_sha256"
        )

    return {
        "status": PROVENANCE_STATUS,
        "repository_root": REPOSITORY_ROOT.as_posix(),
        "config_path": _repo_relative(config_path),
        "critical_reference_path": observed_critical_path,
        "round1_pack_path": observed_pack_path,
        "round2_source_report_encoded_path": observed_source_path,
        "observed_config_git_blob_sha1": observed_config_blob,
        "observed_critical_reference_git_blob_sha1": observed_critical_blob,
        "observed_round1_pack_git_blob_sha1": observed_pack_blob,
        "observed_round2_source_encoded_git_blob_sha1": observed_source_blob,
        "config_declared_critical_reference_git_blob_sha1": declared_critical_blob,
        "config_declared_round1_pack_git_blob_sha1": declared_pack_blob,
        "config_declared_round2_source_encoded_git_blob_sha1": declared_source_blob,
        "critical_source_round1_pack_git_blob_sha1": source_pack_blob,
        "critical_set_canonical_sha256": source_critical_set_hash,
        "receipt_fields_derived_from_verified_declarations": True,
        "single_snapshot_consumption": True,
        "verified_bytes_are_execution_bytes": True,
        "repository_root_independent_of_process_cwd": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--critical-reference", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--docker-image", default="python:3.11-alpine")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)

    # Resolve repository-relative CLI declarations against the repository root
    # before the single immutable read snapshot. Absolute inputs remain valid.
    config_path = _resolve_cli_input_path(args.config)
    critical_path = _resolve_cli_input_path(args.critical_reference)
    pack_path = _resolve_cli_input_path(args.pack)

    # One read per consumed repository input.  The exact same config/critical/
    # pack byte buffers are used for provenance and parsed execution objects.
    # The source receipt is also read once, then reconstructed entirely in-memory.
    config_bytes = config_path.read_bytes()
    critical_bytes = critical_path.read_bytes()
    pack_bytes = pack_path.read_bytes()

    config = json.loads(config_bytes.decode("utf-8"))
    critical = json.loads(critical_bytes.decode("utf-8"))
    pack = json.loads(pack_bytes.decode("utf-8"))

    source_path = _source_path_from_config(config)
    source_encoded_bytes = source_path.read_bytes()

    provenance = validate_provenance(
        config,
        critical,
        config_path=config_path,
        critical_path=critical_path,
        pack_path=pack_path,
        source_path=source_path,
        config_bytes=config_bytes,
        critical_bytes=critical_bytes,
        pack_bytes=pack_bytes,
        source_encoded_bytes=source_encoded_bytes,
    )
    round2_report, source_identity = _decode_round2_source_report(
        config, critical, source_encoded_bytes
    )
    derivation = validate_critical_derivation(config, critical, round2_report)

    report = gate.execute(
        config,
        critical,
        pack,
        endpoint=args.endpoint,
        docker_image=args.docker_image,
        timeout=args.timeout,
    )
    provenance["round2_source_identity"] = source_identity
    provenance["critical_set_derivation"] = derivation
    report["provenance_verification"] = provenance
    print(json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=args.pretty,
        indent=2 if args.pretty else None,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())