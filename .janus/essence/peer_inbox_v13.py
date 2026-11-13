"""ESSENCE v1.3: GitHub-only read-only peer proposal inbox.

Each repository may receive a JSON idea originating from another JANUS repo.
This validator checks versioned Git provenance and the originating source run
receipt hashes. It does not run donor code or make source/weight changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA="janus.essence.github_repo_peer_inbox/1.3"
OFFER="janus.essence.peer_research_offer/1.3"
LEDGER="janus.essence.github_peer_lineage/1.3"
LEDGER_GIT_BLOB="249ff817dc5436b967114331aaa394c55e324efa"
LEDGER_MERGED_COMMIT="88c5eec58a5a8cdd0844034b2dcf584cfb67a8ec"
MAX_BYTES=50000
HASH64=re.compile(r"^[a-f0-9]{64}$")
HASH40=re.compile(r"^[a-f0-9]{40}$")

def canonical(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode("utf-8")

def sha256(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def read_json(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 2<=p.stat().st_size<=MAX_BYTES:
        raise ValueError("UNSAFE_PEER_INPUT")
    return json.loads(p.read_text(encoding="utf-8"),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def read_ledger(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 2<=path.stat().st_size<=MAX_BYTES:
        raise ValueError("UNSAFE_SOURCE_LEDGER")
    if git_blob(path.read_bytes())!=LEDGER_GIT_BLOB:
        raise ValueError("META_LEDGER_SOURCE_GIT_BLOB_MISMATCH")
    ledger=read_json(path)
    if (ledger.get("schema")!=LEDGER or
            ledger.get("mode")!="GITHUB_ONLY_VERSIONED_PEER_RESEARCH" or
            ledger.get("engine_git_blob_sha1")!="1c48b223c8ef64a78506a39b147f881b00022e77" or
            ledger.get("policy",{}).get("automatic_merge") is not False or
            ledger.get("policy",{}).get("automatic_code_import") is not False or
            ledger.get("policy",{}).get("training_weights_updated") is not False):
        raise ValueError("PEER_LEDGER_AUTHORITY_ESCALATION")
    peers=ledger.get("peers")
    if not isinstance(peers,list) or len(peers)!=6 or len({p["repository"] for p in peers})!=6:
        raise ValueError("UNTRUSTED_PEER_ROSTER")
    return ledger

def review(inbox,ledger,root):
    if (not isinstance(root,dict)
            or root.get("schema")!="janus.essence.microkernel/0.1"
            or root.get("enabled") is not False
            or root.get("activation")!="EXPLICIT_READONLY_TEST_ONLY"
            or not isinstance(root.get("capabilities"),dict)
            or any(root["capabilities"].values())):
        raise PermissionError("ROOT_HAS_EXECUTION_AUTHORITY")
    target=root.get("repository")
    if (not isinstance(inbox,dict) or inbox.get("schema")!=SCHEMA
            or inbox.get("repository")!=target
            or inbox.get("source_meta_registry_commit_sha")!=LEDGER_MERGED_COMMIT
            or inbox.get("source_ledger_git_blob_sha1")!=LEDGER_GIT_BLOB
            or inbox.get("delivery_status")!="VERSIONED_GITHUB_PR_REVIEW_ONLY"
            or inbox.get("automatic_merge") is not False
            or inbox.get("executable") is not False
            or inbox.get("production_authority") is not False):
        raise ValueError("INBOX_IDENTITY_OR_AUTHORITY_INVALID")
    offer=inbox.get("offer")
    if (not isinstance(offer,dict)
            or offer.get("schema")!=OFFER
            or offer.get("target_repo")!=target
            or offer.get("source_repo")==target
            or offer.get("review_required") is not True
            or offer.get("foreign_code_imported") is not False
            or offer.get("external_message_delivered") is not False
            or offer.get("production_authority") is not False
            or offer.get("automatic_model_promotion") is not False
            or offer.get("proposed_new_algorithm_verified") is not False
            or offer.get("performance_evidence")!="NO_NEW_INDEPENDENT_GAIN"
            or offer.get("source_research_generation")!=1
            or type(offer.get("proposal")) is not str
            or not 12<=len(offer["proposal"])<=200
            or offer.get("offer_sha256")!=sha256({
                k:v for k,v in offer.items() if k!="offer_sha256"})):
        raise ValueError("UNTRUSTED_SOURCE_OFFER")
    roster=ledger.get("peers")
    if (not isinstance(roster,list) or len(roster)!=6
            or len({p.get("repository") for p in roster if isinstance(p,dict)})!=6):
        raise ValueError("UNTRUSTED_PEER_ROSTER")
    peers={p["repository"]:p for p in roster}
    peer=peers.get(offer.get("source_repo"))
    if peer is None:
        raise ValueError("UNVERIFIED_PEER_ORIGIN")
    if (offer.get("source_commit_sha1")!=peer.get("merge_commit_sha")
            or offer.get("source_first_receipt_sha256")!=peer.get("first_run",{}).get("receipt_sha256")
            or offer.get("source_replay_receipt_sha256")!=peer.get("replay_run",{}).get("receipt_sha256")
            or peer.get("first_run",{}).get("research_generation")!=1
            or peer.get("replay_run",{}).get("research_generation")!=1
            or peer.get("replay_run",{}).get("decision")!="HOLD_NO_NEW_INDEPENDENT_GAIN"):
        raise ValueError("INBOX_SOURCE_RECEIPT_ORIGIN_MISMATCH")
    result={
        "schema":"janus.essence.peer_research_review/1.3",
        "repository":target,
        "source_repo":offer["source_repo"],
        "source_lineage_sha256":sha256(ledger),
        "source_offer_sha256":offer["offer_sha256"],
        "idea_id":offer["idea_id"],
        "status":"GITHUB_PEER_IDEA_RECEIVED_REQUIRES_INDEPENDENT_TEST",
        "research_generation":1,
        "training_performed":False,
        "foreign_code_executed":False,
        "new_candidate_proven":False,
        "automatic_offspring_activation":False,
        "production_authority":False,
    }
    result["receipt_sha256"]=sha256(result)
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inbox",required=True)
    ap.add_argument("--ledger",required=True)
    ap.add_argument("--root",default=".janus/essence/manifest.json")
    ap.add_argument("--out")
    args=ap.parse_args()
    result=review(read_json(args.inbox),read_ledger(args.ledger),read_json(args.root))
    if args.out:
        out=Path(args.out)
        if out.exists():raise FileExistsError("REVIEW_OUTPUT_NO_OVERWRITE")
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"repository":result["repository"],
                      "source":result["source_repo"],"receipt_sha256":result["receipt_sha256"]},sort_keys=True))

if __name__=="__main__":
    main()
