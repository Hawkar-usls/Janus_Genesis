"""JANUS ESSENCE R0: inheritable, local-first, effect-free microkernel.

A peer lesson is a candidate, never an instruction, authenticated fact, model
checkpoint, or permission to train/deploy. No network, subprocess, dynamic
imports, persistence mutation, or automatic execution is performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re

SCHEMA = "janus.essence.genome.v0.1"
PACKET_SCHEMA = "janus.essence.peer_lesson.v0.1"
ROLES = (
    "identity", "sensing", "memory", "planning", "verification",
    "recovery", "learning", "evolution", "routing", "resource",
    "governance", "transport", "coding",
)
REQUIRED = frozenset(("identity", "memory", "verification", "governance", "resource"))
CAPABILITIES = ("local_observation", "candidate_exchange", "lineage_proposal")
GITHUB_REPO = re.compile(r"^Hawkar-usls/[A-Za-z0-9_.-]{1,100}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
MAX_PEERS = 64
MAX_GENERATION = 8


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require_repo(repo):
    if not isinstance(repo, str) or GITHUB_REPO.fullmatch(repo) is None:
        raise ValueError("UNADMITTED_REPOSITORY")
    return repo


def _sealed(document, hash_field):
    return {**document, hash_field: digest(document)}


def _unseal(document, hash_field):
    if not isinstance(document, dict) or hash_field not in document:
        raise ValueError("MISSING_INTEGRITY")
    data = {k: v for k, v in document.items() if k != hash_field}
    if not isinstance(document[hash_field], str) or document[hash_field] != digest(data):
        raise ValueError("INTEGRITY_MISMATCH")
    return data


def genome(repo, roles=ROLES, *, parent=None, specialty="general"):
    require_repo(repo)
    if not isinstance(specialty, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", specialty):
        raise ValueError("INVALID_SPECIALTY")
    if type(roles) not in (list, tuple) or not 5 <= len(roles) <= len(ROLES):
        raise ValueError("INVALID_MICROCORE_COUNT")
    if len(set(roles)) != len(roles) or not REQUIRED.issubset(roles) or any(role not in ROLES for role in roles):
        raise ValueError("MICROCORE_POLICY_VIOLATION")
    generation = 0
    parent_hash = None
    if parent is not None:
        verify_genome(parent)
        generation = parent["generation"] + 1
        if generation > MAX_GENERATION:
            raise ValueError("GENERATION_LIMIT")
        parent_hash = parent["integrity_sha256"]
        if not set(roles).issubset(parent["microcores"]):
            raise ValueError("CHILD_CANNOT_GAIN_NEW_ROLES")
    value = {
        "schema": SCHEMA, "repository": repo, "specialty": specialty,
        "generation": generation, "parent_integrity_sha256": parent_hash,
        "microcores": list(roles), "capabilities": list(CAPABILITIES),
        "runtime": "OFFLINE_NO_SIDE_EFFECTS", "neural_weights": "NOT_INCLUDED",
        "cross_repo_learning": "CANDIDATES_ONLY_UNTIL_INDEPENDENT_EVAL",
        "deployment_authority": False,
    }
    return _sealed(value, "integrity_sha256")


def verify_genome(value):
    data = _unseal(value, "integrity_sha256")
    if set(data) != {
        "schema", "repository", "specialty", "generation",
        "parent_integrity_sha256", "microcores", "capabilities", "runtime",
        "neural_weights", "cross_repo_learning", "deployment_authority",
    }:
        raise ValueError("GENOME_SHAPE")
    if data["schema"] != SCHEMA or data["runtime"] != "OFFLINE_NO_SIDE_EFFECTS":
        raise ValueError("GENOME_RUNTIME")
    require_repo(data["repository"])
    if not isinstance(data["specialty"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", data["specialty"]):
        raise ValueError("INVALID_SPECIALTY")
    if type(data["generation"]) is not int or not 0 <= data["generation"] <= MAX_GENERATION:
        raise ValueError("INVALID_GENERATION")
    if data["generation"] == 0 and data["parent_integrity_sha256"] is not None:
        raise ValueError("ROOT_PARENT_FORBIDDEN")
    if data["generation"] != 0 and (not isinstance(data["parent_integrity_sha256"], str)
                                    or not SHA64.fullmatch(data["parent_integrity_sha256"])):
        raise ValueError("CHILD_PARENT_REQUIRED")
    r = data["microcores"]
    if not isinstance(r, list) or not 5 <= len(r) <= len(ROLES):
        raise ValueError("INVALID_MICROCORE_COUNT")
    if len(set(r)) != len(r) or not REQUIRED.issubset(r) or any(x not in ROLES for x in r):
        raise ValueError("MICROCORE_POLICY_VIOLATION")
    if (data["capabilities"] != list(CAPABILITIES)
        or data["deployment_authority"] is not False
        or data["neural_weights"] != "NOT_INCLUDED"
        or data["cross_repo_learning"] != "CANDIDATES_ONLY_UNTIL_INDEPENDENT_EVAL"):
        raise ValueError("UNADMITTED_CAPABILITY")
    return True


def peer_packet(*, origin_repo, source_sha, target_role, artifact_sha256,
                summary, kind="lesson", metrics=None):
    require_repo(origin_repo)
    if not isinstance(source_sha, str) or SHA40.fullmatch(source_sha) is None:
        raise ValueError("INVALID_SOURCE_COMMIT")
    if target_role not in ROLES:
        raise ValueError("UNKNOWN_TARGET_ROLE")
    if not isinstance(artifact_sha256, str) or SHA64.fullmatch(artifact_sha256) is None:
        raise ValueError("EVIDENCE_DIGEST_REQUIRED")
    if kind not in ("lesson", "failure", "hypothesis"):
        raise ValueError("INVALID_PACKET_KIND")
    if not isinstance(summary, str) or not 1 <= len(summary) <= 600:
        raise ValueError("INVALID_SUMMARY")
    if not isinstance(metrics, dict) and metrics is not None:
        raise ValueError("INVALID_METRICS")
    metrics = {} if metrics is None else dict(metrics)
    if len(metrics) > 12 or any(
        not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", k)
        or type(v) not in (int, float) or not math.isfinite(v)
        or abs(v) > 1e12 for k, v in metrics.items()
    ):
        raise ValueError("INVALID_METRICS")
    return _sealed({
        "schema": PACKET_SCHEMA, "origin_repo": origin_repo,
        "source_commit_sha": source_sha, "target_role": target_role,
        "artifact_sha256": artifact_sha256, "kind": kind,
        "summary": summary, "metrics": metrics,
        "authority": "UNAUTHENTICATED_CANDIDATE_ONLY",
    }, "packet_sha256")


def verify_packet(packet):
    data = _unseal(packet, "packet_sha256")
    if set(data) != {
        "schema", "origin_repo", "source_commit_sha", "target_role",
        "artifact_sha256", "kind", "summary", "metrics", "authority",
    } or data["schema"] != PACKET_SCHEMA or data["authority"] != "UNAUTHENTICATED_CANDIDATE_ONLY":
        raise ValueError("PACKET_SHAPE_OR_AUTHORITY")
    expected = peer_packet(
        origin_repo=data["origin_repo"], source_sha=data["source_commit_sha"],
        target_role=data["target_role"], artifact_sha256=data["artifact_sha256"],
        summary=data["summary"], kind=data["kind"], metrics=data["metrics"],
    )
    if expected != packet:
        raise ValueError("PACKET_INVALID")
    return True


LEGACY_ADAPTER_ROLES = frozenset((
    "sensing", "memory", "planning", "verification", "recovery", "coding",
))


def unified_profile(legacy_adapter_manifest, inherited_genome):
    """Verify that the six-cell offline adapter and ESSENCE genome are one organism.

    This validates manifest *consistency*, not live runtime trust or model
    training. It never executes the legacy adapter or imports its code.
    """
    verify_genome(inherited_genome)
    obj = legacy_adapter_manifest
    if not isinstance(obj, dict) or obj.get("schema") != "janus.essence.microkernel/0.1":
        raise ValueError("UNKNOWN_LEGACY_ADAPTER")
    if obj.get("repository") != inherited_genome["repository"]:
        raise ValueError("REPOSITORY_IDENTITY_SPLIT")
    if obj.get("enabled") is not False or obj.get("activation") != "EXPLICIT_READONLY_TEST_ONLY":
        raise ValueError("LIVE_ADAPTER_FORBIDDEN")
    caps = obj.get("capabilities")
    denied = {"network", "shell", "repo_write", "workflow_dispatch",
              "secrets", "hardware"}
    if not isinstance(caps, dict) or set(caps) != denied or any(v is not False for v in caps.values()):
        raise ValueError("LEGACY_CAPABILITY_ESCALATION")
    if obj.get("birth_policy") != "PROPOSAL_ONLY":
        raise ValueError("UNADMITTED_LEGACY_OFFSPRING")
    cells = obj.get("microkernels")
    if not isinstance(cells, list) or not 6 <= len(cells) <= 16:
        raise ValueError("LEGACY_CELL_BOUNDS")
    roles = []
    ids = set()
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {
            "id", "role", "generation", "gene_sources",
        }:
            raise ValueError("LEGACY_CELL_SHAPE")
        role = cell["role"]
        ident = cell["id"]
        if role not in LEGACY_ADAPTER_ROLES or not isinstance(ident, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", ident):
            raise ValueError("LEGACY_CELL_ROLE_OR_ID")
        if ident in ids:
            raise ValueError("LEGACY_DUPLICATE_ID")
        ids.add(ident)
        roles.append(role)
        if type(cell["generation"]) is not int or not 0 <= cell["generation"] <= 32:
            raise ValueError("LEGACY_GENERATION")
        if not isinstance(cell["gene_sources"], list) or len(cell["gene_sources"]) > 5 or any(
            not isinstance(s, str) or len(s) > 64 for s in cell["gene_sources"]
        ):
            raise ValueError("LEGACY_DONOR_INVALID")
    if not LEGACY_ADAPTER_ROLES.issubset(roles) or not set(roles).issubset(inherited_genome["microcores"]):
        raise ValueError("ADAPTER_ROLES_NOT_INHERITED")
    return _sealed({
        "schema": "janus.essence.unified_profile.v0.1",
        "repository": inherited_genome["repository"],
        "genome_sha256": inherited_genome["integrity_sha256"],
        "legacy_adapter_manifest_sha256": digest(obj),
        "legacy_adapter_roles": sorted(set(roles)),
        "extended_roles": sorted(set(inherited_genome["microcores"]) - LEGACY_ADAPTER_ROLES),
        "logical_core_instances": 1,
        "model_weights_imported": False,
        "cross_repo_gradient_exchange": False,
        "external_effects": False,
    }, "profile_sha256")


class EssenceCore:
    """Small independent supervisor; never dispatches external commands."""

    def __init__(self, local_genome, *, allowed_peers=()):
        verify_genome(local_genome)
        if not isinstance(allowed_peers, (list, tuple, set, frozenset)) or len(allowed_peers) > MAX_PEERS:
            raise ValueError("PEER_ALLOWLIST_BOUNDS")
        self.genome = dict(local_genome)
        self.allowed_peers = frozenset(require_repo(x) for x in allowed_peers)
        self.inbox = []
        self.seen = set()

    def receive(self, packet):
        verify_packet(packet)
        if packet["origin_repo"] not in self.allowed_peers:
            raise ValueError("PEER_NOT_ALLOWLISTED")
        if packet["target_role"] not in self.genome["microcores"]:
            raise ValueError("TARGET_NOT_INSTALLED")
        tag = packet["packet_sha256"]
        if tag in self.seen:
            return {"status": "DEDUPLICATED", "packet_sha256": tag}
        if len(self.inbox) >= MAX_PEERS:
            return {"status": "DEFERRED_INBOX_FULL", "packet_sha256": tag}
        self.inbox.append(dict(packet))
        self.seen.add(tag)
        return {
            "status": "QUARANTINED_LEARNING_CANDIDATE", "packet_sha256": tag,
            "authenticated_source": False, "trained_from_packet": False,
            "next_gate": "FETCH_PINNED_SOURCE_VALIDATE_HOLDOUT_AND_APPROVE",
        }

    def pulse(self, *, simulate_failure=()):
        """Bounded offline cycle; failures isolated, never used as training labels."""
        roles = self.genome["microcores"]
        if any(x not in ROLES for x in simulate_failure):
            raise ValueError("INVALID_TEST_FAULT")
        report = []
        for role in roles:
            try:
                if role in simulate_failure:
                    raise RuntimeError("TEST_FAULT")
                if role in ("learning", "evolution"):
                    status = "HOLD_INDEPENDENT_VALIDATION_REQUIRED"
                elif role == "transport":
                    status = "OFFLINE_NO_NETWORK"
                elif role == "routing":
                    status = "PROPOSALS_ONLY_NO_DISPATCH"
                else:
                    status = "LOCAL_POLICY_READY"
                report.append({"role": role, "status": status})
            except Exception as exc:
                report.append({"role": role, "status": "ISOLATED_FAILURE",
                               "error_type": type(exc).__name__})
        receipt = {
            "schema": "janus.essence.pulse_receipt.v0.1",
            "repo": self.genome["repository"],
            "genome_sha256": self.genome["integrity_sha256"],
            "candidate_count": len(self.inbox),
            "verified_evidence_count": 0,
            "neural_training_performed": False,
            "external_actions": 0,
            "full_autonomy": False,
            "microcores": report,
        }
        return _sealed(receipt, "receipt_sha256")


def demo():
    root = genome("Hawkar-usls/Janus-Demiurge", specialty="conductor")
    child = genome("Hawkar-usls/Janus_Genesis", parent=root, specialty="genesis")
    peer = peer_packet(
        origin_repo=root["repository"],
        source_sha="1" * 40, target_role="memory",
        artifact_sha256=digest({"demo": "synthetic"}),
        summary="Synthetic demonstration; not a validated GitHub fact.",
        metrics={"synthetic_score": 0.5},
    )
    node = EssenceCore(child, allowed_peers=[root["repository"]])
    exchange = node.receive(peer)
    return {"parent": root["integrity_sha256"],
            "child": child["integrity_sha256"],
            "exchange": exchange, "pulse": node.pulse()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("demo", "genome"))
    parser.add_argument("--repo", default="Hawkar-usls/Janus-Demiurge")
    parser.add_argument("--specialty", default="general")
    parser.add_argument("--parent-repo", default="Hawkar-usls/Janus-Demiurge")
    args = parser.parse_args()
    if args.action == "demo":
        result = demo()
    elif args.repo == args.parent_repo:
        result = genome(args.repo, specialty=args.specialty)
    else:
        result = genome(args.repo, parent=genome(args.parent_repo),
                        specialty=args.specialty)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
