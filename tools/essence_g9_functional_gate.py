#!/usr/bin/env python3
"""ESSENCE G9 prospective functional admission scorer: research-only.

Independent Genesis owns 16 legacy frozen tasks plus 48 NEW G9 holdout tasks.
A result is eligible for review ONLY if G9 solves >=2 newly solved tasks,
beats BOTH G3 and G8 in total and does not lose ANY case solved by either.
This module does not itself train, run Qwen or admit weights. A successful
report is not external validation; source-bound real inference is required.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SCHEMA = "janus.essence.g9.function_exam_gate/1.0"
SUITE_SCHEMA = "janus.essence.g9.frozen_functional_cases/1.0"
LEGACY_SCHEMA = "janus.essence.v55.first_look_functional_cases/5.5"
SUITE = "research/essence/g9/FROZEN_FUNCTIONAL_CASES.json"
LEGACY = "research/essence/v55_functional/FROZEN_CASES.json"
SUITE_BLOB = "5098f73ffae7ee1c643322eac639ceaca92c7602"
LEGACY_BLOB = "e76dca95402ccaf9deb5d0d8174757e4417c4c7f"
REFERENCE = {
    "G3": "bc05f07916cab24ae4fe814971b1de7e4b60a948bad1e99df19bbad720b2ef8d",
    "G8": "d689455557ff1f12fd0d7e94adb73f987d1ba48c85566b0a41b60a32d18a3a48",
}
MODELS = ("G3", "G8", "G9")
CATEGORIES = (
    "integer_arithmetic", "number_theory", "modular_arithmetic",
    "bitwise_reasoning", "combinatorics", "graph_shortest_path",
    "sequence_rule", "string_transforms",
)


def require(value, label):
    if not value:
        raise ValueError(label)


def git_blob(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def read_suite(root: Path):
    root=Path(root)
    validated={}
    for tag,path,blob,schema in (
        ("g9",SUITE,SUITE_BLOB,SUITE_SCHEMA),
        ("legacy",LEGACY,LEGACY_BLOB,LEGACY_SCHEMA),
    ):
        raw=(root/path).read_bytes()
        require(100<len(raw)<100_000 and git_blob(raw)==blob,"G9_EXAM_SUITE_BLOB_CHANGED")
        doc=json.loads(raw)
        require(isinstance(doc,dict) and doc.get("schema")==schema,"G9_SUITE_SCHEMA_REJECT")
        items=doc.get("items")
        require(isinstance(items,list) and len(items)==(48 if tag=="g9" else 16),"G9_SUITE_CASE_COUNT")
        if tag=="g9":
            require(doc.get("train_on_cases") is False and
                    doc.get("production_promotion") is False and
                    doc.get("frozen_before_any_new_g9_functional_inference") is True,
                    "G9_SUITE_NOT_PROSPECTIVE")
            categories=[x.get("category") for x in items if isinstance(x,dict)]
            require(all(categories.count(cat)==6 for cat in CATEGORIES) and
                    set(categories)==set(CATEGORIES),"G9_SUITE_CATEGORY_BALANCE")
        for item in items:
            require(isinstance(item,dict) and
                    all(isinstance(item.get(k),str) for k in ("id","prompt","expected","category")) and
                    1<=len(item["expected"])<=90 and
                    len(item["prompt"])<=400,"G9_BAD_FROZEN_TASK")
        validated[tag]=items
    ids=[x["id"] for group in validated.values() for x in group]
    require(len(ids)==64 and len(set(ids))==64,"G9_DUPLICATE_TASK")
    return validated["legacy"]+validated["g9"]


def check_provenance(provenance):
    require(isinstance(provenance,dict),"G9_PROVENANCE_REQUIRED")
    require(provenance.get("source_repositories")==[
        "Hawkar-usls/Janus-Demiurge","Hawkar-usls/Janus_Genesis"],
        "G9_SOURCE_REPO_MISMATCH")
    require(provenance.get("generation")==9 and
            provenance.get("parent_generation")==8 and
            provenance.get("research_only") is True and
            provenance.get("production_promotion") is False,
            "G9_LINEAGE_OR_AUTHORITY_MISMATCH")
    require(provenance.get("suite_git_blob_sha1")==SUITE_BLOB and
            provenance.get("legacy_git_blob_sha1")==LEGACY_BLOB,
            "G9_FROZEN_BLOB_MISMATCH")
    adapters=provenance.get("model_adapter_sha256")
    require(isinstance(adapters,dict) and set(adapters)==set(MODELS) and
            all(isinstance(x,str) and
                len(x)==64 and
                all(ch in "0123456789abcdef" for ch in x) for x in adapters.values()),
            "G9_ADAPTER_ID_INVALID")
    require(adapters["G3"]==REFERENCE["G3"] and
            adapters["G8"]==REFERENCE["G8"] and
            adapters["G9"]!=adapters["G8"] and
            adapters["G9"]!=adapters["G3"],"G9_NOT_DISTINCT_FROM_PARENT")
    # These flags alone are NOT trusted external evidence: only a separate
    # SHA-pinned GitHub Actions runner actually executing the models can attest.
    require(provenance.get("real_cpu_qwen_inference") is True and
            provenance.get("weights_sealed_before_holdout_opened") is True and
            provenance.get("heldout_used_in_training") is False and
            provenance.get("source_commits_verified") is True,
            "G9_REAL_FIRST_LOOK_RUN_NOT_VERIFIED")


def score(root: Path, predictions: dict, provenance: dict):
    cases=read_suite(root)
    check_provenance(provenance)
    require(isinstance(predictions,dict) and set(predictions)==set(MODELS),"G9_EXPECT_THREE_REAL_MODELS")
    keys=[c["id"] for c in cases]
    outcome={}
    response_digests={}
    for model in MODELS:
        rows=predictions[model]
        require(isinstance(rows,list) and len(rows)==64,"G9_INCOMPLETE_TASK_PREDICTIONS")
        answers={}
        for row in rows:
            require(isinstance(row,dict) and
                    isinstance(row.get("id"),str) and
                    isinstance(row.get("response"),str) and
                    len(row["response"])<=4096 and
                    row["id"] not in answers,"G9_INVALID_MODEL_OUTPUT")
            answers[row["id"]]=row["response"].strip()
        require(set(answers)==set(keys),"G9_MISSING_OR_ADDED_CASE")
        correct={c["id"] for c in cases if answers[c["id"]]==c["expected"]}
        outcome[model]=correct
        response_digests[model]=digest([
            {"id":k,"answer_sha256":hashlib.sha256(answers[k].encode()).hexdigest()}
            for k in keys
        ])
    baseline_union=outcome["G3"] | outcome["G8"]
    new=outcome["G9"]-baseline_union
    losses=baseline_union-outcome["G9"]
    g3=len(outcome["G3"])
    g8=len(outcome["G8"])
    g9=len(outcome["G9"])
    approved=(len(new)>=2 and not losses and
              g9>max(g3,g8) and
              provenance["generation"]==9)
    report={
        "schema":SCHEMA,
        "status":"ELIGIBLE_FOR_INDEPENDENT_REVIEW_NOT_PRODUCTION" if approved else "HOLD_G9_FUNCTIONAL_RECOVERY_NOT_PROVEN",
        "suite_git_blob_sha1":SUITE_BLOB,
        "legacy_git_blob_sha1":LEGACY_BLOB,
        "models":{m:{"adapter_sha256":provenance["model_adapter_sha256"][m],
                     "exact":len(outcome[m]),"answer_digest_sha256":response_digests[m]}
                  for m in MODELS},
        "case_count":64,
        "legacy_case_count":16,
        "new_case_count":48,
        "newly_correct_beyond_either_parent":len(new),
        "previously_correct_by_either_parent_lost":len(losses),
        "no_regression_per_previous_solved_case":not losses,
        "strictly_better_than_g3_and_g8":g9>max(g3,g8),
        "minimum_newly_correct_required":2,
        "eligible_for_research_review":approved,
        "weights_sealed_before_exam":True,
        "source_commits_verified_by_input_receipt":True,
        "actual_external_independent_validation":False,
        "production_promotion":False,
        "accepted_into_essence_ledger":False,
        "scope":"SAME_OWNER_CROSS_REPO_INTERNAL_FIRST_LOOK_ONLY",
    }
    report["sha256"]=digest(report)
    return report
