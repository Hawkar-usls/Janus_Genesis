#!/usr/bin/env python3
"""Opt-in local AURA peer downstream of an attested JANUS Corpus v2 receipt.

AURA's real deterministic heuristic CLI is a symbolic adviser, NOT an LLM,
scientific oracle, permission engine, or verified world forecast. This module
never edits the earlier native/external evidence or Genesis HOME core.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from genesis_beetle_model_consumption import ConsumptionError, compact, sha256
from janus_corpus_callosum import _body_hash, _safe_native_env, _save_atomic
from janus_corpus_callosum_v2 import attest_roundtrip
from janus_corpus_home_handoff import protected_snapshot
from genesis_v18_7_51_shabitat_aura_oracle import build_aura_request, validate_aura_response

SCHEMA = "janus.genesis.corpus_aura_oracle_peer.v1"
AURA_REPOSITORY = "Hawkar-usls/aura-oracle-tg"
AURA_HEAD = "d04d9d0e5d14c0849cde33925974300f722e69cc"
AURA_CEILING = "AURA_HEURISTIC_IS_REFLECTIVE_INPUT_NOT_EVIDENCE_COMMAND_PERMISSION_OR_PREDICTION"
MAX_RECEIPT = 16000


def make_request(v2: dict, v2_sha: str) -> dict:
    native = v2["native_initial"]
    simulated = v2["external_simulated"] is not None
    # Never send entire Beetle history or provider tokens to a symbolic peer.
    summary = ("v2_sha256=" + v2_sha +
               "; context_sha256=" + v2["context_sha256"] +
               "; untrusted_native_text=" + native["generated_text"][:400] +
               "; external_mode=" + ("SIMULATED_NOT_REAL_MODEL" if simulated
                                     else "NO_EXTERNAL_MODEL"))
    return build_aura_request(
        request_id="CORPUS-AURA-" + v2_sha[:24],
        speaker="JANUS",
        topic="Corpus Callosum: evidence gaps and reversible alternatives",
        question="Offer alternative questions or empirical controls only. "
                 "Do not claim future knowledge or grant permissions.",
        context=summary,
    )


def real_local_aura(repo: Path, expected_head: str, request: dict) -> dict:
    """Run ONLY the pinned upstream AURA heuristic CLI with no inherited secrets."""
    if expected_head != AURA_HEAD or repo.is_symlink() or not repo.is_dir():
        raise ConsumptionError("AURA_SOURCE_NOT_APPROVED")
    script = repo / "tools" / "aura_shabitat_heuristic.py"
    if script.is_symlink() or not script.is_file():
        raise ConsumptionError("AURA_ENTRYPOINT_MISSING_OR_UNSAFE")
    env = _safe_native_env()
    try:
        actual = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5,
                                env=env, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5,
                               env=env, check=True).stdout.strip()
        if actual != expected_head or dirty:
            raise ConsumptionError("AURA_PINNED_CHECKOUT_NOT_CLEAN")
        result = subprocess.run([sys.executable, "-B", str(script), "--request", "-"],
                                input=compact(request).decode("utf-8"),
                                text=True, capture_output=True, cwd=repo,
                                env=env, timeout=12, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConsumptionError("AURA_LOCAL_PROCESS_FAILED") from exc
    if result.returncode != 0 or not result.stdout:
        raise ConsumptionError("AURA_LOCAL_HEURISTIC_REJECTED")
    if len(result.stdout.encode("utf-8")) > MAX_RECEIPT:
        raise ConsumptionError("AURA_LOCAL_RESPONSE_TOO_LARGE")
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ConsumptionError("AURA_LOCAL_RESPONSE_INVALID_JSON") from exc


def _project(response: dict, request: dict) -> dict:
    validated = validate_aura_response(response, request_id=request["request_id"])
    if (validated.get("engine") != "AURA_SHABITAT_REFLECTIVE_V1" or
        validated.get("decision_authority") != "CALLER_RETAINS_CHOICE" or
        validated.get("claim_ceiling") != AURA_CEILING or
        validated.get("deterministic_request_sha256") != sha256(compact(request))):
        raise ConsumptionError("AURA_CONTRACT_OR_REQUEST_HASH_MISMATCH")
    cards = validated.get("cards")
    if not isinstance(cards, list) or not 1 <= len(cards) <= 4:
        raise ConsumptionError("AURA_CARDS_UNBOUND")
    for card in cards:
        if (not isinstance(card, dict) or set(card) !=
            {"id", "name", "lens", "question", "caution"} or
            any(not isinstance(v, str) or not 0 < len(v) <= 600
                for v in card.values())):
            raise ConsumptionError("AURA_CARD_INVALID")
    for key in ("heuristics", "questions", "cautions"):
        if len(validated[key]) > 5 or any(len(x) > 600 or not x
                                        for x in validated[key]):
            raise ConsumptionError("AURA_ADVISORY_TEXT_TOO_LARGE")
    return {
        "status": "HEURISTIC_ONLY",
        "engine": validated["engine"],
        "deterministic_request_sha256": validated["deterministic_request_sha256"],
        "cards": cards, "heuristics": validated["heuristics"],
        "questions": validated["questions"], "cautions": validated["cautions"],
        "may_be_ignored": True, "permission_granted": False,
        "evidence_upgrade": False, "verification_claim": False,
        "prediction_claim": False, "professional_advice": False,
        "world_effect_requested": False,
        "authority_delta": 0, "mass_effect_budget_delta": 0,
        "decision_authority": "CALLER_RETAINS_CHOICE",
    }


def _context(home: Path, baseline: dict | None,
             native_head: str | None) -> tuple[dict, str]:
    attested = attest_roundtrip(home, baseline=baseline,
                                expected_native_head=native_head)
    return (json.loads((home / attested["receipt_path"]).read_bytes()),
            attested["receipt_sha256"])


def _path(home: Path, v2_hash: str) -> Path:
    return home / "corpus_aura_oracle" / (v2_hash[:32] + ".json")


def _validate_receipt(doc: dict, v2: dict, v2_hash: str) -> None:
    request = make_request(v2, v2_hash)
    allowed = {"schema", "status", "oracle_repository", "oracle_commit",
               "oracle_source_type", "v2_receipt_sha256", "context_sequence",
               "context_sha256", "request_sha256", "oracle", "oracle_sha256",
               "oracle_is_model", "forecast_claimed", "scientific_authority_delta",
               "external_effect_authority_delta", "ack_advanced",
               "training_authorized", "receipt_sha256"}
    if not isinstance(doc, dict) or set(doc) != allowed:
        raise ConsumptionError("AURA_RECEIPT_FIELDS_INVALID")
    if (doc["schema"] != SCHEMA or
        doc["status"] != "AURA_REFLECTIVE_PEER_OBSERVED__NOT_EVIDENCE" or
        doc["oracle_repository"] != AURA_REPOSITORY or doc["oracle_commit"] != AURA_HEAD or
        doc["oracle_source_type"] not in {"PINNED_LOCAL_AURA_CLI", "MOCKED_AURA_TEST_ONLY"} or
        doc["v2_receipt_sha256"] != v2_hash or
        doc["context_sequence"] != v2["context_sequence"] or
        doc["context_sha256"] != v2["context_sha256"] or
        doc["request_sha256"] != sha256(compact(request)) or
        doc["oracle_sha256"] != sha256(compact(doc["oracle"])) or
        doc["oracle_is_model"] is not False or doc["forecast_claimed"] is not False or
        doc["scientific_authority_delta"] != 0 or
        doc["external_effect_authority_delta"] != 0 or
        doc["ack_advanced"] is not False or doc["training_authorized"] is not False or
        doc["receipt_sha256"] != _body_hash(doc)):
        raise ConsumptionError("AURA_RECEIPT_CAUSAL_BINDING_INVALID")
    oracle = doc["oracle"]
    if not isinstance(oracle, dict) or set(oracle) != {
        "status", "engine", "deterministic_request_sha256", "cards",
        "heuristics", "questions", "cautions", "may_be_ignored",
        "permission_granted", "evidence_upgrade", "verification_claim",
        "prediction_claim", "professional_advice", "world_effect_requested",
        "authority_delta", "mass_effect_budget_delta", "decision_authority"}:
        raise ConsumptionError("AURA_RECEIPT_PROJECTION_INVALID")
    rebuilt = {**oracle, "schema": "aura.oracle.shabitat_heuristic_response.v1",
               "request_id": request["request_id"], "claim_ceiling": AURA_CEILING}
    if _project(rebuilt, request) != oracle:
        raise ConsumptionError("AURA_RECEIPT_ADVISORY_FORGED")


def attest_oracle(home: Path, *, baseline: dict | None = None,
                  native_head: str | None = None) -> dict:
    if baseline is not None and protected_snapshot(home) != baseline:
        raise ConsumptionError("AURA_HOME_BASELINE_CHANGED")
    v2, v2_hash = _context(home, baseline, native_head)
    target = _path(home, v2_hash)
    if target.is_symlink() or target.parent.is_symlink() or (
        not target.is_file() or target.stat().st_size > MAX_RECEIPT):
        raise ConsumptionError("AURA_RECEIPT_MISSING_OR_UNSAFE")
    _validate_receipt(json.loads(target.read_bytes()), v2, v2_hash)
    return {"status": "AURA_REFLECTIVE_RECEIPT_VALIDATED_NOT_TRUTH",
            "path": str(target), "receipt_sha256": sha256(target.read_bytes()),
            "oracle_repository": AURA_REPOSITORY,
            "scientific_authority_delta": 0, "ack_advanced": False}


def consult_oracle(home: Path, env: dict[str, str], *,
                   execute: bool = False, aura_repo: Path | None = None,
                   aura_head: str = AURA_HEAD,
                   native_head: str | None = None,
                   oracle_runner: Callable = real_local_aura) -> dict:
    baseline = protected_snapshot(home)
    v2, v2_hash = _context(home, baseline, native_head)
    if not execute:
        return {"status": "AURA_REFLECTIVE_PEER_DRY_RUN_NO_PROCESS",
                "v2_receipt_sha256": v2_hash}
    if env.get("JANUS_CORPUS_AURA_ENABLED") != "1" or (
        aura_head != AURA_HEAD or aura_repo is None):
        raise ConsumptionError("AURA_LOCAL_PEER_OPT_IN_AND_PINNED_SOURCE_REQUIRED")
    target = _path(home, v2_hash)
    if target.is_symlink() or target.parent.is_symlink():
        raise ConsumptionError("AURA_RECEIPT_PATH_UNSAFE")
    if target.exists():
        existing = attest_oracle(home, baseline=baseline, native_head=native_head)
        return {"status": "AURA_ALREADY_RECEIPTED_NO_REEXECUTION",
                "receipt_sha256": existing["receipt_sha256"]}
    request = make_request(v2, v2_hash)
    projection = _project(oracle_runner(aura_repo, aura_head, request), request)
    doc = {
        "schema": SCHEMA, "status": "AURA_REFLECTIVE_PEER_OBSERVED__NOT_EVIDENCE",
        "oracle_repository": AURA_REPOSITORY, "oracle_commit": aura_head,
        "oracle_source_type": ("PINNED_LOCAL_AURA_CLI" if oracle_runner is
                               real_local_aura else "MOCKED_AURA_TEST_ONLY"),
        "v2_receipt_sha256": v2_hash, "context_sequence": v2["context_sequence"],
        "context_sha256": v2["context_sha256"],
        "request_sha256": sha256(compact(request)), "oracle": projection,
        "oracle_sha256": sha256(compact(projection)), "oracle_is_model": False,
        "forecast_claimed": False, "scientific_authority_delta": 0,
        "external_effect_authority_delta": 0, "ack_advanced": False,
        "training_authorized": False,
    }
    doc["receipt_sha256"] = _body_hash(doc)
    _validate_receipt(doc, v2, v2_hash)
    if protected_snapshot(home) != baseline:
        raise ConsumptionError("AURA_HOME_CHANGED_DURING_CONSULT")
    _save_atomic(target, doc)
    return {"status": doc["status"], "receipt_path": str(target),
            "oracle_source_type": doc["oracle_source_type"],
            "oracle_scientific_authority": False}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--home-root", required=True, type=Path)
    p.add_argument("--aura-repo", type=Path)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    result = consult_oracle(args.home_root, dict(os.environ),
                            execute=args.execute, aura_repo=args.aura_repo)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
