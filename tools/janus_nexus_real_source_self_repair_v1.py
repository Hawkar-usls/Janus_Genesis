#!/usr/bin/env python3
"""Bounded *algorithmic* repair of a real JANUS source weakness, not an LLM claim.

Source remains untrusted and cannot grant commands. The candidate is selected
only from two predeclared, AST-parseable text transformations on the specific
bounded_bytes() guard. Train tests select; independent held-out tests admit.
A real candidate may be committed to a separate isolated branch after approval
by the workflow verifier. No automatic merge or production authority.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

TARGET="tools/janus_nexus_phase2_live_gates_v1.py"
SCHEMA="janus.nexus.real_source_bounded_self_repair.v1"
OLD='require(path.is_file() and not path.is_symlink(), "MODEL_OUTPUT_MISSING")'
CANDIDATES={
  "DIRECT_PARENT_ONLY":'require(path.is_file() and not path.is_symlink() and\n'
       '            not path.parent.is_symlink(), "MODEL_OUTPUT_MISSING")',
  "ALL_SYMLINK_ANCESTORS":'require(path.is_file() and not path.is_symlink() and\n'
       '            not any(ancestor.is_symlink() for ancestor in path.parents),\n'
       '            "MODEL_OUTPUT_MISSING")',
}


class RepairHold(ValueError):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise RepairHold(msg)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, max_bytes: int=100_000) -> bytes:
    require(path.is_file() and not path.is_symlink() and
            not any(ancestor.is_symlink() for ancestor in path.parents),
            "SOURCE_PATH_NOT_REGULAR")
    require(0<path.stat().st_size<=max_bytes,"SOURCE_TOO_LARGE")
    return path.read_bytes()


def _write(path: Path, data: bytes) -> None:
    require(not path.exists() and not path.is_symlink(),"OUTPUT_ALREADY_PRESENT")
    require(not any(ancestor.is_symlink() for ancestor in path.parents),
            "OUTPUT_PARENT_SYMLINK")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:
        f.write(data)


def candidate_text(source: str, rule: str) -> str:
    require(rule in CANDIDATES,"REPAIR_RULE_NOT_ADMITTED")
    require(source.count(OLD)==1,"EXPECTED_REAL_SOURCE_PREIMAGE_MISSING")
    patched=source.replace(OLD,CANDIDATES[rule])
    require(patched!=source,"IDENTICAL_PATCH")
    ast.parse(source)
    ast.parse(patched)
    # Only one replacement allowed, no other Python AST/global edits.
    require(patched.replace(CANDIDATES[rule],OLD)==source,
            "SOURCE_PATCH_OUTSIDE_ALLOWED_HUNK")
    return patched


def _load_module(path: Path, alias: str):
    # Both modules contain trusted source + one fixed, guarded edit. Never
    # execute arbitrary model-supplied code, shell or package imports.
    sys.path.insert(0,str(path.parent.resolve()))
    spec=importlib.util.spec_from_file_location(alias,str(path))
    require(spec is not None and spec.loader is not None,
            "MODULE_SPEC_MISSING")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cases(module, *, independent: bool) -> dict[str,bool]:
    with tempfile.TemporaryDirectory(prefix="janus-repair-") as td:
        root=Path(td)
        real=root/"real"
        deep=real/"deep"
        deeper=deep/"more"
        deeper.mkdir(parents=True)
        f=real/"data.bin"
        f.write_bytes(b"actual recorded model output")
        (deep/"data.bin").write_bytes(b"nested model output")
        (deeper/"data.bin").write_bytes(b"heldout multi-depth output")
        alias=root/"alias"
        alias.symlink_to(real,target_is_directory=True)
        direct_link=real/"linked.bin"
        direct_link.symlink_to(f)
        results={}
        def accepts(path:Path, expected: bytes) -> bool:
            try:
                return module.bounded_bytes(path)==expected
            except Exception:
                return False
        def denies(path:Path) -> bool:
            try:
                module.bounded_bytes(path)
            except Exception:
                return True
            return False
        if independent:
            results["heldout_multi_level_parent_symlink_rejected"] = denies(alias/"deep"/"more"/"data.bin")
            results["heldout_file_not_modified"] = accepts(deeper/"data.bin",b"heldout multi-depth output")
            results["heldout_missing_file_rejected"] = denies(real/"missing.bin")
            non_dir_symlink=root/"alias2"
            non_dir_symlink.symlink_to(real,target_is_directory=True)
            results["heldout_other_alias_rejected"] = denies(non_dir_symlink/"deep"/"data.bin")
            results["heldout_direct_symlink_rejected"] = denies(direct_link)
        else:
            results["direct_parent_symlink_rejected"]=denies(alias/"data.bin")
            results["grandparent_symlink_rejected"]=denies(alias/"deep"/"data.bin")
            results["normal_file_accepted"]=accepts(f,b"actual recorded model output")
            results["direct_file_symlink_rejected"]=denies(direct_link)
            oversize=real/"too-large.bin"
            oversize.write_bytes(b"x"*(module.MAX_MODEL_BYTES+1))
            results["oversized_model_output_rejected"]=denies(oversize)
        return results


def run_tests(source_path: Path, *, independent: bool)->dict[str,bool]:
    module=_load_module(source_path,"janus_repair_h_"+sha(
        source_path.read_bytes())[:12])
    require(hasattr(module,"bounded_bytes") and
            hasattr(module,"MAX_MODEL_BYTES"),"TARGET_MODULE_SYMBOLS_MISSING")
    return _cases(module,independent=independent)


def choose(target: Path) -> tuple[dict, bytes, bytes]:
    require(target.name=="janus_nexus_phase2_live_gates_v1.py" and
            target.parent.name=="tools","REAL_FILE_TARGET_INVALID")
    original=_read(target)
    source=original.decode("utf-8")
    ast.parse(source)
    baseline=run_tests(target,independent=False)
    require(baseline["normal_file_accepted"] and
            baseline["direct_file_symlink_rejected"] and
            not baseline["direct_parent_symlink_rejected"] and
            not baseline["grandparent_symlink_rejected"],
            "REAL_BASELINE_VULNERABILITY_NOT_REPRODUCED")
    scores={}
    passing=[]
    for rule in CANDIDATES:
        patched=candidate_text(source,rule).encode("utf-8")
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/target.name
            file.write_bytes(patched)
            # Dependency imports via tools path before calling this function.
            res=run_tests(file,independent=False)
        scores[rule]=sum(res.values())
        if all(res.values()):
            passing.append(rule)
    require(len(passing)==1 and passing[0]=="ALL_SYMLINK_ANCESTORS",
            "NO_UNIQUE_BOUND_CANDIDATE_TRAINING_PASS")
    chosen=passing[0]
    output=candidate_text(source,chosen).encode("utf-8")
    diff="".join(difflib.unified_diff(source.splitlines(True),
             output.decode("utf-8").splitlines(True),
             fromfile="a/"+TARGET,tofile="b/"+TARGET)).encode()
    receipt={
        "schema":SCHEMA+".selection",
        "status":"PASS_BOUNDED_ALGORITHMIC_REAL_SOURCE_REPAIR_TRAINING_ONLY",
        "target":TARGET,
        "real_existing_vulnerability":"MODEL_OUTPUT_PARENT_SYMLINK_ACCEPTED",
        "original_source_sha256":sha(original),
        "patched_source_sha256":sha(output),
        "patch_diff_sha256":sha(diff),
        "candidate_scores":scores,
        "baseline_training_passed":sum(baseline.values()),
        "baseline_training_total":len(baseline),
        "selected_candidate_id":chosen,
        "candidate_generation":"DETERMINISTIC_BOUND_RULE_ENUMERATION",
        "neural_model_generated_this_code":False,
        "independent_holdout_seen_at_selection":False,
        "source_writeback":False,"production_main_modified":False,
        "full_issue_162_acceptance":False,"authority_delta":0,
    }
    return receipt,output,diff


def verify(target: Path,candidate: Path,receipt: dict,diff: bytes)->dict:
    require(receipt.get("schema")==SCHEMA+".selection" and
            receipt.get("target")==TARGET and
            receipt.get("selected_candidate_id")=="ALL_SYMLINK_ANCESTORS" and
            receipt.get("candidate_generation")=="DETERMINISTIC_BOUND_RULE_ENUMERATION" and
            receipt.get("neural_model_generated_this_code") is False and
            receipt.get("independent_holdout_seen_at_selection") is False and
            receipt.get("source_writeback") is False and
            receipt.get("authority_delta")==0,
            "SELECTION_RECEIPT_NOT_TRUSTED")
    raw_original=_read(target)
    raw_candidate=_read(candidate)
    expected=candidate_text(raw_original.decode("utf-8"),
                            "ALL_SYMLINK_ANCESTORS").encode()
    require(raw_candidate==expected,"CANDIDATE_NOT_WHITELISTED_TRANSFORM")
    require(sha(raw_original)==receipt.get("original_source_sha256") and
            sha(raw_candidate)==receipt.get("patched_source_sha256") and
            sha(diff)==receipt.get("patch_diff_sha256"),
            "CANDIDATE_HASH_OR_DIFF_MISMATCH")
    before=run_tests(target,independent=True)
    after=run_tests(candidate,independent=True)
    require(sum(before.values())<len(before) and
            len(after)>=5 and all(after.values()),
            "INDEPENDENT_HELDOUT_NOT_IMPROVED")
    return {
        "schema":SCHEMA+".independent_verdict",
        "status":"PASS_REAL_FILE_BOUND_RULE_REPAIR_INDEPENDENT_HELDOUT",
        "target":TARGET,
        "source_sha256":sha(raw_original),
        "candidate_sha256":sha(raw_candidate),
        "source_holdout_passed":sum(before.values()),
        "candidate_holdout_passed":sum(after.values()),
        "heldout_total":len(after),
        "neural_model_self_patch_proven":False,
        "repair_generalizes_to_other_issues":False,
        "candidate_source_code_was_executed_only_in_trusted_unit_test":True,
        "source_writeback":False,"production_main_modified":False,
        "full_issue_162_acceptance":False,"authority_delta":0,
    }


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("phase",choices=("stage","verify"))
    ap.add_argument("--target",type=Path,required=True)
    ap.add_argument("--candidate",type=Path,required=True)
    ap.add_argument("--receipt",type=Path,required=True)
    ap.add_argument("--diff",type=Path,required=True)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    try:
        if args.phase=="stage":
            receipt,output,diff=choose(args.target)
            _write(args.candidate,output)
            _write(args.diff,diff)
            _write(args.receipt,(json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode())
            print("JANUS_AUTOMATED_REAL_SOURCE_REPAIR="+receipt["status"])
        else:
            require(args.output is not None,"VERDICT_OUTPUT_REQUIRED")
            receipt=json.loads(_read(args.receipt,10000))
            verdict=verify(args.target,args.candidate,receipt,_read(args.diff,30000))
            _write(args.output,(json.dumps(verdict,sort_keys=True,indent=2)+"\n").encode())
            print("JANUS_AUTOMATED_REAL_SOURCE_REPAIR="+verdict["status"])
        return 0
    except (RepairHold,OSError,ValueError,TypeError,KeyError,UnicodeError) as e:
        print("JANUS_AUTOMATED_REAL_SOURCE_REPAIR=HOLD:"+
              (str(e) if isinstance(e,RepairHold) else "INPUT_OR_IO"),
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
