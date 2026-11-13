#!/usr/bin/env python3
"""ESSENCE v1.2 pinned-real-algorithm evaluator (research-only).

Runs a source-pinned JanusTinyTransformer ByteTokenizer from the actual model
source (only the audited class AST) plus the real Genesis gene_bank algorithm.
On machines with PyTorch, optionally benchmarks an actual randomly initialized
JanusTinyTransformer CPU forward pass using original no_grad vs inference_mode.

The holdout lives in independently versioned Meta Registry, but it is publicly
visible, not secret or blinded. No historic donor code, model weights, pickles
or downloaded arbitrary Python packages are executed.
"""
from __future__ import annotations

import ast
import gc
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
ESSENCE=ROOT/".janus"/"essence"
FIX=ROOT/"research"/"essence"/"v12"
MODEL=FIX/"sources"/"janus_model_model.py.txt"
HOLDOUT=FIX/"frozen_registry_holdout.json"
SRC_BLOB="11e359e89d3946895b2e0d6817c54253f09dfed1"
CORPUS_BLOB="71f23a157a9849998dc9655bc6bdf15c08d9934a"
GENE_BLOB="e7fe6f59591009df1905dbbf06b164d49e422660"
FREEZE_COMMIT="5fcd50ad7fc26f9e26aef6ff25ebcb42ef7c8f28"
SCHEMA="janus.essence.real_algorithm_benchmark/1.2"
sys.path.insert(0,str(ESSENCE))
import kernel


def blob(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def bounded_source(path:Path,expected:str,max_bytes=50000)->bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>max_bytes:
        raise ValueError("SOURCE_NOT_BOUNDED_REGULAR_FILE")
    raw=path.read_bytes()
    if blob(raw)!=expected:
        raise ValueError("FROZEN_SOURCE_HASH_MISMATCH")
    return raw


def load_corpus()->dict:
    raw=bounded_source(HOLDOUT,CORPUS_BLOB,10000)
    value=json.loads(raw.decode("utf-8"),parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    if (not isinstance(value,dict)
            or value.get("schema")!="janus.essence.real_algorithm_cross_repo_holdout/1.2"
            or value.get("blinded") is not False
            or not isinstance(value.get("text_cases"),list)
            or not 10<=len(value["text_cases"])<=100
            or any(type(x) is not str or len(x)>500 for x in value["text_cases"])
            or not isinstance(value.get("gene_cases"),list)
            or not 10<=len(value["gene_cases"])<=100
            or any(type(x) is not str or len(x)>120 for x in value["gene_cases"])):
        raise ValueError("FROZEN_CORPUS_SCHEMA_MISMATCH")
    return value


def verified_byte_tokenizer():
    """Only compile the class AST from a pinned real GPT source, not its imports."""
    raw=bounded_source(MODEL,SRC_BLOB)
    tree=ast.parse(raw.decode("utf-8"),filename=MODEL.name)
    found=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=="ByteTokenizer"]
    if len(found)!=1:
        raise ValueError("PINNED_TOKENIZER_NOT_FOUND")
    cls=found[0]
    if (cls.bases or cls.keywords or cls.decorator_list
            or {n.name for n in cls.body if isinstance(n,ast.FunctionDef)}!={"encode","decode"}
            or len(cls.body)!=5):
        raise ValueError("TOKENIZER_SOURCE_SHAPE_CHANGED")
    for node in ast.walk(cls):
        if isinstance(node,(ast.Import,ast.ImportFrom,ast.Lambda,ast.Global,ast.Nonlocal)):
            raise ValueError("TOKENIZER_UNSAFE_AST")
        if isinstance(node,ast.Name) and node.id.startswith("__"):
            raise ValueError("TOKENIZER_UNSAFE_NAME")
    env={"__name__":"janus_verified_byte_tokenizer",
         "__builtins__":{"__build_class__":__build_class__,"classmethod":classmethod,
                         "list":list,"bytes":bytes,"int":int}}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),MODEL.name,"exec"),env)
    return env["ByteTokenizer"]


