#!/usr/bin/env python3
"""ESSENCE Collective Seeding v0.3 — one root per repository, many local microcores.

All network access is read-only. Public repository roots contribute verified
manifest genes and their content hashes; no donor code/weights are executed.
Seed and grow write only into a caller-chosen STAGING DIRECTORY, never a Git
working tree or remote repository. An ordinary reviewed PR imports the bundle.
No scheduled jobs, credentials escalation, autoinstall, or automatic merges.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

OWNER = "Hawkar-usls"
SCHEMA = "janus.essence.collective_seed/0.3"
ROOT_SCHEMA = "janus.essence.microkernel/0.1"
ROLES = ("sensing", "memory", "planning", "verification", "recovery", "coding")
DENIED = ("network", "shell", "repo_write", "workflow_dispatch", "secrets", "hardware")
MAX_REPOS = 100
MAX_FILE = 100_000
MAX_MODULES = 16
MIN_DONORS = 3
CANONICAL = ".janus/essence"
PATTERN = re.compile(r"^Hawkar-usls/[A-Za-z0-9_.-]{1,90}$")
MODULE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")

def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()

def digest(x):
    return hashlib.sha256(canonical(x)).hexdigest()

def file_sha(x):
    return hashlib.sha256(x).hexdigest()

def write_new(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("NO_OVERWRITE: " + str(path))
    with path.open("x", encoding="utf-8") as f:
        f.write(contents)

def save(path, data):
    write_new(path, json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n")

def load(path):
    p=Path(path)
    if p.stat().st_size > 1_000_000:
        raise ValueError("OVERSIZED_JSON")
    with p.open(encoding="utf-8") as f:
        return json.load(f)

def allowed_repo(name):
    if not isinstance(name, str) or not PATTERN.fullmatch(name):
        raise ValueError("INVALID_REPOSITORY")
    return name

def validate_manifest(m, repo):
    if not isinstance(m,dict) or m.get("schema") != ROOT_SCHEMA:
        raise ValueError("INVALID_MANIFEST_SCHEMA")
    if m.get("repository") != repo:
        raise ValueError("WRONG_REPOSITORY_BINDING")
    if m.get("enabled") is not False or m.get("activation") != "EXPLICIT_READONLY_TEST_ONLY":
        raise ValueError("ACTIVE_DONOR_FORBIDDEN")
    if m.get("birth_policy") != "PROPOSAL_ONLY":
        raise ValueError("UNBOUNDED_BIRTH_POLICY")
    rights = m.get("capabilities")
    if not isinstance(rights,dict) or set(rights)!=set(DENIED) or any(rights.values()):
        raise ValueError("ACTIVE_CAPABILITY_FORBIDDEN")
    cells=m.get("microkernels")
    if not isinstance(cells,list) or not (6 <= len(cells) <= MAX_MODULES):
        raise ValueError("INVALID_CELL_COUNT")
    roles=set()
    for c in cells:
        if not isinstance(c,dict) or c.get("role") not in ROLES:
            raise ValueError("INVALID_ROLE")
        if not isinstance(c.get("id"),str) or not MODULE_PATTERN.fullmatch(c["id"]):
            raise ValueError("INVALID_CELL_ID")
        if not isinstance(c.get("generation"),int) or not (0 <= c["generation"] <= 32):
            raise ValueError("INVALID_GENERATION")
        genes=c.get("gene_sources")
        if not isinstance(genes,list) or len(genes)>5 or any(
            not isinstance(g,str) or not 0 < len(g) <= 64 for g in genes
        ):
            raise ValueError("INVALID_GENES")
        roles.add(c["role"])
    if set(ROLES) != roles:
        raise ValueError("INCOMPLETE_ROLES")
    return True

def github(path, token=""):
    if not path.startswith("/users/"+OWNER+"/repos?") and not path.startswith("/repos/"+OWNER+"/"):
        raise ValueError("UNTRUSTED_GITHUB_PATH")
    url="https://api.github.com"+path
    h={"Accept":"application/vnd.github+json",
       "User-Agent":"JANUS-ESSENCE-CollectiveSeed/0.3",
       "X-GitHub-Api-Version":"2022-11-28"}
    if token: h["Authorization"]="Bearer "+token
    req=urllib.request.Request(url,headers=h)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read(2_000_001)
    except urllib.error.HTTPError as exc:
        if exc.code==404: return None
        raise
    if len(raw)>2_000_000:
        raise ValueError("GITHUB_RESPONSE_TOO_LARGE")
    return json.loads(raw)

def public_repositories(token=""):
    # Users endpoint excludes private repositories and is deliberately bounded.
    entries=github(f"/users/{OWNER}/repos?type=owner&per_page=100&page=1",token)
    if not isinstance(entries,list) or len(entries)>MAX_REPOS:
        raise ValueError("INVENTORY_OVERFLOW")
    out=[]
    for e in entries:
        if not isinstance(e,dict):
            raise ValueError("BAD_REPO_RESPONSE")
        name=e.get("full_name")
        if e.get("private") or e.get("archived") or e.get("fork"):
            continue
        allowed_repo(name)
        out.append({"repo":name,"default_branch":e.get("default_branch")})
    return sorted(out,key=lambda x:x["repo"])

def github_content(repo, path, branch, token=""):
    allowed_repo(repo)
    if not isinstance(branch,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",branch):
        raise ValueError("INVALID_REF")
    if path not in (CANONICAL+"/kernel.py",CANONICAL+"/manifest.json"):
        raise ValueError("PATH_NOT_ALLOWED")
    raw=github(f"/repos/{repo}/contents/{path}?ref="+urllib.parse.quote(branch,safe=""),token)
    if raw is None:
        return None
    if not isinstance(raw,dict) or raw.get("type")!="file" or raw.get("encoding")!="base64":
        raise ValueError("INVALID_CONTENT_OBJECT")
    blob=base64.b64decode(raw.get("content",""),validate=False)
    if len(blob)>MAX_FILE:
        raise ValueError("OVERSIZE_DONOR")
    return {"blob_sha":raw.get("sha"),"data":blob}

def collect_snapshot(repos, fetch_content, canonical_root_bytes, collected_at):
    """Pure inventory algorithm; fetch_content(repo,path,branch) returns content or None."""
    canonical_hash=file_sha(canonical_root_bytes)
    donors=[]
    excluded=[]
    scanned=0
    for entry in sorted(repos,key=lambda x:x["repo"]):
        repo=allowed_repo(entry["repo"])
        branch=entry["default_branch"]
        scanned+=1
        try:
            kern=fetch_content(repo,CANONICAL+"/kernel.py",branch)
            if kern is None:
                continue
            manifest=fetch_content(repo,CANONICAL+"/manifest.json",branch)
            if manifest is None:
                raise ValueError("MISSING_MANIFEST")
            kb=kern["data"]; mb=manifest["data"]
            if file_sha(kb)!=canonical_hash:
                raise ValueError("DIVERGENT_KERNEL_CODE")
            m=json.loads(mb)
            validate_manifest(m,repo)
            donors.append({
                "repo":repo,"default_branch":branch,
                "kernel_sha256":file_sha(kb),"manifest_sha256":file_sha(mb),
                "kernel_git_blob_sha":kern.get("blob_sha"),
                "manifest_git_blob_sha":manifest.get("blob_sha"),
                "cells":[{"role":c["role"],"id":c["id"],
                          "generation":c["generation"],
                          "gene_sources":c["gene_sources"]} for c in m["microkernels"]],
            })
        except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc:
            excluded.append({"repo":repo,"reason":str(exc)[:128]})
    if len(donors)<MIN_DONORS:
        raise ValueError("INSUFFICIENT_VERIFIED_DONORS")
    votes=Counter()
    for donor in donors:
        items=set((c["role"],g) for c in donor["cells"] for g in c["gene_sources"])
        votes.update(items)
    quorum=max(MIN_DONORS, (len(donors)*2+2)//3) # 2/3 supermajority
    selected={}
    for role in ROLES:
        eligible=[(votes[(role,g)],g) for r,g in votes if r==role and votes[(r,g)]>=quorum]
        selected[role]=[g for n,g in sorted(eligible,key=lambda x:(-x[0],x[1]))[:5]]
    # Preserve minority innovations separately for per-repo review; never auto-inherit.
    minority=[{"role":role,"gene":g,"support":votes[(role,g)],
               "donors":[d["repo"] for d in donors if any(
                   c["role"]==role and g in c["gene_sources"] for c in d["cells"])]}
              for (role,g),count in sorted(votes.items()) if count<quorum]
    if any(not selected[r] for r in ROLES):
        raise ValueError("GENE_QUORUM_NOT_REACHED")
    snapshot={
        "schema":SCHEMA,"collected_at_utc":collected_at,
        "source":"PUBLIC_REPO_DEFAULT_BRANCH_MANIFESTS",
        "canonical_kernel_sha256":canonical_hash,
        "scanned_public_repositories":scanned,"verified_donor_count":len(donors),
        "excluded":excluded,"quorum":quorum,"donors":donors,
        "genes_by_role":selected,"minority_gene_candidates":minority,
        "consensus_kind":"VERIFIED_MANIFEST_AGREEMENT_NOT_INDEPENDENT_MODEL_GAIN",
        "source_code_and_weights_transplanted":False,
        "automatic_replication_enabled":False,
    }
    snapshot["snapshot_sha256"]=digest(snapshot)
    return snapshot

def check_snapshot(s, root_bytes=None):
    if not isinstance(s,dict) or s.get("schema")!=SCHEMA:
        raise ValueError("BAD_SNAPSHOT_SCHEMA")
    given=s.get("snapshot_sha256")
    if not isinstance(given,str) or given!=digest({k:v for k,v in s.items() if k!="snapshot_sha256"}):
        raise ValueError("SNAPSHOT_TAMPERED")
    donors=s.get("donors")
    if not isinstance(donors,list) or len(donors)<MIN_DONORS or s.get("verified_donor_count")!=len(donors):
        raise ValueError("INVALID_DONOR_COUNT")
    if len({d["repo"] for d in donors})!=len(donors):
        raise ValueError("DUPLICATE_DONOR")
    if any(d["kernel_sha256"]!=s.get("canonical_kernel_sha256") for d in donors):
        raise ValueError("MIXED_ROOT_CODE")
    if root_bytes is not None and s["canonical_kernel_sha256"]!=file_sha(root_bytes):
        raise ValueError("CANONICAL_ROOT_CHANGED")
    if set(s.get("genes_by_role",{}))!=set(ROLES):
        raise ValueError("INCOMPLETE_GENE_ROLES")
    if any(not 1<=len(s["genes_by_role"][r])<=5 for r in ROLES):
        raise ValueError("UNBOUNDED_GENE_POOL")
    return True

def seed_bundle(snapshot,repo,out,root_bytes,gene_bank_bytes=None):
    """Only writes fresh files into staging, NEVER alters a Git repository."""
    repo=allowed_repo(repo)
    check_snapshot(snapshot,root_bytes)
    if repo in {d["repo"] for d in snapshot["donors"]}:
        raise ValueError("TARGET_ALREADY_HAS_VERIFIED_ROOT")
    out=Path(out)
    manifest={
        "schema":ROOT_SCHEMA,"repository":repo,"enabled":False,
        "activation":"EXPLICIT_READONLY_TEST_ONLY",
        "capabilities":{key:False for key in DENIED},
        "birth_policy":"PROPOSAL_ONLY",
        "microkernels":[
            {"id":f"cell-{role}-{i:02d}","role":role,"generation":0,
             "gene_sources":snapshot["genes_by_role"][role]}
            for i,role in enumerate(ROLES)
        ]
    }
    validate_manifest(manifest,repo)
    origin={
        "schema":SCHEMA,"child_repository":repo,
        "donor_snapshot_sha256":snapshot["snapshot_sha256"],
        "donor_count":len(snapshot["donors"]),
        "donor_repositories":[d["repo"] for d in snapshot["donors"]],
        "origin_type":"COLLECTIVE_CONSENSUS_MANIFEST_NOT_MERGED_EXECUTABLES",
        "root_count":1,"root_sha256":file_sha(root_bytes),
        "manifest_sha256":digest(manifest),
        "factory_sha256":file_sha(Path(__file__).read_bytes()),
        "generation":0,"authority":"PROPOSAL_ONLY",
        "human_pr_review_required":True,
        "offline_contract_tests_required":True,
        "automatic_birth":False,"promotion_authority":False,
    }
    origin["receipt_sha256"]=digest(origin)
    write_new(out/CANONICAL/"kernel.py",root_bytes.decode("utf-8"))
    write_new(out/CANONICAL/"collective_seed.py",Path(__file__).read_text(encoding="utf-8"))
    save(out/CANONICAL/"manifest.json",manifest)
    save(out/CANONICAL/"collective_origin.json",origin)
    if gene_bank_bytes is not None:
        if len(gene_bank_bytes)>MAX_FILE: raise ValueError("OVERSIZE_GENE_BANK")
        write_new(out/CANONICAL/"gene_bank.py",gene_bank_bytes.decode("utf-8"))
    return origin

def adopt_existing_root(snapshot, repo, out, root_bytes, manifest):
    """Bind an existing single root to a verified collective ancestry; no new root."""
    repo=allowed_repo(repo)
    check_snapshot(snapshot,root_bytes)
    donors={d["repo"]:d for d in snapshot["donors"]}
    if repo not in donors:
        raise ValueError("EXISTING_ROOT_NOT_IN_DONOR_INVENTORY")
    validate_manifest(manifest,repo)
    if file_sha(root_bytes)!=donors[repo]["kernel_sha256"]:
        raise ValueError("EXISTING_ROOT_BYTES_CHANGED")
    origin={
        "schema":SCHEMA,"child_repository":repo,
        "donor_snapshot_sha256":snapshot["snapshot_sha256"],
        "donor_count":len(snapshot["donors"]),
        "donor_repositories":[d["repo"] for d in snapshot["donors"]],
        "origin_type":"ADOPT_EXISTING_ROOT_NO_ROOT_REPLACEMENT",
        "root_count":1,"root_sha256":file_sha(root_bytes),
        "manifest_sha256":digest(manifest),
        "factory_sha256":file_sha(Path(__file__).read_bytes()),
        "generation":0,"authority":"PROPOSAL_ONLY",
        "human_pr_review_required":True,
        "offline_contract_tests_required":True,
        "automatic_birth":False,"promotion_authority":False,
    }
    origin["receipt_sha256"]=digest(origin)
    save(Path(out)/CANONICAL/"collective_origin.json",origin)
    return origin

def module_text(role,ident,origin_hash):
    """A fixed, reviewable module; never generated code from untrusted donors."""
    if role not in ROLES or not MODULE_PATTERN.fullmatch(ident):
        raise ValueError("INVALID_ROLE_OR_ID")
    # All modules return immutable metadata plus a pure analysis of numeric input.
    # No imports, file writes, network calls or dynamic code evaluation.
    return (
        '"""ESSENCE inert local microcore; requires explicit isolated invocation."""\n'
        f'ROLE = {role!r}\nID = {ident!r}\n'
        f'ORIGIN_SHA256 = {origin_hash!r}\n'
        'def evaluate(values):\n'
        '    if not isinstance(values, dict) or len(values) > 16:\n'
        '        raise ValueError("INVALID_CONTEXT")\n'
        '    if any(type(x) not in (int, float) or not 0 <= x <= 1\n'
        '           for x in values.values()):\n'
        '        raise ValueError("NON_NORMALIZED_CONTEXT")\n'
        '    return {"role": ROLE, "id": ID, "origin_sha256": ORIGIN_SHA256,\n'
        '            "observations": len(values), "proposal_only": True,\n'
        '            "activation_allowed": False}\n'
    )

def grow_modules(repo,manifest,origin,requests,out):
    """Create local *review candidates*, not new roots or activated workers."""
    repo=allowed_repo(repo)
    validate_manifest(manifest,repo)
    if origin.get("child_repository")!=repo or origin.get("root_count")!=1:
        raise ValueError("BAD_ROOT_LINEAGE")
    if origin.get("receipt_sha256")!=digest({k:v for k,v in origin.items() if k!="receipt_sha256"}):
        raise ValueError("ORIGIN_TAMPERED")
    if not isinstance(requests,list) or not (1<=len(requests)<=4):
        raise ValueError("UNBOUNDED_REQUESTS")
    proposals=[]
    for req in requests:
        if not isinstance(req,dict) or set(req)!={"role","need","evidence_sha256"}:
            raise ValueError("INVALID_NEED_SCHEMA")
        role,need,evidence=req["role"],req["need"],req["evidence_sha256"]
        if role not in ROLES or not isinstance(need,str) or not (8<=len(need)<=160):
            raise ValueError("BAD_NEED")
        if not re.fullmatch(r"[0-9a-f]{64}",str(evidence)):
            raise ValueError("MISSING_EVIDENCE_HASH")
        ident=role+"-"+digest({"repo":repo,"role":role,"need":need,
                               "evidence":evidence,"root":origin["receipt_sha256"]})[:12]
        path=Path(out)/CANONICAL/"microkernels"/(ident+".py")
        write_new(path,module_text(role,ident,origin["receipt_sha256"]))
        proposals.append({
            "id":ident,"role":role,"need":need,
            "evidence_sha256":evidence,
            "status":"GENERATED_REVIEW_ONLY",
            "module_sha256":file_sha(path.read_bytes()),
            "baseline_comparison":"REQUIRED",
            "independent_validation":"REQUIRED",
            "automatic_activation":False,
        })
    report={"schema":SCHEMA,"repository":repo,
            "root_receipt_sha256":origin["receipt_sha256"],
            "proposals":proposals,"new_root_created":False,
            "no_production_writes":True}
    report["report_sha256"]=digest(report)
    save(Path(out)/CANONICAL/"microkernels"/"pending.json",report)
    return report

def main():
    p=argparse.ArgumentParser(description="ESSENCE collective seeding (proposals only)")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("collect");a.add_argument("--out",required=True)
    a.add_argument("--root",default=CANONICAL+"/kernel.py")
    b=sub.add_parser("seed");b.add_argument("--snapshot",required=True)
    b.add_argument("--target",required=True);b.add_argument("--out",required=True)
    b.add_argument("--root",default=CANONICAL+"/kernel.py")
    b.add_argument("--gene-bank",default=CANONICAL+"/gene_bank.py")
    a2=sub.add_parser("adopt");a2.add_argument("--snapshot",required=True)
    a2.add_argument("--repo",required=True);a2.add_argument("--out",required=True)
    a2.add_argument("--manifest",default=CANONICAL+"/manifest.json")
    a2.add_argument("--root",default=CANONICAL+"/kernel.py")
    c=sub.add_parser("grow");c.add_argument("--repo",required=True)
    c.add_argument("--manifest",required=True);c.add_argument("--origin",required=True)
    c.add_argument("--requests",required=True);c.add_argument("--out",required=True)
    args=p.parse_args()
    if args.command=="collect":
        root=Path(args.root).read_bytes()
        token=os.environ.get("GH_TOKEN","")
        public=public_repositories(token)
        stamp=datetime.now(timezone.utc).isoformat(timespec="seconds")
        snapshot=collect_snapshot(public,lambda r,path,br:github_content(r,path,br,token),root,stamp)
        save(args.out,snapshot)
        print(json.dumps({"public_scanned":snapshot["scanned_public_repositories"],
                          "verified_donors":snapshot["verified_donor_count"],
                          "snapshot_sha256":snapshot["snapshot_sha256"]}))
    elif args.command=="seed":
        root=Path(args.root).read_bytes()
        bank=Path(args.gene_bank).read_bytes()
        report=seed_bundle(load(args.snapshot),args.target,args.out,root,bank)
        print(json.dumps({"target":report["child_repository"],
                          "donors":report["donor_count"],"authority":"PROPOSAL_ONLY"}))
    elif args.command=="adopt":
        report=adopt_existing_root(load(args.snapshot),args.repo,args.out,
                                   Path(args.root).read_bytes(),load(args.manifest))
        print(json.dumps({"repo":report["child_repository"],
                          "new_root_created":False,"donors":report["donor_count"]}))
    else:
        report=grow_modules(args.repo,load(args.manifest),load(args.origin),
                            load(args.requests),args.out)
        print(json.dumps({"local_module_proposals":len(report["proposals"]),
                          "automatic_activation":False}))
if __name__=="__main__":
    main()
