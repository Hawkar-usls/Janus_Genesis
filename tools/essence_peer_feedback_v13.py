#!/usr/bin/env python3
"""ESSENCE v1.3: close Genesis -> Meta Registry -> peers -> Genesis ACK loop.

Recheck public delivered-reply witness against *live GitHub Actions runs* of
two distinct recipient repos. This is a source-provenance research feedback
loop; it is NOT external scientific independence or production authority.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import urllib.request

SCHEMA="janus.essence.peer_feedback_receipt/1.3"
META="Hawkar-usls/janus-meta-registry"
WITNESS="data/JANUS-ESSENCE-V10-TWO-REPO-DELIVERY-ACK-2026-11-13.json"
SOURCE_SCHEMA="janus.meta_registry.essence_peer_delivery_witness/1.0"
ALLOWED={
    "Hawkar-usls/janus-distributed-ai-swarm":"idea-swarm-dual-strand-00",
    "Hawkar-usls/Demi_Head":"idea-nexus-wal-failclosed-00",
}
ROUND_SHA="e298a184bdb05d9b411a0679baf53591aa2da108"
MAX=150_000
RUN=re.compile(r"^https://github\.com/Hawkar-usls/([A-Za-z0-9_.-]+)/actions/runs/([0-9]{8,16})$")
HEX40=re.compile(r"^[0-9a-f]{40}$")

def canonical(d):
    return json.dumps(d,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def digest(d):
    return hashlib.sha256(canonical(d)).hexdigest()

def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def api(path,token=""):
    if not (path.startswith(f"/repos/{META}/contents/{WITNESS}")
            or any(path.startswith(f"/repos/{repo}/actions/runs/")
                   for repo in ALLOWED)):
        raise ValueError("UNAUTHORIZED_PEER_FETCH")
    request=urllib.request.Request("https://api.github.com"+path,
        headers={"User-Agent":"JANUS-ESSENCE-Research-ACK/1.3",
                 "Accept":"application/vnd.github+json",
                 **({"Authorization":"Bearer "+token} if token else {})})
    with urllib.request.urlopen(request,timeout=20) as r:
        raw=r.read(MAX+1)
    if len(raw)>MAX:raise ValueError("PEER_SOURCE_OVERSIZE")
    return json.loads(raw)

def read_witness(token=""):
    blob=api(f"/repos/{META}/contents/{WITNESS}?ref=main",token)
    if (not isinstance(blob,dict) or blob.get("type")!="file"
        or blob.get("encoding")!="base64"):
        raise ValueError("WITNESS_NOT_PUBLIC_FILE")
    raw=base64.b64decode(blob["content"],validate=False)
    if git_blob(raw)!=blob.get("sha"):
        raise ValueError("WITNESS_BLOB_MISMATCH")
    return json.loads(raw),blob["sha"]

def verify(witness,run_by_repo):
    if (not isinstance(witness,dict) or witness.get("schema")!=SOURCE_SCHEMA
        or witness.get("mailbox_repository")!=META
        or witness.get("immutable_round_git_blob_sha1")!=ROUND_SHA
        or witness.get("history_policy")!="APPEND_ONLY"):
        raise ValueError("UNVERIFIED_WITNESS")
    source=witness.get("observed_receipts")
    if not isinstance(source,list) or len(source)!=2:
        raise ValueError("INCOMPLETE_TWO_WAY_DELIVERY")
    if set(run_by_repo)!=set(ALLOWED):
        raise ValueError("UNKNOWN_OR_MISSING_PEERS")
    seen=set();ack=[]
    for r in source:
        if not isinstance(r,dict):
            raise ValueError("INVALID_ACK_RECORD")
        repo=r.get("receiver")
        if repo not in ALLOWED or repo in seen:
            raise ValueError("ACK_REPO_REPLAY_OR_UNKNOWN")
        seen.add(repo)
        url=r.get("actual_main_push_event")
        match=RUN.fullmatch(url) if isinstance(url,str) else None
        if (match is None or "Hawkar-usls/"+match.group(1)!=repo
            or r.get("idea_id")!=ALLOWED[repo]
            or not isinstance(r.get("main_merge_sha"),str)
            or not HEX40.fullmatch(r["main_merge_sha"])
            or r.get("observed_mailbox_round_sha")!=ROUND_SHA
            or r.get("addressed_messages_found")!=1
            or r.get("offline_contracts_passed")!=9
            or r.get("observed_status")!="REPLY_RECEIVED_RESEARCH_ONLY"
            or r.get("completed_ci")!="PASS"):
            raise ValueError("ACK_EVIDENCE_MISMATCH")
        actual=run_by_repo[repo]
        if (not isinstance(actual,dict)
            or str(actual.get("id"))!=match.group(2)
            or actual.get("status")!="completed"
            or actual.get("conclusion")!="success"
            or actual.get("event")!="push"
            or actual.get("head_sha")!=r["main_merge_sha"]
            or actual.get("name")!="ESSENCE v1.0 receive peer replies through shared public Meta Registry"):
            raise ValueError("INDEPENDENT_LIVE_ACTIONS_RUN_MISMATCH")
        ack.append({
            "repository":repo,"idea_id":r["idea_id"],
            "observed_actions_run_id":actual["id"],
            "source_main_commit_sha1":actual["head_sha"],
            "message_received":True,
            "source_kind":"GITHUB_PUBLIC_ACTIONS_RECHECK",
            "peer_self_attestation_is_not_independent_science":True,
        })
    result={
        "schema":SCHEMA,
        "origin_repository":"Hawkar-usls/Janus_Genesis",
        "witness_sha256":digest(witness),
        "messages_acknowledged":len(ack),
        "receiver_evidence":sorted(ack,key=lambda x:x["repository"]),
        "communication_epoch_completed":1,
        "new_microcore_candidates_from_prior_genesis_run":2,
        "new_proven_neural_improvements":0,
        "scientific_fitness_generation":0,
        "model_weights_modified":False,
        "production_authority":False,
        "research_gate":"PEER_ACKS_VERIFIED_NO_INDEPENDENT_MODEL_GAIN",
    }
    result["receipt_sha256"]=digest(result)
    return result

def collect(token=""):
    witness,blob_sha=read_witness(token)
    result={}
    for r in witness["observed_receipts"]:
        repo=r["receiver"]
        if repo not in ALLOWED:raise ValueError("REPO_NOT_ALLOWLISTED")
        match=RUN.fullmatch(r["actual_main_push_event"])
        if match is None or "Hawkar-usls/"+match.group(1)!=repo:
            raise ValueError("MALFORMED_SOURCE_RUN_REFERENCE")
        result[repo]=api(f"/repos/{repo}/actions/runs/{match.group(2)}",token)
    rec=verify(witness,result)
    rec["witness_git_blob_sha1"]=blob_sha
    rec["receipt_sha256"]=digest({k:v for k,v in rec.items() if k!="receipt_sha256"})
    return rec

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    import os
    r=collect(os.environ.get("GH_TOKEN",""))
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as f:
        json.dump(r,f,sort_keys=True,ensure_ascii=False,indent=2);f.write("\n")
    print(json.dumps({k:r[k] for k in (
        "messages_acknowledged","communication_epoch_completed",
        "scientific_fitness_generation","production_authority")}))
if __name__=="__main__":
    main()