def load_gene_bank():
    src=ESSENCE/"gene_bank.py"
    # Reproducible against the exact tested upstream source blob.
    if blob(src.read_bytes())!=GENE_BLOB:
        # Windows git core.autocrlf is allowed: normalized LF must match Git blob.
        normalized=src.read_bytes().replace(b"\r\n",b"\n")
        if blob(normalized)!=GENE_BLOB:
            raise ValueError("GENE_BANK_NOT_PINNED")
    import gene_bank
    return gene_bank


def fast_decoder(ids)->str:
    # Candidate restricted to integer token IDs, matching the real model contract.
    return bytes(i for i in ids if 0<=i<256).decode("utf-8",errors="replace")


PREFIXES=("JGPT1","MicroGPTSlime_quantized","MicroGPTSlime","MicroGPT",
          "CatGPT","FractalGPT","All_starsGPT","NonceMapGPT",
          "VacuumGPT","HoloGPT_TEST2","HoloGPT")


def fast_normalize(label,model_gene):
    if type(label) is not str or len(label)>120:
        return None
    if label in model_gene:
        return label
    if label.endswith(".py") and label[:-3] in PREFIXES:
        return label[:-3]
    head,sep,_=label.partition("(")
    if sep and head in PREFIXES:
        return head
    return None


def fingerprint(values)->str:
    return kernel.digest(values)


def perf(func,inputs,rounds=9,repetitions=120)->dict:
    for _ in range(4):
        for data in inputs:
            func(data)
    durations=[];mem=[]
    for _ in range(rounds):
        gc.collect()
        tracemalloc.start()
        st=time.perf_counter_ns()
        for _ in range(repetitions):
            for data in inputs:
                func(data)
        duration=time.perf_counter_ns()-st
        _,peak=tracemalloc.get_traced_memory()
        tracemalloc.stop()
        durations.append(duration/(repetitions*len(inputs)))
        mem.append(peak)
    return {
        "median_ns_per_call":round(statistics.median(durations),1),
        "min_ns_per_call":round(min(durations),1),
        "median_tracemalloc_python_peak_bytes":int(statistics.median(mem)),
        "rounds":rounds,"repetitions_each_round":repetitions,
        "measurement_kind":"LOCAL_WALL_CLOCK_PLUS_PYTHON_TRACEMALLOC_NOT_TOTAL_RSS",
    }


def judge(base:list,cand:list,base_perf:dict,cand_perf:dict)->dict:
    failures=[i for i,(a,b) in enumerate(zip(base,cand)) if a!=b]
    if len(base)!=len(cand):
        raise ValueError("OUTPUT_COUNT_CHANGED")
    wall_speedup=base_perf["median_ns_per_call"]/max(cand_perf["median_ns_per_call"],1)
    mem_factor=cand_perf["median_tracemalloc_python_peak_bytes"]/max(base_perf["median_tracemalloc_python_peak_bytes"],1)
    if failures:
        gate="HOLD_SEMANTIC_REGRESSION"
    elif mem_factor>1.25:
        gate="HOLD_PYTHON_MEMORY_REGRESSION"
    elif wall_speedup<0.95:
        gate="HOLD_TIME_REGRESSION"
    elif wall_speedup<1.05:
        gate="HOLD_NO_REPRODUCIBLE_SPEED_GAIN"
    else:
        gate="RESEARCH_CANDIDATE_PENDING_INDEPENDENT_BLIND_REPLICATION"
    return {"gate":gate,"counterexample_indices":failures[:6],
            "counterexample_count":len(failures),
            "median_wall_speed_ratio":round(wall_speedup,4),
            "python_peak_mem_ratio":round(mem_factor,4)}


def rollback_dry_run(oracle,wrong,inputs)->dict:
    baseline=[oracle(x) for x in inputs]
    candidate=[wrong(x) for x in inputs]
    bad=[i for i,(a,b) in enumerate(zip(baseline,candidate)) if a!=b]
    if not bad:
        raise RuntimeError("NEGATIVE_CONTROL_NOT_CAUGHT")
    # Pure in-memory router: never changes production weights or active service.
    active=oracle
    recovered=[active(x) for x in inputs]
    if recovered!=baseline:
        raise RuntimeError("IN_MEMORY_ROLLBACK_FAILED")
    return {
        "candidate_held":True,"first_counterexample_index":bad[0],
        "counterexample_count":len(bad),
        "rollback_kind":"IN_MEMORY_ROUTER_NO_DEPLOYMENT_OR_CHECKPOINT_CHANGE",
        "rollback_verified":True,"baseline_output_sha256":fingerprint(baseline),
        "recovered_output_sha256":fingerprint(recovered),
        "production_weights_or_modules_changed":False,
    }


