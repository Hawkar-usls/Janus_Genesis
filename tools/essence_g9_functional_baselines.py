#!/usr/bin/env python3
"""ESSENCE G9: genuine read-only G3/G8 Qwen CPU baseline on 64 frozen cases.

This is NOT a G9 candidate examination or evidence of accepted new weights.
Runs only with both saved SHA-pinned LoRA adapters from Demiurge shadow state.
Records answer hashes and correctness, never executes model output as code.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from tools import essence_g9_functional_gate as gate
from tools import essence_v55_functional_witness as v55

SCHEMA="janus.essence.g9.g3_g8_real_cpu_baseline/1.0"
LEDGER_PATH="research/essence/peer_v55_state/ledger.json"


def run(producer: Path, genesis: Path):
    producer=Path(producer)
    genesis=Path(genesis)
    suite=gate.read_suite(genesis)
    ledger=json.loads((producer/LEDGER_PATH).read_text())
    v55.validate_ledger(ledger)
    gate.require(ledger["current_generation"]==8 and
                 ledger["current_adapter_sha256"]==gate.REFERENCE["G8"] and
                 ledger["external_validation"] is False and
                 ledger["production_promotion"] is False,
                 "G9_NO_PINNED_REFERENCE_G8")
    g8lineage=ledger["current_lineage_sha256"]
    v55.verify_adapter(producer,"models/v54gen0003",gate.REFERENCE["G3"],
                       v55.G3_LINEAGE,3)
    v55.verify_adapter(producer,"models/v55gen0008",gate.REFERENCE["G8"],
                       g8lineage,8)
    sha=subprocess.check_output(["git","-C",str(producer),"rev-parse","HEAD"],
                               text=True,timeout=15).strip()
    gate.require(len(sha)==40 and all(c in "0123456789abcdef" for c in sha),
                 "G9_UNTRUSTED_PRODUCER_COMMIT")
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import PeftModel
    start=time.monotonic()
    torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(v55.BASE,revision=v55.REV,trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained(
        v55.BASE,revision=v55.REV,torch_dtype=torch.float32,
        trust_remote_code=False,use_safetensors=True).to("cpu")
    gate.require(getattr(base.config,"_commit_hash",None)==v55.REV,
                 "G9_BASE_MODEL_REV_UNPINNED")
    model=PeftModel.from_pretrained(base,str(producer/"models/v54gen0003"),
                                   is_trainable=False).to("cpu").eval()
    model.load_adapter(str(producer/"models/v55gen0008"),
                       adapter_name="g8",is_trainable=False)
    rows=[]
    for case in suite:
        tokens=tokenizer.apply_chat_template(
            [{"role":"user","content":case["prompt"]}],
            tokenize=True,add_generation_prompt=True,return_tensors="pt")
        gate.require(tokens.shape[1]<=200,"G9_PROMPT_TOO_LONG")
        output={}
        for role,adapter in (("G3","default"),("G8","g8")):
            model.set_adapter(adapter)
            with torch.inference_mode():
                response=model.generate(
                    tokens,attention_mask=torch.ones_like(tokens),
                    max_new_tokens=24,do_sample=False,pad_token_id=tokenizer.eos_token_id)
            text=tokenizer.decode(response[0,tokens.shape[1]:],
                                  skip_special_tokens=True).strip()
            gate.require(len(text)<=200,"G9_MODEL_RESPONSE_EXCESSIVE")
            output[role]={
                "exact":text==case["expected"],
                "answer_sha256":hashlib.sha256(text.encode()).hexdigest()
            }
        rows.append({"id":case["id"],"category":case["category"],
                     "G3":output["G3"],"G8":output["G8"]})
    g3=sum(x["G3"]["exact"] for x in rows)
    g8=sum(x["G8"]["exact"] for x in rows)
    gained=sum(x["G8"]["exact"] and not x["G3"]["exact"] for x in rows)
    lost=sum(x["G3"]["exact"] and not x["G8"]["exact"] for x in rows)
    receipt={
        "schema":SCHEMA,"source_owner":"Hawkar-usls/Janus-Demiurge",
        "verifier_repo":"Hawkar-usls/Janus_Genesis",
        "producer_commit":sha,
        "ledger_sha256":ledger["sha256"],
        "new_frozen_suite_git_blob_sha1":gate.SUITE_BLOB,
        "legacy_suite_git_blob_sha1":gate.LEGACY_BLOB,
        "model_adapter_sha256":dict(gate.REFERENCE),
        "model_lineage_sha256":{"G3":v55.G3_LINEAGE,"G8":g8lineage},
        "base_model_revision":v55.REV,
        "real_cpu_qwen_inference":True,"model_text_executed_as_code":False,
        "training_performed":False,"production_promotion":False,
        "external_validation":False,
        "case_count":len(rows),"g3_exact":g3,"g8_exact":g8,
        "g8_newly_correct":gained,"g8_previously_correct_lost":lost,
        "per_task":rows,
        "g9_candidate_exam_performed":False,
        "g9_candidate_accepted":False,
        "elapsed_seconds":round(time.monotonic()-start,3),
        "scientific_ceiling":"SAME_OWNER_INTERNAL_READONLY_BASELINE_ONLY"
    }
    receipt["sha256"]=gate.digest(receipt)
    return receipt


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--producer",type=Path,required=True)
    ap.add_argument("--genesis",type=Path,default=Path("."))
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    report=run(args.producer,args.genesis)
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("G9_BASELINE_RECEIPT_IMMUTABLE")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"g3_exact":report["g3_exact"],"g8_exact":report["g8_exact"],
                      "losses":report["g8_previously_correct_lost"],
                      "g9_accepted":False,"sha256":report["sha256"]}))


if __name__=="__main__":
    main()
