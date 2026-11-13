"""ESSENCE v1.2 admission firewall for real-algorithm benchmark receipts.

A hash-bound *research review*, NOT external authentication. In particular,
self-hashing JSON, cross-repository fixtures or matching outputs cannot confer
production execution rights or substitute for externally signed blind trials.
"""
from __future__ import annotations

import kernel

SCHEMA="janus.essence.real_algorithm_review/1.2"
BENCH="janus.essence.real_algorithm_benchmark/1.2"
HOLDOUT="71f23a157a9849998dc9655bc6bdf15c08d9934a"
SOURCE="11e359e89d3946895b2e0d6817c54253f09dfed1"
BANK="e7fe6f59591009df1905dbbf06b164d49e422660"
FREEZE_COMMIT="5fcd50ad7fc26f9e26aef6ff25ebcb42ef7c8f28"
KNOWN_GATES={
    "HOLD_SEMANTIC_REGRESSION",
    "HOLD_PYTHON_MEMORY_REGRESSION",
    "HOLD_TIME_REGRESSION",
    "HOLD_NO_REPRODUCIBLE_SPEED_GAIN",
    "RESEARCH_CANDIDATE_PENDING_INDEPENDENT_BLIND_REPLICATION",
}


def _lane(lane,identity):
    if not isinstance(lane,dict) or lane.get("source_git_blob_sha1")!=identity:
        raise ValueError("V12_SOURCE_FINGERPRINT_MISMATCH")
    if (lane.get("case_count",0)<10 or type(lane.get("case_count")) is not int
            or not isinstance(lane.get("decision"),dict)
            or lane["decision"].get("gate") not in KNOWN_GATES
            or lane["decision"].get("counterexample_count")!=0
            or lane.get("baseline_output_sha256")!=lane.get("candidate_output_sha256")):
        raise ValueError("V12_OUTPUT_OR_DECISION_CONTRADICTION")
    restore=lane.get("negative_control")
    if (not isinstance(restore,dict) or restore.get("candidate_held") is not True
            or restore.get("rollback_verified") is not True
            or restore.get("production_weights_or_modules_changed") is not False
            or restore.get("counterexample_count",0)<=0
            or restore.get("baseline_output_sha256")!=restore.get("recovered_output_sha256")):
        raise ValueError("V12_ROLLBACK_DRILL_UNVERIFIED")
    for name in ("baseline_metrics","candidate_metrics"):
        data=lane.get(name)
        if (not isinstance(data,dict) or
                type(data.get("median_ns_per_call")) not in (float,int) or
                data["median_ns_per_call"]<=0 or
                type(data.get("median_tracemalloc_python_peak_bytes")) is not int or
                data["median_tracemalloc_python_peak_bytes"]<0):
            raise ValueError("V12_METRICS_MISSING")
    return True


def review(report:dict,expected_repo:str | None=None)->dict:
    if not isinstance(report,dict) or report.get("schema")!=BENCH:
        raise ValueError("V12_BAD_REPORT_SCHEMA")
    if report.get("receipt_sha256")!=kernel.digest({
            k:v for k,v in report.items() if k!="receipt_sha256"}):
        raise ValueError("V12_REPORT_TAMPERED")
    if (report.get("repository") not in ("Hawkar-usls/Janus_Genesis","Hawkar-usls/Janus-Demiurge")
            or (expected_repo is not None and report.get("repository")!=expected_repo)
            or report.get("holdout_origin_repo")!="Hawkar-usls/janus-meta-registry"
            or report.get("holdout_origin_commit")!=FREEZE_COMMIT
            or report.get("holdout_git_blob_sha1")!=HOLDOUT
            or report.get("holdout_blinded") is not False
            or report.get("independent_external_evaluator_attested") is not False
            or report.get("model_weights_updated") is not False
            or report.get("automatic_promotion") is not False
            or report.get("runtime_execution_authority") is not False
            or report.get("candidates_executed_in_working_production") is not False
            or report.get("rollback_drill_not_production_deployment") is not True
            or report.get("overall_gate")!="HOLD_EXTERNAL_BLIND_REPLICATION_AND_REAL_CHECKPOINT_REVIEW"):
        raise ValueError("V12_PREMATURE_AUTHORITY_OR_BAD_PROVENANCE")
    _lane(report.get("byte_tokenizer"),SOURCE)
    _lane(report.get("essence_gene_bank"),BANK)
    t=report.get("transformer_forward")
    if not isinstance(t,dict) or t.get("weights_trained") is not False:
        raise ValueError("V12_UNTRUSTED_TRANSFORMER_STATUS")
    if t.get("status")=="REAL_TORCH_CPU_FORWARD_TESTED":
        if (t.get("weights_modified") is not False
                or t.get("exact_logits_match") is not True
                or t.get("native_tensor_memory_measurement")!="NOT_MEASURED"
                or t.get("gate") not in {
                    "HOLD_OBSERVED_CPU_TIME_REGRESSION",
                    "HOLD_NO_STABLE_CPU_GAIN_ON_16_PAIRED_ROUNDS",
                    "RESEARCH_ONLY_CPU_GAIN_PENDING_INDEPENDENT_REPLICATION"}):
            raise ValueError("V12_INVALID_CPU_EVIDENCE")
    elif t.get("status") not in ("NOT_RUN_TORCH_NOT_INSTALLED","NOT_RUN_TORCH_OPTIONAL_CI"):
        raise ValueError("V12_UNKNOWN_TORCH_RUNTIME")
    receipt={
        "schema":SCHEMA,
        "benchmark_receipt_sha256":report["receipt_sha256"],
        "repository":report["repository"],
        "holdout_commit_sha1":FREEZE_COMMIT,
        "holdout_git_blob_sha1":HOLDOUT,
        "real_gpt_tokenizer_evaluated":True,
        "real_gene_bank_evaluated":True,
        "real_model_cpu_tested":t.get("status")=="REAL_TORCH_CPU_FORWARD_TESTED",
        "external_blind_verification_completed":False,
        "production_authority":False,
        "child_activation":False,
        "model_weights_modified":False,
        "gate":"HOLD_EXTERNAL_BLIND_REPLICATION_AND_REAL_CHECKPOINT_REVIEW",
    }
    receipt["receipt_sha256"]=kernel.digest(receipt)
    return receipt


def verify(review_receipt:dict,source_benchmark:dict)->bool:
    expected=review(source_benchmark)
    if review_receipt!=expected:
        raise ValueError("V12_ADMISSION_REVIEW_REPLAY_MISMATCH")
    return True