def bench_actual_transformer(source:bytes,corpus:dict)->dict:
    try:
        import torch
    except ImportError:
        return {"status":"NOT_RUN_TORCH_NOT_INSTALLED","weights_trained":False}
    if not torch.__version__:
        raise RuntimeError("UNUSABLE_TORCH")
    # The full published source is immutable/hash-pinned and manually reviewed,
    # not an arbitrary recovered historic script. Never call generate/train/load.
    import types
    module=types.ModuleType("janus_v12_frozen_real_model")
    sys.modules[module.__name__]=module
    try:
        exec(compile(source.decode("utf-8"),MODEL.name,"exec"),module.__dict__)
    finally:
        sys.modules.pop(module.__name__,None)
    Config=module.__dict__["JanusModelConfig"]; Model=module.__dict__["JanusTinyTransformer"]
    torch.manual_seed(12612)
    torch.set_num_threads(1)
    net=Model(Config(vocab_size=258,context_length=32,d_model=32,
                     n_heads=4,n_layers=1,ff_mult=2,dropout=0.0)).cpu().eval()
    ids=[256]+list(corpus["text_cases"][0].encode("utf-8")[:24])+[257]
    src=torch.tensor([ids,ids],dtype=torch.long)
    def base():
        with torch.no_grad():
            logits,_=net(src)
            return logits
    def cand():
        with torch.inference_mode():
            logits,_=net(src)
            return logits
    before=base();after=cand()
    if not torch.allclose(before,after,rtol=0.0,atol=0.0):
        raise RuntimeError("TRANSFORMER_NUMERIC_REGRESSION")
    for _ in range(5):
        base();cand()
    baseline_rounds=[];candidate_rounds=[]
    # AB/BA counterbalance minimizes drift from always measuring one mode first.
    for iteration in range(16):
        for label,fn in ((("baseline",base),("candidate",cand)) if iteration%2==0
                         else (("candidate",cand),("baseline",base))):
            st=time.perf_counter_ns()
            for _ in range(8):
                fn()
            dt=(time.perf_counter_ns()-st)/8
            (baseline_rounds if label=="baseline" else candidate_rounds).append(dt)
    a=round(statistics.median(baseline_rounds),1)
    b=round(statistics.median(candidate_rounds),1)
    faster=sum(new<old for old,new in zip(baseline_rounds,candidate_rounds))
    ratio=a/max(b,1)
    if ratio<0.95:
        speed_gate="HOLD_OBSERVED_CPU_TIME_REGRESSION"
    elif ratio<1.05 or faster<12:
        speed_gate="HOLD_NO_STABLE_CPU_GAIN_ON_16_PAIRED_ROUNDS"
    else:
        speed_gate="RESEARCH_ONLY_CPU_GAIN_PENDING_INDEPENDENT_REPLICATION"
    # Native CPU tensor allocations aren't tracked by tracemalloc.
    # Report runtime only and explicitly decline to claim total memory gain.
    return {"status":"REAL_TORCH_CPU_FORWARD_TESTED",
            "model":"JanusTinyTransformer_random_init_NO_CHECKPOINT",
            "hardware":"CPU_ONLY_NO_CUDA",
            "config":{"d_model":32,"n_layers":1,"batch":2,"sequence_length":len(ids)},
            "weights_trained":False,"weights_modified":False,
            "exact_logits_match":True,
            "paired_rounds":16,"candidate_faster_paired_rounds":faster,
            "baseline_no_grad_median_ns":a,"candidate_inference_mode_median_ns":b,
            "wall_speed_ratio":round(ratio,4),
            "native_tensor_memory_measurement":"NOT_MEASURED",
            "gate":speed_gate}


