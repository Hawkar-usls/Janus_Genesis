# -*- coding: utf-8 -*-
"""Monotonic cross-run promotion gate for Round-2.1 quantization admission.

This layer does not alter CriticalFrozenSet, model identities, or per-run
admission. It evaluates an append-only-style frozen evidence object derived
from exact admission artifacts. Under one experimental-spec fingerprint,
any historical negative receipt is a permanent veto: later PASS receipts
cannot average away or overwrite that counterexample.
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

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = "janus.genesis.top100.round2_1_cross_run_promotion_gate.v1"
EVIDENCE_SCHEMA = "janus.genesis.top100.round2_1_cross_run_evidence.v1"
ADMISSION_REPORT_SCHEMA = "janus.genesis.top100.round2_1_capability_admission_report.v1"
EXPERIMENTAL_SPEC_SCHEMA = "janus.genesis.top100.round2_1_cross_run_experimental_spec.v1"
GENESIS_NEGATIVE_ANCHOR = {
    "workflow_run_id": 31349156794,
    "head_sha": "81898c0f4ee09d1b530e3cc1c38ecdd993d4d9c9",
    "artifact_id": 9048707870,
    "report_json_sha256": "32954cbe3dbadde7e2e6489882eb3c111249d08f7c52dc9c143817d8a48db6aa",
    "candidate_model_id": "Q8_0",
}


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def git_blob_sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _repo_path(declared: str) -> Path:
    path = Path(declared)
    if not declared or path.is_absolute() or ".." in path.parts:
        raise ValueError("evidence path must be repository-relative and non-traversing")
    resolved = (REPOSITORY_ROOT / path).resolve()
    try:
        observed = resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("evidence path escapes repository root") from exc
    if observed != declared:
        raise ValueError("evidence path identity mismatch")
    return resolved


def load_evidence(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _repo_path(str(config.get("evidence_path") or ""))
    raw = path.read_bytes()
    observed_blob = git_blob_sha1_bytes(raw)
    observed_sha256 = hashlib.sha256(raw).hexdigest()
    if observed_blob != config.get("evidence_git_blob_sha1"):
        raise ValueError("frozen cross-run evidence Git blob mismatch")
    if observed_sha256 != config.get("evidence_sha256"):
        raise ValueError("frozen cross-run evidence SHA-256 mismatch")
    evidence = json.loads(raw.decode("utf-8"))
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("cross-run evidence schema mismatch")
    return evidence, {
        "path": config["evidence_path"],
        "observed_git_blob_sha1": observed_blob,
        "observed_sha256": observed_sha256,
        "single_snapshot_consumption": True,
    }


def _project_model_identity(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "digest": model["digest"],
        "expected_digest_prefix": model["expected_digest_prefix"],
        "id": model["id"],
        "is_reference": bool(model["is_reference"]),
        "size_bytes": int(model["size_bytes"]),
        "tag": model["tag"],
    }


def _derive_experimental_spec(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != ADMISSION_REPORT_SCHEMA:
        raise ValueError("source admission report schema mismatch")
    execution = report.get("execution")
    models = report.get("model_receipts")
    selection = report.get("selection")
    if not isinstance(execution, dict) or not isinstance(models, dict) or not isinstance(selection, dict):
        raise ValueError("source admission report is missing spec-bearing objects")
    order = execution.get("execution_order")
    if not isinstance(order, list):
        raise ValueError("source admission execution order missing")
    try:
        model_identities = [_project_model_identity(models[str(model_id)]) for model_id in order]
    except KeyError as exc:
        raise ValueError("source admission model receipt missing from execution order") from exc
    return {
        "admission_rule": {
            "aggregate_score_used": bool(selection["aggregate_score_used"]),
            "critical_set_average_score_used_for_admission": bool(
                report["critical_set_average_score_used_for_admission"]
            ),
            "noncritical_compensation_allowed": bool(selection["noncritical_compensation_allowed"]),
            "reference_model": selection["reference_model"],
            "rule": selection["rule"],
        },
        "campaign": report["campaign"],
        "critical_reference": report["critical_reference"],
        "execution_order": order,
        "frozen_pack": report["frozen_pack"],
        "inference": report["inference"],
        "model_count": int(report["model_count"]),
        "model_identities": model_identities,
        "ollama_version": report["ollama_version"],
        "quantized_candidate_count": int(report["quantized_candidate_count"]),
        "schema": EXPERIMENTAL_SPEC_SCHEMA,
    }


def _project_assessment(assessment: dict[str, Any], *, include_failure_evidence: bool) -> dict[str, Any]:
    out = {
        "admission_status": assessment["admission_status"],
        "failed_sample_ids": assessment.get("failed_sample_ids") or [],
        "nonpass_trials": int(assessment["nonpass_trials"]),
        "pass_trials": int(assessment["pass_trials"]),
        "required_trials": int(assessment["required_trials"]),
        "strict_capability_preservation": bool(assessment["strict_capability_preservation"]),
        "within_model_status_instability": assessment.get("within_model_status_instability") or {},
    }
    if include_failure_evidence:
        out["failure_evidence"] = assessment.get("failure_evidence") or []
    return out


def _derive_evidence_receipt(
    report: dict[str, Any],
    source_config: dict[str, Any],
    expected_spec: str,
) -> dict[str, Any]:
    spec = _derive_experimental_spec(report)
    observed_spec = canonical_sha256(spec)
    if observed_spec != expected_spec:
        raise ValueError("source admission report experimental spec fingerprint mismatch")
    models = report["model_receipts"]
    assessments = report["assessments"]
    candidate_id = "Q8_0"
    reference_id = "FP16"
    candidate_records = [
        {
            "output_sha256": row["output_sha256"],
            "replay": int(row["replay"]),
            "sample_id": row["sample_id"],
            "status": row["status"],
        }
        for row in report["records"]
        if row.get("model_id") == candidate_id
    ]
    candidate_records.sort(key=lambda row: (row["sample_id"], row["replay"]))
    execution = report["execution"]
    return {
        "candidate_assessment": _project_assessment(assessments[candidate_id], include_failure_evidence=True),
        "candidate_model": _project_model_identity(models[candidate_id]),
        "candidate_records": candidate_records,
        "execution": {
            "all_records_accounted_for": bool(execution["all_records_accounted_for"]),
            "expected_record_count": int(execution["expected_record_count"]),
            "record_count": int(execution["record_count"]),
        },
        "experimental_spec_fingerprint_sha256": observed_spec,
        "reference_assessment": _project_assessment(assessments[reference_id], include_failure_evidence=False),
        "reference_model": _project_model_identity(models[reference_id]),
        "source": {
            "artifact_digest": source_config["artifact_digest"],
            "artifact_id": int(source_config["artifact_id"]),
            "artifact_name": source_config["artifact_name"],
            "head_sha": source_config["head_sha"],
            "report_json_sha256": source_config["report_json_sha256"],
            "report_raw_git_blob_sha1": source_config["report_raw_git_blob_sha1"],
            "report_schema": report["schema"],
            "workflow_run_id": int(source_config["workflow_run_id"]),
        },
    }


def load_source_reports(
    config: dict[str, Any],
    expected_spec: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_configs = config.get("source_reports")
    if not isinstance(source_configs, list) or len(source_configs) < 2:
        raise ValueError("at least two frozen source reports are required")
    derived: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for source in source_configs:
        if not isinstance(source, dict):
            raise ValueError("source report config must be an object")
        path = _repo_path(str(source.get("encoded_path") or ""))
        encoded = path.read_bytes()
        observed_encoded_blob = git_blob_sha1_bytes(encoded)
        observed_encoded_sha256 = hashlib.sha256(encoded).hexdigest()
        if observed_encoded_blob != source.get("encoded_git_blob_sha1"):
            raise ValueError("frozen source report encoded Git blob mismatch")
        if observed_encoded_sha256 != source.get("encoded_sha256"):
            raise ValueError("frozen source report encoded SHA-256 mismatch")
        try:
            compressed = base64.b64decode(encoded.strip(), validate=True)
        except Exception as exc:
            raise ValueError("frozen source report base64 decode failed") from exc
        observed_gzip_sha256 = hashlib.sha256(compressed).hexdigest()
        if observed_gzip_sha256 != source.get("gzip_sha256"):
            raise ValueError("frozen source report gzip SHA-256 mismatch")
        try:
            raw = gzip.decompress(compressed)
        except Exception as exc:
            raise ValueError("frozen source report gzip decompression failed") from exc
        observed_raw_sha256 = hashlib.sha256(raw).hexdigest()
        observed_raw_blob = git_blob_sha1_bytes(raw)
        if observed_raw_sha256 != source.get("report_json_sha256"):
            raise ValueError("frozen source report raw SHA-256 mismatch")
        if observed_raw_blob != source.get("report_raw_git_blob_sha1"):
            raise ValueError("frozen source report raw Git blob mismatch")
        report = json.loads(raw.decode("utf-8"))
        receipt = _derive_evidence_receipt(report, source, expected_spec)
        derived.append(receipt)
        provenance.append({
            "workflow_run_id": int(source["workflow_run_id"]),
            "encoded_path": source["encoded_path"],
            "observed_encoded_git_blob_sha1": observed_encoded_blob,
            "observed_encoded_sha256": observed_encoded_sha256,
            "observed_gzip_sha256": observed_gzip_sha256,
            "observed_report_json_sha256": observed_raw_sha256,
            "observed_report_raw_git_blob_sha1": observed_raw_blob,
            "raw_report_byte_count": len(raw),
            "identity_channels_verified": 5,
            "derived_from_exact_report_bytes": True,
        })
    return derived, provenance


def decide_promotion(
    *,
    negative_receipt_count: int,
    positive_receipt_count: int,
    minimum_positive_receipts: int,
) -> tuple[bool, str]:
    if negative_receipt_count > 0:
        return False, "BLOCKED_BY_HISTORICAL_NEGATIVE_EVIDENCE"
    if positive_receipt_count < minimum_positive_receipts:
        return False, "BLOCKED_INSUFFICIENT_INDEPENDENT_ALL_PASS_RECEIPTS"
    return True, "AUTHORITATIVE_RUNTIME_PROMOTED"


def _validate_record_profile(records: list[dict[str, Any]], required_trials: int) -> tuple[int, str, str]:
    if len(records) != required_trials:
        raise ValueError("candidate record count does not equal required trials")
    keys = [(str(row["sample_id"]), int(row["replay"])) for row in records]
    if len(set(keys)) != required_trials:
        raise ValueError("candidate record profile contains duplicate sample/replay keys")
    statuses = [{"sample_id": a, "replay": b, "status": row["status"]} for (a, b), row in zip(keys, records)]
    outputs = [{"sample_id": a, "replay": b, "output_sha256": row["output_sha256"]} for (a, b), row in zip(keys, records)]
    pass_count = sum(1 for row in records if row.get("status") == "PASS")
    return pass_count, canonical_sha256(statuses), canonical_sha256(outputs)


def evaluate(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("cross-run config schema mismatch")
    if config.get("negative_evidence_policy") != "ANY_CONFORMING_HISTORICAL_NEGATIVE_BLOCKS_PROMOTION":
        raise ValueError("unsupported negative evidence policy")
    if config.get("positive_evidence_policy") != "NO_AVERAGING_NO_COMPENSATION_EVERY_CONFORMING_RECEIPT_MUST_PASS":
        raise ValueError("unsupported positive evidence policy")
    if config.get("historical_evidence_policy") != "REQUIRED_GENESIS_NEGATIVE_ANCHOR_CANNOT_BE_REMOVED":
        raise ValueError("unsupported historical evidence policy")
    if config.get("required_genesis_negative_anchor") != GENESIS_NEGATIVE_ANCHOR:
        raise ValueError("genesis negative anchor was removed or altered")

    evidence, evidence_provenance = load_evidence(config)
    expected_spec = str(config["expected_experimental_spec_fingerprint_sha256"])
    derived_receipts, source_report_provenance = load_source_reports(config, expected_spec)
    if evidence.get("experimental_spec_fingerprint_sha256") != expected_spec:
        raise ValueError("evidence experimental spec fingerprint mismatch")
    if canonical_sha256(evidence.get("experimental_spec")) != expected_spec:
        raise ValueError("embedded experimental spec does not hash to expected fingerprint")
    if evidence.get("candidate_model_id") != config.get("candidate_model_id"):
        raise ValueError("candidate model mismatch")
    if evidence.get("reference_model_id") != config.get("reference_model_id"):
        raise ValueError("reference model mismatch")

    receipts = evidence.get("receipts")
    if not isinstance(receipts, list):
        raise ValueError("cross-run receipts must be a list")
    raw_anchor_receipts = [
        receipt for receipt in receipts
        if isinstance(receipt, dict)
        and isinstance(receipt.get("source"), dict)
        and receipt["source"].get("workflow_run_id") == GENESIS_NEGATIVE_ANCHOR["workflow_run_id"]
    ]
    if len(raw_anchor_receipts) != 1:
        raise ValueError("genesis negative receipt cannot be forgotten")
    if len(receipts) < 2:
        raise ValueError("at least two independent receipts are required")
    raw_run_ids = [int(receipt["source"]["workflow_run_id"]) for receipt in receipts]
    raw_heads = [str(receipt["source"]["head_sha"]) for receipt in receipts]
    if len(set(raw_run_ids)) != len(raw_run_ids):
        raise ValueError("workflow run IDs must be independent/distinct")
    if len(set(raw_heads)) != len(raw_heads):
        raise ValueError("head SHAs must be independent/distinct")
    evidence_sorted = sorted(receipts, key=lambda row: int(row["source"]["workflow_run_id"]))
    derived_sorted = sorted(derived_receipts, key=lambda row: int(row["source"]["workflow_run_id"]))
    if derived_sorted != evidence_sorted:
        raise ValueError("compact cross-run evidence does not equal projection derived from exact source reports")

    required_trials = int(config["required_trials_per_receipt"])
    candidate_id = str(config["candidate_model_id"])
    reference_id = str(config["reference_model_id"])
    rows: list[dict[str, Any]] = []
    run_ids: list[int] = []
    heads: list[str] = []

    for receipt in receipts:
        if receipt.get("experimental_spec_fingerprint_sha256") != expected_spec:
            raise ValueError("receipt does not conform to experimental spec fingerprint")
        source = receipt.get("source")
        execution = receipt.get("execution")
        candidate = receipt.get("candidate_assessment")
        reference = receipt.get("reference_assessment")
        candidate_model = receipt.get("candidate_model")
        reference_model = receipt.get("reference_model")
        records = receipt.get("candidate_records")
        if not all(isinstance(x, dict) for x in (source, execution, candidate, reference, candidate_model, reference_model)):
            raise ValueError("receipt is missing required objects")
        if not isinstance(records, list):
            raise ValueError("candidate_records must be a list")
        if source.get("report_schema") != "janus.genesis.top100.round2_1_capability_admission_report.v1":
            raise ValueError("source admission report schema mismatch")
        if execution.get("all_records_accounted_for") is not True:
            raise ValueError("source execution records were not fully accounted")
        if int(execution.get("record_count", -1)) != int(execution.get("expected_record_count", -2)):
            raise ValueError("source execution record count mismatch")
        if candidate_model.get("id") != candidate_id or reference_model.get("id") != reference_id:
            raise ValueError("candidate/reference model identity mismatch")

        pass_count, status_hash, output_hash = _validate_record_profile(records, required_trials)
        nonpass_count = required_trials - pass_count
        if pass_count != int(candidate.get("pass_trials", -1)):
            raise ValueError("candidate pass count disagrees with frozen record profile")
        if nonpass_count != int(candidate.get("nonpass_trials", -1)):
            raise ValueError("candidate nonpass count disagrees with frozen record profile")
        strict = pass_count == required_trials
        if strict != bool(candidate.get("strict_capability_preservation")):
            raise ValueError("candidate strict-capability flag disagrees with frozen record profile")
        if int(reference.get("pass_trials", -1)) != required_trials:
            raise ValueError("reference did not pass every required trial")
        if int(reference.get("nonpass_trials", -1)) != 0:
            raise ValueError("reference contains non-PASS trial evidence")
        if reference.get("strict_capability_preservation") is not True:
            raise ValueError("reference strict-capability flag is not true")

        run_id = int(source["workflow_run_id"])
        head = str(source["head_sha"])
        run_ids.append(run_id)
        heads.append(head)
        rows.append({
            "workflow_run_id": run_id,
            "head_sha": head,
            "artifact_id": int(source["artifact_id"]),
            "artifact_digest": source["artifact_digest"],
            "report_json_sha256": source["report_json_sha256"],
            "report_raw_git_blob_sha1": source["report_raw_git_blob_sha1"],
            "candidate_model_digest": candidate_model["digest"],
            "candidate_model_tag": candidate_model["tag"],
            "candidate_size_bytes": candidate_model["size_bytes"],
            "candidate_pass_trials": pass_count,
            "candidate_nonpass_trials": nonpass_count,
            "candidate_strict_capability_preservation": strict,
            "candidate_failed_sample_ids": candidate.get("failed_sample_ids") or [],
            "candidate_within_run_status_instability": candidate.get("within_model_status_instability") or {},
            "candidate_status_profile_sha256": status_hash,
            "candidate_output_profile_sha256": output_hash,
            "historical_negative_evidence": not strict,
            "reference_pass_trials": int(reference["pass_trials"]),
        })

    if len(set(run_ids)) != len(run_ids):
        raise ValueError("workflow run IDs must be independent/distinct")
    if len(set(heads)) != len(heads):
        raise ValueError("head SHAs must be independent/distinct")
    if len({row["candidate_model_digest"] for row in rows}) != 1:
        raise ValueError("candidate model digest differs across receipts")
    if len({row["candidate_model_tag"] for row in rows}) != 1:
        raise ValueError("candidate model tag differs across receipts")
    if len({row["candidate_size_bytes"] for row in rows}) != 1:
        raise ValueError("candidate model size differs across receipts")

    anchor_rows = [row for row in rows if row["workflow_run_id"] == GENESIS_NEGATIVE_ANCHOR["workflow_run_id"]]
    if len(anchor_rows) != 1:
        raise ValueError("genesis negative receipt cannot be forgotten")
    anchor = anchor_rows[0]
    for key in ("head_sha", "artifact_id", "report_json_sha256"):
        if anchor[key] != GENESIS_NEGATIVE_ANCHOR[key]:
            raise ValueError(f"genesis negative source mismatch at {key}")
    if anchor["historical_negative_evidence"] is not True:
        raise ValueError("genesis negative anchor no longer contains negative evidence")

    negatives = [row for row in rows if row["historical_negative_evidence"]]
    positives = [row for row in rows if not row["historical_negative_evidence"]]
    promoted, decision = decide_promotion(
        negative_receipt_count=len(negatives),
        positive_receipt_count=len(positives),
        minimum_positive_receipts=int(config["minimum_independent_all_pass_receipts"]),
    )

    return {
        "schema": "janus.genesis.top100.round2_1_cross_run_promotion_receipt.v1",
        "campaign": config["campaign"],
        "candidate_model_id": candidate_id,
        "reference_model_id": reference_id,
        "experimental_spec_fingerprint_sha256": expected_spec,
        "evidence_provenance": evidence_provenance,
        "source_report_provenance": source_report_provenance,
        "compact_evidence_rederived_from_exact_source_reports": True,
        "receipt_count": len(rows),
        "independent_workflow_run_count": len(set(run_ids)),
        "independent_head_count": len(set(heads)),
        "all_receipts_exact_spec_conforming": True,
        "reference_model_passed_every_receipt": True,
        "candidate_positive_receipt_count": len(positives),
        "candidate_negative_receipt_count": len(negatives),
        "candidate_any_historical_negative": bool(negatives),
        "cross_run_status_divergence_observed": len({row["candidate_status_profile_sha256"] for row in rows}) > 1,
        "cross_run_output_divergence_observed": len({row["candidate_output_profile_sha256"] for row in rows}) > 1,
        "receipts": rows,
        "evidence_policy": {
            "negative": config["negative_evidence_policy"],
            "positive": config["positive_evidence_policy"],
            "historical": config["historical_evidence_policy"],
            "minimum_independent_all_pass_receipts": int(config["minimum_independent_all_pass_receipts"]),
            "no_averaging": True,
            "no_compensation": True,
            "new_pass_cannot_erase_old_fail": True,
        },
        "promotion": {
            "authoritative_runtime_promoted": promoted,
            "selected_runtime_representation": candidate_id if promoted else reference_id,
            "decision": decision,
            "historical_negative_is_veto": bool(negatives),
            "fresh_positive_compensates_historical_negative": False,
        },
        "claim_ceiling": config["claim_ceiling"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    receipt = evaluate(config)
    text = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None,
                      separators=None if args.pretty else (",", ":"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
