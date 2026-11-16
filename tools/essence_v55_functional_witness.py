#!/usr/bin/env python3
"""Independent-runner, same-owner first-look FUNCTIONAL transfer test for JANUS.

Compare accepted ESSENCE v5.5 descendant against frozen G3 on 16 algorithmic
questions never used in repo-metadata LoRA training. No dynamic code from
either model is executed. No production model / Sentinel changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

SCHEMA="janus.essence.v55.genesis_functional_transfer_witness/5.5"
PLAN="janus.essence.v55.function_transfer_plan/5.5"
LEDGER="janus.essence.v55.shadow_ledger/5.5"
SOURCE_STATE="research/essence/peer_v55_state/ledger.json"
SUITE="research/essence/v55_functional/FROZEN_CASES.json"
SUITE_BLOB="e76dca95402ccaf9deb5d0d8174757e4417c4c7f"
RECEIPTS="research/essence/v55_functional/receipts"
BASE="Qwen/Qwen2.5-0.5B-Instruct"
REV="7ae557604adf67be50417f59c2c2f167def9a775"
G3="bc05f07916cab24ae4fe814971b1de7e4b60a948bad1e99df19bbad720b2ef8d"
G3_LINEAGE="9f8d54a6e3d497a46a12d3a27752caa710900e1c5b4a506f6477812d35162025"
G3_EXAM="97249bb17665069a527beff88645643035cd4b87106f23bdf39a639b23eb6af6"
SHA40=re.compile("^[a-f0-9]{40}$")
SHA64=re.compile("^[a-f0-9]{64}$")
PATH=re.compile("^models/v55gen000[4-9]$")
CURRENT_G3="models/v54gen0003"


def require(value,tag):
    if not value: raise ValueError(tag)


def canonical(d):
    return json.dumps(d,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def digest(d):
    return hashlib.sha256(canonical(d)).hexdigest()


def seal(d):
    return dict(d,sha256=digest(d))


def check(d):
    require(isinstance(d,dict) and d.get("sha256")==digest({
        k:v for k,v in d.items() if k!="sha256"}),"WF55_UNSEALED")
    return d


def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,"WF55_DUPLICATE_JSON_KEY")
        result[k]=v
    return result


def read(path,limit=120_000):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and
            2<=p.stat().st_size<=limit,"WF55_UNSAFE_JSON")
    return json.loads(p.read_text(encoding="utf-8"),
             object_pairs_hook=unique,
             parse_constant=lambda _: (_ for _ in ()).throw(
                 ValueError("WF55_NONFINITE_JSON")))


def head(repo):
    result=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],
                                   text=True,timeout=10).strip()
    require(bool(SHA40.fullmatch(result)),"WF55_NOT_GIT_PINNED")
    return result


def git_blob(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"WF55_UNSAFE_TEST_SUITE")
    return hashlib.sha1(b"blob "+str(p.stat().st_size).encode()+b"\0"+
                        p.read_bytes()).hexdigest()


def cases(root):
    file=Path(root)/SUITE
    require(git_blob(file)==SUITE_BLOB,"WF55_FROZEN_SUITE_CHANGED")
    suite=read(file,16000)
    require(suite.get("schema")=="janus.essence.v55.first_look_functional_cases/5.5"
            and suite.get("task_policy")=="FROZEN_BEFORE_FIRST_G3_VS_GN_INFERENCE"
            and suite.get("source_training_excluded") is True
            and suite.get("production_promotion") is False
            and isinstance(suite.get("items"),list)
            and len(suite["items"])==16,"WF55_BAD_FROZEN_SUITE")
    ids=set()
    for item in suite["items"]:
        require(isinstance(item,dict) and set(item)==
                {"id","prompt","expected","category"} and
                isinstance(item["id"],str) and
                re.fullmatch("A[0-9]{2}",item["id"]) is not None and
                item["id"] not in ids and
                isinstance(item["prompt"],str) and
                5<=len(item["prompt"])<=220 and
                isinstance(item["expected"],str) and
                1<=len(item["expected"])<=12 and
                isinstance(item["category"],str),
                "WF55_BAD_CHALLENGE_ROW")
        ids.add(item["id"])
    return suite["items"]


def validate_ledger(d):
    check(d)
    require(d.get("schema")==LEDGER and
            d.get("parent_v54_acceptance_exam_sha256")==G3_EXAM and
            d.get("production_promotion") is False and
            d.get("sentinel_dispatch") is False and
            d.get("external_validation") is False and
            isinstance(d.get("attempts"),list) and
            isinstance(d.get("admitted"),list) and
            len(d["attempts"])<=36 and len(d["admitted"])<=6 and
            type(d.get("current_generation")) is int and
            3<=d["current_generation"]<=9,
            "WF55_UNTRUSTED_STATE")
    gen=3
    adapter=G3
    lineage=G3_LINEAGE
    for accepted in d["admitted"]:
        require(isinstance(accepted,dict) and
                accepted.get("generation")==gen+1 and
                accepted.get("parent_adapter_sha256")==adapter and
                bool(SHA64.fullmatch(str(accepted.get("adapter_sha256","")))) and
                bool(SHA64.fullmatch(str(accepted.get("lineage_sha256","")))) and
                bool(SHA64.fullmatch(str(accepted.get("exam_sha256","")))) and
                accepted.get("external_validation") is False and
                any(a.get("status")=="PASS_INTERNAL_SHADOW" and
                    a.get("shadow_accepted") is True and
                    a.get("exam_sha256")==accepted["exam_sha256"] and
                    a.get("candidate_generation")==gen+1 for a in d["attempts"]),
                "WF55_ACCEPTANCE_CHAIN_BROKEN")
        gen+=1
        adapter=accepted["adapter_sha256"]
        lineage=accepted["lineage_sha256"]
    require(gen==d["current_generation"] and
            adapter==d.get("current_adapter_sha256") and
            lineage==d.get("current_lineage_sha256") and
            d.get("current_parent_path")==(
                CURRENT_G3 if gen==3 else f"models/v55gen{gen:04d}") and
            sum(a.get("shadow_accepted") is True for a in d["attempts"])==
            len(d["admitted"]) and
            all(a.get("production_promotion") is False and
                a.get("status") in ("PASS_INTERNAL_SHADOW","HOLD_NOT_BETTER")
                for a in d["attempts"]),
            "WF55_CURRENT_PARENT_NOT_SUPPORTED")
    return d


def verify_adapter(root,path,sha,lineage,gen):
    require(path==CURRENT_G3 or bool(PATH.fullmatch(path)),
            "WF55_UNTRUSTED_MODEL_PATH")
    folder=Path(root)/path
    require(folder.is_dir() and not folder.is_symlink(),"WF55_MISSING_ADAPTER")
    weights=folder/"adapter_model.safetensors"
    require(weights.is_file() and not weights.is_symlink() and
            2000<=weights.stat().st_size<=6_000_000 and
            hashlib.sha256(weights.read_bytes()).hexdigest()==sha,
            "WF55_MODEL_BYTES_MISMATCH")
    rec=check(read(folder/"lineage.json",60000))
    require(rec.get("adapter_sha256")==sha and
            rec.get("sha256")==lineage and
            rec.get("generation")==gen and
            rec.get("production_promotion") is False and
            rec.get("sentinel_dispatch") is False and
            rec.get("parent_generation")==gen-1,
            "WF55_MODEL_LINEAGE_MISMATCH")
    return folder


def plan(producer,receiver,genesis):
    cases(genesis)  # test blob was committed before any model evaluation
    ledger_file=Path(producer)/SOURCE_STATE
    if not ledger_file.is_file():
        return seal({"schema":PLAN,"action":"WAIT_FOR_ACCEPTED_MODEL",
                     "production_promotion":False})
    ledger=validate_ledger(read(ledger_file))
    if ledger["current_generation"]<=3:
        return seal({"schema":PLAN,"action":"WAIT_FOR_DESCENDANT",
                     "production_promotion":False})
    path=ledger["current_parent_path"]
    verify_adapter(producer,CURRENT_G3,G3,G3_LINEAGE,3)
    verify_adapter(producer,path,ledger["current_adapter_sha256"],
                   ledger["current_lineage_sha256"],ledger["current_generation"])
    token=ledger["sha256"][:24]
    receipt=RECEIPTS+"/"+token+".json"
    previous=Path(receiver)/receipt
    if previous.exists():
        old=check(read(previous))
        require(old.get("ledger_sha256")==ledger["sha256"],
                "WF55_RECEIPT_REPLAY_COLLISION")
        return seal({"schema":PLAN,"action":"ALREADY_WITNESSED",
                     "ledger_sha256":ledger["sha256"],
                     "production_promotion":False})
    return seal({"schema":PLAN,"action":"PAIR_G3_AGAINST_ACCEPTED_DESCENDANT",
       "producer_repo":"Hawkar-usls/Janus-Demiurge",
       "producer_commit":head(producer),
       "producer_branch":"essence-peer-shadow-state",
       "ledger_sha256":ledger["sha256"],
       "g3_adapter_sha256":G3,
       "g3_lineage_sha256":G3_LINEAGE,
       "candidate_generation":ledger["current_generation"],
       "candidate_path":path,
       "candidate_adapter_sha256":ledger["current_adapter_sha256"],
       "candidate_lineage_sha256":ledger["current_lineage_sha256"],
       "suite_blob_sha1":SUITE_BLOB,
       "receipt_file":receipt,
       "production_promotion":False,
       "sentinel_dispatch":False})


def verify_plan(p,producer,genesis):
    check(p)
    require(p.get("schema")==PLAN and
            p.get("action")=="PAIR_G3_AGAINST_ACCEPTED_DESCENDANT" and
            p.get("producer_repo")=="Hawkar-usls/Janus-Demiurge" and
            p.get("producer_branch")=="essence-peer-shadow-state" and
            p.get("producer_commit")==head(producer) and
            p.get("suite_blob_sha1")==SUITE_BLOB and
            p.get("production_promotion") is False and
            p.get("sentinel_dispatch") is False,"WF55_UNTRUSTED_PLAN")
    ledger=validate_ledger(read(Path(producer)/SOURCE_STATE))
    require(p.get("ledger_sha256")==ledger["sha256"] and
            p.get("g3_adapter_sha256")==G3 and
            p.get("g3_lineage_sha256")==G3_LINEAGE and
            p.get("candidate_generation")==ledger["current_generation"] and
            p.get("candidate_path")==ledger["current_parent_path"] and
            p.get("candidate_adapter_sha256")==ledger["current_adapter_sha256"] and
            p.get("candidate_lineage_sha256")==ledger["current_lineage_sha256"] and
            p.get("receipt_file")==RECEIPTS+"/"+ledger["sha256"][:24]+".json",
            "WF55_STALE_PLAN")
    cases(genesis)
    verify_adapter(producer,CURRENT_G3,G3,G3_LINEAGE,3)
    verify_adapter(producer,p["candidate_path"],
                   p["candidate_adapter_sha256"],
                   p["candidate_lineage_sha256"],p["candidate_generation"])
    return p


def inference(p,producer,genesis):
    verify_plan(p,producer,genesis)
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    started=time.monotonic()
    torch.set_num_threads(4)
    tk=AutoTokenizer.from_pretrained(BASE,revision=REV,trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained(BASE,revision=REV,
            torch_dtype=torch.float32,trust_remote_code=False,
            use_safetensors=True).to("cpu")
    require(getattr(base.config,"_commit_hash",None)==REV,"WF55_BASE_MODEL_UNPINNED")
    model=PeftModel.from_pretrained(base,str(Path(producer)/CURRENT_G3),
                                   is_trainable=False).to("cpu").eval()
    model.load_adapter(str(Path(producer)/p["candidate_path"]),
                       adapter_name="candidate",is_trainable=False)
    challenge=cases(genesis)
    results=[]
    for row in challenge:
        tokens=tk.apply_chat_template([{"role":"user","content":row["prompt"]}],
            tokenize=True,add_generation_prompt=True,return_tensors="pt")
        require(tokens.shape[1]<=200,"WF55_UNBOUNDED_PROMPT")
        outputs={}
        for name,adapter in (("g3","default"),("descendant","candidate")):
            model.set_adapter(adapter)
            with torch.inference_mode():
                response=model.generate(tokens,attention_mask=torch.ones_like(tokens),
                      max_new_tokens=24,do_sample=False,pad_token_id=tk.eos_token_id)
            text=tk.decode(response[0,tokens.shape[1]:],
                           skip_special_tokens=True).strip()
            require(len(text)<=200,"WF55_UNBOUNDED_RESPONSE")
            outputs[name]={"exact":text==row["expected"],
                           "response_sha256":hashlib.sha256(text.encode()).hexdigest()}
        results.append({"id":row["id"],"category":row["category"],
                        "g3_exact":outputs["g3"]["exact"],
                        "candidate_exact":outputs["descendant"]["exact"],
                        "g3_answer_sha256":outputs["g3"]["response_sha256"],
                        "candidate_answer_sha256":outputs["descendant"]["response_sha256"]})
    g3_score=sum(x["g3_exact"] for x in results)
    candidate_score=sum(x["candidate_exact"] for x in results)
    gains=sum(x["candidate_exact"] and not x["g3_exact"] for x in results)
    losses=sum(x["g3_exact"] and not x["candidate_exact"] for x in results)
    status=("PASS_PROSPECTIVE_INTERNAL_FUNCTIONAL_TRANSFER"
            if gains>=1 and losses==0 and candidate_score>g3_score else
            "HOLD_FUNCTIONAL_TRANSFER_NOT_PROVEN")
    return seal({"schema":SCHEMA,"status":status,
      "consumer_repo":"Hawkar-usls/Janus_Genesis",
      "producer_repo":p["producer_repo"],
      "producer_commit":p["producer_commit"],
      "ledger_sha256":p["ledger_sha256"],
      "frozen_test_git_blob_sha1":SUITE_BLOB,
      "accepted_generation":p["candidate_generation"],
      "accepted_adapter_sha256":p["candidate_adapter_sha256"],
      "reference_generation":3,"reference_adapter_sha256":G3,
      "task_count":len(results),
      "g3_exact":g3_score,"candidate_exact":candidate_score,
      "newly_correct":gains,"previously_correct_lost":losses,
      "per_task":results,
      "real_cpu_qwen_inference":True,
      "model_text_executed_as_code":False,
      "receiver_training":False,
      "evidence_level":"SAME_OWNER_CROSS_REPO_FIRST_LOOK_INTERNAL",
      "external_validation":False,"production_promotion":False,
      "sentinel_dispatch":False,
      "elapsed_seconds":round(time.monotonic()-started,3)})


def write(path,obj):
    p=Path(path)
    require(not p.exists() and not p.is_symlink(),"WF55_RECEIPT_ALREADY_EXISTS")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False).encode()+b"\n")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("phase",choices=("plan","infer"))
    ap.add_argument("--producer",required=True)
    ap.add_argument("--genesis",required=True)
    ap.add_argument("--receiver")
    ap.add_argument("--plan")
    ap.add_argument("--out",required=True)
    x=ap.parse_args()
    if x.phase=="plan":
        require(bool(x.receiver),"WF55_RECEIVER_REQUIRED")
        result=plan(x.producer,x.receiver,x.genesis)
    else:
        require(bool(x.plan),"WF55_PLAN_REQUIRED")
        result=inference(read(x.plan),x.producer,x.genesis)
    write(x.out,result)
    print(json.dumps({"phase":x.phase,
       "status":result.get("status",result.get("action")),
       "generation":result.get("accepted_generation"),
       "production_promotion":False},sort_keys=True))


if __name__=="__main__":
    main()
