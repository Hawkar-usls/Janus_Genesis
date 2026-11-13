#!/usr/bin/env python3
"""ESSENCE v0.9: real public donor messages and staged microcore offspring.

A verified live GitHub donor census supplies bounded cross-repository offers.
The existing collective factory creates Python microcore proposals in TEMP,
without importing/executing source from donors or committing changes. Replies
are local artifacts, not yet sent to remote repositories. No independent gain
=> learning generation stays zero and production admission is denied.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from tools import essence_collective_seed as g

SCHEMA = "janus.essence.peer_evolution_cycle/0.9"
MESSAGE = "janus.essence.peer_offer_reply/0.9"
MAX_OFFERS = 4
IDEA_ID = re.compile(r"^[a-z][a-z0-9_-]{0,50}$")
HEX = re.compile(r"^[0-9a-f]{64}$")

def validate_idea(idea, target, donors):
    if not isinstance(idea,dict):
        raise ValueError("INVALID_PEER_IDEA")
    origin=g.allowed_repo(idea.get("repo"))
    if origin not in donors or origin==target:
        raise ValueError("PEER_NOT_INDEPENDENT_VERIFIED_DONOR")
    if (idea.get("role") not in g.ROLES
        or not isinstance(idea.get("id"),str)
        or not IDEA_ID.fullmatch(idea["id"])
        or idea.get("status")!="IDEA_NOT_PERFORMANCE_PROOF"
        or not isinstance(idea.get("idea"),str)
        or not 12<=len(idea["idea"])<=240):
        raise ValueError("BAD_IDEA_PROVENANCE")
    for k in ("evidence_sha256","precommit_sha256","origin_receipt_sha256",
              "source_manifest_sha256","source_ideas_sha256"):
        if not isinstance(idea.get(k),str) or not HEX.fullmatch(idea[k]):
            raise ValueError("MISSING_PINNED_SOURCE")
    return origin

def offer_and_reply(idea,target,donors,snapshot_hash):
    origin=validate_idea(idea,target,donors)
    offer={
        "schema":MESSAGE,"kind":"OFFER",
        "from_repository":origin,"to_repository":target,
        "idea_id":idea["id"],"role":idea["role"],
        "source_evidence_sha256":idea["evidence_sha256"],
        "origin_receipt_sha256":idea["origin_receipt_sha256"],
        "precommit_sha256":idea["precommit_sha256"],
        "donor_snapshot_sha256":snapshot_hash,
        "data_only":True,"execution_authority":False,
    }
    offer["offer_sha256"]=g.digest(offer)
    reply={
        "schema":MESSAGE,"kind":"RESEARCH_REPLY",
        "from_repository":target,"to_repository":origin,
        "in_reply_to_sha256":offer["offer_sha256"],
        "decision":"PROPOSE_RESEARCH_CHILD_NO_MODEL_PROMOTION",
        "external_source_authenticated":False,
        "production_authority":False,
    }
    reply["reply_sha256"]=g.digest(reply)
    return {"offer":offer,"reply":reply}

def run(snapshot,repo,manifest,root_bytes,out,manifest_raw=None):
    repo=g.allowed_repo(repo)
    g.check_snapshot(snapshot,root_bytes)
    g.validate_manifest(manifest,repo)
    donors={d["repo"] for d in snapshot["donors"]}
    local=next((d for d in snapshot["donors"] if d["repo"]==repo),None)
    if not local:raise ValueError("TARGET_NOT_VERIFIED_DONOR")
    if manifest_raw is not None and local["manifest_sha256"]!=g.file_sha(manifest_raw):
        raise ValueError("LOCAL_MANIFEST_NOT_LIVE_DONOR_VERSION")
    ideas=snapshot.get("innovation_candidates")
    if not isinstance(ideas,list) or len(ideas)>128:
        raise ValueError("UNBOUNDED_PEER_MESSAGES")
    seen=set();chosen=[]
    for idea in sorted(ideas,key=lambda x:(x.get("repo",""),x.get("id",""))):
        if idea.get("repo")==repo:continue
        origin=validate_idea(idea,repo,donors)
        ident=(origin,idea["id"])
        if ident in seen:raise ValueError("DUPLICATE_ORIGIN_ID")
        seen.add(ident)
        if len(chosen)<MAX_OFFERS:chosen.append(idea)
    if not chosen:raise ValueError("NO_OTHER_REPO_IDEAS")
    out=Path(out)
    if out.exists():raise FileExistsError("NO_STAGING_OVERWRITE")
    out.mkdir(parents=True)
    origin=g.adopt_existing_root(snapshot,repo,out,root_bytes,manifest)
    conversations=[offer_and_reply(x,repo,donors,snapshot["snapshot_sha256"])
                   for x in chosen]
    needs=[{
        "role":x["role"],
        "need":f"Compare peer {x['id']} from {x['repo']} on independent unseen tasks",
        "evidence_sha256":x["evidence_sha256"],
    } for x in chosen]
    birth=g.grow_modules(repo,manifest,origin,needs,out)
    proposals=birth["proposals"]
    if len(proposals)!=len(conversations) or any(
        x["automatic_activation"] is not False for x in proposals):
        raise ValueError("CHILD_MAY_NOT_BE_AUTOMATICALLY_ACTIVATED")
    for exchange,child in zip(conversations,proposals):
        reply=exchange["reply"]
        reply.pop("reply_sha256")
        reply["candidate_microcore_id"]=child["id"]
        reply["candidate_module_sha256"]=child["module_sha256"]
        reply["reply_sha256"]=g.digest(reply)
    # No authenticated new improvement: preserve generation zero.
    independent=g.rank_independent_fitness(snapshot,[])
    memory=g.learn_evolution(repo,independent,
        g.load(out/g.CANONICAL/"evolution_memory.json"))
    if (memory["generation"]!=0 or memory["evaluations"]
        or independent["research_shortlist"]):
        raise ValueError("HALLUCINATED_IMPROVEMENT")
    g.save(out/"peer_messages.json",{
        "schema":MESSAGE,"repository":repo,
        "local_unsent_responses":conversations,
        "published_to_other_repositories":False,
        "independent_authentication":False,
    })
    g.save(out/"independent_ranking.json",independent)
    g.save(out/"learning_state.json",memory)
    receipt={
        "schema":SCHEMA,"repository":repo,
        "origin_sha256":origin["receipt_sha256"],
        "snapshot_sha256":snapshot["snapshot_sha256"],
        "verified_donors":len(donors),
        "peer_offers":len(conversations),
        "new_microcore_proposals":len(proposals),
        "new_microcore_module_sha256":[x["module_sha256"] for x in proposals],
        "independent_evaluations":len(memory["evaluations"]),
        "learning_generation":memory["generation"],
        "existing_root_replaced":False,
        "foreign_weights_or_code_executed":False,
        "peer_replies_sent":False,
        "automatic_child_activation":False,
        "production_authority":False,
        "research_gate":"RESEARCH_CHILDREN_WITH_NO_PROVEN_INDEPENDENT_GAIN",
    }
    receipt["receipt_sha256"]=g.digest(receipt)
    g.save(out/"cycle_receipt.json",receipt)
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot",required=True)
    p.add_argument("--repo",required=True)
    p.add_argument("--manifest",default=".janus/essence/manifest.json")
    p.add_argument("--root",default=".janus/essence/kernel.py")
    p.add_argument("--out",required=True)
    a=p.parse_args()
    snapshot=g.load(a.snapshot)
    manifest=g.load(a.manifest)
    raw=Path(a.manifest).read_bytes()
    root=Path(a.root).read_bytes()
    receipt=run(snapshot,a.repo,manifest,root,a.out,manifest_raw=raw)
    print(json.dumps({k:receipt[k] for k in (
        "verified_donors","peer_offers","new_microcore_proposals",
        "learning_generation","research_gate","production_authority")}))
if __name__=="__main__":
    main()
