#!/usr/bin/env python3
"""Genesis #162 research-only real-time Git lease expiry and stale-owner fencing.

JSON lease stages are immutable, written to an isolated lab branch with a real
non-force Git push per distinct hosted worker. Git ref updates are the only
global compare-and-swap. The code itself NEVER grants production/source writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time

SCHEMA="janus.nexus.git_lease_expiry.v1"
RUN_RE=re.compile(r"[1-9][0-9]{3,23}\Z")
SHA_RE=re.compile(r"[0-9a-f]{40}\Z")
HEX_RE=re.compile(r"[0-9a-f]{64}\Z")
ROOT=Path("data/nexus_lease_expiry_lab/runs")
TTL_MS=90_000
MAX_WAIT_MS=120_000


class LeaseHold(ValueError):
    pass


def require(condition: bool, label: str) -> None:
    if not condition:
        raise LeaseHold(label)


def canonical(row: dict) -> bytes:
    return json.dumps(row,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode("utf-8")


def sha256(row: dict) -> str:
    return hashlib.sha256(canonical(row)).hexdigest()


def check_identity(run_id: str, attempt: int, source_sha: str) -> None:
    require(isinstance(run_id,str) and bool(RUN_RE.fullmatch(run_id)),
            "INVALID_RUN_ID")
    require(type(attempt) is int and 1<=attempt<=1000,"INVALID_ATTEMPT")
    require(isinstance(source_sha,str) and bool(SHA_RE.fullmatch(source_sha)),
            "INVALID_SOURCE_SHA")


def base(root: Path, run_id: str, attempt: int) -> Path:
    require(isinstance(run_id,str) and bool(RUN_RE.fullmatch(run_id)),
            "INVALID_RUN_ID")
    require(type(attempt) is int and 1<=attempt<=1000,"INVALID_ATTEMPT")
    root=root.resolve()
    target=root/ROOT/(run_id+"-"+str(attempt))
    require(target.resolve().is_relative_to(root),"OUTPUT_PATH_ESCAPE")
    return target


def read(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "RECEIPT_UNAVAILABLE")
    require(path.stat().st_size<=12_000,"RECEIPT_TOO_BIG")
    result=json.loads(path.read_text("utf-8"))
    require(isinstance(result,dict),"RECEIPT_NOT_OBJECT")
    return result


def save_once(path: Path, value: dict) -> None:
    require(not path.is_symlink(),"OUTPUT_IS_SYMLINK")
    data=json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    require(len(data.encode())<=12_000,"RECEIPT_TOO_BIG")
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        require(path.read_text("utf-8")==data,"IMMUTABLE_RECEIPT_CONFLICT")
        return
    with path.open("x",encoding="utf-8") as f:
        f.write(data)


def now_ms() -> int:
    return time.time_ns()//1_000_000


def _ms(value: int) -> int:
    require(type(value) is int and 1_600_000_000_000<=value<=4_000_000_000_000,
            "WALLCLOCK_INVALID")
    return value


def _nonce(value: str) -> str:
    require(isinstance(value,str) and bool(re.fullmatch("[0-9a-f]{32}",value)),
            "NONCE_INVALID")
    return value


def _token(run_id: str, source_sha: str, owner: str, nonce: str) -> str:
    return hashlib.sha256((run_id+":"+source_sha+":"+owner+":"+nonce).encode()).hexdigest()


def seed(run_id: str, attempt: int, source_sha: str,
         observed_ms: int, nonce: str) -> dict:
    check_identity(run_id,attempt,source_sha)
    t=_ms(observed_ms)
    token=_token(run_id,source_sha,"worker-old",_nonce(nonce))
    return {"schema":SCHEMA+".lease","phase":"SEED",
            "run_id":run_id,"attempt":attempt,"source_sha":source_sha,
            "owner":"worker-old","fence_epoch":1,"lease_id":token,
            "observed_ms":t,"expires_at_ms":t+TTL_MS,
            "previous_digest":None,"ttl_ms":TTL_MS,
            "source_writeback":False,"authority_delta":0}


def renew(initial: dict, observed_ms: int) -> dict:
    validate_seed(initial)
    t=_ms(observed_ms)
    require(initial["observed_ms"]<=t<initial["expires_at_ms"],
            "OLD_LEASE_EXPIRED_BEFORE_RENEW")
    return {**initial,"phase":"RENEW","observed_ms":t,
            "expires_at_ms":t+TTL_MS,"previous_digest":sha256(initial)}


def takeover(initial: dict, renewed: dict, observed_ms: int,
             nonce: str) -> dict:
    validate_chain(initial,renewed)
    t=_ms(observed_ms)
    require(t>=renewed["expires_at_ms"],"TAKEOVER_BEFORE_EXPIRE")
    require(t<renewed["expires_at_ms"]+MAX_WAIT_MS,
            "TAKEOVER_CLOCK_EXCESSIVE_DRIFT")
    owner="worker-new"
    token=_token(initial["run_id"],initial["source_sha"],owner,_nonce(nonce))
    require(token!=renewed["lease_id"],"FENCE_TOKEN_REUSED")
    return {**renewed,"phase":"TAKEOVER","owner":owner,"fence_epoch":2,
            "lease_id":token,"observed_ms":t,"expires_at_ms":t+TTL_MS,
            "previous_digest":sha256(renewed)}


def validate_seed(row: dict) -> None:
    require(isinstance(row,dict) and row.get("schema")==SCHEMA+".lease"
            and row.get("phase")=="SEED","SEED_SCHEMA_INVALID")
    check_identity(row.get("run_id"),row.get("attempt"),row.get("source_sha"))
    t=_ms(row.get("observed_ms"))
    require(row.get("owner")=="worker-old" and
            row.get("fence_epoch")==1 and
            isinstance(row.get("lease_id"),str) and
            HEX_RE.fullmatch(row["lease_id"]) is not None and
            row.get("ttl_ms")==TTL_MS and
            row.get("expires_at_ms")==t+TTL_MS and
            row.get("previous_digest") is None and
            row.get("source_writeback") is False and
            row.get("authority_delta")==0 and
            set(row)=={"schema","phase","run_id","attempt","source_sha",
                      "owner","fence_epoch","lease_id","observed_ms",
                      "expires_at_ms","previous_digest","ttl_ms",
                      "source_writeback","authority_delta"},"SEED_FIELDS_INVALID")


def validate_chain(initial: dict, renewed: dict) -> None:
    validate_seed(initial)
    require(isinstance(renewed,dict) and
            renewed==renew(initial,renewed.get("observed_ms")),
            "RENEW_CHAIN_INVALID")


def validate_three(initial: dict, renewed: dict, successor: dict) -> None:
    validate_chain(initial,renewed)
    require(isinstance(successor,dict) and
            successor.get("phase")=="TAKEOVER" and
            successor.get("previous_digest")==sha256(renewed) and
            successor.get("source_sha")==initial["source_sha"] and
            successor.get("run_id")==initial["run_id"] and
            successor.get("attempt")==initial["attempt"] and
            successor.get("owner")=="worker-new" and
            successor.get("fence_epoch")==2 and
            successor.get("ttl_ms")==TTL_MS and
            successor.get("source_writeback") is False and
            successor.get("authority_delta")==0 and
            isinstance(successor.get("lease_id"),str) and
            HEX_RE.fullmatch(successor["lease_id"]) is not None and
            successor["lease_id"]!=renewed["lease_id"] and
            successor["observed_ms"]>=renewed["expires_at_ms"] and
            successor["observed_ms"]<renewed["expires_at_ms"]+MAX_WAIT_MS and
            successor.get("expires_at_ms")==successor["observed_ms"]+TTL_MS and
            set(successor)==set(renewed),
            "TAKEOVER_CHAIN_INVALID")


def assert_holder(current: dict, presented: dict, observed_ms: int) -> None:
    t=_ms(observed_ms)
    require(current.get("lease_id")==presented.get("lease_id") and
            current.get("fence_epoch")==presented.get("fence_epoch") and
            current.get("owner")==presented.get("owner") and
            current.get("source_sha")==presented.get("source_sha") and
            current.get("run_id")==presented.get("run_id") and
            current.get("attempt")==presented.get("attempt"),
            "STALE_FENCING_TOKEN_REJECTED")
    require(current.get("expires_at_ms")>t,"PRESENTED_LEASE_EXPIRED")


def late_attempt(initial: dict, renewed: dict, successor: dict,
                 observed_ms: int, remote_push_rejected: bool,
                 old_git_head: str, current_git_head: str) -> dict:
    validate_three(initial,renewed,successor)
    require(type(remote_push_rejected) is bool and remote_push_rejected,
            "OLD_GIT_PUSH_NOT_REJECTED")
    require(isinstance(old_git_head,str) and
            SHA_RE.fullmatch(old_git_head) is not None and
            isinstance(current_git_head,str) and
            SHA_RE.fullmatch(current_git_head) is not None and
            old_git_head!=current_git_head,"GIT_FENCE_HEAD_INVALID")
    try:
        assert_holder(successor,renewed,observed_ms)
    except LeaseHold as exc:
        require(str(exc)=="STALE_FENCING_TOKEN_REJECTED",
                "OLD_HOLDER_REJECTED_FOR_WRONG_REASON")
    else:
        raise LeaseHold("OLD_HOLDER_ACCEPTED_AFTER_TAKEOVER")
    return {"schema":SCHEMA+".stale_attempt",
            "run_id":initial["run_id"],"attempt":initial["attempt"],
            "source_sha":initial["source_sha"],
            "old_owner":"worker-old","new_owner":"worker-new",
            "old_lease_id":renewed["lease_id"],
            "new_lease_id":successor["lease_id"],
            "old_lease_epoch":1,"new_lease_epoch":2,
            "old_git_head":old_git_head,"current_git_head":current_git_head,
            "nonforce_git_push_rejected":True,
            "semantic_fence_rejected":True,"observed_ms":_ms(observed_ms),
            "source_writeback":False,"authority_delta":0}


def verify(initial: dict, renewed: dict, successor: dict, late: dict,
           seed_git_sha: str, renew_git_sha: str,
           successor_git_sha: str, verified_remote_git_sha: str) -> dict:
    validate_three(initial,renewed,successor)
    for h in (seed_git_sha,renew_git_sha,successor_git_sha,verified_remote_git_sha):
        require(isinstance(h,str) and SHA_RE.fullmatch(h) is not None,
                "GIT_HEAD_INVALID")
    require(len({seed_git_sha,renew_git_sha,successor_git_sha})==3 and
            successor_git_sha==verified_remote_git_sha,
            "DURABLE_GIT_LINEAGE_OR_HEAD_MISMATCH")
    require(late==late_attempt(initial,renewed,successor,
           late["observed_ms"],late["nonforce_git_push_rejected"],
           renew_git_sha,successor_git_sha),
            "LATE_ATTEMPT_FORGED")
    return {"schema":SCHEMA+".verdict",
            "status":"PASS_SCOPED_REAL_WALLCLOCK_TTL_TAKEOVER_GIT_STALE_FENCE",
            "run_id":initial["run_id"],"attempt":initial["attempt"],
            "source_sha":initial["source_sha"],
            "seed_git_sha":seed_git_sha,"renew_git_sha":renew_git_sha,
            "takeover_git_sha":successor_git_sha,
            "original_lease_id_sha256":hashlib.sha256(renewed["lease_id"].encode()).hexdigest(),
            "replacement_lease_id_sha256":hashlib.sha256(successor["lease_id"].encode()).hexdigest(),
            "expires_after_renew_ms":renewed["expires_at_ms"],
            "takeover_observed_ms":successor["observed_ms"],
            "real_wallclock_tested":True,"fence_epoch_advanced":True,
            "late_owner_semantic_rejected":True,
            "late_owner_git_nonforce_rejected":True,
            "source_writeback":False,"authority_delta":0,
            "external_effect_lease_fence_tested":False,
            "full_issue_162_acceptance":False}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=["seed","renew","takeover","late","verify"])
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--attempt",type=int,default=1)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--seed-head",default="")
    p.add_argument("--renew-head",default="")
    p.add_argument("--takeover-head",default="")
    p.add_argument("--remote-head",default="")
    p.add_argument("--git-push-rejected",action="store_true")
    p.add_argument("--late-path",type=Path)
    p.add_argument("--live-wait",action="store_true")
    args=p.parse_args()
    try:
        check_identity(args.run_id,args.attempt,args.source_sha)
        b=base(args.root,args.run_id,args.attempt)
        if args.phase=="seed":
            require(not b.exists(),"RUN_EXISTS_NO_REPLACEMENT")
            result=seed(args.run_id,args.attempt,args.source_sha,now_ms(),
                        secrets.token_hex(16))
        elif args.phase=="renew":
            result=renew(read(b/"seed.json"),now_ms())
        else:
            first=read(b/"seed.json")
            renewed=read(b/"renew.json")
            if args.phase=="takeover":
                if args.live_wait:
                    current=now_ms()
                    require(renewed["expires_at_ms"]-current<MAX_WAIT_MS,
                            "LIVE_WAIT_EXCEEDS_ALLOWED_LIMIT")
                    if current<renewed["expires_at_ms"]+2000:
                        time.sleep((renewed["expires_at_ms"]+2000-current)/1000)
                result=takeover(first,renewed,now_ms(),secrets.token_hex(16))
            else:
                successor=read(b/"takeover.json")
                if args.phase=="late":
                    result=late_attempt(first,renewed,successor,now_ms(),
                         args.git_push_rejected,args.renew_head,args.takeover_head)
                else:
                    result=verify(first,renewed,successor,
                        read(args.late_path or b/"late-attempt.json"),args.seed_head,
                        args.renew_head,args.takeover_head,args.remote_head)
        save_once(args.out,result)
        print("JANUS_REAL_GIT_LEASE_"+args.phase.upper()+"="+
              result.get("status","PASS_BOUNDED"))
        return 0
    except (LeaseHold,KeyError,TypeError,ValueError,OSError) as exc:
        print("JANUS_REAL_GIT_LEASE=HOLD:"+
              (str(exc) if isinstance(exc,LeaseHold) else "INPUT_OR_IO"),
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
