#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

SCHEMA = "janus.genesis.personal_sandbox_grant.v1"
EXACT_REF = "janus/habitat"
REQUIRED_ALLOWED = {
    "DISCOVER",
    "READ",
    "INSPECT",
    "INDEX_METADATA",
    "HASH",
    "COMPARE",
    "REFERENCE",
    "WRITE_SANDBOX_BRANCH",
    "CREATE_SANDBOX_ARTIFACT",
    "UPDATE_SANDBOX_STATE",
    "RUN_TARGET_LOCAL_VERIFIER",
    "SEAL_SANDBOX_RECEIPT",
}
REQUIRED_DENIED = {
    "WRITE_MAIN",
    "MERGE_MAIN",
    "DELETE_MAIN",
    "ADMIN",
    "SECRETS_READ",
    "SECRETS_WRITE",
    "PERMISSION_CHANGE",
    "AUTHORITY_ELEVATION",
}
REQUIRED_FIREWALLS = {
    "GENESIS_SANDBOX_ACCESS != MAIN_AUTHORITY",
    "SANDBOX_WRITE != MERGE_AUTHORITY",
    "NEXUS_ACTIVITY != NATURAL_GIT_LIFE_WITNESS",
    "READ_OR_EXPERIMENT != SECRETS_ACCESS",
    "NO_EXPLICIT_GRANT -> DENY",
    "TARGET_LOCAL_VERIFIER_REQUIRED",
    "SANDBOX_RECEIPT != WORLD_TRUTH",
}


def load(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("GENESIS_SANDBOX_CONTRACT_NOT_OBJECT")
    return obj


def _safe_prefix(prefix: str) -> bool:
    p = PurePosixPath(prefix)
    return (
        prefix.startswith("habitat/")
        and prefix.endswith("/")
        and ".." not in p.parts
        and not p.is_absolute()
    )


def path_allowed(path: str, prefixes: list[str]) -> bool:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or path.endswith("/"):
        return False
    return any(path.startswith(prefix) for prefix in prefixes)


def validate(contract: dict, *, target_ref: str | None = None, target_path: str | None = None) -> None:
    if contract.get("schema") != SCHEMA:
        raise RuntimeError("GENESIS_SANDBOX_SCHEMA_REJECTED")
    if contract.get("status") != "ACTIVE_BOUNDED_GRANT":
        raise RuntimeError("GENESIS_SANDBOX_GRANT_NOT_ACTIVE")
    if contract.get("resident_id") != "JANUS":
        raise RuntimeError("GENESIS_SANDBOX_RESIDENT_REJECTED")
    if contract.get("repository") != "Hawkar-usls/Janus_Genesis":
        raise RuntimeError("GENESIS_SANDBOX_REPOSITORY_REJECTED")
    if contract.get("architecture_ref") != "main" or contract.get("sandbox_ref") != EXACT_REF:
        raise RuntimeError("GENESIS_SANDBOX_REF_REJECTED")
    if contract.get("sandbox_root") != "habitat/":
        raise RuntimeError("GENESIS_SANDBOX_ROOT_REJECTED")

    allowed = set(contract.get("allowed_operations") or [])
    denied = set(contract.get("denied_operations") or [])
    if not REQUIRED_ALLOWED.issubset(allowed):
        raise RuntimeError("GENESIS_SANDBOX_ALLOWED_SURFACE_INCOMPLETE")
    if not REQUIRED_DENIED.issubset(denied):
        raise RuntimeError("GENESIS_SANDBOX_DENY_SURFACE_INCOMPLETE")
    if allowed & denied:
        raise RuntimeError("GENESIS_SANDBOX_ALLOW_DENY_COLLISION")

    prefixes = contract.get("allowed_write_prefixes") or []
    if not isinstance(prefixes, list) or not prefixes or not all(isinstance(x, str) and _safe_prefix(x) for x in prefixes):
        raise RuntimeError("GENESIS_SANDBOX_WRITE_PREFIX_REJECTED")

    authority = contract.get("authority") or {}
    exact_false = (
        "main_mutation_allowed",
        "autonomous_merge",
        "secrets_access",
        "sandbox_receipt_is_world_truth",
        "sandbox_activity_is_natural_git_life_witness",
    )
    if authority.get("authority_delta") != 0:
        raise RuntimeError("GENESIS_SANDBOX_AUTHORITY_DELTA_REJECTED")
    if any(authority.get(k) is not False for k in exact_false):
        raise RuntimeError("GENESIS_SANDBOX_AUTHORITY_CEILING_REJECTED")
    if authority.get("target_local_verifier_required") is not True:
        raise RuntimeError("GENESIS_SANDBOX_LOCAL_VERIFIER_REQUIRED")

    execution = contract.get("execution_policy") or {}
    if execution.get("default") != "DENY" or execution.get("failure_mode") != "FAIL_CLOSED":
        raise RuntimeError("GENESIS_SANDBOX_FAIL_CLOSED_REJECTED")
    if execution.get("write_requires_exact_ref") != EXACT_REF:
        raise RuntimeError("GENESIS_SANDBOX_EXACT_REF_GATE_REJECTED")
    for key in ("write_requires_allowed_prefix", "write_requires_target_local_verification", "write_requires_receipt"):
        if execution.get(key) is not True:
            raise RuntimeError(f"GENESIS_SANDBOX_EXECUTION_GATE_REJECTED:{key}")

    firewalls = set(contract.get("firewalls") or [])
    if not REQUIRED_FIREWALLS.issubset(firewalls):
        raise RuntimeError("GENESIS_SANDBOX_FIREWALL_INCOMPLETE")

    if target_ref is not None and target_ref != EXACT_REF:
        raise RuntimeError("GENESIS_SANDBOX_TARGET_REF_DENIED")
    if target_path is not None and not path_allowed(target_path, prefixes):
        raise RuntimeError("GENESIS_SANDBOX_TARGET_PATH_DENIED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--target-ref")
    ap.add_argument("--path", dest="target_path")
    args = ap.parse_args()
    contract = load(Path(args.contract))
    validate(contract, target_ref=args.target_ref, target_path=args.target_path)
    print("JANUS_GENESIS_PERSONAL_SANDBOX_GATE=PASS")
    print("AUTHORITY_DELTA=0")
    print("MAIN_MUTATION_ALLOWED=false")
    print("TARGET_LOCAL_VERIFIER_REQUIRED=true")


if __name__ == "__main__":
    main()
