#!/usr/bin/env python3
"""ESSENCE v5.4 read-only GitHub-to-GitHub Qwen lineage consumption.

An independent Genesis Actions runner reads an accepted Demiurge shadow
generation, verifies its hash chain, loads the exact adapter and performs
real inference. It never trains on peer text or changes a production model.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

SCHEMA="janus.essence.v54.cross_repo_neural_witness/5.4"
PLAN="janus.essence.v54.cross_repo_witness_plan/5.4"
LEDGER="janus.essence.v54.shadow_ledger/5.4"
STATE="research/essence/peer_v54_state/ledger.json"
MODEL="Qwen/Qwen2.5-0.5B-Instruct"
REVISION="7ae557604adf67be50417f59c2c2f167def9a775"
G2_SHA="1ec5b21689ee5af6eec5345e0f5b91fc0870ffa520a56ef8778ce914ac28f3bc"
G2_LINEAGE="bea00f89a3e03b05faaed901afdb6cdd0c7f5f70293615250c20dec171196b6c"
SHA64=re.compile(r"^[a-f0-9]{64}$")
SHA40=re.compile(r"^[a-f0-9]{40}$")
MODEL_PATH=re.compile(r"^models/(?:gen0002|v54gen000[3-8])$")
RECEIPT_DIR="research/essence/v54_witness/receipts"


def require(ok,tag):
    if not ok:
        raise ValueError(tag)


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,
                separators=(",",":"),allow_nan=False).encode()).hexdigest()


def seal(obj):
    return dict(obj,sha256=digest(obj))


def check(obj):
    require(isinstance(obj,dict) and obj.get("sha256")==digest({
            k:v for k,v in obj.items() if k!="sha256"}),"W54_BROKEN_SEAL")
    return obj


def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,"W54_DUPLICATE_JSON_KEY")
        result[k]=v
    return result


def read(path,limit=100_000):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and
            2<=path.stat().st_size<=limit,"W54_UNSAFE_READ")
    return json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=unique,
             parse_constant=lambda _: (_ for _ in ()).throw(
                 ValueError("W54_NONFINITE_JSON")))


def write_once(path,obj):
    path=Path(path)
    require(not path.exists() and not path.is_symlink(),"W54_REPLAY_RECEIPT")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+"\n")


def head(root):
    x=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],
                              text=True,timeout=10).strip()
    require(bool(SHA40.fullmatch(x)),"W54_UNPINNED_REPOSITORY")
    return x


def validate_ledger(obj):
    check(obj)
    require(obj.get("schema")==LEDGER and
            obj.get("production_promotion") is False and
            obj.get("sentinel_dispatch") is False and
            obj.get("external_validation") is False and
            isinstance(obj.get("attempts"),list) and
            isinstance(obj.get("admitted"),list) and
            len(obj["attempts"])<=24 and len(obj["admitted"])<=6 and
            isinstance(obj.get("current_generation"),int) and
            2<=obj["current_generation"]<=8 and
            isinstance(obj.get("current_parent_path"),str) and
            MODEL_PATH.fullmatch(obj["current_parent_path"]) is not None,
            "W54_ESCALATED_OR_INVALID_LEDGER")
    generation=2
    adapter=G2_SHA
    lineage=G2_LINEAGE
    for admitted in obj["admitted"]:
        require(isinstance(admitted,dict) and
                admitted.get("generation")==generation+1 and
                admitted.get("parent_adapter_sha256")==adapter and
                isinstance(admitted.get("adapter_sha256"),str) and
                bool(SHA64.fullmatch(admitted["adapter_sha256"])) and
                isinstance(admitted.get("lineage_sha256"),str) and
                bool(SHA64.fullmatch(admitted["lineage_sha256"])) and
                admitted.get("external_validation") is False,
                "W54_PARENT_CHAIN_BREAK")
        generation+=1
        adapter=admitted["adapter_sha256"]
        lineage=admitted["lineage_sha256"]
    require(obj["current_generation"]==generation and
            obj.get("current_adapter_sha256")==adapter and
            obj.get("current_lineage_sha256")==lineage and
            obj["current_parent_path"]==
                ("models/gen0002" if generation==2 else f"models/v54gen{generation:04d}") and
            sum(row.get("shadow_accepted") is True for row in obj["attempts"])==
                len(obj["admitted"]) and
            all(row.get("production_promotion") is False and
                row.get("status") in ("PASS_INTERNAL_SHADOW","HOLD_NOT_BETTER")
                for row in obj["attempts"]),
            "W54_CURRENT_PARENT_NOT_ACCEPTED")
    return obj


def exact_adapter(producer,ledger):
    path=Path(producer)/ledger["current_parent_path"]
    require(path.is_dir() and not path.is_symlink() and
            all(not x.is_symlink() for x in path.parents),
            "W54_UNTRUSTED_CHECKPOINT_DIRECTORY")
    weights=path/"adapter_model.safetensors"
    require(weights.is_file() and not weights.is_symlink() and
            2000<=weights.stat().st_size<=6_000_000 and
            hashlib.sha256(weights.read_bytes()).hexdigest()==
                ledger["current_adapter_sha256"],
            "W54_WEIGHT_BYTES_MISMATCH")
    meta=check(read(path/"lineage.json",50_000))
    require(meta.get("sha256")==ledger["current_lineage_sha256"] and
            meta.get("adapter_sha256")==ledger["current_adapter_sha256"] and
            meta.get("sentinel_dispatch") in (False,None) and
            meta.get("production_promotion") in (False,None),
            "W54_MODEL_LINEAGE_DRIFT")
    return path


def plan(producer,receiver):
    ledgerfile=Path(producer)/STATE
    if not ledgerfile.exists():
        return seal({"schema":PLAN,"action":"WAIT_FOR_FIRST_V54_LINEAGE",
                     "production_promotion":False})
    ledger=validate_ledger(read(ledgerfile))
    model=exact_adapter(producer,ledger)
    revision=head(producer)
    ticket=ledger["sha256"][:24]
    out=Path(receiver)/RECEIPT_DIR/(ticket+".json")
    if out.exists():
        check(read(out))
        return seal({"schema":PLAN,"action":"ALREADY_WITNESSED",
                     "ledger_sha256":ledger["sha256"],
                     "production_promotion":False})
    return seal({"schema":PLAN,"action":"CONSUME_VERIFIED_MODEL",
        "producer_repo":"Hawkar-usls/Janus-Demiurge",
        "producer_branch":"essence-peer-shadow-state",
        "producer_commit":revision,
        "model_path":str(model.relative_to(producer)),
        "model_adapter_sha256":ledger["current_adapter_sha256"],
        "model_lineage_sha256":ledger["current_lineage_sha256"],
        "generation":ledger["current_generation"],
        "ledger_sha256":ledger["sha256"],
        "receipt_file":RECEIPT_DIR+"/"+ticket+".json",
        "production_promotion":False,
        "sentinel_dispatch":False})


def verify_plan(p,producer):
    check(p)
    require(p.get("schema")==PLAN and p.get("action")=="CONSUME_VERIFIED_MODEL"
         and p.get("producer_repo")=="Hawkar-usls/Janus-Demiurge"
         and p.get("producer_branch")=="essence-peer-shadow-state"
         and p.get("producer_commit")==head(producer)
         and p.get("production_promotion") is False
         and p.get("sentinel_dispatch") is False,"W54_UNTRUSTED_PLAN")
    ledger=validate_ledger(read(Path(producer)/STATE))
    require(p.get("ledger_sha256")==ledger["sha256"] and
         p.get("model_path")==ledger["current_parent_path"] and
         p.get("model_adapter_sha256")==ledger["current_adapter_sha256"] and
         p.get("model_lineage_sha256")==ledger["current_lineage_sha256"] and
         p.get("generation")==ledger["current_generation"] and
         p.get("receipt_file")==RECEIPT_DIR+"/"+ledger["sha256"][:24]+".json",
         "W54_STALE_SOURCE_REVIEW")
    exact_adapter(producer,ledger)
    return p


def consume(p,producer,genesis):
    verify_plan(p,producer)
    source=read(Path(genesis)/"PROJECT_STATUS.json")
    require(source.get("project")=="Janus Genesis","W54_UNREVIEWED_RECEIVER_SOURCE")
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    started=time.monotonic()
    torch.set_num_threads(4)
    tk=AutoTokenizer.from_pretrained(MODEL,revision=REVISION,trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained(
         MODEL,revision=REVISION,torch_dtype=torch.float32,
         trust_remote_code=False,use_safetensors=True).to("cpu")
    require(getattr(base.config,"_commit_hash",None)==REVISION,"W54_UNPINNED_BASE")
    model=PeftModel.from_pretrained(base,str(Path(producer)/p["model_path"]),
                                  is_trainable=False).to("cpu").eval()
    question=("In Hawkar-usls/Janus_Genesis/PROJECT_STATUS.json, "
              "what is the exact value of project? Output only the value.")
    ids=tk.apply_chat_template([{"role":"user","content":question}],
         tokenize=True,add_generation_prompt=True,return_tensors="pt")
    with torch.inference_mode():
        out=model.generate(ids,attention_mask=torch.ones_like(ids),
           max_new_tokens=24,do_sample=False,pad_token_id=tk.eos_token_id)
    reply=tk.decode(out[0,ids.shape[1]:],skip_special_tokens=True).strip()
    require(len(reply)<300,"W54_UNBOUNDED_GENERATION")
    return seal({"schema":SCHEMA,
        "consumer_repo":"Hawkar-usls/Janus_Genesis",
        "producer_repo":p["producer_repo"],
        "producer_branch":p["producer_branch"],
        "producer_commit":p["producer_commit"],
        "ledger_sha256":p["ledger_sha256"],
        "adapter_sha256":p["model_adapter_sha256"],
        "lineage_sha256":p["model_lineage_sha256"],
        "generation":p["generation"],
        "genesis_source_commit":head(genesis),
        "prompt_sha256":hashlib.sha256(question.encode()).hexdigest(),
        "answer_sha256":hashlib.sha256(reply.encode()).hexdigest(),
        "answer_exact_to_source":reply==source["project"],
        "real_qwen_cpu_inference":True,
        "elapsed_seconds":round(time.monotonic()-started,3),
        "evidence_level":"SAME_OWNER_CROSS_REPO_INTERNAL_WITNESS",
        "weight_training_in_receiver":False,
        "production_promotion":False,"sentinel_dispatch":False})


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("phase",choices=("plan","consume"))
    ap.add_argument("--producer",required=True)
    ap.add_argument("--receiver")
    ap.add_argument("--genesis")
    ap.add_argument("--plan")
    ap.add_argument("--out",required=True)
    ap.add_argument("--registry-release")
    ap.add_argument("--registry-release-pin")
    ap.add_argument("--registry-previous")
    ap.add_argument("--registry-previous-pin")
    ap.add_argument("--registry-boot",help="Optional verified historical Registry Mind sidecar; advisory only")
    ap.add_argument("--registry-homeostasis")
    ap.add_argument("--registry-homeostasis-pin")
    x=ap.parse_args()
    if x.phase=="plan" and (x.registry_homeostasis or x.registry_homeostasis_pin):
        if not (x.registry_homeostasis and x.registry_homeostasis_pin):
            raise ValueError("R67_CONTEXT_ARGS_REQUIRED")
        if __package__:
            from . import registry_homeostasis_r67 as homeostasis
        else:
            import registry_homeostasis_r67 as homeostasis
        homeostasis.consume_current(x.registry_homeostasis,x.registry_homeostasis_pin,"Hawkar-usls/Janus_Genesis",Path(__file__).resolve().parents[1])
    if x.phase=="plan" and any((x.registry_release,x.registry_release_pin,x.registry_previous,x.registry_previous_pin)):
        if not all((x.registry_release,x.registry_release_pin,x.registry_previous,x.registry_previous_pin)):
            raise ValueError("R65_REVIEWED_RELEASE_ARGS_REQUIRED")
        if __package__:
            from . import registry_update_r65 as registry_update
        else:
            import registry_update_r65 as registry_update
        registry_update.load_reviewed_context("Hawkar-usls/Janus_Genesis",Path(__file__).resolve().parents[1],x.registry_previous,x.registry_previous_pin,x.registry_release,x.registry_release_pin)
    if x.phase=="plan" and x.registry_boot:
        if __package__:
            from . import registry_boot_r64 as registry_boot
        else:
            import registry_boot_r64 as registry_boot
        registry_boot.consume_boot(x.registry_boot,"Hawkar-usls/Janus_Genesis",Path(__file__).resolve().parents[1])
    result=(plan(x.producer,x.receiver) if x.phase=="plan" else
            consume(read(x.plan),x.producer,x.genesis))
    write_once(x.out,result)
    print(json.dumps({"phase":x.phase,
        "action":result.get("action","WITNESSED"),
        "generation":result.get("generation"),
        "production_promotion":False}))


if __name__=="__main__":
    main()
