#!/usr/bin/env python3
"""JANUS cross-repository Sentinel: bounded peer observation and optional one-hop recovery.

GITHUB_TOKEN is read-only for foreign repositories. Remote Actions write must
use a separately permitted token; no token => HOLD. GitHub-wide outage
remains a common failure mode. No remote code/weights can be adopted.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path

SCHEMA="janus.sentinel.crossrepo_mesh/1.0"
ROLES={"A":"Hawkar-usls/Janus-Demiurge",
       "B":"Hawkar-usls/Janus_Genesis",
       "C":"Hawkar-usls/janus-meta-registry"}
REPO_ROLES={v:k for k,v in ROLES.items()}
PRIMARY={"A":"C","B":"A","C":"B"}
WORKFLOW="janus-sentinel-mesh.yml"
MAX_AGE=40*60
MIN_FAILED_AGE=6*60
MAX_RUNS=8
RUN_ID=re.compile(r"^[1-9][0-9]{0,19}$")

def require(ok,why):
    if not ok:raise ValueError(why)

def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def seal(obj):
    return dict(obj,receipt_sha256=hashlib.sha256(canonical(obj)).hexdigest())

def clock(value):
    require(type(value) is str and len(value)<55,"BAD_GITHUB_TIME")
    parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    require(parsed.tzinfo is not None,"NAIVE_GITHUB_TIME")
    return parsed.astimezone(timezone.utc)

def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def get_runs(repo,token,opener=urllib.request.urlopen):
    require(repo in REPO_ROLES,"UNAUTHORIZED_REPOSITORY")
    require(type(token) is str and 16<len(token)<4096,"NO_READ_TOKEN")
    url=("https://api.github.com/repos/"+repo+
         "/actions/workflows/"+WORKFLOW+"/runs?per_page=8")
    req=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":"Bearer "+token,
        "User-Agent":"JANUS-Sentinel-Mesh/1.0",
        "X-GitHub-Api-Version":"2022-11-28"})
    with opener(req,timeout=15) as response:
        require(response.status==200,"PEER_READ_STATUS_NOT_200")
        raw=response.read(128001)
    require(len(raw)<=128000,"PEER_RESPONSE_OVERSIZED")
    data=json.loads(raw)
    require(isinstance(data,dict) and
            isinstance(data.get("workflow_runs"),list) and
            len(data["workflow_runs"])<=MAX_RUNS,
            "INVALID_PEER_RUN_INVENTORY")
    return data["workflow_runs"]

def health(rows,now):
    require(type(rows) is list and len(rows)<=MAX_RUNS,"BAD_PEER_RUN_LIST")
    trusted=[];seen=set()
    for item in rows:
        require(isinstance(item,dict),"BAD_PEER_RUN")
        if item.get("event")=="pull_request":continue
        require(item.get("event") in ("push","schedule","workflow_dispatch","workflow_run")
                and item.get("head_branch")=="main"
                and type(item.get("id")) is int and item["id"]>0
                and item["id"] not in seen
                and item.get("status") in ("completed","queued","in_progress","waiting","pending")
                and item.get("conclusion") in (None,"success","failure","cancelled","timed_out","skipped","neutral"),
                "INVALID_PEER_RUN_METADATA")
        seen.add(item["id"])
        created=clock(item["created_at"])
        age=(now-created).total_seconds()
        require(-60<=age<=30*86400,"PEER_CLOCK_UNTRUSTWORTHY")
        trusted.append((created,item))
    trusted.sort(key=lambda x:(x[0],x[1]["id"]),reverse=True)
    if not trusted:
        return {"status":"UNKNOWN_NO_PEER_EVIDENCE","last_run_id":None}
    created,last=trusted[0]
    age=(now-created).total_seconds()
    prior=any(x.get("status")=="completed" and
              x.get("conclusion")=="success" and
              (now-t).total_seconds()<=48*3600 for t,x in trusted)
    if not prior:status="UNKNOWN_NO_PRIOR_SUCCESS"
    elif last["status"]!="completed":status="BUSY_OR_PENDING_HOLD"
    elif last["conclusion"]=="failure" and age>=MIN_FAILED_AGE:status="STALE_FAILED"
    elif age>=MAX_AGE:status="STALE_SILENT"
    else:status="HEALTHY"
    return {"status":status,"last_run_id":last["id"],
            "last_event":last["event"],"age_seconds":round(age)}

def decide(repo,now,observations,*,recovery_only=False):
    require(repo in REPO_ROLES and set(observations)==set(ROLES),
            "UNKNOWN_LOCAL_ROLE_OR_PEER")
    role=REPO_ROLES[repo]
    stale={r for r in ROLES if observations[r]["status"] in
           ("STALE_FAILED","STALE_SILENT")}
    candidates=[]
    if not recovery_only:
        for target in sorted(stale):
            if target==role:continue
            primary=PRIMARY[target]
            if role==primary or primary in stale:
                candidates.append(target)
    target=candidates[0] if candidates else None
    return {"role":role,"target":target,
            "reason":("PRIMARY_WAKE" if target and PRIMARY[target]==role
                      else "STALE_PRIMARY_FALLBACK" if target else "OBSERVE_ONLY"),
            "max_dispatches_per_run":1,"remote_code_executed":False,
            "production_authority":False,"recovery_only":bool(recovery_only)}

def send(target,origin_repo,origin_run,token,opener=urllib.request.urlopen):
    require(target in ROLES and origin_repo in REPO_ROLES and
            type(origin_run) is str and RUN_ID.fullmatch(origin_run) and
            type(token) is str and 24<len(token)<4096,
            "CROSS_REPO_WRITE_NOT_AUTHORIZED")
    require(ROLES[target]!=origin_repo,"SELF_DISPATCH_DENIED")
    url=("https://api.github.com/repos/"+ROLES[target]+
         "/actions/workflows/"+WORKFLOW+"/dispatches")
    body={"ref":"main","inputs":{"recovery_only":"true",
           "source_repo":origin_repo,"source_run":origin_run}}
    req=urllib.request.Request(url,data=canonical(body),method="POST",
        headers={"Accept":"application/vnd.github+json",
                 "Authorization":"Bearer "+token,
                 "Content-Type":"application/json",
                 "X-GitHub-Api-Version":"2022-11-28",
                 "User-Agent":"JANUS-Sentinel-Mesh/1.0"})
    with opener(req,timeout=15) as response:
        require(response.status==204,"REMOTE_DISPATCH_NOT_ACCEPTED")
    return "REMOTE_DISPATCH_SUBMITTED_NOT_RECOVERY_PROOF"

def run(repo,run_id,read_token,remote_token="",recovery_only=False,
        *,now=None,fetch=get_runs,dispatch=send):
    require(repo in REPO_ROLES and type(run_id) is str and
            RUN_ID.fullmatch(run_id),"BAD_MESH_CONTEXT")
    now=now or datetime.now(timezone.utc)
    peers={}
    for role,target in ROLES.items():
        try:peers[role]=health(fetch(target,read_token),now)
        except (ValueError,KeyError,TypeError,urllib.error.URLError,
                TimeoutError,OSError,json.JSONDecodeError) as err:
            peers[role]={"status":"UNKNOWN_PEER_API_HOLD",
                         "error_class":type(err).__name__,"last_run_id":None}
    proposal=decide(repo,now,peers,recovery_only=recovery_only)
    target=proposal["target"]
    if target is None:outcome="OBSERVE_ONLY_NO_VERIFIED_STALE_TARGET"
    elif not remote_token:outcome="HOLD_NO_CROSS_REPO_ACTIONS_WRITE_TOKEN"
    else:
        # Direct network dispatch is denied. The separately scoped token must
        # pass through janus_sentinel_mesh_lease.py (shared non-force Git CAS).
        outcome="HOLD_UNLEASED_DISPATCH_DENIED"
    return seal({"schema":SCHEMA,"observed_utc":iso(now),
                 "repository":repo,"run_id":run_id,
                 "role":REPO_ROLES[repo],"peers":peers,
                 "plan":proposal,"outcome":outcome,
                 "actual_recovery_verified":False,
                 "github_wide_outage_survivable":False,
                 "shared_cross_repo_cas_implemented":False,
                 "model_promotion_allowed":False,
                 "automatic_code_adoption":False})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True)
    p.add_argument("--recovery-only",action="store_true")
    args=p.parse_args()
    rec=run(os.environ.get("GITHUB_REPOSITORY",""),
            os.environ.get("GITHUB_RUN_ID",""),
            os.environ.get("GH_READ_TOKEN",""),
            os.environ.get("GH_MESH_DISPATCH_TOKEN",""),
            recovery_only=args.recovery_only)
    dest=Path(args.out)
    require(not dest.exists() and not dest.is_symlink(),
            "IMMUTABLE_MESH_RECEIPT")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(rec,sort_keys=True,indent=2)+"\n")
    print(rec["outcome"],rec["receipt_sha256"])
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a") as f:
            f.write("## Sentinel cross-repo mesh\n")
            f.write("- Role: "+rec["role"]+"\n")
            f.write("- Outcome: "+rec["outcome"]+"\n")
            f.write("- Proposed target: "+str(rec["plan"]["target"])+"\n")
            for k,v in rec["peers"].items():
                f.write("- "+k+": "+v["status"]+"\n")
            f.write("- Dispatch is not verified recovery. No model authority.\n")

if __name__=="__main__":
    main()
