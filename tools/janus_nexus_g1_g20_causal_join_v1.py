#!/usr/bin/env python3
"""Strict one-run G1-G20 causal-join witness. Research-only; NEVER promotes authority.

This verifier joins two separately implemented *reusable GitHub workflows*
inside one caller run, but a join of bounded receipts is not itself a complete
Habitat acceptance. The explicit hard holds are intentional and mandatory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA="janus.nexus.g1_g20_causal_join.v1"
RUN_RE=re.compile(r"[1-9][0-9]{3,23}\Z")
SHA_RE=re.compile(r"[a-f0-9]{40}\Z")
DIGEST_RE=re.compile(r"[a-f0-9]{64}\Z")

class JoinHold(ValueError):
    pass

def require(ok: bool, reason: str) -> None:
    if not ok:
        raise JoinHold(reason)

def digest(row: dict) -> str:
    return hashlib.sha256(json.dumps(
        row,sort_keys=True,separators=(",",":"),ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()

def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and
            not any(parent.is_symlink() for parent in path.parents),
            "MISSING_OR_SYMLINK_RECEIPT")
    require(0<path.stat().st_size<=30_000,"RECEIPT_SIZE_INVALID")
    row=json.loads(path.read_text("utf-8"))
    require(isinstance(row,dict),"RECEIPT_NOT_OBJECT")
    return row

def check_run(run_id: str, attempt: int, source_sha: str) -> None:
    require(isinstance(run_id,str) and RUN_RE.fullmatch(run_id) is not None,
            "RUN_ID_INVALID")
    require(type(attempt) is int and 1<=attempt<=1000,"ATTEMPT_INVALID")
    require(isinstance(source_sha,str) and SHA_RE.fullmatch(source_sha) is not None,
            "SOURCE_SHA_INVALID")

def check_sha(value: str, label: str)->None:
    require(isinstance(value,str) and SHA_RE.fullmatch(value) is not None,label)

def same_source(row: dict, run: str, attempt: int, source: str,
                source_key: str)->None:
    require(row.get("run_id")==run and row.get("attempt")==attempt and
            row.get(source_key)==source,"CROSS_RUN_OR_SOURCE_MISMATCH")

def reconcile(root: Path, run_id: str, attempt: int, source_sha: str,
              phase2: dict, ttl: dict, phase2_b_head: str,
              ttl_takeover_head: str, ttl_seed_parent: str,
              *, external_ack: dict|None=None,
              neural_patch: dict|None=None) -> dict:
    check_run(run_id,attempt,source_sha)
    for v in (phase2_b_head,ttl_takeover_head,ttl_seed_parent):
        check_sha(v,"GIT_SHA_INVALID")
    base=root/"data/nexus_integrated_native_lab/runs"/(run_id+"-"+str(attempt))
    lb=root/"data/nexus_lease_expiry_lab/runs"/(run_id+"-"+str(attempt))
    checkpoint=read_json(base/"checkpoint.json")
    variants=read_json(base/"variants.json")
    a=read_json(base/"worker-a.json")
    b=read_json(base/"worker-b.json")
    receiver=read_json(base/"receiver.json")
    seed=read_json(lb/"seed.json")
    renewed=read_json(lb/"renew.json")
    takeover=read_json(lb/"takeover.json")

    same_source(checkpoint,run_id,attempt,source_sha,"code_sha")
    require(checkpoint.get("schema")=="janus.nexus.integrated_native_git_lab.v1.checkpoint" and
            variants.get("schema")=="janus.nexus.integrated_native_git_lab.v1.variants",
            "PHASE2_SCHEMA_DRIFT")
    require(checkpoint.get("variant_digest")==digest(variants) and
            a.get("variant_digest")==digest(variants) and
            b.get("variants_digest")==digest(variants) and
            a.get("checkpoint_digest")==digest(checkpoint) and
            b.get("checkpoint_digest")==digest(checkpoint),
            "VARIANT_CHECKPOINT_CHAIN_BROKEN")
    require(variants.get("selected_variant_id")==checkpoint.get("selected_variant_id") and
            b.get("completion_id")==phase2.get("completion_id"),
            "VARIANT_OR_COMPLETION_DRIFT")
    candidates=variants.get("candidates")
    require(isinstance(candidates,list) and len(candidates)>=2 and
            variants.get("model_generated_count")>=2 and
            len(variants.get("rejected_variant_ids_retained",[]))>=1 and
            len({r["variant_id"] for r in candidates})==len(candidates),
            "REJECTED_VARIANT_NOT_RETAINED")
    selected=next((r for r in candidates
                   if r.get("variant_id")==variants["selected_variant_id"]),None)
    require(selected is not None and
            isinstance(selected.get("proposal"),dict) and
            DIGEST_RE.fullmatch(str(selected["proposal"].get("proposal_sha256",""))),
            "SELECTED_VARIANT_DIGEST_INVALID")
    selected_sha=selected["proposal"]["proposal_sha256"]
    require(receiver.get("selected_variant_id")==variants["selected_variant_id"] and
            receiver.get("consumed_proposal_sha256")==selected_sha and
            b.get("receiver_digest")==digest(receiver),
            "RECEIVER_SELECTED_VARIANT_CHAIN_BROKEN")
    same_source(a,run_id,attempt,source_sha,"code_sha") if "code_sha" in a else require(
        a.get("run_id")==run_id and a.get("attempt")==attempt,"A_RUN_DRIFT")
    require(b.get("run_id")==run_id and b.get("attempt")==attempt and
            b.get("status")=="LAB_CONSUMED_COMPLETED_ONCE",
            "B_COMPLETION_INVALID")
    require(phase2.get("schema")=="janus.nexus.phase2_live_gates.v1.independent_verdict" and
            phase2.get("status")=="PASS_SCOPED_NATIVE_CONSUMER_GIT_CAS_LAB_WITH_HARD_HOLDS",
            "PHASE2_INDEPENDENT_VERDICT_NOT_PASS")
    same_source(phase2,run_id,attempt,source_sha,"source_code_sha")
    require(phase2.get("b_head")==phase2_b_head and
            phase2.get("real_native_consumer") is True and
            phase2.get("real_github_branch_ref_cas_winner") is True and
            phase2.get("real44_two_clean_rebuilds_same_run") is True and
            phase2.get("full_issue_162_acceptance") is False and
            phase2.get("source_writeback") is False and
            phase2.get("authority_delta")==0,"PHASE2_GATE_INCOMPLETE")
    require(ttl.get("schema")=="janus.nexus.git_lease_expiry.v1.verdict" and
            ttl.get("status")=="PASS_SCOPED_REAL_WALLCLOCK_TTL_TAKEOVER_GIT_STALE_FENCE",
            "TTL_INDEPENDENT_VERDICT_NOT_PASS")
    same_source(ttl,run_id,attempt,source_sha,"source_sha")
    require(ttl.get("seed_git_sha")!=ttl.get("renew_git_sha") and
            ttl.get("renew_git_sha")!=ttl.get("takeover_git_sha") and
            ttl.get("takeover_git_sha")==ttl_takeover_head and
            ttl_seed_parent==phase2_b_head and
            ttl.get("real_wallclock_tested") is True and
            ttl.get("late_owner_semantic_rejected") is True and
            ttl.get("late_owner_git_nonforce_rejected") is True and
            ttl.get("external_effect_lease_fence_tested") is False and
            ttl.get("full_issue_162_acceptance") is False and
            ttl.get("source_writeback") is False and
            ttl.get("authority_delta")==0,"TTL_GIT_PARENT_OR_SCOPE_MISMATCH")
    from tools.janus_nexus_live_git_lease_expiry_v1 import validate_three, LeaseHold
    try:
        validate_three(seed,renewed,takeover)
    except (LeaseHold,KeyError,TypeError) as exc:
        raise JoinHold("TTL_REPLAY_INVALID") from exc
    require(seed.get("run_id")==run_id and seed.get("attempt")==attempt and
            seed.get("source_sha")==source_sha and
            takeover.get("observed_ms")>=renewed.get("expires_at_ms"),
            "TTL_SEED_OR_REAL_EXPIRY_DRIFT")
    for row in (checkpoint,a,b,receiver,seed,renewed,takeover):
        require(row.get("authority_delta")==0 and
                row.get("source_writeback",False) is False,
                "AUTHORITY_OR_SOURCE_WRITEBACK_ESCALATION")

    # Genuine external organ ACK from *this* run is required. Historical
    # Demiurge ACKs are rejected even when their model hash matches.
    external_bound=False
    if external_ack is not None:
        require(external_ack.get("sender_source_run_id")==run_id and
                external_ack.get("sender_source_attempt")==attempt and
                external_ack.get("sender_code_sha")==source_sha and
                external_ack.get("selected_proposal_sha256")==selected_sha and
                external_ack.get("receiver_repository")=="Hawkar-usls/Janus-Demiurge" and
                external_ack.get("real_external_organ_readonly_consumption_proven") is True and
                external_ack.get("external_organ_is_separate_git_repository_and_runner") is True and
                external_ack.get("source_writeback") is False and
                external_ack.get("full_issue_162_acceptance") is False,
                "EXTERNAL_ACK_WRONG_RUN_OR_PROPOSAL")
        external_bound=True
    neural_bound=False
    if neural_patch is not None:
        require(neural_patch.get("run_id")==run_id and
                neural_patch.get("attempt")==attempt and
                neural_patch.get("source_sha")==source_sha and
                neural_patch.get("model_generated_actual_source_patch") is True and
                neural_patch.get("independent_heldout_pass") is True and
                neural_patch.get("source_writeback") is False and
                neural_patch.get("authority_delta")==0,
                "NEURAL_PATCH_WRONG_RUN_OR_FALSE_ATTESTATION")
        neural_bound=True

    # G1-G20 are conservative scoped engineering labels, NOT official launch
    # acceptance. A source pointer that still refers to archived REAL44
    # means the model did not consume the fresh 44-source snapshot.
    same_run_source_bound=(checkpoint.get("source_witness",{})
                           .get("same_run_real44_materialized") is True)
    bounded_gates={
        "G1_EXACT_PIN_BINDING":"PASS_SCOPED",
        "G2_MATERIALIZED_NEXUS_ID_REPRODUCED":
            "PASS_SCOPED_REAL44_BUT_MODEL_INPUT_NOT_BOUND" if not same_run_source_bound
            else "PASS_SCOPED",
        "G3_VARIANT_LINEAGE_HEAD_REPRODUCED":"PASS_SCOPED",
        "G4_FAILED_VARIANT_RETAINED":"PASS_SCOPED",
        "G5_HANDOFF_LEDGER_HEAD_REPRODUCED":"HOLD_NO_INDEPENDENT_LEDGER_HEAD",
        "G6_CONFLICT_RETENTION_HOLD_RECONCILE":"PASS_SCOPED_GIT_CAS_ONLY",
        "G7_EXCLUSIVE_LEASE_NO_DOUBLE_OWNER":"PASS_SCOPED_GIT_FENCE_ONLY",
        "G8_SESSION_DROP_RECOVERY":"PASS_SCOPED",
        "G9_HANDOFF_CONSUMED_WITHOUT_HIDDEN_SESSION_CONTEXT":"PASS_SCOPED",
        "G10_RESIDENT_IDENTITY_AND_JOURNAL_CONTINUITY":"HOLD_FULL_RESIDENT_JOURNAL",
        "G11_EXACTLY_ONCE_COMPLETION":"PASS_SCOPED_GIT_ONLY",
        "G12_SOURCE_PIN_DRIFT":"FALSE",
        "G13_SOURCE_WRITEBACK_OBSERVED":"FALSE",
        "G14_HISTORY_DELETE_OR_REWRITE":"HOLD_INDEPENDENT_HISTORY_AUDIT",
        "G15_PRIVATE_SOURCE_METADATA_PUBLIC_LEAK":"HOLD_FULL_LOG_AUDIT",
        "G16_AUTHORITY_DELTA":"0",
        "G17_PC_DEPENDENCY_OBSERVED":"FALSE_SCOPED_CLOUD",
        "G18_REMOTE_DESKTOP_DEPENDENCY_OBSERVED":"FALSE_SCOPED_CLOUD",
        "G19_NAS_DEPENDENCY_OBSERVED":"FALSE_SCOPED_CLOUD",
        "G20_CLEAN_CLOUD_WORKER_RECONSTRUCTION":"PASS_SCOPED"
    }
    holds=["HOLD_NATIVE_NEURAL_SOURCE_REPAIR"] if not neural_bound else []
    if not external_bound: holds.append("HOLD_CAUSAL_EXTERNAL_DEMIURGE_ACK")
    if not same_run_source_bound: holds.append("HOLD_REAL44_MODEL_INPUT_CAUSAL_LINK")
    holds += ["HOLD_FULL_RESIDENT_AND_HANDOFF_LEDGER",
              "HOLD_EXTERNAL_EFFECT_EXACTLY_ONCE",
              "HOLD_INDEPENDENT_G1_G20_HARD_GATE_COVERAGE"]
    return {
        "schema":SCHEMA+".verdict","status":"PASS_SAME_RUN_PHASE2_TO_TTL_GIT_JOIN_WITH_HARD_HOLDS",
        "run_id":run_id,"attempt":attempt,"source_sha":source_sha,
        "phase2_b_head":phase2_b_head,"ttl_seed_parent":ttl_seed_parent,
        "ttl_seed_git_sha":ttl["seed_git_sha"],"ttl_takeover_git_sha":ttl_takeover_head,
        "selected_proposal_sha256":selected_sha,
        "phase2_completion_id":b["completion_id"],
        "same_run_phase2_to_ttl_git_parent_verified":True,
        "phase2_two_clean_real44_verified":True,
        "lease_expiry_stale_owner_git_fence_verified":True,
        "external_organ_same_cohort_ack":external_bound,
        "neural_patch_same_cohort_holdout":neural_bound,
        "g1_g20_scoped_observations":bounded_gates,
        "hard_holds":holds,"full_issue_162_acceptance":False,
        "g1_to_g20_full_acceptance":False,
        "scientific_authority_delta":0,"source_writeback":False
    }

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--attempt",type=int,required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--phase2",type=Path,required=True)
    p.add_argument("--ttl",type=Path,required=True)
    p.add_argument("--phase2-b-head",required=True)
    p.add_argument("--ttl-takeover-head",required=True)
    p.add_argument("--ttl-seed-parent",required=True)
    p.add_argument("--external-ack",type=Path)
    p.add_argument("--neural-patch",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:
        require(not a.out.exists() and not a.out.is_symlink(),
                "EXISTING_VERDICT_REWRITE_DENIED")
        val=reconcile(a.root,a.run_id,a.attempt,a.source_sha,
                      read_json(a.phase2),read_json(a.ttl),
                      a.phase2_b_head,a.ttl_takeover_head,
                      a.ttl_seed_parent,
                      external_ack=read_json(a.external_ack) if a.external_ack else None,
                      neural_patch=read_json(a.neural_patch) if a.neural_patch else None)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(val,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print("JANUS_G1_G20_CAUSAL_JOIN="+val["status"])
        print("JANUS_G1_G20_FULL_ACCEPTANCE=HOLD")
        return 0
    except (JoinHold,OSError,ValueError,TypeError,KeyError,StopIteration) as exc:
        reason=str(exc) if isinstance(exc,JoinHold) else "UNTRUSTED_INPUT_OR_IO"
        print("JANUS_G1_G20_CAUSAL_JOIN=HOLD:"+reason,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
