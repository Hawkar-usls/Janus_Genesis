#!/usr/bin/env python3
"""ESSENCE v0.1: inert-by-default, offline, bounded repository-local microkernel.

This is a policy/provenance scaffold, NOT a trained language model or an
autonomous software agent.  No GitHub, network, shell, or model invocation.
Child kernels are proposals, never executed or persisted by the runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA = "janus.essence.microkernel/0.1"
ROLES = ("sensing", "memory", "planning", "verification", "recovery", "coding")
DENIED_CAPABILITIES = ("network", "shell", "repo_write", "workflow_dispatch", "secrets", "hardware")
MAX_BYTES = 65536
ROOT_HASH = "0" * 64


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def load_json(path):
    target = Path(path)
    if target.stat().st_size > MAX_BYTES:
        raise ValueError("JSON exceeds offline safety limit")
    with target.open("r", encoding="utf-8") as stream:
        value = json.load(stream, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    return value


def validate_manifest(manifest, expected_repo=None):
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("unknown ESSENCE schema")
    repo = manifest.get("repository")
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository binding")
    if expected_repo is not None and repo != expected_repo:
        raise ValueError("repository identity mismatch")
    if manifest.get("enabled") is not False or manifest.get("activation") != "EXPLICIT_READONLY_TEST_ONLY":
        raise ValueError("manifest must remain inert by default")
    rights = manifest.get("capabilities")
    if not isinstance(rights, dict) or set(rights) != set(DENIED_CAPABILITIES) or any(rights.values()):
        raise ValueError("non-read-only capability requested")
    if manifest.get("birth_policy") != "PROPOSAL_ONLY":
        raise ValueError("automatic birth not permitted")
    cells = manifest.get("microkernels")
    if not isinstance(cells, list) or not 6 <= len(cells) <= 16:
        raise ValueError("unbounded or incomplete microkernel set")
    ids = set()
    observed_roles = set()
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {"id", "role", "generation", "gene_sources"}:
            raise ValueError("invalid microkernel descriptor")
        ident, role = cell["id"], cell["role"]
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", ident):
            raise ValueError("invalid microkernel id")
        if role not in ROLES or ident in ids:
            raise ValueError("duplicate microkernel or unknown role")
        if type(cell["generation"]) is not int or not 0 <= cell["generation"] <= 32:
            raise ValueError("invalid generation")
        sources = cell["gene_sources"]
        if not isinstance(sources, list) or len(sources) > 5 or any(not isinstance(s, str) or len(s) > 64 for s in sources):
            raise ValueError("invalid donor gene source")
        ids.add(ident)
        observed_roles.add(role)
    if set(ROLES) - observed_roles:
        raise ValueError("six role families required")
    return cells


def validate_fixture(fixture):
    if not isinstance(fixture, dict) or set(fixture) != {"kind", "id", "metrics"}:
        raise ValueError("unknown input shape")
    if fixture["kind"] != "SYNTHETIC_FIXTURE":
        raise ValueError("v0.1 accepts only synthetic fixtures")
    if not isinstance(fixture["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", fixture["id"]):
        raise ValueError("invalid fixture id")
    metrics = fixture["metrics"]
    if not isinstance(metrics, dict) or not 1 <= len(metrics) <= 16:
        raise ValueError("metrics required")
    for key, value in metrics.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z_]{1,40}", key):
            raise ValueError("invalid metric name")
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("metrics must be finite normalized numbers")
    return metrics


def observe_role(role, metrics, evidence_hash):
    """Deterministic per-role adapter: no training, execution, or external effects."""
    if role == "sensing":
        return {"count": len(metrics), "mean": round(sum(metrics.values()) / len(metrics), 6)}
    if role == "memory":
        return {"observation_sha256": evidence_hash, "persistence": "NOT_ENABLED"}
    if role == "planning":
        return {"action": "HOLD", "execution": False}
    if role == "verification":
        return {"finite_and_normalized": True, "claim_limit": "SYNTHETIC_ONLY"}
    if role == "recovery":
        return {"numeric_guard": "PASS", "external_recovery": False}
    if role == "coding":
        return {"patch_authority": False, "proposal_only": True}
    raise ValueError("unknown role")


def evaluate(manifest, fixture, *, explicit_readonly=False, propose_child=None, expected_repo=None):
    if not explicit_readonly:
        raise PermissionError("ESSENCE is inert; explicit read-only test flag required")
    cells = validate_manifest(manifest, expected_repo)
    metrics = validate_fixture(fixture)
    evidence_hash = digest(fixture)
    chain = ROOT_HASH
    receipts = []
    for seq, cell in enumerate(cells):
        receipt = {
            "sequence": seq,
            "microkernel_id": cell["id"],
            "role": cell["role"],
            "generation": cell["generation"],
            "status": "SYNTHETIC_OBSERVATION_ONLY",
            "result": observe_role(cell["role"], metrics, evidence_hash),
            "previous_sha256": chain,
        }
        receipt["receipt_sha256"] = digest(receipt)
        chain = receipt["receipt_sha256"]
        receipts.append(receipt)
    proposals = []
    if propose_child is not None:
        if propose_child not in ROLES:
            raise ValueError("unsupported child role")
        parent = next(c for c in cells if c["role"] == propose_child)
        candidate_id = "proposed-" + digest({
            "repository": manifest["repository"], "parent": parent["id"],
            "fixture": evidence_hash, "role": propose_child
        })[:16]
        proposals.append({
            "id": candidate_id,
            "parent_id": parent["id"],
            "role": propose_child,
            "generation": parent["generation"] + 1,
            "state": "PROPOSED_NOT_ACTIVE",
            "activation_allowed": False,
            "admission_gates": ["human_review", "baseline_comparison", "independent_verification", "rollback"],
        })
    report = {
        "schema": SCHEMA,
        "repository": manifest["repository"],
        "runtime": "OFFLINE_READ_ONLY_PILOT",
        "scientific_claim": "SYNTHETIC_FIXTURE_ONLY_NOT_TRAINED_MODEL",
        "manifest_sha256": digest(manifest),
        "fixture_sha256": evidence_hash,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "microkernel_count": len(cells),
        "receipts": receipts,
        "proposed_children": proposals,
        "action_authority": False,
        "status": "PASS_WITH_OPERATIONAL_HOLD",
    }
    report["report_sha256"] = digest(report)
    return report


def verify_report(report):
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("invalid report schema")
    stamp = report.get("report_sha256")
    if not isinstance(stamp, str) or stamp != digest({k: v for k, v in report.items() if k != "report_sha256"}):
        raise ValueError("report integrity mismatch")
    receipts = report.get("receipts")
    if not isinstance(receipts, list) or not 6 <= len(receipts) <= 16 or report.get("microkernel_count") != len(receipts):
        raise ValueError("invalid receipt count")
    prev = ROOT_HASH
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict) or receipt.get("sequence") != index or receipt.get("previous_sha256") != prev:
            raise ValueError("broken receipt chain")
        stamp = receipt.get("receipt_sha256")
        if not isinstance(stamp, str) or stamp != digest({k: v for k, v in receipt.items() if k != "receipt_sha256"}):
            raise ValueError("receipt integrity mismatch")
        prev = stamp
    if report.get("action_authority") is not False or report.get("status") != "PASS_WITH_OPERATIONAL_HOLD":
        raise ValueError("invalid authority status")
    for proposal in report.get("proposed_children", []):
        if proposal.get("state") != "PROPOSED_NOT_ACTIVE" or proposal.get("activation_allowed") is not False:
            raise ValueError("active offspring not permitted")
    return True


def main():
    parser = argparse.ArgumentParser(description="Offline ESSENCE microkernel read-only pilot")
    parser.add_argument("--manifest")
    parser.add_argument("--fixture")
    parser.add_argument("--out")
    parser.add_argument("--allow-readonly", action="store_true")
    parser.add_argument("--propose-child", choices=ROLES)
    parser.add_argument("--verify")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps({"verified": verify_report(load_json(args.verify))}, sort_keys=True))
        return
    if not args.manifest or not args.fixture:
        parser.error("--manifest and --fixture are required")
    report = evaluate(load_json(args.manifest), load_json(args.fixture),
                      explicit_readonly=args.allow_readonly, propose_child=args.propose_child)
    verify_report(report)
    payload = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.out:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
    print(json.dumps({"status": report["status"], "microkernels": len(report["receipts"]),
                      "report_sha256": report["report_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
