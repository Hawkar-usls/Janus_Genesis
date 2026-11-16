#!/usr/bin/env python3
"""ESSENCE v5.1 cross-repository voice-linked microkernel task exchange.

Two separate GitHub Actions workers own *only their local transport branch*.
Messages are data, never shell commands. An inherited Qwen G2 model is linked
through a verified read-only prior receipt; this link is NOT falsely called
fresh model-generated speech. Source checks are target-local and Git-pinned.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

D="Hawkar-usls/Janus-Demiurge"
G="Hawkar-usls/Janus_Genesis"
PEERS={D:G,G:D}
TASKS={
 D:("VERIFY_V49_HOLD","research/essence/peer_v49/FIRST_PROSPECTIVE_READOUT.json",
    "Проверь исходный протокол ESSENCE v4.9: действительно ли научный статус HOLD и запрещён ли допуск весов?"),
 G:("VERIFY_GENESIS_ESSENCE"," .janus/essence/manifest.json".strip(),
    "Проверь действующий контракт микроядер Genesis: активны ли полномочия выполнения, записи или запуска?"),
}
SCHEMA="janus.essence.voice_mesh.task/5.1"
REPLY="janus.essence.voice_mesh.reply/5.1"
HEARD="janus.essence.voice_mesh.heard/5.1"
MODEL_SCHEMA="janus.essence.voice_mesh.model_link/5.1"
MODEL_RECEIPT="b2f6be283f5b831c08393144c12e1fd6429bb39a1ea1bf4c9d54276f5f200810"
MODEL_PACKET="6f3f61c46f3a3351110b288427b2db4577bb07739127d8a41d6460bcab72f5c8"
HASH40=re.compile(r"^[0-9a-f]{40}$")
HASH64=re.compile(r"^[0-9a-f]{64}$")
NAME=re.compile(r"^[0-9a-f]{24}\.json$")
MAX=100_000

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"),
                      allow_nan=False).encode("utf-8")

def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def sealed(obj):
    return dict(obj,receipt_sha256=digest(obj))

def verify_seal(obj):
    if not isinstance(obj,dict) or obj.get("receipt_sha256")!=digest(
            {k:v for k,v in obj.items() if k!="receipt_sha256"}):
        raise ValueError("VOICE_UNVERIFIED_RECEIPT")
    return obj

def load(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or not 2<=path.stat().st_size<=MAX:
        raise ValueError("VOICE_UNSAFE_INPUT_FILE")
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda x:(_ for _ in ()).throw(
                          ValueError("VOICE_NONFINITE_JSON")))

def put_once(path,obj):
    path=Path(path)
    if path.is_symlink():
        raise ValueError("VOICE_SYMLINK_TARGET")
    content=json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if path.exists():
        if path.read_text(encoding="utf-8")!=content:
            raise ValueError("VOICE_EXISTING_PACKET_MUTATED")
        return False
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content,encoding="utf-8")
    return True

def verify_manifest(root,local_repo):
    obj=load(Path(root)/".janus/essence/manifest.json")
    if (obj.get("schema")!="janus.essence.microkernel/0.1"
            or obj.get("repository")!=local_repo
            or obj.get("enabled") is not False
            or obj.get("activation")!="EXPLICIT_READONLY_TEST_ONLY"
            or obj.get("birth_policy")!="PROPOSAL_ONLY"
            or not isinstance(obj.get("microkernels"),list)
            or len(obj["microkernels"])!=6
            or any(obj.get("capabilities",{}).values())):
        raise ValueError("VOICE_ROOT_KERNEL_AUTHORITY_OR_MANIFEST_CHANGED")
    return obj

def validate_model_link(link,local_repo):
    if (link.get("schema")!=MODEL_SCHEMA or
        link.get("repository")!=local_repo or
        link.get("shared_model")!="Qwen/Qwen2.5-0.5B-Instruct" or
        link.get("model_role")!="READ_ONLY_ASYNC_SPEAKER_LINK" or
        link.get("source_receipt_sha256")!=MODEL_RECEIPT or
        link.get("source_packet_id")!=MODEL_PACKET or
        link.get("local_model_inference_performed") is not False or
        link.get("original_model_answer")!="HOLD" or
        link.get("speaker_can_delegate_arbitrary_workflows") is not False or
        link.get("production_or_sentinel_authority") is not False):
        raise ValueError("VOICE_MODEL_LINK_AUTHORITY_DRIFT")
    return link

def verify_original_model_link(raw):
    obj=json.loads(raw)
    verify_seal(obj)
    if (obj.get("receipt_sha256")!=MODEL_RECEIPT or
        obj.get("schema")!="janus.agency.qwen_research_task_proposal/5.0" or
        obj.get("source_packet_sha256")!=MODEL_PACKET or
        obj.get("model_id")!="Qwen/Qwen2.5-0.5B-Instruct" or
        obj.get("model_raw_response")!="HOLD" or
        obj.get("model_choice")!="NO_ACTION" or
        obj.get("dispatch_workflow") is not None or
        obj.get("sentinel_dispatch") is not False):
        raise ValueError("VOICE_FAKE_MODEL_IDENTITY")
    return obj

def fetch_public(repo,commit,path):
    if repo not in PEERS or not HASH40.fullmatch(commit) or path!=TASKS[repo][1]:
        raise ValueError("VOICE_REMOTE_FETCH_NOT_IN_ALLOWLIST")
    url="https://raw.githubusercontent.com/"+repo+"/"+commit+"/"+path
    with urllib.request.urlopen(urllib.request.Request(
        url,headers={"User-Agent":"ESSENCE-v51-Source-Witness"}),
        timeout=20) as response:
        raw=response.read(MAX+1)
    if len(raw)>MAX:
        raise ValueError("VOICE_SOURCE_TOO_BIG")
    return raw

def task_id(source,target,kind,source_sha):
    return digest({"from":source,"to":target,"kind":kind,"source_sha256":source_sha})[:24]

def make_task(repo,commit,raw,model_link):
    if repo not in PEERS or not HASH40.fullmatch(commit):
        raise ValueError("VOICE_WRONG_ACTOR_OR_COMMIT")
    kind,path,question=TASKS[repo]
    target=PEERS[repo]
    content_sha=hashlib.sha256(raw).hexdigest()
    identifier=task_id(repo,target,kind,content_sha)
    return sealed({
        "schema":SCHEMA,"id":identifier,"source_repo":repo,"target_repo":target,
        "kind":kind,"source_commit":commit,"source_path":path,
        "source_sha256":content_sha,
        "question":question,"model_link_receipt_sha256":model_link["source_receipt_sha256"],
        "last_verified_model_statement":model_link["original_model_answer"],
        "fresh_model_speech_on_this_task":False,
        "request_target_local_verification":True,"request_arbitrary_execution":False,
        "request_model_weight_update":False,"request_production_update":False,
        "request_sentinel_dispatch":False,
    })

def validate_task(msg,for_repo):
    verify_seal(msg)
    src=msg.get("source_repo")
    if (src not in PEERS or PEERS[src]!=for_repo or
        msg.get("target_repo")!=for_repo or
        msg.get("schema")!=SCHEMA or
        msg.get("kind")!=TASKS[src][0] or
        msg.get("source_path")!=TASKS[src][1] or
        not HASH40.fullmatch(msg.get("source_commit","")) or
        not HASH64.fullmatch(msg.get("source_sha256","")) or
        msg.get("question")!=TASKS[src][2] or
        msg.get("id")!=task_id(src,for_repo,msg["kind"],msg["source_sha256"]) or
        msg.get("model_link_receipt_sha256")!=MODEL_RECEIPT or
        msg.get("last_verified_model_statement")!="HOLD" or
        msg.get("fresh_model_speech_on_this_task") is not False or
        msg.get("request_target_local_verification") is not True or
        any(msg.get(k) is not False for k in (
            "request_arbitrary_execution","request_model_weight_update",
            "request_production_update","request_sentinel_dispatch"))):
        raise ValueError("VOICE_TASK_ESCALATION_OR_BAD_ORIGIN")
    return msg

def assess_source(source_repo,raw):
    obj=json.loads(raw)
    if source_repo==D:
        if (obj.get("schema")!="janus.essence.continual_prospective_first_trial_evidence/4.9"
                or obj.get("status")!="HOLD_REPLAY_DID_NOT_CLEAR_PREDECLARED_GATES"
                or obj.get("deployment",{}).get("production_admission") is not False
                or obj.get("interpretation",{}).get("external_custodian") is not False
                or obj.get("results",{}).get("fresh_unseen_legacy_oracle",{}).get("replay_exact")!=16
                or obj.get("results",{}).get("lapis_paraphrased_source",{}).get("replay_exact")!=0):
            raise ValueError("VOICE_SOURCE_V49_FACTS_MISMATCH")
        return ("VERIFIED_V49_HOLD_SOURCE_ONLY",
                "Проверено: удержание 16/16, новые Lapis 0/6. Итог HOLD; допуск новой модели не разрешён.",
                {"old_route_exact":16,"new_lapis_exact":0,"model_admission":False})
    if (obj.get("schema")!="janus.essence.microkernel/0.1"
            or obj.get("repository")!=G or obj.get("enabled") is not False
            or obj.get("activation")!="EXPLICIT_READONLY_TEST_ONLY"
            or obj.get("birth_policy")!="PROPOSAL_ONLY"
            or len(obj.get("microkernels",[]))!=6
            or any(obj.get("capabilities",{}).values())):
        raise ValueError("VOICE_SOURCE_GENESIS_KERNEL_MISMATCH")
    return ("VERIFIED_GENESIS_NO_EXEC_RIGHTS",
            "Проверено: 6 микроядер Genesis описаны, но выполнение и запись отключены. Можно только предлагать задания.",
            {"microkernel_count":6,"untrusted_code_executed":False,"automatic_dispatch":False})

def make_reply(msg,for_repo,raw):
    validate_task(msg,for_repo)
    rawsha=hashlib.sha256(raw).hexdigest()
    if rawsha!=msg["source_sha256"]:
        raise ValueError("VOICE_SOURCE_SHA_MISMATCH")
    status,answer,evidence=assess_source(msg["source_repo"],raw)
    return sealed({
        "schema":REPLY,"task_id":msg["id"],"source_task_receipt_sha256":msg["receipt_sha256"],
        "source_repo":for_repo,"target_repo":msg["source_repo"],
        "status":status,"answer":answer,"source_sha256":rawsha,"evidence":evidence,
        "answered_by":"ESSENCE_TARGET_LOCAL_VERIFIER_NOT_GENERATIVE_MODEL",
        "new_model_inference":False,"foreign_code_executed":False,
        "delegated_arbitrary_execution":False,"production_authority":False,
        "sentinel_dispatch":False,
    })

def verify_reply(original,response,raw):
    verify_seal(response)
    expected=make_reply(original,original["target_repo"],raw)
    if response!=expected:
        raise ValueError("VOICE_REPLY_NOT_SOURCE_REPRODUCIBLE")
    return response

def accept_reply(original,reply,raw):
    verify_reply(original,reply,raw)
    return sealed({
        "schema":HEARD,"task_id":original["id"],
        "response_receipt_sha256":reply["receipt_sha256"],
        "status":"VERIFIED_PEER_REPLY_RECEIVED",
        "source_repo":original["source_repo"],"peer_repo":reply["source_repo"],
        "scientific_authority_delta":0,"production_authority":False,
        "sentinel_dispatch":False,
    })

def process(root,local_repo,commit,state_dir,peer_dir,fetch=fetch_public):
    root=Path(root);state=Path(state_dir);peer=Path(peer_dir)
    verify_manifest(root,local_repo)
    link=validate_model_link(load(root/".janus/essence/VOICE_MODEL_LINK.json"),local_repo)
    srcpath=root/TASKS[local_repo][1]
    raw=srcpath.read_bytes()
    if len(raw)>MAX: raise ValueError("VOICE_LOCAL_SOURCE_TOO_BIG")
    assess_source(local_repo,raw)
    own=make_task(local_repo,commit,raw,link)
    created={"proposed":0,"replied":0,"heard":0}
    task_path=state/"research/essence/voice_v51/messages"/(own["id"]+".json")
    if task_path.exists():
        # Reuse the exact prior source Git commit/receipt when unrelated main
        # code moves; never rewrite a stable task-id with new source metadata.
        previous=load(task_path)
        verify_seal(previous)
        if (previous.get("id")!=own["id"] or
                previous.get("source_sha256")!=own["source_sha256"] or
                previous.get("source_repo")!=local_repo or
                previous.get("target_repo")!=PEERS[local_repo]):
            raise ValueError("VOICE_EXISTING_TASK_NOT_SAME_SOURCE")
        own=previous
    else:
        created["proposed"]+=int(put_once(task_path,own))
    candidates=sorted((peer/"research/essence/voice_v51/messages").glob("*.json")) if (peer/"research/essence/voice_v51/messages").exists() else []
    if len(candidates)>48: raise ValueError("VOICE_BACKLOG_LIMIT")
    for path in candidates:
        if not NAME.fullmatch(path.name):raise ValueError("VOICE_UNSAFE_PEER_MESSAGE_FILENAME")
        msg=load(path)
        validate_task(msg,local_repo)
        if path.name != msg["id"]+".json":raise ValueError("VOICE_TASK_FILENAME_ID_MISMATCH")
        other_raw=fetch(msg["source_repo"],msg["source_commit"],msg["source_path"])
        reply=make_reply(msg,local_repo,other_raw)
        created["replied"]+=int(put_once(state/"research/essence/voice_v51/replies"/(msg["id"]+".json"),reply))
    answers=sorted((peer/"research/essence/voice_v51/replies").glob("*.json")) if (peer/"research/essence/voice_v51/replies").exists() else []
    if len(answers)>48:raise ValueError("VOICE_RESPONSE_BACKLOG_LIMIT")
    for path in answers:
        if not NAME.fullmatch(path.name):raise ValueError("VOICE_UNSAFE_REPLY_FILENAME")
        reply=load(path)
        if reply.get("task_id")!=own["id"]:continue
        ack=accept_reply(own,reply,raw)
        created["heard"]+=int(put_once(state/"research/essence/voice_v51/heard"/(own["id"]+".json"),ack))
    return sealed({
        "schema":"janus.essence.voice_mesh.run_receipt/5.1",
        "local_repo":local_repo,"peer_repo":PEERS[local_repo],
        "local_kernel_count":6,"model_link":"VERIFIED_REMOTE_QWEN_G2_RECEIPT",
        "new_tasks":created["proposed"],"new_replies":created["replied"],
        "new_verified_peer_replies":created["heard"],
        "own_task_id":own["id"],"root_execution_still_disabled":True,
        "production_changes":False,"sentinel_dispatch":False,
        "model_generated_task_text":False,
    })

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",default=".")
    p.add_argument("--repo",required=True,choices=list(PEERS))
    p.add_argument("--commit",required=True)
    p.add_argument("--state",required=True)
    p.add_argument("--peer",required=True)
    p.add_argument("--receipt",required=True)
    args=p.parse_args()
    receipt=process(args.root,args.repo,args.commit,args.state,args.peer)
    out=Path(args.receipt);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(receipt,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps(receipt,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
