#!/usr/bin/env python3
"""ESSENCE controlled cross-repository draft-PR birth publisher.

Separate from local kernel and donor collector. Explicit publish action only.
The token must belong to a GitHub App or fine-grained credential with access
to the *specific* target repository and permission to open PRs. Never merges,
never edits default branch, and never invokes another workflow. No secrets in
staged source or logs.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from tools import essence_collective_seed as c

BASE = "https://api.github.com"
MANDATORY = (
    ".janus/essence/kernel.py",
    ".janus/essence/manifest.json",
    ".janus/essence/collective_origin.json",
    ".janus/essence/collective_seed.py",
)
OPTIONAL = (".janus/essence/gene_bank.py", ".janus/essence/innovations.json",
            ".janus/essence/inherited_ideas.json", ".janus/essence/evolution_memory.json")
MAX_BUNDLE_BYTES = 400_000

def bundle_files(root, expected_target):
    target=c.allowed_repo(expected_target)
    base=Path(root)
    paths=MANDATORY+tuple(p for p in OPTIONAL if (base/p).is_file())
    contents={}
    for name in paths:
        file=base/name
        if file.is_symlink() or not file.is_file():
            raise ValueError("BAD_BUNDLE_FILE_"+name)
        contents[name]=file.read_bytes()
    if sum(map(len,contents.values()))>MAX_BUNDLE_BYTES:
        raise ValueError("BUNDLE_TOO_LARGE")
    m=json.loads(contents[".janus/essence/manifest.json"])
    c.validate_manifest(m,target)
    origin=json.loads(contents[".janus/essence/collective_origin.json"])
    if origin.get("child_repository")!=target or origin.get("root_count")!=1:
        raise ValueError("INVALID_ORIGIN_BINDING")
    if origin.get("origin_type")!="COLLECTIVE_CONSENSUS_MANIFEST_NOT_MERGED_EXECUTABLES":
        raise ValueError("NOT_A_NEW_ROOT_BUNDLE")
    if origin.get("automatic_birth") is not False or origin.get("promotion_authority") is not False:
        raise ValueError("UNSAFE_ORIGIN_AUTHORITY")
    if origin.get("receipt_sha256")!=c.digest({k:v for k,v in origin.items() if k!="receipt_sha256"}):
        raise ValueError("TAMPERED_ORIGIN")
    if origin.get("root_sha256")!=c.file_sha(contents[".janus/essence/kernel.py"]):
        raise ValueError("ROOT_HASH_MISMATCH")
    if origin.get("manifest_sha256")!=c.digest(m):
        raise ValueError("MANIFEST_HASH_MISMATCH")
    if origin.get("factory_sha256")!=c.file_sha(contents[".janus/essence/collective_seed.py"]):
        raise ValueError("FACTORY_HASH_MISMATCH")
    if not isinstance(origin.get("donor_repositories"),list) or len(origin["donor_repositories"])<c.MIN_DONORS:
        raise ValueError("NOT_COLLECTIVE")
    if origin.get("donor_count")!=len(origin["donor_repositories"]):
        raise ValueError("DONOR_COUNT_MISMATCH")
    if len(set(origin["donor_repositories"]))!=len(origin["donor_repositories"]):
        raise ValueError("DUPLICATE_DONOR")
    if any(c.allowed_repo(n)==target for n in origin["donor_repositories"]):
        raise ValueError("TARGET_ALREADY_DONOR")
    idea_file=contents.get(".janus/essence/innovations.json")
    if idea_file is not None:
        c.validate_innovations(json.loads(idea_file),target)
    inherited_file=contents.get(".janus/essence/inherited_ideas.json")
    if inherited_file is not None:
        inherited=json.loads(inherited_file)
        if (inherited.get("schema")!=c.SCHEMA or
            inherited.get("parent_snapshot_sha256")!=origin["donor_snapshot_sha256"] or
            inherited.get("activation_allowed") is not False or
            inherited.get("independent_fitness_gate")!="REQUIRED" or
            not isinstance(inherited.get("innovation_candidates"),list) or
            not isinstance(inherited.get("minority_gene_candidates"),list)):
            raise ValueError("BAD_INHERITED_IDEAS")
    memory_file=contents.get(".janus/essence/evolution_memory.json")
    if memory_file is not None:
        memory=json.loads(memory_file)
        if (memory.get("schema")!=c.EVOLUTION_SCHEMA or
            memory.get("repository")!=target or
            memory.get("generation")!=0 or
            memory.get("evaluations")!=[] or
            memory.get("automatic_activation") is not False or
            memory.get("state_sha256")!=c.digest({k:v for k,v in memory.items() if k!="state_sha256"})):
            raise ValueError("BAD_EVOLUTION_MEMORY")
    return contents,origin

def branch_name(origin):
    return "janus/essence-collective-birth-"+origin["donor_snapshot_sha256"][:12]

def api(method,path,token,payload=None):
    if not path.startswith("/repos/"+c.OWNER+"/"):
        raise ValueError("UNTRUSTED_WRITE_DESTINATION")
    url=BASE+path
    raw=None if payload is None else json.dumps(payload,sort_keys=True).encode()
    headers={"Accept":"application/vnd.github+json","User-Agent":"JANUS-ESSENCE-SeedPublisher/0.3",
             "X-GitHub-Api-Version":"2022-11-28","Authorization":"Bearer "+token}
    if raw is not None: headers["Content-Type"]="application/json"
    req=urllib.request.Request(url,data=raw,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as resp:
            data=resp.read(1_000_001)
    except urllib.error.HTTPError as ex:
        if ex.code==404 and method=="GET": return None
        # Do not print response bodies: GitHub errors can include server details.
        raise RuntimeError("GITHUB_API_"+method+"_"+str(ex.code)) from None
    if len(data)>1_000_000: raise ValueError("API_RESPONSE_TOO_LARGE")
    return json.loads(data) if data else {}

def publish_draft(target, bundle_dir, token, do_request=api):
    target=c.allowed_repo(target)
    if not token or len(token)<10: raise PermissionError("EXPLICIT_TARGET_SCOPED_TOKEN_REQUIRED")
    files,origin=bundle_files(bundle_dir,target)
    def call(method,path,payload=None):
        return do_request(method,path,token,payload)
    meta=call("GET",f"/repos/{target}")
    if not isinstance(meta,dict) or meta.get("full_name")!=target:
        raise ValueError("TARGET_REPO_NOT_FOUND")
    if meta.get("archived") or meta.get("disabled") or meta.get("fork"):
        raise ValueError("UNSAFE_TARGET_REPOSITORY")
    base=meta.get("default_branch")
    if not isinstance(base,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",base):
        raise ValueError("INVALID_DEFAULT_BRANCH")
    existing=call("GET",f"/repos/{target}/contents/{MANDATORY[0]}?ref="+urllib.parse.quote(base,safe=""))
    if existing is not None:
        raise ValueError("ALREADY_HAS_ROOT_NO_SECOND_ROOT")
    ref=call("GET",f"/repos/{target}/git/ref/heads/"+urllib.parse.quote(base,safe=""))
    base_sha=((ref or {}).get("object") or {}).get("sha")
    if not isinstance(base_sha,str) or not re.fullmatch(r"[0-9a-f]{40}",base_sha):
        raise ValueError("NO_VALID_TARGET_BRANCH")
    branch=branch_name(origin)
    # All modifications limited to a NEW target branch. Never force-push.
    call("POST",f"/repos/{target}/git/refs",{"ref":"refs/heads/"+branch,"sha":base_sha})
    for path in MANDATORY+tuple(p for p in OPTIONAL if p in files):
        call("PUT",f"/repos/{target}/contents/"+path,{
            "message":"ESSENCE collective birth: stage "+path+" as reviewed proposal",
            "branch":branch,
            "content":base64.b64encode(files[path]).decode("ascii")})
    body=(
        "ESSENCE v0.3 collective root birth (review-only).\n\n"
        f"Verified parent manifests: {origin['donor_count']}.\n"
        f"Donor snapshot SHA-256: {origin['donor_snapshot_sha256']}.\n"
        f"Root SHA-256: {origin['root_sha256']}.\n"
        f"Factory SHA-256: {origin['factory_sha256']}.\n\n"
        "Exactly one new root; inherited factory generates bounded local candidate microcores. "
        "No new runtime rights, unattended workflows, or self-merging. "
        "Before merge: verify license/provenance, offline tests, default-branch policy, "
        "rollback plan and independent review.")
    pr=call("POST",f"/repos/{target}/pulls",{
        "title":"ESSENCE v0.3: seed one collective root (review-only)",
        "head":branch,"base":base,"body":body,"draft":True,
        "maintainer_can_modify":True})
    return {"target":target,"draft_pr":pr.get("html_url"),
            "pr_number":pr.get("number"),"branch":branch,
            "source_root_count":origin["donor_count"],
            "production_activated":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--target",required=True)
    p.add_argument("--bundle",required=True)
    p.add_argument("--publish-draft-pr",action="store_true")
    args=p.parse_args()
    files,origin=bundle_files(args.bundle,args.target)
    if not args.publish_draft_pr:
        print(json.dumps({"target":args.target,"files":list(files),
                          "donor_count":origin["donor_count"],
                          "action":"DRY_RUN_NO_REMOTE_CHANGES"}))
        return
    token=os.getenv("ESSENCE_SEED_PR_TOKEN","")
    result=publish_draft(args.target,args.bundle,token)
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":
    main()
