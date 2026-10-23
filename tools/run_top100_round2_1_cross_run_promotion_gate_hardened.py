# -*- coding: utf-8 -*-
"""Authenticated canonical entrypoint for the Round-2.1 cross-run promotion gate.

The lower-level cross-run evaluator reconstructs exact admission reports and
rederives compact evidence. This wrapper adds promotion-critical trust
boundaries before that evaluator may count receipts:

1. candidate trial keys must equal the frozen CriticalFrozenSet x replay range;
2. workflow-run and artifact identities are authenticated against live GitHub;
3. the exact downloaded artifact ZIP and its report.json bytes are bound to the
   frozen source-report SHA-256 and raw Git-blob identity;
4. repeated source identities are rejected.

The canonical CLI is live-authentication-only. Test fixtures can call helper
functions directly, but there is deliberately no CLI option that accepts local
GitHub metadata as authoritative evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from tools import run_top100_round2_1_cross_run_promotion_gate as core

EXPECTED_REPOSITORY = "Hawkar-usls/Janus_Genesis"
HARDENED_SCHEMA = "janus.genesis.top100.round2_1_cross_run_promotion_hardened_receipt.v1"
LIVE_AUTHENTICATION_MODE = "LIVE_GITHUB_ACTIONS_WITH_ARTIFACT_BYTES"
FIXTURE_AUTHENTICATION_MODE = "CALLER_SUPPLIED_TEST_FIXTURE_NON_AUTHORITATIVE"


def _repo_path(declared: str) -> Path:
    path = Path(declared)
    if not declared or path.is_absolute() or ".." in path.parts:
        raise ValueError("critical reference path must be repository-relative and non-traversing")
    resolved = (core.REPOSITORY_ROOT / path).resolve()
    try:
        observed = resolved.relative_to(core.REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("critical reference path escapes repository root") from exc
    if observed != declared:
        raise ValueError("critical reference path identity mismatch")
    return resolved


def load_frozen_critical_profile(config: dict[str, Any]) -> dict[str, Any]:
    evidence, _ = core.load_evidence(config)
    spec = evidence.get("experimental_spec")
    if not isinstance(spec, dict):
        raise ValueError("experimental spec missing from cross-run evidence")
    critical_decl = spec.get("critical_reference")
    inference = spec.get("inference")
    if not isinstance(critical_decl, dict) or not isinstance(inference, dict):
        raise ValueError("experimental spec missing critical/inference declarations")

    declared_path = str(critical_decl.get("path") or "")
    path = _repo_path(declared_path)
    raw = path.read_bytes()
    observed_blob = core.git_blob_sha1_bytes(raw)
    if observed_blob != critical_decl.get("git_blob_sha1"):
        raise ValueError("frozen critical reference Git blob mismatch")
    critical = json.loads(raw.decode("utf-8"))
    frozen_rows = critical.get("critical_set")
    if not isinstance(frozen_rows, list):
        raise ValueError("frozen critical_set must be a list")
    if len(frozen_rows) != int(critical_decl.get("critical_set_count", -1)):
        raise ValueError("frozen critical count disagrees with experimental spec")
    observed_hash = core.canonical_sha256(frozen_rows)
    if observed_hash != critical_decl.get("critical_set_canonical_sha256"):
        raise ValueError("frozen critical canonical hash mismatch")
    if observed_hash != critical.get("critical_set_canonical_sha256"):
        raise ValueError("frozen critical object self-hash mismatch")

    replay_count = int(inference.get("critical_replays_per_model", -1))
    if replay_count <= 0:
        raise ValueError("critical replay count must be positive")
    sample_ids = [str(row["sample_id"]) for row in frozen_rows]
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("frozen critical_set contains duplicate sample IDs")
    expected_keys = sorted(
        (sample_id, replay)
        for sample_id in sample_ids
        for replay in range(1, replay_count + 1)
    )
    return {
        "path": declared_path,
        "observed_git_blob_sha1": observed_blob,
        "critical_set_canonical_sha256": observed_hash,
        "critical_sample_count": len(sample_ids),
        "replays_per_sample": replay_count,
        "expected_trial_count": len(expected_keys),
        "sample_ids": sorted(sample_ids),
        "expected_keys": expected_keys,
    }


def validate_exact_critical_trial_profiles(
    evidence: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    receipts = evidence.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("cross-run evidence receipts missing")
    expected_keys = [tuple(row) for row in profile["expected_keys"]]
    expected_set = set(expected_keys)
    if len(expected_set) != int(profile["expected_trial_count"]):
        raise ValueError("expected critical trial profile contains duplicate keys")

    verified_runs: list[int] = []
    for receipt in receipts:
        source = receipt.get("source")
        records = receipt.get("candidate_records")
        if not isinstance(source, dict) or not isinstance(records, list):
            raise ValueError("receipt missing source/candidate records")
        observed_keys = [(str(row["sample_id"]), int(row["replay"])) for row in records]
        if len(observed_keys) != len(expected_keys):
            raise ValueError("candidate record count does not equal frozen critical trial profile")
        if len(set(observed_keys)) != len(observed_keys):
            raise ValueError("candidate record profile contains duplicate sample/replay keys")
        if set(observed_keys) != expected_set:
            raise ValueError("candidate record keys do not equal frozen critical sample/replay profile")
        verified_runs.append(int(source["workflow_run_id"]))

    return {
        "status": "EXACT_FROZEN_CRITICAL_TRIAL_PROFILE_VERIFIED",
        "critical_reference_path": profile["path"],
        "critical_reference_git_blob_sha1": profile["observed_git_blob_sha1"],
        "critical_set_canonical_sha256": profile["critical_set_canonical_sha256"],
        "critical_sample_count": profile["critical_sample_count"],
        "replays_per_sample": profile["replays_per_sample"],
        "expected_trial_count": profile["expected_trial_count"],
        "receipt_count_verified": len(verified_runs),
        "workflow_run_ids": verified_runs,
        "candidate_key_set_equals_frozen_profile": True,
    }


def _github_request(url: str, token: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "janus-genesis-cross-run-promotion-gate",
        },
    )


def _github_get(url: str, token: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(_github_request(url, token), timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"GitHub Actions metadata lookup failed: {exc}") from exc


def _github_get_bytes(url: str, token: str) -> bytes:
    try:
        with urllib.request.urlopen(_github_request(url, token), timeout=60) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"GitHub Actions artifact download failed: {exc}") from exc


def _artifact_report_identity(
    archive_bytes: bytes,
    *,
    source: dict[str, Any],
) -> dict[str, Any]:
    expected_digest = str(source.get("artifact_digest") or "")
    observed_archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if expected_digest != f"sha256:{observed_archive_sha256}":
        raise ValueError("downloaded artifact ZIP digest does not match configured GitHub artifact digest")

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            report_members = [name for name in members if Path(name).name == "report.json"]
            if len(report_members) != 1:
                raise ValueError("artifact must contain exactly one report.json")
            report_member = report_members[0]
            report_raw = archive.read(report_member)
    except zipfile.BadZipFile as exc:
        raise ValueError("downloaded GitHub artifact is not a valid ZIP") from exc

    observed_report_sha256 = hashlib.sha256(report_raw).hexdigest()
    observed_report_git_blob = core.git_blob_sha1_bytes(report_raw)
    if observed_report_sha256 != str(source.get("report_json_sha256") or ""):
        raise ValueError("live artifact report.json does not equal frozen report SHA-256")
    if observed_report_git_blob != str(source.get("report_raw_git_blob_sha1") or ""):
        raise ValueError("live artifact report.json does not equal frozen raw Git blob")

    return {
        "artifact_archive_sha256": observed_archive_sha256,
        "artifact_report_member": report_member,
        "artifact_report_json_sha256": observed_report_sha256,
        "artifact_report_raw_git_blob_sha1": observed_report_git_blob,
        "artifact_report_byte_count": len(report_raw),
        "artifact_report_matches_frozen_source": True,
    }


def fetch_live_github_source_metadata(
    config: dict[str, Any],
    *,
    repository: str,
    token: str,
) -> dict[str, Any]:
    if repository != EXPECTED_REPOSITORY:
        raise ValueError(f"unexpected GitHub repository: {repository!r}")
    if not token:
        raise ValueError("GITHUB_TOKEN is required for authoritative source authentication")
    source_configs = config.get("source_reports")
    if not isinstance(source_configs, list) or not source_configs:
        raise ValueError("source_reports missing from cross-run config")

    rows: list[dict[str, Any]] = []
    api = f"https://api.github.com/repos/{repository}"
    for source in source_configs:
        run_id = int(source["workflow_run_id"])
        artifact_id = int(source["artifact_id"])
        run = _github_get(f"{api}/actions/runs/{run_id}", token)
        artifact = _github_get(f"{api}/actions/artifacts/{artifact_id}", token)
        artifact_run = artifact.get("workflow_run") or {}
        if bool(artifact.get("expired", False)):
            raise ValueError("source artifact is expired and cannot authenticate frozen report bytes")
        archive_bytes = _github_get_bytes(
            f"{api}/actions/artifacts/{artifact_id}/zip",
            token,
        )
        report_identity = _artifact_report_identity(archive_bytes, source=source)
        rows.append({
            "workflow_run_id": int(run.get("id", -1)),
            "run_head_sha": run.get("head_sha"),
            "run_status": run.get("status"),
            "run_conclusion": run.get("conclusion"),
            "run_event": run.get("event"),
            "artifact_id": int(artifact.get("id", -1)),
            "artifact_name": artifact.get("name"),
            "artifact_digest": artifact.get("digest"),
            "artifact_expired": bool(artifact.get("expired", False)),
            "artifact_size_in_bytes": int(artifact.get("size_in_bytes", -1)),
            "artifact_workflow_run_id": int(artifact_run.get("id", -1)),
            "artifact_workflow_head_sha": artifact_run.get("head_sha"),
            **report_identity,
        })
    return {
        "schema": "janus.genesis.github_actions_source_authentication.v2",
        "repository": repository,
        "sources": rows,
        "fetched_live": True,
        "artifact_payloads_authenticated": True,
        "authentication_mode": LIVE_AUTHENTICATION_MODE,
    }


def validate_authenticated_independence(
    config: dict[str, Any],
    metadata: dict[str, Any],
    *,
    require_live_artifact_binding: bool = True,
) -> dict[str, Any]:
    if metadata.get("repository") != EXPECTED_REPOSITORY:
        raise ValueError("GitHub metadata repository mismatch")
    if require_live_artifact_binding:
        if metadata.get("fetched_live") is not True:
            raise ValueError("authoritative metadata was not fetched live")
        if metadata.get("artifact_payloads_authenticated") is not True:
            raise ValueError("live artifact payload binding is missing")
        if metadata.get("authentication_mode") != LIVE_AUTHENTICATION_MODE:
            raise ValueError("GitHub authentication mode is not authoritative")

    sources = config.get("source_reports")
    live_rows = metadata.get("sources")
    if not isinstance(sources, list) or not isinstance(live_rows, list):
        raise ValueError("source/authentication rows missing")
    if len(sources) != len(live_rows):
        raise ValueError("GitHub authenticated source count mismatch")

    by_run: dict[int, dict[str, Any]] = {}
    for row in live_rows:
        run_id = int(row.get("workflow_run_id", -1))
        if run_id in by_run:
            raise ValueError("GitHub metadata contains duplicate workflow run identity")
        by_run[run_id] = row

    authenticated: list[dict[str, Any]] = []
    for source in sources:
        run_id = int(source["workflow_run_id"])
        row = by_run.get(run_id)
        if row is None:
            raise ValueError("configured workflow run is absent from authenticated GitHub metadata")
        if row.get("run_head_sha") != source.get("head_sha"):
            raise ValueError("workflow run head SHA is not authenticated by GitHub metadata")
        if row.get("run_status") != "completed" or row.get("run_conclusion") != "success":
            raise ValueError("source workflow run is not a completed success")
        if int(row.get("artifact_id", -1)) != int(source["artifact_id"]):
            raise ValueError("artifact ID is not authenticated by GitHub metadata")
        if row.get("artifact_name") != source.get("artifact_name"):
            raise ValueError("artifact name is not authenticated by GitHub metadata")
        if row.get("artifact_digest") != source.get("artifact_digest"):
            raise ValueError("artifact digest is not authenticated by GitHub metadata")
        if int(row.get("artifact_workflow_run_id", -1)) != run_id:
            raise ValueError("artifact is not bound to the configured workflow run")
        if row.get("artifact_workflow_head_sha") != source.get("head_sha"):
            raise ValueError("artifact workflow head SHA is not bound to the configured source head")

        if require_live_artifact_binding:
            expected_archive_sha = str(source["artifact_digest"]).removeprefix("sha256:")
            if row.get("artifact_archive_sha256") != expected_archive_sha:
                raise ValueError("downloaded artifact archive digest is not authenticated")
            if row.get("artifact_report_json_sha256") != source.get("report_json_sha256"):
                raise ValueError("artifact report SHA-256 is not bound to frozen source report")
            if row.get("artifact_report_raw_git_blob_sha1") != source.get("report_raw_git_blob_sha1"):
                raise ValueError("artifact report Git blob is not bound to frozen source report")
            if row.get("artifact_report_matches_frozen_source") is not True:
                raise ValueError("artifact report/frozen source binding is not proven")

        authenticated.append({
            "workflow_run_id": run_id,
            "head_sha": source["head_sha"],
            "artifact_id": int(source["artifact_id"]),
            "artifact_digest": source["artifact_digest"],
            "artifact_report_json_sha256": row.get("artifact_report_json_sha256"),
            "artifact_report_raw_git_blob_sha1": row.get("artifact_report_raw_git_blob_sha1"),
            "artifact_report_byte_count": row.get("artifact_report_byte_count"),
            "artifact_expired_at_verification": bool(row.get("artifact_expired", False)),
            "github_run_conclusion": row["run_conclusion"],
            "github_metadata_authenticated": True,
            "artifact_payload_authenticated": require_live_artifact_binding,
        })

    identity_sets = {
        "workflow_run_id": [int(row["workflow_run_id"]) for row in sources],
        "artifact_id": [int(row["artifact_id"]) for row in sources],
        "artifact_digest": [str(row["artifact_digest"]) for row in sources],
        "report_json_sha256": [str(row["report_json_sha256"]) for row in sources],
        "report_raw_git_blob_sha1": [str(row["report_raw_git_blob_sha1"]) for row in sources],
        "encoded_git_blob_sha1": [str(row["encoded_git_blob_sha1"]) for row in sources],
    }
    for label, values in identity_sets.items():
        if len(set(values)) != len(values):
            raise ValueError(f"independent source receipts reuse {label}")

    return {
        "status": (
            "GITHUB_ACTIONS_SOURCE_AND_ARTIFACT_BYTES_AUTHENTICATED"
            if require_live_artifact_binding
            else "TEST_FIXTURE_METADATA_VALIDATED_NON_AUTHORITATIVELY"
        ),
        "repository": EXPECTED_REPOSITORY,
        "source_count": len(authenticated),
        "sources": authenticated,
        "distinct_workflow_run_ids": True,
        "distinct_artifact_ids": True,
        "distinct_artifact_digests": True,
        "distinct_raw_report_sha256": True,
        "distinct_raw_report_git_blobs": True,
        "distinct_encoded_git_blobs": True,
        "live_artifact_payload_binding": require_live_artifact_binding,
        "independence_counting_uses_authenticated_metadata": require_live_artifact_binding,
    }


def _evaluate_common(
    config: dict[str, Any],
    metadata: dict[str, Any],
    *,
    authoritative: bool,
) -> dict[str, Any]:
    evidence, _ = core.load_evidence(config)
    profile = load_frozen_critical_profile(config)
    trial_verification = validate_exact_critical_trial_profiles(evidence, profile)
    source_auth = validate_authenticated_independence(
        config,
        metadata,
        require_live_artifact_binding=authoritative,
    )
    receipt = core.evaluate(config)
    receipt["schema"] = HARDENED_SCHEMA
    receipt["canonical_entrypoint"] = "tools.run_top100_round2_1_cross_run_promotion_gate_hardened"
    receipt["critical_trial_profile_verification"] = trial_verification
    receipt["github_source_authentication"] = source_auth
    receipt["independence_authenticated_against_github_actions"] = authoritative
    receipt["authentication_mode"] = (
        LIVE_AUTHENTICATION_MODE if authoritative else FIXTURE_AUTHENTICATION_MODE
    )
    receipt["promotion_preconditions"] = {
        "exact_frozen_critical_key_set": True,
        "exact_source_report_rederivation": bool(receipt.get("compact_evidence_rederived_from_exact_source_reports")),
        "github_actions_run_artifact_authentication": authoritative,
        "live_artifact_report_bytes_equal_frozen_reports": authoritative,
        "distinct_source_identities": True,
        "historical_negative_veto": True,
    }
    if not authoritative:
        # A fixture/caller-supplied metadata path is useful for unit testing but
        # must never be serialized as an authenticated promotion receipt.
        receipt["non_authoritative_fixture"] = True
        receipt["promotion"]["authoritative_runtime_promoted"] = False
        receipt["promotion"]["selected_runtime_representation"] = "FP16"
        receipt["promotion"]["decision"] = "BLOCKED_NON_AUTHORITATIVE_METADATA_FIXTURE"
    return receipt


def evaluate_hardened(
    config: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Non-authoritative helper retained for deterministic unit tests only."""
    return _evaluate_common(config, metadata, authoritative=False)


def evaluate_hardened_live(
    config: dict[str, Any],
    *,
    repository: str,
    token: str,
) -> dict[str, Any]:
    metadata = fetch_live_github_source_metadata(
        config,
        repository=repository,
        token=token,
    )
    return _evaluate_common(config, metadata, authoritative=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--github-repository",
        default=os.environ.get("GITHUB_REPOSITORY", EXPECTED_REPOSITORY),
    )
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    config_path = args.config if args.config.is_absolute() else core.REPOSITORY_ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    receipt = evaluate_hardened_live(
        config,
        repository=str(args.github_repository),
        token=os.environ.get("GITHUB_TOKEN", ""),
    )
    print(json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=args.pretty,
        indent=2 if args.pretty else None,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