def run(*, skip_torch:bool=False)->dict:
    data=load_corpus()
    source=bounded_source(MODEL,SRC_BLOB)
    Tokenizer=verified_byte_tokenizer()
    bank=load_gene_bank()
    ids=[Tokenizer.encode(x,bos=True,eos=True) for x in data["text_cases"]]
    base=[Tokenizer.decode(x) for x in ids]
    candidate=[fast_decoder(x) for x in ids]
    if base!=candidate:
        raise RuntimeError("GPT_TOKENIZER_BEHAVIOR_MISMATCH")
    bprof=perf(Tokenizer.decode,ids)
    cprof=perf(fast_decoder,ids)
    token_report={
        "source":"PINNED_REAL_JANUS_GPT_BYTE_TOKENIZER",
        "source_git_blob_sha1":SRC_BLOB,
        "case_count":len(ids),
        "baseline_output_sha256":fingerprint(base),
        "candidate_output_sha256":fingerprint(candidate),
        "baseline_metrics":bprof,"candidate_metrics":cprof,
        "decision":judge(base,candidate,bprof,cprof),
        "negative_control":rollback_dry_run(
            Tokenizer.decode,
            lambda arr: bytes(i for i in arr if 0<=i<256 and i!=32).decode("utf-8",errors="replace"),
            ids),
    }
    names=data["gene_cases"]
    norm_orig=[bank.normalized_model(x) for x in names]
    norm_new=[fast_normalize(x,bank.MODEL_GENE) for x in names]
    bprof=perf(bank.normalized_model,names)
    cprof=perf(lambda x:fast_normalize(x,bank.MODEL_GENE),names)
    gene_report={
        "source":"PINNED_REAL_ESSENCE_GENE_BANK_NORMALIZED_MODEL",
        "source_git_blob_sha1":GENE_BLOB,
        "case_count":len(names),
        "baseline_output_sha256":fingerprint(norm_orig),
        "candidate_output_sha256":fingerprint(norm_new),
        "baseline_metrics":bprof,"candidate_metrics":cprof,
        "decision":judge(norm_orig,norm_new,bprof,cprof),
        "negative_control":rollback_dry_run(
            bank.normalized_model,
            lambda x:None if x=="MicroGPT" else fast_normalize(x,bank.MODEL_GENE),
            names),
    }
    result={
        "schema":SCHEMA,
        "repository":kernel.load_json(ESSENCE/"manifest.json")["repository"],
        "holdout_origin_repo":"Hawkar-usls/janus-meta-registry",
        "holdout_origin_commit":FREEZE_COMMIT,
        "holdout_git_blob_sha1":CORPUS_BLOB,
        "holdout_independent_of_candidate_source_repo":True,
        "holdout_blinded":False,
        "independent_external_evaluator_attested":False,
        "candidates_executed_in_working_production":False,
        "byte_tokenizer":token_report,
        "essence_gene_bank":gene_report,
        "transformer_forward":({"status":"NOT_RUN_TORCH_OPTIONAL_CI","weights_trained":False}
                               if skip_torch else bench_actual_transformer(source,data)),
        "model_weights_updated":False,"automatic_promotion":False,
        "runtime_execution_authority":False,
        "rollback_drill_not_production_deployment":True,
        "overall_gate":"HOLD_EXTERNAL_BLIND_REPLICATION_AND_REAL_CHECKPOINT_REVIEW",
    }
    result["receipt_sha256"]=kernel.digest(result)
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-torch",action="store_true",help="stdlib CI lane; preserve explicit NOT_RUN evidence")
    parser.add_argument("--out",default=str(FIX/"comparison.json"))
    args=parser.parse_args()
    obj=run(skip_torch=args.skip_torch)
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "tokenizer":obj["byte_tokenizer"]["decision"],
        "microkernel":obj["essence_gene_bank"]["decision"],
        "torch":obj["transformer_forward"],
        "rollback_tokenizer":obj["byte_tokenizer"]["negative_control"]["rollback_verified"],
        "rollback_gene":obj["essence_gene_bank"]["negative_control"]["rollback_verified"],
        "overall_gate":obj["overall_gate"],
        "receipt_sha256":obj["receipt_sha256"]
    },ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()
