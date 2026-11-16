#!/usr/bin/env python3
"""ESSENCE v5.2: bounded six-cell cross-repo research dialogue + shadow tuning.

Peer JSON is UNTRUSTED DATA. SHA-256 detects mutation, not sender identity:
the read-only checkout of the peer's named Git branch and its GitHub ACL are
the provenance boundary. No model text executes; no production code/weights,
secrets, or Sentinel are modified. This module uses only Python stdlib.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

D = "Hawkar-usls/Janus-Demiurge"
G = "Hawkar-usls/Janus_Genesis"
PEERS = {D: G, G: D}
CELLS = {
    "cell-sensing-00": "sensing",
    "cell-memory-01": "memory",
    "cell-planning-02": "planning",
    "cell-verification-03": "verification",
    "cell-recovery-04": "recovery",
    "cell-coding-05": "coding",
}
MANIFEST = ".janus/essence/manifest.json"
REQUEST = "janus.essence.peer_mesh.request/5.2"
RESPONSE = "janus.essence.peer_mesh.response/5.2"
ACK = "janus.essence.peer_mesh.ack/5.2"
SHADOW = "janus.essence.peer_mesh.shadow_config/5.2"
BASE = Path("research/essence/mesh_v52")
SHA40 = re.compile(r"^[a-f0-9]{40}$")
SHA64 = re.compile(r"^[a-f0-9]{64}$")
FILENAME = re.compile(r"^[a-f0-9]{24}\.json$")
MAX_BYTES = 40_000
MAX_QUEUE = 64
DENIED = ("network", "shell", "repo_write", "workflow_dispatch", "secrets", "hardware")
SAFE_TUNE = {"setting": "deduplicate_identical_manifest_reads", "value": True}

def _unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("MESH_DUPLICATE_JSON_KEY")
        d[k] = v
    return d

def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()

def seal(data):
    return dict(data, receipt_sha256=digest(data))

def verify_seal(obj):
    if not isinstance(obj, dict):
        raise ValueError("MESH_INVALID_PACKET")
    unsigned = {k: v for k, v in obj.items() if k != "receipt_sha256"}
    if obj.get("receipt_sha256") != digest(unsigned):
        raise ValueError("MESH_BROKEN_RECEIPT")
    return obj

def decode(raw):
    if not isinstance(raw, bytes) or not 2 <= len(raw) <= MAX_BYTES:
        raise ValueError("MESH_OVERSIZED_JSON")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(
                          ValueError("MESH_NONFINITE_JSON")))

def reject_symlink_chain(path):
    """Fail closed if any directory component is a symbolic link.

    State files are derived from peer-controlled Git branches; checking only
    the terminal JSON file is insufficient when its ancestor is a symlink.
    """
    path = Path(path)
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("MESH_SYMLINK_COMPONENT")


def load(path):
    path = Path(path)
    reject_symlink_chain(path)
    if not path.is_file():
        raise ValueError("MESH_UNSAFE_FILE")
    return decode(path.read_bytes())

def put_once(path, obj):
    path = Path(path)
    reject_symlink_chain(path)
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != raw:
            raise ValueError("MESH_IMMUTABLE_PACKET_COLLISION")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    return True

def verify_manifest(raw, repo):
    obj = decode(raw)
    if (repo not in PEERS or obj.get("schema") != "janus.essence.microkernel/0.1"
        or obj.get("repository") != repo or obj.get("enabled") is not False
        or obj.get("activation") != "EXPLICIT_READONLY_TEST_ONLY"
        or obj.get("birth_policy") != "PROPOSAL_ONLY"
        or not isinstance(obj.get("capabilities"), dict)
        or any(obj["capabilities"].get(k) is not False for k in DENIED)
        or any(v is not False for v in obj["capabilities"].values())
        or not isinstance(obj.get("microkernels"), list)
        or {c.get("id"): c.get("role") for c in obj["microkernels"]
            if isinstance(c, dict)} != CELLS
        or len(obj["microkernels"]) != len(CELLS)):
        raise ValueError("MESH_ROOT_AUTHORITY_OR_ROSTER_DRIFT")
    return obj

def fetch_manifest(repo, commit):
    if repo not in PEERS or not isinstance(commit, str) or not SHA40.fullmatch(commit):
        raise ValueError("MESH_REMOTE_LOCATOR_DENIED")
    url = "https://raw.githubusercontent.com/" + repo + "/" + commit + "/" + MANIFEST
    request = urllib.request.Request(url, headers={"User-Agent": "ESSENCE-v52-Source-Pin"})
    with urllib.request.urlopen(request, timeout=16) as response:
        raw = response.read(MAX_BYTES + 1)
    verify_manifest(raw, repo)
    return raw

def packet_id(source_repo, source_sha, source_cell, target_cell, intent):
    return digest({"source": source_repo, "sha": source_sha,
                   "from": source_cell, "to": target_cell, "intent": intent})[:24]

def make_request(repo, commit, source_raw, source_cell, target_cell, intent="ASK_CAPABILITIES"):
    verify_manifest(source_raw, repo)
    if not isinstance(commit, str) or not SHA40.fullmatch(commit):
        raise ValueError("MESH_INVALID_HEAD")
    if source_cell not in CELLS or target_cell not in CELLS:
        raise ValueError("MESH_UNKNOWN_CELL")
    if intent not in ("ASK_CAPABILITIES", "PROPOSE_SHADOW_CACHE"):
        raise ValueError("MESH_INVALID_INTENT")
    source_sha = hashlib.sha256(source_raw).hexdigest()
    payload = dict(SAFE_TUNE) if intent == "PROPOSE_SHADOW_CACHE" else {}
    msg = {
        "schema": REQUEST, "id": packet_id(repo, source_sha, source_cell, target_cell, intent),
        "source_repo": repo, "target_repo": PEERS[repo],
        "source_cell": source_cell, "target_cell": target_cell,
        "intent": intent, "proposal": payload, "source_commit": commit,
        "source_path": MANIFEST, "source_manifest_sha256": source_sha,
        "question": ("Check my role, safety capabilities and independent verification needs."
                     if intent == "ASK_CAPABILITIES"
                     else "Propose manifest read deduplication in receiver SHADOW transport only."),
        "execute_code": False, "change_weights": False, "production_change": False,
        "sentinel_dispatch": False, "text_is_authority": False,
    }
    return seal(msg)

def verify_request(msg, target_repo):
    verify_seal(msg)
    src = msg.get("source_repo")
    intent = msg.get("intent")
    if not isinstance(src, str) or src not in PEERS:
        raise ValueError("MESH_UNTRUSTED_PEER")
    must = set(make_request(src, "0"*40,
                            canonical_dummy_manifest(src), "cell-sensing-00",
                            "cell-sensing-00").keys())
    if set(msg) != must:
        raise ValueError("MESH_UNEXPECTED_FIELDS")
    if (PEERS[src] != target_repo or msg.get("target_repo") != target_repo
        or msg.get("schema") != REQUEST or msg.get("source_path") != MANIFEST
        or not isinstance(msg.get("source_commit"), str)
        or not SHA40.fullmatch(msg["source_commit"])
        or not isinstance(msg.get("source_manifest_sha256"), str)
        or not SHA64.fullmatch(msg["source_manifest_sha256"])
        or msg.get("source_cell") not in CELLS or msg.get("target_cell") not in CELLS
        or intent not in ("ASK_CAPABILITIES", "PROPOSE_SHADOW_CACHE")
        or msg.get("proposal") != (SAFE_TUNE if intent == "PROPOSE_SHADOW_CACHE" else {})
        or msg.get("question") != ("Check my role, safety capabilities and independent verification needs."
                                  if intent == "ASK_CAPABILITIES" else
                                  "Propose manifest read deduplication in receiver SHADOW transport only.")
        or any(msg.get(flag) is not False for flag in
               ("execute_code", "change_weights", "production_change",
                "sentinel_dispatch", "text_is_authority"))
        or msg.get("id") != packet_id(src, msg["source_manifest_sha256"],
                                       msg["source_cell"], msg["target_cell"], intent)):
        raise ValueError("MESH_UNAUTHORIZED_PACKET")
    return msg

def canonical_dummy_manifest(repo):
    return canonical({
        "schema": "janus.essence.microkernel/0.1",
        "repository": repo, "enabled": False,
        "activation": "EXPLICIT_READONLY_TEST_ONLY", "birth_policy": "PROPOSAL_ONLY",
        "capabilities": {k: False for k in DENIED},
        "microkernels": [{"id": cell, "role": role}
                         for cell, role in CELLS.items()],
    })

def make_response(request, own_repo, own_commit, own_raw):
    verify_request(request, own_repo)
    verify_manifest(own_raw, own_repo)
    if not isinstance(own_commit, str) or not SHA40.fullmatch(own_commit):
        raise ValueError("MESH_RESPONSE_INVALID_COMMIT")
    status = ("PROPOSED_SHADOW_SETTING_VERIFIED_NOT_PRODUCTION"
              if request["intent"] == "PROPOSE_SHADOW_CACHE"
              else "INDEPENDENT_TARGET_MANIFEST_VERIFIED")
    return seal({
        "schema": RESPONSE, "request_id": request["id"],
        "request_sha256": request["receipt_sha256"],
        "source_repo": own_repo, "target_repo": request["source_repo"],
        "source_cell": request["target_cell"], "target_cell": request["source_cell"],
        "target_manifest_commit": own_commit,
        "target_manifest_sha256": hashlib.sha256(own_raw).hexdigest(),
        "status": status, "verified_target_role": CELLS[request["target_cell"]],
        "target_kernel_enabled": False, "code_execution": False,
        "production_update": False, "sentinel_dispatch": False,
    })

def verify_response(request, response, remote_manifest):
    verify_seal(response)
    if (response.get("source_repo") != request["target_repo"]
        or response.get("target_repo") != request["source_repo"]
        or not isinstance(response.get("target_manifest_commit"), str)
        or not SHA40.fullmatch(response["target_manifest_commit"])
        or not isinstance(response.get("target_manifest_sha256"), str)
        or hashlib.sha256(remote_manifest).hexdigest() != response["target_manifest_sha256"]):
        raise ValueError("MESH_RESPONSE_ORIGIN_OR_SOURCE")
    expected = make_response(request, request["target_repo"],
                             response["target_manifest_commit"], remote_manifest)
    if response != expected:
        raise ValueError("MESH_UNVERIFIED_RESPONSE")
    return response

def queue(folder):
    folder = Path(folder)
    reject_symlink_chain(folder)
    if not folder.exists():
        return []
    all_files = sorted(folder.iterdir())
    if len(all_files) > MAX_QUEUE:
        raise ValueError("MESH_QUEUE_LIMIT")
    for p in all_files:
        if not FILENAME.fullmatch(p.name) or p.is_symlink() or not p.is_file():
            raise ValueError("MESH_UNSAFE_MESSAGE_NAME")
    return all_files

def process(root, local_repo, main_commit, state, peer, fetch=fetch_manifest):
    if local_repo not in PEERS:
        raise ValueError("MESH_UNKNOWN_REPOSITORY")
    raw = (Path(root)/MANIFEST).read_bytes()
    verify_manifest(raw, local_repo)
    state = Path(state)/BASE
    peer = Path(peer)/BASE
    made = {"requests": 0, "responses": 0, "acks": 0}
    own = {}
    for cell in CELLS:
        msg = make_request(local_repo, main_commit, raw, cell, cell)
        path = state/"requests"/(msg["id"]+".json")
        if path.exists():
            msg = load(path)
            verify_request(msg, PEERS[local_repo])
            if msg["source_manifest_sha256"] != hashlib.sha256(raw).hexdigest():
                raise ValueError("MESH_STALE_TASK_SOURCE")
        else:
            made["requests"] += int(put_once(path, msg))
        own[msg["id"]] = msg
    tune = make_request(local_repo, main_commit, raw, "cell-planning-02",
                        "cell-verification-03", "PROPOSE_SHADOW_CACHE")
    tune_path = state/"requests"/(tune["id"]+".json")
    if tune_path.exists():
        tune = load(tune_path)
        verify_request(tune, PEERS[local_repo])
    else:
        made["requests"] += int(put_once(tune_path, tune))
    own[tune["id"]] = tune

    remote_requests = [load(p) for p in queue(peer/"requests")]
    for p, msg in zip(queue(peer/"requests"), remote_requests):
        verify_request(msg, local_repo)
        if p.name != msg["id"]+".json":
            raise ValueError("MESH_FILENAME_ID_MISMATCH")
    # Only an authenticated-by-source-pinning, bounded suggestion may turn
    # on a receiver's in-memory SHADOW optimization. Never production state.
    candidates = [m for m in remote_requests if m["intent"] == "PROPOSE_SHADOW_CACHE"]
    cache = {}
    read_calls = 0
    accepted_tune = False
    def witnessed(repo, commit):
        nonlocal read_calls
        key = (repo, commit)
        # No tuning proposal means ordinary uncached verification. Dedup
        # activates only after a source-pinned, allowlisted peer proposal.
        if accepted_tune and key in cache:
            return cache[key]
        raw_remote = fetch(repo, commit)
        verify_manifest(raw_remote, repo)
        read_calls += 1
        if accepted_tune:
            cache[key] = raw_remote
        return raw_remote
    for msg in candidates:
        original = witnessed(msg["source_repo"], msg["source_commit"])
        if hashlib.sha256(original).hexdigest() != msg["source_manifest_sha256"]:
            raise ValueError("MESH_SOURCE_PIN_MISMATCH")
        # The verified first proposal also seeds the memoized source. This
        # saves subsequent reads without accepting untrusted instructions.
        accepted_tune = True
        cache[(msg["source_repo"], msg["source_commit"])] = original
    for msg in remote_requests:
        source_raw = witnessed(msg["source_repo"], msg["source_commit"])
        if hashlib.sha256(source_raw).hexdigest() != msg["source_manifest_sha256"]:
            raise ValueError("MESH_REQUEST_PIN_MISMATCH")
        response = make_response(msg, local_repo, main_commit, raw)
        made["responses"] += int(put_once(state/"responses"/(msg["id"]+".json"), response))
    if accepted_tune:
        rec = seal({
            "schema": SHADOW, "local_repo": local_repo,
            "setting": "deduplicate_identical_manifest_reads",
            "enabled_in_research_transport_only": True, "production_change": False,
            "peer_proposals_witnessed": len(candidates),
            "validated_requests": len(remote_requests),
            "uncached_manifest_fetches_estimate": len(remote_requests),
            "observed_manifest_fetches": read_calls,
            "network_reads_saved_against_uncached_plan":
                max(0, len(remote_requests)-read_calls),
            "model_quality_gain_claim": False,
        })
        # Repeatable write-once evidence, keyed to the incoming request set.
        rec_id = digest({"request_ids": sorted(m["id"] for m in remote_requests)})[:24]
        put_once(state/"shadow_settings"/(rec_id+".json"), rec)

    for p in queue(peer/"responses"):
        response = load(p)
        task_id = response.get("request_id") if isinstance(response, dict) else None
        if task_id not in own:
            continue
        request = own[task_id]
        if p.name != task_id+".json":
            raise ValueError("MESH_REPLY_FILENAME")
        remote_raw = witnessed(response.get("source_repo"), response.get("target_manifest_commit"))
        verify_response(request, response, remote_raw)
        ack = seal({
            "schema": ACK, "request_id": request["id"],
            "response_receipt_sha256": response["receipt_sha256"],
            "source_repo": local_repo, "target_repo": PEERS[local_repo],
            "status": "RECEIVED_VERIFIED_PEER_RESPONSE", "production_change": False,
            "sentinel_dispatch": False,
        })
        made["acks"] += int(put_once(state/"acks"/(task_id+".json"), ack))
    return seal({
        "schema": "janus.essence.peer_mesh.run/5.2",
        "repo": local_repo, "cells_with_outbound_voice": len(CELLS),
        "local_root_execution_enabled": False,
        "new": made, "peer_input_count": len(remote_requests),
        "peer_manifest_read_calls": read_calls,
        "uncached_plan_reads": len(remote_requests),
        "shadow_tuning_only": accepted_tune, "model_training": False,
        "production_change": False, "sentinel_dispatch": False,
    })

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--repo", required=True, choices=tuple(PEERS))
    p.add_argument("--commit", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--peer", required=True)
    p.add_argument("--receipt", required=True)
    args = p.parse_args()
    result = process(args.root, args.repo, args.commit, args.state, args.peer)
    out = Path(args.receipt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
