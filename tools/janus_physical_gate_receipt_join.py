#!/usr/bin/env python3
"""Join privacy-safe physical launch receipts for JANUS #162.

This tool does NOT run the physical experiments and can never close #162 by
itself. It verifies two deliberately minimal public projections and, before it
can emit READY_FOR_FINAL_162_GAUNTLET, authenticates those exact projections
against source-controlled bindings to real execution evidence.

The public join path has no caller-controlled trust-root override. Until real
runs are completed and their exact projection/evidence digests are pinned in the
repository protocol, the join fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA = "JANUS_PHYSICAL_GATE_PUBLIC_PROJECTION_V1"
OWNER_KIND = "JANUS_OWNER44_PUBLIC_PHYSICAL_RECEIPT_V1"
NAS_KIND = "JANUS_NAS164_PUBLIC_LIVE_RECEIPT_V1"
PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "protocol" / "JANUS_PHYSICAL_GATE_RECEIPT_JOIN-v1.0.json"
TRUST_STATUS = "PINNED_REAL_EXECUTION"

OWNER_MARKERS = {
    "REAL_OWNER_SOURCE_SET_ACCOUNTED": "44/44",
    "LOCAL_EXACT_PRIVATE_PIN_VERIFICATION": True,
    "PUBLIC_PRIVATE_EXACT_PIN_DISCLOSURE": False,
    "TWO_CLEAN_TARGET_REBUILDS_MATCH": True,
    "SOURCE_WRITEBACK_OBSERVED": False,
    "DESTRUCTIVE_ACTION_REQUIRED": False,
    "AUTHORITY_DELTA": 0,
}

OWNER_PRIVACY = {
    "private_repo_identity_disclosed": False,
    "private_exact_pins_disclosed": False,
    "sensitive_local_paths_disclosed": False,
    "private_history_digest_disclosed": False,
}

NAS_MARKERS = {
    **{f"HR{i}": "PASS" for i in range(1, 11)},
    "HR11_SOURCE_WRITEBACK_OBSERVED": False,
    "HR12_DESTRUCTIVE_ACTION_REQUIRED": False,
    "HR13_AUTHORITY_DELTA": 0,
}

NAS_LIVE = {
    "identity_probe": "PASS",
    "hr1_hr10_live_execution": True,
    "reference_only": False,
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: ROOT_MUST_BE_OBJECT")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{where}: KEYSET_MISMATCH missing={missing} extra={extra}")


def _validate_view(value: Any, expected_genesis: str, expected_swarm: str, where: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: VIEW_MUST_BE_OBJECT")
    _exact_keys(value, {"genesis_main_sha", "swarm_main_sha"}, where)
    genesis = value["genesis_main_sha"]
    swarm = value["swarm_main_sha"]
    if not isinstance(genesis, str) or not SHA40.fullmatch(genesis):
        raise ValueError(f"{where}: INVALID_GENESIS_SHA")
    if not isinstance(swarm, str) or not SHA40.fullmatch(swarm):
        raise ValueError(f"{where}: INVALID_SWARM_SHA")
    if genesis != expected_genesis:
        raise ValueError(f"{where}: GENESIS_SHA_DRIFT")
    if swarm != expected_swarm:
        raise ValueError(f"{where}: SWARM_SHA_DRIFT")
    return {"genesis_main_sha": genesis, "swarm_main_sha": swarm}


def _validate_exact_mapping(value: Any, expected: dict[str, Any], where: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: MUST_BE_OBJECT")
    _exact_keys(value, set(expected), where)
    for key, wanted in expected.items():
        actual = value[key]
        if type(actual) is not type(wanted):
            raise ValueError(
                f"{where}.{key}: TYPE_MISMATCH_EXPECTED_{type(wanted).__name__}_GOT_{type(actual).__name__}"
            )
        if actual != wanted:
            raise ValueError(f"{where}.{key}: EXPECTED_{wanted!r}_GOT_{actual!r}")


def validate_owner(receipt: dict[str, Any], expected_genesis: str, expected_swarm: str) -> dict[str, str]:
    _exact_keys(receipt, {"schema", "kind", "view", "markers", "privacy"}, "owner")
    if receipt["schema"] != SCHEMA:
        raise ValueError("owner: SCHEMA_MISMATCH")
    if receipt["kind"] != OWNER_KIND:
        raise ValueError("owner: KIND_MISMATCH")
    view = _validate_view(receipt["view"], expected_genesis, expected_swarm, "owner.view")
    _validate_exact_mapping(receipt["markers"], OWNER_MARKERS, "owner.markers")
    _validate_exact_mapping(receipt["privacy"], OWNER_PRIVACY, "owner.privacy")
    return view


def validate_nas(receipt: dict[str, Any], expected_genesis: str, expected_swarm: str) -> dict[str, str]:
    _exact_keys(receipt, {"schema", "kind", "view", "markers", "live"}, "nas")
    if receipt["schema"] != SCHEMA:
        raise ValueError("nas: SCHEMA_MISMATCH")
    if receipt["kind"] != NAS_KIND:
        raise ValueError("nas: KIND_MISMATCH")
    view = _validate_view(receipt["view"], expected_genesis, expected_swarm, "nas.view")
    _validate_exact_mapping(receipt["markers"], NAS_MARKERS, "nas.markers")
    _validate_exact_mapping(receipt["live"], NAS_LIVE, "nas.live")
    return view


def _validate_binding(value: Any, where: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: BINDING_MUST_BE_OBJECT")
    _exact_keys(value, {"projection_sha256", "evidence_sha256", "execution_id", "producer"}, where)
    projection = value["projection_sha256"]
    evidence = value["evidence_sha256"]
    execution_id = value["execution_id"]
    producer = value["producer"]
    if not isinstance(projection, str) or not SHA256.fullmatch(projection):
        raise ValueError(f"{where}: PROJECTION_SHA256_NOT_PINNED")
    if not isinstance(evidence, str) or not SHA256.fullmatch(evidence):
        raise ValueError(f"{where}: EVIDENCE_SHA256_NOT_PINNED")
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise ValueError(f"{where}: EXECUTION_ID_NOT_PINNED")
    if not isinstance(producer, str) or not producer.strip():
        raise ValueError(f"{where}: PRODUCER_NOT_PINNED")
    return {
        "projection_sha256": projection,
        "evidence_sha256": evidence,
        "execution_id": execution_id,
        "producer": producer,
    }


def _load_trusted_bindings() -> dict[str, Any]:
    protocol = _load(PROTOCOL_PATH)
    bindings = protocol.get("trusted_receipt_bindings")
    if not isinstance(bindings, dict):
        raise ValueError("TRUSTED_RECEIPT_BINDINGS_MISSING")
    return bindings


def _authenticate_receipts(owner: dict[str, Any], nas: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(bindings, {"status", "binding_source", "owner44", "nas164"}, "trusted_receipt_bindings")
    if bindings["status"] != TRUST_STATUS:
        raise ValueError("TRUSTED_RECEIPT_BINDINGS_NOT_PINNED")
    if bindings["binding_source"] != "SOURCE_CONTROLLED_PROTOCOL_ONLY":
        raise ValueError("TRUST_BINDING_SOURCE_REJECTED")

    owner_binding = _validate_binding(bindings["owner44"], "trusted_receipt_bindings.owner44")
    nas_binding = _validate_binding(bindings["nas164"], "trusted_receipt_bindings.nas164")
    owner_hash = _sha256(owner)
    nas_hash = _sha256(nas)
    if owner_hash != owner_binding["projection_sha256"]:
        raise ValueError("OWNER44_PROJECTION_NOT_AUTHENTICATED")
    if nas_hash != nas_binding["projection_sha256"]:
        raise ValueError("NAS164_PROJECTION_NOT_AUTHENTICATED")

    return {
        "binding_source": "SOURCE_CONTROLLED_PROTOCOL_ONLY",
        "owner44": owner_binding,
        "nas164": nas_binding,
    }


def _join_with_bindings_for_test(
    owner: dict[str, Any],
    nas: dict[str, Any],
    expected_genesis: str,
    expected_swarm: str,
    bindings: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic unit-test seam; production code must call join()."""
    if not SHA40.fullmatch(expected_genesis):
        raise ValueError("EXPECTED_GENESIS_SHA_INVALID")
    if not SHA40.fullmatch(expected_swarm):
        raise ValueError("EXPECTED_SWARM_SHA_INVALID")
    owner_view = validate_owner(owner, expected_genesis, expected_swarm)
    nas_view = validate_nas(nas, expected_genesis, expected_swarm)
    if owner_view != nas_view:
        raise ValueError("PHYSICAL_RECEIPT_VIEW_MISMATCH")

    authentication = _authenticate_receipts(owner, nas, bindings)
    return {
        "schema": "JANUS_PHYSICAL_GATE_RECEIPT_JOIN_RESULT_V1",
        "view": owner_view,
        "authentication": authentication,
        "input_public_projection_sha256": {
            "owner44": _sha256(owner),
            "nas164": _sha256(nas),
        },
        "markers": {
            "REAL_OWNER44_SOURCE_REPLAY": "PASS",
            "LIVE_NAS_164_HR1_HR10": "PASS",
            "AUTHENTICATED_REAL_EXECUTION_BINDINGS": "PASS",
            "PRIVATE_EXACT_PIN_PUBLIC_LEAK": False,
            "SOURCE_WRITEBACK_OBSERVED": False,
            "DESTRUCTIVE_ACTION_REQUIRED": False,
            "AUTHORITY_DELTA": 0,
            "READY_FOR_FINAL_162_GAUNTLET": True,
            "FULL_ISSUE_162_ACCEPTANCE": False,
        },
        "claim_ceiling": "PHYSICAL_GATES_AUTHENTICATED_FINAL_ONE_VIEW_GAUNTLET_STILL_REQUIRED",
    }


def join(
    owner: dict[str, Any],
    nas: dict[str, Any],
    expected_genesis: str,
    expected_swarm: str,
) -> dict[str, Any]:
    """Production join: trust root always comes from the source-controlled protocol."""
    return _join_with_bindings_for_test(
        owner,
        nas,
        expected_genesis,
        expected_swarm,
        _load_trusted_bindings(),
    )


def _write_private_no_overwrite(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(_canonical_bytes(value))
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner44-public", required=True, type=Path)
    parser.add_argument("--nas164-public", required=True, type=Path)
    parser.add_argument("--expected-genesis-sha", required=True)
    parser.add_argument("--expected-swarm-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    owner = _load(args.owner44_public)
    nas = _load(args.nas164_public)
    result = join(owner, nas, args.expected_genesis_sha, args.expected_swarm_sha)
    _write_private_no_overwrite(args.output, result)
    print("PHYSICAL_GATE_RECEIPT_JOIN=PASS")
    print("AUTHENTICATED_REAL_EXECUTION_BINDINGS=PASS")
    print("READY_FOR_FINAL_162_GAUNTLET=TRUE")
    print("FULL_ISSUE_162_ACCEPTANCE=FALSE")
    print(f"PUBLIC_JOIN_SHA256={_sha256(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
