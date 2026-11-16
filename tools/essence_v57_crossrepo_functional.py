#!/usr/bin/env python3
"""Read-only separate GitHub runner for accepted ESSENCE v5.7 functional G4.

Both genuine Qwen LoRA adapters are checked against independently received
state-branch tensor hashes and lineage. Never executes model-generated code,
trains, sends Sentinel commands, or alters production model weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

SCHEMA="janus.essence.v57.genesis_firstlook_functional_witness/5.7"
PLAN="janus.essence.v57.genesis_witness_plan/5.7"
LEDGER="janus.essence.v57.functional_shadow_ledger/5.7"
SOURCE="research/essence/functional_v57_state/ledger.json"
SUITE="research/essence/v57_transfer/FROZEN_CASES.json"
SUITE_SHA1="6d9ffceb0ed68595865e2b02077a112088a199e7"
RECEIPTS="research/essence/v57_transfer/receipts"
MODEL="Qwen/Qwen2.5-0.5B-Instruct"
BASE_REV="7ae557604adf67be50417f59c2c2f167def9a775"
PARENT_PATH="models/v54gen0003"
CHILD_PATH="models/v57funcgen0004"
PARENT_SHA="bc05f07916cab24ae4fe814971b1de7e4b60a948bad1e99df19bbad720b2ef8d"
PARENT_LINEAGE="9f8d54a6e3d497a46a12d3a27752caa710900e1c5b4a506f6477812d35162025"
CHILD_SHA="b9241064a6b0622df82c1402b256deee2a56cc87658f7e5cd3d02b2d6b6b4f1e"
CHILD_LINEAGE="55e74eee352a2e90a8ac7ff52e565fb05e4abe62da28eec8eeca474ee347682c"
EXAM_SHA="accc7c514af4f34ecf6f27e1bfa6bf2f585bf733da0a0377e0ff7fd489f24ffe"
SHA40=re.compile(r"^[0-9a-f]{40}$")
SHA64=re.compile(r"^[0-9a-f]{64}$")


def require(ok,reason):
    if not ok:
        raise ValueError("GENESIS_V57_"+reason)


def canonical(x):
    return json.dumps(x,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def sha(x):
    return hashlib.sha256(canonical(x)).hexdigest()


def sealed(x):
    return dict(x,sha256=sha(x))


def checked(x):
    require(isinstance(x,dict) and x.get("sha256")==sha({
        k:v for k,v in x.items() if k!="sha256"}),"INVALID_SEAL")
    return x


def unique(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,"DUPLICATE_JSON_KEY")
        d[k]=v
    return d


def read(path,limit=100_000):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and
            2<=p.stat().st_size<=limit,"UNSAFE_JSON_FILE")
    return json.loads(p.read_text(encoding="utf-8"),object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("GENESIS_V57_NONFINITE_JSON")))


def file_sha1(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"UNSAFE_BENCHMARK")
    raw=p.read_bytes()
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def cases(genesis):
    file=Path(genesis)/SUITE
    require(file_sha1(file)==SUITE_SHA1,"BENCHMARK_CHANGED")
    data=read(file,14000)
    require(data.get("schema")=="janus.essence.v57.cross_repo_functional_firstlook_suite/5.7"
        and data.get("frozen_before_first_real_g3_g4_inference") is True
        and data.get("training_in_receiver") is False
        and data.get("source_training_excluded") is True
        and data.get("production_promotion") is False
        and isinstance(data.get("items"),list) and len(data["items"])==24,
        "INVALID_FIRSTLOOK_SUITE")
    observed=set()
    for r in data["items"]:
        require(isinstance(r,dict) and set(r)=={"id","category","prompt","expected"}
          and isinstance(r["id"],str) and bool(re.fullmatch(r"T[0-9]{2}",r["id"]))
          and r["id"] not in observed and isinstance(r["prompt"],str)
          and 10<=len(r["prompt"])<=240 and isinstance(r["expected"],str)
          and 1<=len(r["expected"])<=15 and bool(re.fullmatch(r"[0-9]+",r["expected"])),
          "INVALID_FIRSTLOOK_ROW")
        observed.add(r["id"])
    return data["items"]


def head(repo):
    h=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],
                               text=True,timeout=10).strip()
    require(bool(SHA40.fullmatch(h)),"PRODUCER_NOT_COMMIT_PINNED")
    return h


def ledger(producer):
    obj=checked(read(Path(producer)/SOURCE,100_000))
    require(obj.get("schema")==LEDGER
      and obj.get("status")=="PASS_PROSPECTIVE_INTERNAL_FUNCTIONAL_GAIN"
      and obj.get("shadow_accepted") is True
      and obj.get("candidate_generation")==4
      and obj.get("parent_generation")==3
      and obj.get("parent_adapter_sha256")==PARENT_SHA
      and obj.get("candidate_adapter_sha256")==CHILD_SHA
      and obj.get("candidate_lineage_sha256")==CHILD_LINEAGE
      and obj.get("exam_sha256")==EXAM_SHA
      and obj.get("child_path")==CHILD_PATH
      and obj.get("production_promotion") is False
      and obj.get("sentinel_dispatch") is False
      and obj.get("external_validation") is False
      and obj.get("previously_correct_lost")==0
      and obj.get("newly_correct",0)>=3,
      "MODEL_NOT_ACCEPTED_OR_RESEARCH_ONLY")
    return obj


def adapter(producer,path,weight_sha,lineage_sha,generation):
    require(path in (PARENT_PATH,CHILD_PATH),"UNTRUSTED_ADAPTER_PATH")
    d=Path(producer)/path
    require(d.is_dir() and not d.is_symlink(),"MISSING_MODEL_DIRECTORY")
    weights=d/"adapter_model.safetensors"
    require(weights.is_file() and not weights.is_symlink()
            and 2000<=weights.stat().st_size<=6_000_000
            and hashlib.sha256(weights.read_bytes()).hexdigest()==weight_sha,
            "MODEL_BYTES_SHA_MISMATCH")
    meta=checked(read(d/"lineage.json",60000))
    require(meta.get("sha256")==lineage_sha
        and meta.get("adapter_sha256")==weight_sha
        and meta.get("generation")==generation
        and meta.get("parent_generation")==generation-1
        and meta.get("production_promotion") is False
        and meta.get("sentinel_dispatch") is False
        and (generation!=4 or meta.get("parent_adapter_sha256")==PARENT_SHA),
        "MODEL_LINEAGE_NOT_VERIFIED")
    return d


def verify_source(producer):
    obj=ledger(producer)
    adapter(producer,PARENT_PATH,PARENT_SHA,PARENT_LINEAGE,3)
    adapter(producer,CHILD_PATH,CHILD_SHA,CHILD_LINEAGE,4)
    return obj


def plan(producer,genesis,receiver):
    cases(genesis)
    d=verify_source(producer)
    filename=RECEIPTS+"/"+d["sha256"][:24]+"_"+SUITE_SHA1[:8]+".json"
    output=Path(receiver)/filename
    if output.exists():
        old=checked(read(output))
        require(old.get("source_ledger_sha256")==d["sha256"]
            and old.get("suite_git_blob_sha1")==SUITE_SHA1,
            "RECEIPT_REPLAY_COLLISION")
        return sealed({"schema":PLAN,"action":"ALREADY_TESTED",
                       "production_promotion":False})
    return sealed({"schema":PLAN,"action":"COMPARE_ACCEPTED_G3_G4",
        "producer_repository":"Hawkar-usls/Janus-Demiurge",
        "producer_commit":head(producer),"producer_branch":"essence-peer-shadow-state",
        "source_ledger_sha256":d["sha256"],
        "parent_model_sha256":PARENT_SHA,"accepted_model_sha256":CHILD_SHA,
        "candidate_generation":4,"suite_git_blob_sha1":SUITE_SHA1,
        "receipt_path":filename,
        "production_promotion":False,"sentinel_dispatch":False})


def verify_plan(p,producer,genesis):
    checked(p)
    require(p.get("schema")==PLAN and
        p.get("action")=="COMPARE_ACCEPTED_G3_G4" and
        p.get("producer_repository")=="Hawkar-usls/Janus-Demiurge" and
        p.get("producer_branch")=="essence-peer-shadow-state" and
        p.get("producer_commit")==head(producer) and
        p.get("suite_git_blob_sha1")==SUITE_SHA1 and
        p.get("parent_model_sha256")==PARENT_SHA and
        p.get("accepted_model_sha256")==CHILD_SHA and
        p.get("candidate_generation")==4 and
        p.get("production_promotion") is False and
        p.get("sentinel_dispatch") is False,
        "UNTRUSTED_OR_STALE_PLAN")
    obj=verify_source(producer)
    require(p.get("source_ledger_sha256")==obj["sha256"] and
            p.get("receipt_path")==RECEIPTS+"/"+obj["sha256"][:24]+
                       "_"+SUITE_SHA1[:8]+".json",
            "LEDGER_SHA_OR_RECEIPT_PATH_MISMATCH")
    cases(genesis)
    return p


def inference(p,producer,genesis):
    verify_plan(p,producer,genesis)
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    start=time.monotonic()
    torch.set_num_threads(4)
    tk=AutoTokenizer.from_pretrained(MODEL,revision=BASE_REV,
                                    trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained(MODEL,revision=BASE_REV,
        use_safetensors=True,torch_dtype=torch.float32,
        trust_remote_code=False).to("cpu")
    require(getattr(base.config,"_commit_hash",None)==BASE_REV,
            "BASE_MODEL_REVISION_DRIFT")
    model=PeftModel.from_pretrained(base,str(Path(producer)/PARENT_PATH),
                                    is_trainable=False).to("cpu").eval()
    model.load_adapter(str(Path(producer)/CHILD_PATH),
                        adapter_name="functional_g4",is_trainable=False)
    out=[]
    for row in cases(genesis):
        ids=tk.apply_chat_template([{"role":"user","content":row["prompt"]}],
             tokenize=True,add_generation_prompt=True,return_tensors="pt")
        require(ids.shape[1]<=220,"UNBOUNDED_PROMPT")
        answers={}
        for model_name,adapter_name in (("g3","default"),("g4","functional_g4")):
            model.set_adapter(adapter_name)
            with torch.inference_mode():
                output=model.generate(ids,attention_mask=torch.ones_like(ids),
                     max_new_tokens=32,do_sample=False,
                     pad_token_id=tk.eos_token_id)
            answer=tk.decode(output[0,ids.shape[1]:],
                             skip_special_tokens=True).strip()
            require(len(answer)<=256,"UNBOUNDED_ANSWER")
            answers[model_name]={"exact":answer==row["expected"],
                "answer_sha256":hashlib.sha256(answer.encode()).hexdigest()}
        out.append({"id":row["id"],"category":row["category"],
                    "g3_exact":answers["g3"]["exact"],
                    "g4_exact":answers["g4"]["exact"],
                    "g3_answer_sha256":answers["g3"]["answer_sha256"],
                    "g4_answer_sha256":answers["g4"]["answer_sha256"]})
    p_correct=sum(x["g3_exact"] for x in out)
    c_correct=sum(x["g4_exact"] for x in out)
    gained=sum(not x["g3_exact"] and x["g4_exact"] for x in out)
    lost=sum(x["g3_exact"] and not x["g4_exact"] for x in out)
    status=("PASS_INTERNAL_CROSS_REPO_FUNCTIONAL_TRANSFER"
            if gained>=2 and lost==0 and c_correct>p_correct else
            "HOLD_CROSS_REPO_FUNCTIONAL_TRANSFER")
    return sealed({"schema":SCHEMA,"status":status,
       "source_repository":"Hawkar-usls/Janus-Demiurge",
       "consumer_repository":"Hawkar-usls/Janus_Genesis",
       "source_commit":p["producer_commit"],
       "source_ledger_sha256":p["source_ledger_sha256"],
       "suite_git_blob_sha1":SUITE_SHA1,
       "parent_model_sha256":PARENT_SHA,"candidate_model_sha256":CHILD_SHA,
       "parent_generation":3,"candidate_generation":4,
       "task_count":len(out),"g3_exact":p_correct,"g4_exact":c_correct,
       "newly_correct":gained,"previously_correct_lost":lost,
       "per_task":out,"real_qwen_cpu_inference":True,
       "model_code_execution":False,"receiver_training":False,
       "evidence_level":"SAME_OWNER_SEPARATE_REPOSITORY_FIRST_LOOK",
       "production_promotion":False,"sentinel_dispatch":False,
       "external_validation":False,
       "elapsed_seconds":round(time.monotonic()-start,3)})


def write_once(path,d):
    p=Path(path)
    require(not p.exists() and not p.is_symlink(),"RECEIPT_REPLAY")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(json.dumps(d,sort_keys=True,indent=2,
                             ensure_ascii=False).encode()+b"\n")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("phase",choices=("plan","infer"))
    ap.add_argument("--producer",required=True)
    ap.add_argument("--genesis",required=True)
    ap.add_argument("--receiver")
    ap.add_argument("--plan")
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    if a.phase=="plan":
        require(bool(a.receiver),"MISSING_RECEIVER")
        result=plan(a.producer,a.genesis,a.receiver)
    else:
        require(bool(a.plan),"MISSING_SIGNED_PLAN")
        result=inference(read(a.plan),a.producer,a.genesis)
    write_once(a.out,result)
    print(json.dumps({"phase":a.phase,
        "decision":result.get("status",result.get("action")),
        "production_promotion":False},sort_keys=True))


if __name__=="__main__":
    main()
