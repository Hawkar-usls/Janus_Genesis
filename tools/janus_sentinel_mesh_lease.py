#!/usr/bin/env python3
"""Sentinel cross-repository CAS. No dispatch without a non-force Git lease.

Requires two separately scoped secrets: JANUS_MESH_STATE_TOKEN with contents
write to Meta Registry state branch, JANUS_MESH_DISPATCH_TOKEN with actions
write to three approved receivers. No secrets -> HOLD, never fake success.
"""
from __future__ import annotations
import argparse,base64,json,os,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from tools import janus_sentinel_mesh as m

STATE="janus.sentinel.crossrepo_cas_state/1.0"
RECEIPT="janus.sentinel.crossrepo_lease_dispatch/1.0"
BRANCH="sentinel-mesh-state"
REPO="Hawkar-usls/janus-meta-registry"
FILE="sentinel-mesh/claims.json"
COOLDOWN=1800

def require(b,s):m.require(b,s)
def state_check(s):
    require(isinstance(s,dict) and set(s)=={
        "schema","epoch","last_dispatch","cooldown_seconds",
        "production_authority","shared_failure_domain","version"} and
        s["schema"]==STATE and type(s["epoch"]) is int and
        0<=s["epoch"]<1000000 and isinstance(s["last_dispatch"],dict) and
        s["cooldown_seconds"]==COOLDOWN and
        s["production_authority"] is False and
        s["shared_failure_domain"]=="GitHub" and s["version"]=="1.0",
        "INVALID_CAS_STATE")
    require(set(s["last_dispatch"]).issubset(m.ROLES),"UNKNOWN_CAS_TARGET")
    for target,v in s["last_dispatch"].items():
        require(isinstance(v,dict) and v.get("target")==target
            and v.get("issuer") in m.ROLES and v["issuer"]!=target
            and type(v.get("run_id")) is str and m.RUN_ID.fullmatch(v["run_id"])
            and type(v.get("observed_target_run_id")) is int
            and v["observed_target_run_id"]>0
            and type(v.get("epoch")) is int and v["epoch"]>0,
            "INVALID_CAS_RECORD")
        m.clock(v["issued_at"])
    return s

def transition(s,o,now):
    state_check(s)
    require(isinstance(o,dict) and o.get("schema")==m.SCHEMA and
            o.get("receipt_sha256")==m.seal({k:v for k,v in o.items()
                               if k!="receipt_sha256"})["receipt_sha256"] and
            o.get("repository") in m.REPO_ROLES and
            o.get("role")==m.REPO_ROLES[o["repository"]] and
            type(o.get("run_id")) is str and m.RUN_ID.fullmatch(o["run_id"]) and
            isinstance(o.get("plan"),dict),"FORGED_OBSERVATION")
    plan=o["plan"]
    target=plan.get("target")
    require(target in m.ROLES and target!=o["role"] and
            plan.get("role")==o["role"] and
            plan.get("reason") in ("PRIMARY_WAKE","STALE_PRIMARY_FALLBACK") and
            plan.get("recovery_only") is False and
            plan.get("max_dispatches_per_run")==1 and
            plan.get("production_authority") is False,
            "UNAUTHORIZED_WAKE_PLAN")
    require(0<=(now-m.clock(o["observed_utc"])).total_seconds()<=300,
            "STALE_WAKE_OBSERVATION")
    observed=o["peers"][target]
    require(observed["status"] in ("STALE_FAILED","STALE_SILENT") and
            type(observed["last_run_id"]) is int and observed["last_run_id"]>0,
            "NO_KNOWN_FAILED_TARGET")
    prior=s["last_dispatch"].get(target)
    if prior:
        require((now-m.clock(prior["issued_at"])).total_seconds()>=COOLDOWN,
                "CAS_COOLDOWN_ACTIVE")
    x=json.loads(json.dumps(s))
    x["epoch"]+=1
    x["last_dispatch"][target]={
        "target":target,"issuer":o["role"],"run_id":o["run_id"],
        "observed_target_run_id":observed["last_run_id"],
        "issued_at":m.iso(now),"epoch":x["epoch"]}
    state_check(x)
    return x

def git(args,env):
    p=subprocess.run(["git",*args],env=env,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,timeout=40)
    return p.returncode==0

