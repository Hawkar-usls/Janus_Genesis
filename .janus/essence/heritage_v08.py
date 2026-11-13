#!/usr/bin/env python3
"""ESSENCE v0.8 per-repository legacy inheritance observer (no runtime authority).

Runs AFTER existing R0.5 local kernel verification. Preserves 13 historical R0
role identities as review-only overlays atop the six existing inert microcores.
Reads only this repository's disabled manifest, local innovations and the
synthetic heartbeat report. It NEVER imports foreign scripts or weights, opens
network connections, trains a model, writes to a repo or grants execution.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "janus.essence.distributed_heritage_receipt/0.8"
ROOT_SHA1 = "de5199978fbafcbda836b77da370943f7ea2514e"
UPSTREAM_CATALOG_SHA1 = "2727721de135f2f421f33bfd7919ab91174adb89"
SOURCE = "Hawkar-usls/Janus-Demiurge"
SOURCE_PATH = "research/essence/v08/heritage_sources.json"
BASE = ("sensing", "memory", "planning", "verification", "recovery", "coding")
R0 = ("identity", "sensing", "memory", "planning", "verification", "recovery",
      "learning", "evolution", "routing", "resource", "governance",
      "transport", "coding")
MAP = {
    "identity": "memory",
    "learning": "memory",
    "evolution": "planning",
    "routing": "planning",
    "resource": "recovery",
    "governance": "verification",
    "transport": "sensing",
}
OWNER = re.compile(r"^Hawkar-usls/[A-Za-z0-9_.-]{1,90}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 150_000
MAX_IDEAS = 12

def encode(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()

def sha(x):
    return hashlib.sha256(encode(x)).hexdigest()

def gitblob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def read(path):
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ValueError("HERITAGE_LOCAL_INPUT_TOO_LARGE")
    return json.loads(p.read_text(encoding="utf-8"))

def root_gate(manifest, repo, kernel_bytes):
    if not isinstance(repo, str) or OWNER.fullmatch(repo) is None:
        raise ValueError("INVALID_REPOSITORY")
    if (not isinstance(manifest, dict) or
        manifest.get("schema") != "janus.essence.microkernel/0.1" or
        manifest.get("repository") != repo or
        manifest.get("enabled") is not False or
        manifest.get("activation") != "EXPLICIT_READONLY_TEST_ONLY" or
        manifest.get("birth_policy") != "PROPOSAL_ONLY" or
        any(manifest.get("capabilities", {}).values())):
        raise ValueError("UNSAFE_PARENT_MANIFEST")
    modules = manifest.get("microkernels")
    if (not isinstance(modules, list) or len(modules) != len(BASE) or
        set(x.get("role") for x in modules) != set(BASE) or
        len({x.get("id") for x in modules}) != len(BASE)):
        raise ValueError("PARENT_MICROCORES_CHANGED")
    if gitblob(kernel_bytes) != ROOT_SHA1:
        raise ValueError("BASE_ROOT_CODE_CHANGED")
    return True

def genes_gate(ideas, repo):
    if (not isinstance(ideas, dict) or
        ideas.get("schema") != "janus.essence.innovations/0.1" or
        ideas.get("repository") != repo or
        ideas.get("authority") != "RESEARCH_PROPOSAL_ONLY"):
        raise ValueError("WRONG_LOCAL_GENE_CATALOG")
    candidates = ideas.get("entries")
    if not isinstance(candidates, list) or len(candidates) > MAX_IDEAS:
        raise ValueError("UNBOUNDED_LOCAL_GENES")
    seen=set()
    for item in candidates:
        if (not isinstance(item, dict) or
            set(item) != {"id", "role", "idea", "evidence_sha256",
                          "precommit_sha256", "origin_receipt_sha256"} or
            not isinstance(item["id"], str) or
            not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", item["id"]) or
            item["id"] in seen or
            item["role"] not in BASE or
            not isinstance(item["idea"], str) or
            not 12 <= len(item["idea"]) <= 240 or
            any(not isinstance(item[k], str) or not HASH.fullmatch(item[k])
                for k in ("evidence_sha256","precommit_sha256",
                          "origin_receipt_sha256"))):
            raise ValueError("UNAUTHENTICATED_OR_DUPLICATE_LOCAL_GENE")
        seen.add(item["id"])
    return sorted(candidates,key=lambda x:x["id"])

def heartbeat_gate(value, repo):
    if (not isinstance(value, dict) or
        value.get("schema") != "janus.essence.readonly_heartbeat/0.5" or
        value.get("repository") != repo or
        value.get("input_class") != "SYNTHETIC_FIXTURE_ONLY" or
        value.get("production_authority") is not False or
        value.get("automated_birth") is not False):
        raise ValueError("UNTRUSTED_HEARTBEAT")
    result=value.get("report")
    if (not isinstance(result, dict) or
        result.get("status") != "PASS_WITH_OPERATIONAL_HOLD" or
        result.get("action_authority") is not False or
        any(x.get("activation_allowed") is not False
            for x in result.get("proposed_children", []))):
        raise ValueError("DANGEROUS_HEARTBEAT_RESULT")
    return True

def run(repo, manifest, ideas, heartbeat, kernel_bytes):
    root_gate(manifest,repo,kernel_bytes)
    local_ideas=genes_gate(ideas,repo)
    heartbeat_gate(heartbeat,repo)
    if set(MAP) != set(R0)-set(BASE):
        raise ValueError("MISSING_R0_LEGACY_ROLE")
    role_map={role:{
        "origin":"R0_HISTORICAL_ROLE",
        "base_microcore":MAP.get(role,role),
        "execution":"ORIGINAL_R05_OFFLINE_KERNEL" if role in BASE
                    else "ADVISORY_ROLE_NO_CODE_EXECUTION",
    } for role in R0}
    # These are deterministic checks of provenance, fitness and permitted
    # side-effects, not three independently trained or signed models.
    lenses={
        "provenance":"SOURCE_IDENTITIES_PINNED_BUT_EXTERNAL_CATALOG_NOT_FETCHED",
        "fitness":"HOLD_NO_INDEPENDENT_PROSPECTIVE_GAIN",
        "authority":"NO_PRODUCTION_OR_EXTERNAL_EFFECTS",
    }
    if not all(x["base_microcore"] in BASE for x in role_map.values()):
        raise ValueError("UNMAPPED_HISTORICAL_ROLE")
    candidates=[{
        "id":x["id"],"role":x["role"],
        "evidence_sha256":x["evidence_sha256"],
        "origin_receipt_sha256":x["origin_receipt_sha256"],
        "selection":"PRESERVED_FOR_INDEPENDENT_EVALUATION",
        "runtime_authority":False,
    } for x in local_ideas]
    report={
        "schema":SCHEMA,"repository":repo,
        "kernel_git_blob_sha1":ROOT_SHA1,
        "upstream_heritage_repository":SOURCE,
        "upstream_heritage_path":SOURCE_PATH,
        "upstream_heritage_git_blob_sha1":UPSTREAM_CATALOG_SHA1,
        "upstream_heritage_not_re_fetched_here":True,
        "role_count":len(R0),"live_base_microcores":len(BASE),
        "advisory_legacy_roles":len(MAP),"roles":role_map,
        "advisory_lenses":lenses,"local_candidate_count":len(candidates),
        "local_rare_genes":candidates,
        "source_kind":"LOCAL_SYNTHETIC_HEARTBEAT_PLUS_ADVISORY_ONLY",
        "selection_gate":"HOLD_NO_INDEPENDENT_PROSPECTIVE_GAIN",
        "model_training":False,"automatic_birth":False,
        "automatic_merging":False,"external_execution":False,
        "production_authority":False,
    }
    report["report_sha256"]=sha(report)
    return report

def selftest(repo, root):
    manifest=read(root/"manifest.json")
    kernel=(root/"kernel.py").read_bytes()
    root_gate(manifest,repo,kernel)
    bad=copy.deepcopy(manifest);bad["enabled"]=True
    try:root_gate(bad,repo,kernel)
    except ValueError:pass
    else:raise AssertionError("FAILED_TO_REJECT_ENABLED_ROOT")
    bad=copy.deepcopy(manifest);bad["repository"]="Hawkar-usls/Another"
    try:root_gate(bad,repo,kernel)
    except ValueError:pass
    else:raise AssertionError("FAILED_TO_REJECT_WRONG_REPO")
    if len(R0)!=13 or len(BASE)!=6 or set(MAP)!=set(R0)-set(BASE):
        raise AssertionError("LEGACY_ROLE_LOSS")
    ideas=read(root/"innovations.json")
    genes_gate(ideas,repo)
    bad=copy.deepcopy(ideas)
    bad["authority"]="AUTO_EXECUTE"
    try:genes_gate(bad,repo)
    except ValueError:pass
    else:raise AssertionError("FAILED_TO_REJECT_AUTO_EXECUTE")
    if gitblob(kernel)!=ROOT_SHA1:
        raise AssertionError("WRONG_ROOT")
    print("ESSENCE_V08_13_ROLE_ADVISORY_SELFTEST_PASS",repo)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",required=True)
    parser.add_argument("--root",default=".janus/essence")
    parser.add_argument("--heartbeat")
    parser.add_argument("--out")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    root=Path(args.root)
    if args.selftest:
        selftest(args.repo,root)
        return
    if not args.heartbeat or not args.out:
        parser.error("--heartbeat and --out required")
    receipt=run(args.repo,read(root/"manifest.json"),
                read(root/"innovations.json"),read(args.heartbeat),
                (root/"kernel.py").read_bytes())
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as fp:
        json.dump(receipt,fp,ensure_ascii=False,sort_keys=True,indent=2)
        fp.write("\n")
    print("ESSENCE_V08_INHERITANCE_RESEARCH_HOLD",args.repo,
          "roles:",receipt["role_count"],"ideas:",receipt["local_candidate_count"])
if __name__=="__main__":
    main()
