#!/usr/bin/env python3
"""Genesis ESSENCE: receive actual Demiurge Qwen text as an untrusted peer turn."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "essence_voice_transport",str(ROOT/".janus/essence/voice_mesh_v51.py"))
mesh=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mesh)

SCHEMA="janus.essence.voice_mesh.qwen_spoken_turn/5.1"
RESPONSE="janus.essence.voice_mesh.qwen_speech_review/5.1"


def verify_speech(speech,request,demiurge_reply,raw_genesis_manifest):
    mesh.verify_seal(speech)
    mesh.validate_task(request,mesh.D)
    mesh.verify_reply(request,demiurge_reply,raw_genesis_manifest)
    if (speech.get("schema")!=SCHEMA or
        speech.get("source_repo")!=mesh.D or
        speech.get("target_repo")!=mesh.G or
        speech.get("origin_genesis_task_id")!=request["id"] or
        speech.get("origin_genesis_task_receipt")!=request["receipt_sha256"] or
        speech.get("demiurge_checked_reply_sha256")!=demiurge_reply["receipt_sha256"] or
        speech.get("model_id")!="Qwen/Qwen2.5-0.5B-Instruct" or
        speech.get("model_adapter_sha256")!="1ec5b21689ee5af6eec5345e0f5b91fc0870ffa520a56ef8778ce914ac28f3bc" or
        speech.get("model_parent_lineage_sha256")!="bea00f89a3e03b05faaed901afdb6cdd0c7f5f70293615250c20dec171196b6c" or
        speech.get("model_weights_loaded_for_fresh_inference") is not True or
        speech.get("from_microkernel")!="cell-planning-02" or
        speech.get("to_microkernel")!="cell-verification-03" or
        speech.get("execution_allowed") is not False or
        speech.get("untrusted_speech_is_source_evidence") is not False or
        speech.get("auto_dispatch_from_speech") is not False or
        speech.get("training_or_production_change") is not False or
        speech.get("sentinel_dispatch") is not False):
        raise ValueError("UNAUTHORIZED_QWEN_PEER_SPEECH")
    text=speech.get("raw_model_statement")
    if (not isinstance(text,str) or len(text)>440 or
        any(ord(c)<32 and c not in ("\n","\t") for c in text) or
        speech.get("status")!=(
            "NEW_MODEL_SPEECH_UNTRUSTED_RESEARCH_QUESTION" if text
            else "HOLD_EMPTY_MODEL_SPEECH")):
        raise ValueError("MALFORMED_OR_OVERSIZED_QWEN_SPEECH")
    if not mesh.HASH64.fullmatch(speech.get("prompt_sha256","")):
        raise ValueError("MISSING_QWEN_PROMPT_COMMITMENT")
    return speech


def review(speech,request,demiurge_reply,raw_genesis_manifest):
    verify_speech(speech,request,demiurge_reply,raw_genesis_manifest)
    return mesh.sealed({
        "schema":RESPONSE,
        "source_repo":mesh.G,"target_repo":mesh.D,
        "origin_task_id":request["id"],
        "model_utterance_receipt":speech["receipt_sha256"],
        "model_raw_text_sha256":mesh.digest({"raw":speech["raw_model_statement"]}),
        "microkernel_receiver":"cell-verification-03",
        "review_status":"UNTRUSTED_NEURAL_QUESTION_RECEIVED_NO_NEW_DELEGATION",
        "answer":"Принято как необязательное исследовательское предложение; исходное проверенное ограничение Genesis — шесть микроядер, исполнение отключено. Нужна отдельная проверка каждой новой гипотезы.",
        "source_is_verified":True,
        "natural_language_is_not_verified_facts":True,
        "model_question_is_not_workflow_command":True,
        "automatic_tasks_spawned":0,
        "external_independent_science":False,
        "model_weights_changed":False,
        "production_authority":False,
        "sentinel_dispatch":False,
    })


def process(root,state,peer):
    root=Path(root);state=Path(state);peer=Path(peer)
    mesh.verify_manifest(root,mesh.G)
    speech_dir=peer/"research/essence/voice_v51/model_utterances"
    if not speech_dir.exists():
        return {"status":"HOLD_NO_QWEN_SPEECH_YET","reviewed":0}
    files=sorted(speech_dir.glob("*.json"))
    if len(files)>24:
        raise ValueError("UNBOUNDED_MODEL_SPEECH_INBOX")
    accepted=0
    for path in files:
        if not mesh.NAME.fullmatch(path.name):
            raise ValueError("UNSAFE_MODEL_SPEECH_FILENAME")
        original=mesh.load(state/"research/essence/voice_v51/messages"/path.name)
        source=mesh.fetch_public(mesh.G,original["source_commit"],original["source_path"])
        reply=mesh.load(peer/"research/essence/voice_v51/replies"/path.name)
        speech=mesh.load(path)
        record=review(speech,original,reply,source)
        out=state/"research/essence/voice_v51/model_reviews"/path.name
        accepted+=int(mesh.put_once(out,record))
    return {"status":"QWEN_SPEECH_REVIEWED_AS_UNTRUSTED_ONLY",
            "new_model_speech_reviews":accepted,
            "model_command_executed":False,"production_authority":False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--state",required=True)
    p.add_argument("--peer",required=True)
    p.add_argument("--receipt",required=True)
    a=p.parse_args()
    result=process(a.root,a.state,a.peer)
    dest=Path(a.receipt)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,ensure_ascii=False))


if __name__=="__main__":
    main()