def claim(o,token,now):
    require(type(token) is str and 24<len(token)<4096,"STATE_TOKEN_REQUIRED")
    header=base64.b64encode(("x-access-token:"+token).encode()).decode()
    env=os.environ.copy()
    env.update(GIT_CONFIG_COUNT="2",
      GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
      GIT_CONFIG_VALUE_0="AUTHORIZATION: basic "+header,
      GIT_CONFIG_KEY_1="core.hooksPath",GIT_CONFIG_VALUE_1="/dev/null",
      GIT_TERMINAL_PROMPT="0")
    with tempfile.TemporaryDirectory(prefix="sentinel-mesh-cas-") as d:
        root=Path(d)/"state"
        if not git(["clone","--quiet","--depth","1","--single-branch",
                    "--branch",BRANCH,"https://github.com/"+REPO+".git",
                    str(root)],env):
            return "HOLD_CAS_CHECKOUT"
        p=root/FILE
        if not p.is_file() or p.is_symlink() or p.stat().st_size>8192:
            return "HOLD_CAS_STATE_FILE"
        try:
            s=transition(json.loads(p.read_text()),o,now)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
            return "HOLD_CAS_INVALID_OR_COOLDOWN"
        p.write_text(json.dumps(s,sort_keys=True,indent=2)+"\n")
        git(["-C",str(root),"config","user.name","github-actions[bot]"],env)
        git(["-C",str(root),"config","user.email",
             "41898282+github-actions[bot]@users.noreply.github.com"],env)
        if not git(["-C",str(root),"add",FILE],env):
            return "HOLD_CAS_GIT_ADD"
        if not git(["-C",str(root),"commit","-m",
                    "SENTINEL CAS lease "+o["run_id"]],env):
            return "HOLD_CAS_GIT_COMMIT"
        if not git(["-C",str(root),"push","origin",
                    "HEAD:refs/heads/"+BRANCH],env):
            return "HOLD_CAS_LOST_NO_DISPATCH"
        return "CAS_WON"

def execute(o,state_token,dispatch_token,read_token,now=None,
            *,claim_fn=claim,dispatch=m.send,fetch=m.get_runs):
    now=now or datetime.now(timezone.utc)
    target=o.get("plan",{}).get("target")
    report={"schema":RECEIPT,"target":target,
       "observation_receipt_sha256":o.get("receipt_sha256"),
       "status":"OBSERVE_ONLY","claim_won":False,
       "dispatch_accepted":False,"actual_recovery_verified":False,
       "production_authority":False,"github_global_outage_survivable":False}
    if target is None:return m.seal(report)
    if not state_token or not dispatch_token:
        report["status"]="HOLD_MISSING_TWO_NARROW_TOKENS"
        return m.seal(report)
    try:
        fresh=m.health(fetch(m.ROLES[target],read_token),now)
        require(fresh["last_run_id"]==o["peers"][target]["last_run_id"] and
                fresh["status"] in ("STALE_FAILED","STALE_SILENT"),
                "TARGET_RECOVERED_SINCE_OBSERVATION")
        verdict=claim_fn(o,state_token,now)
        report["status"]=verdict
        if verdict=="CAS_WON":
            report["claim_won"]=True
            report["status"]=dispatch(target,o["repository"],o["run_id"],
                                      dispatch_token)
            report["dispatch_accepted"]=(report["status"]==
                         "REMOTE_DISPATCH_SUBMITTED_NOT_RECOVERY_PROOF")
    except (ValueError,TypeError,KeyError,subprocess.SubprocessError,
            TimeoutError,OSError) as e:
        report["status"]="HOLD_"+type(e).__name__
    return m.seal(report)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observation",required=True)
    ap.add_argument("--out",required=True)
    opts=ap.parse_args()
    p=Path(opts.observation)
    require(p.is_file() and not p.is_symlink() and
            2<=p.stat().st_size<=16000,"UNTRUSTED_OBSERVATION_FILE")
    o=json.loads(p.read_text())
    result=execute(o,os.environ.get("GH_MESH_STATE_TOKEN",""),
                   os.environ.get("GH_MESH_DISPATCH_TOKEN",""),
                   os.environ.get("GH_READ_TOKEN",""))
    out=Path(opts.out)
    require(not out.exists() and not out.is_symlink(),"NO_OVERWRITE")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(result["status"],result["receipt_sha256"])
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a") as f:
            f.write("### JANUS crossrepo Git CAS\n"+result["status"]+
                    "\nNo verified real recovery or production authority.\n")
if __name__=="__main__":
    main()
