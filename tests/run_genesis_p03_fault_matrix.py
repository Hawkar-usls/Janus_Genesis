#!/usr/bin/env python3
"""P0.3 synthetic recovery fault matrix; real HOME read is another CI job.

The faults use a controlled fixture, not claims of actual GitHub outage,
machine crash or autonomous model recovery. No code execution of input text.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile

from tools import genesis_beetle_consumption_receipt as consumer
from tests.test_genesis_beetle_consumption_receipt import fixture, fixture_context, store


def hold_run(setup):
    with tempfile.TemporaryDirectory() as td:
        fixture(td)
        setup(Path(td))
        try:
            consumer.receipt_from_state(td,"a"*40)
        except consumer.ContextHold:
            return True
        return False


def simulate():
    cases={}
    with tempfile.TemporaryDirectory() as td:
        fixture(td)
        first=consumer.receipt_from_state(td,"a"*40)
        second=consumer.receipt_from_state(td,"a"*40)
        cases["WORKER_LOSS_AFTER_QUERY_BEFORE_RECEIPT_REPLAY_IDENTICAL"] = first==second
        path=Path(td)/"out"/"receipt.json"
        cases["EXACT_DUPLICATE_RECEIPT_IDEMPOTENT"]=(
            consumer.save_once(path,first) is True and
            consumer.save_once(path,first) is False
        )
        try:
            consumer.save_once(path,dict(first,model_call_attested=True))
        except consumer.ContextHold:
            cases["SAME_ID_ALTERED_RECEIPT_REJECTED"]=True
        else:
            cases["SAME_ID_ALTERED_RECEIPT_REJECTED"]=False
        cases["NO_EXTERNAL_EFFECT_OR_UNATTESTED_MODEL_PROMOTION"]=(
            first["external_effects"] is False and
            first["model_call_attested"] is False and
            first["p03_admission"] is False
        )
    cases["TAMPER_CONTEXT_SHA_FAIL_CLOSED"]=hold_run(lambda root:
        (root/consumer.MEMORY/"CONTEXT.json").write_bytes(
             (root/consumer.MEMORY/"CONTEXT.json").read_bytes()+b"X"))
    cases["MISSING_CURSOR_FAIL_CLOSED"]=hold_run(lambda root:
         (root/consumer.MEMORY/"CURSOR.json").unlink())
    def delete_receipt(root):
        state=json.loads((root/consumer.STATE).read_text())
        (root/state["checkpoint_head"]).unlink()
    cases["MISSING_HOME_PARENT_RECEIPT_FAIL_CLOSED"]=hold_run(delete_receipt)
    q=fixture_context()
    original=consumer.execute_query(q)
    q["recent_items"][0]["mirror_lens"]="CONTROL"
    newer=consumer.execute_query(q)
    # The fixture's item[0] starts FORWARD, so the changed lens affects result.
    cases["REAL_INPUT_MUTATION_CHANGES_QUERY_RESULT"]=(
        original["lens_counts"]!=newer["lens_counts"] and
        original["lens_identity_sha256"]!=newer["lens_identity_sha256"]
    )
    q=fixture_context()
    q["recent_items"][0]["external_effect_authority"]=True
    try:
        consumer.execute_query(q)
    except consumer.ContextHold:
        cases["MALICIOUS_SOURCE_AUTHORITY_REJECTED"]=True
    else:
        cases["MALICIOUS_SOURCE_AUTHORITY_REJECTED"]=False
    report={
        "schema":"janus.genesis.p03_bounded_fault_matrix.v1",
        "status":"SYNTHETIC_ENGINEERING_FAULTS_PASS__PRODUCTION_RECOVERY_UNVERIFIED"
                 if all(cases.values()) else "HOLD_SYNTHETIC_FAULT_FAILURE",
        "cases":cases,
        "total_cases":len(cases),
        "passed_cases":sum(cases.values()),
        "model_inference_performed":False,
        "actual_github_outage_simulated":False,
        "production_state_written":False,
        "new_forks_created":0,
        "p03_admission":False,
        "useful_work":"REAL_CONTEXT_LENS_INDEX_QUERY_TESTED__NEURAL_GAIN_NOT_TESTED",
    }
    report["sha256"]=consumer.sha(consumer.canonical(report))
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    report=simulate()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"cases":report["total_cases"],
                      "passed":report["passed_cases"]}))
    if report["passed_cases"]!=report["total_cases"]:
        raise SystemExit(2)


if __name__=="__main__":
    main()
