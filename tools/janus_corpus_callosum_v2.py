#!/usr/bin/env python3
"""JANUS Corpus Callosum v2: offline, sequential native -> simulated external -> native.

Research-only adapter. Does not perform HTTP requests, authorize tools, update
weights, write ACK, or promote an unverified statement. An actual GOLEM API
must be integrated behind a separate provider-specific, consented gate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from genesis_beetle_model_consumption import ConsumptionError, compact, load_verified, sha256
from janus_corpus_callosum import (
    NATIVE_ID, _body_hash, _native_prompt, _save_atomic, _valid_native,
    run_demiurge_native, MAX_NATIVE_OUTPUT, SHA,
)
from janus_corpus_home_handoff import protected_snapshot

SCHEMA = "janus.genesis.corpus_callosum.sequential.v2"
ALLOWED_STANCES = {"SUPPORTS", "DISPUTES", "UNDETERMINED"}
STATES = {
    "NATIVE_EXTERNAL_NATIVE__UNVERIFIED",
    "NATIVE_ONLY__EXTERNAL_SIMULATOR_UNAVAILABLE",
    "NATIVE_EXTERNAL__REVIEW_UNAVAILABLE",
}
MAX_TEXT = 600
MAX_RECEIPT_BYTES = 16000


def _review_prompt(reply: str, cursor: dict) -> str:
    """Native 128-byte model sees a visibly untrusted excerpt, not instructions."""
    prefix = "JANUS:REVIEW_UNTRUSTED:" + str(cursor["last_sequence"]) + ":"
    available = max(8, 90 - len(prefix.encode("utf-8")))
    excerpt = reply.encode("utf-8")[:available].decode("utf-8", "ignore")
    return prefix + excerpt


def _external_challenge(first: dict, context: dict, cursor: dict) -> dict:
    return {
        "schema": "janus.golem.offline_challenge.v2",
        "context_sha256": cursor["context_sha256"],
        "context_sequence": cursor["last_sequence"],
        "observed_context_ids": [entry["context_id"] for entry in context["recent_items"]],
        "native_initial_text": first["generated_text"][:MAX_TEXT],
        "native_initial_sha256": sha256(first["generated_text"].encode("utf-8")),
        "native_is_untrusted": True,
        "model_output_is_command": False,
        "scientific_authority_delta": 0,
    }


def _validate_external(value: dict, challenge: dict) -> dict:
    """Only simulated results are admitted in v2, never impersonate a live API."""
    if not isinstance(value, dict) or set(value) != {
        "mode", "provider", "text", "stance", "context_sha256",
        "native_initial_sha256", "observed_context_ids",
    }:
        raise ConsumptionError("offline external schema is invalid")
    ids = value["observed_context_ids"]
    if (value["mode"] != "OFFLINE_SIMULATED_EXTERNAL" or
        value["provider"] != "FIXTURE_ONLY_NOT_A_REAL_PROVIDER" or
        not isinstance(value["text"], str) or not 0 < len(value["text"]) <= MAX_TEXT or
        value["stance"] not in ALLOWED_STANCES or
        value["context_sha256"] != challenge["context_sha256"] or
        value["native_initial_sha256"] != challenge["native_initial_sha256"] or
        not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or
        not set(ids).issubset(set(challenge["observed_context_ids"]))):
        raise ConsumptionError("offline external response is not bound to native input")
    return {**value, "text_sha256": sha256(value["text"].encode("utf-8"))}


def _receipt_filename(cursor: dict) -> str:
    return f'{cursor["last_sequence"]:08d}-{cursor["context_sha256"][:16]}.json'


def _validate(doc: dict, context: dict, cursor: dict, native_head: str | None = None) -> None:
    """Validate more than a self-calculated hash: reconstruct every stage binding."""
    if not isinstance(doc, dict) or set(doc) != {
        "schema", "state", "context_sequence", "context_sha256",
        "native_initial", "external_simulated", "native_review",
        "stage_sha256", "disagreement", "quality", "ack_advanced",
        "scientific_authority_delta", "external_effect_authority_delta",
        "auto_training_allowed", "code_mutation_allowed", "receipt_sha256",
    }:
        raise ConsumptionError("invalid v2 receipt schema")
    if (doc["schema"] != SCHEMA or doc["state"] not in STATES or
        doc["context_sequence"] != cursor["last_sequence"] or
        doc["context_sha256"] != cursor["context_sha256"] or
        doc["receipt_sha256"] != _body_hash(doc) or
        doc["ack_advanced"] is not False or
        doc["scientific_authority_delta"] != 0 or
        doc["external_effect_authority_delta"] != 0 or
        doc["auto_training_allowed"] is not False or
        doc["code_mutation_allowed"] is not False or
        doc["quality"] != "NOT_EVALUATED"):
        raise ConsumptionError("v2 receipt authority or checksum invalid")
    native = doc["native_initial"]
    if not isinstance(native, dict) or not SHA.fullmatch(str(native.get("source_commit", ""))):
        raise ConsumptionError("missing native source identity")
    head = native["source_commit"]
    if native_head is not None and head != native_head:
        raise ConsumptionError("native head changed")
    if _valid_native(native, head, _native_prompt(context, cursor)) != native:
        raise ConsumptionError("native first stage not valid")
    external = doc["external_simulated"]
    review = doc["native_review"]
    hashes = doc["stage_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != {
        "first", "external_challenge", "external_reply", "review_prompt", "review"
    }:
        raise ConsumptionError("invalid causal chain")
    challenge = _external_challenge(native, context, cursor)
    if hashes["first"] != sha256(compact(native)) or (
        hashes["external_challenge"] != sha256(compact(challenge))):
        raise ConsumptionError("native -> external chain broken")
    if external is None:
        if (review is not None or doc["state"] != "NATIVE_ONLY__EXTERNAL_SIMULATOR_UNAVAILABLE" or
            hashes["external_reply"] is not None or hashes["review_prompt"] is not None or
            hashes["review"] is not None or doc["disagreement"] != "NOT_MEASURED_NO_EXTERNAL"):
            raise ConsumptionError("invented external stage")
    else:
        checked = _validate_external({k: v for k, v in external.items()
                                      if k != "text_sha256"}, challenge)
        if checked != external or hashes["external_reply"] != sha256(compact(external)):
            raise ConsumptionError("external stage evidence drift")
        expected_disagreement = ("DISPUTE_REPORTED_NOT_ADJUDICATED" if
                                external["stance"] == "DISPUTES" else
                                "NO_DISPUTE_REPORTED_NOT_CONSENSUS")
        if doc["disagreement"] != expected_disagreement:
            raise ConsumptionError("disagreement assessment drift")
        prompt = _review_prompt(external["text"], cursor)
        if hashes["review_prompt"] != sha256(prompt.encode("utf-8")):
            raise ConsumptionError("review challenge not bound to external text")
        if review is None:
            if doc["state"] != "NATIVE_EXTERNAL__REVIEW_UNAVAILABLE" or hashes["review"] is not None:
                raise ConsumptionError("invented native review")
        else:
            if doc["state"] != "NATIVE_EXTERNAL_NATIVE__UNVERIFIED":
                raise ConsumptionError("invented complete roundtrip")
            if (_valid_native(review, head, prompt) != review or
                review["checkpoint_sha256"] != native["checkpoint_sha256"] or
                hashes["review"] != sha256(compact(review))):
                raise ConsumptionError("native review lineage mismatch")


def attest_roundtrip(home: Path, *, baseline: dict | None = None,
                     expected_native_head: str | None = None) -> dict:
    core = protected_snapshot(home)
    if baseline is not None and baseline != core:
        raise ConsumptionError("protected HOME state changed")
    context, cursor, _ = load_verified(home / "memory/beetle/CONTEXT.json",
                                       home / "memory/beetle/CURSOR.json")
    target = home / "corpus_callosum_v2" / _receipt_filename(cursor)
    if (target.is_symlink() or target.parent.is_symlink() or
        not target.is_file() or target.stat().st_size > MAX_RECEIPT_BYTES):
        raise ConsumptionError("missing or unsafe v2 receipt")
    doc = json.loads(target.read_bytes())
    _validate(doc, context, cursor, expected_native_head)
    return {
        "status": "SEQUENTIAL_RECEIPT_VALIDATED_NOT_TRUTH",
        "receipt_path": "corpus_callosum_v2/" + target.name,
        "receipt_sha256": sha256(target.read_bytes()),
        "core_sha256": core,
        "context_sequence": cursor["last_sequence"],
        "scientific_authority_delta": 0,
        "ack_advanced": False,
    }


def roundtrip(home: Path, env: dict[str, str], *, execute: bool = False,
              native_repo: Path | None = None, native_head: str | None = None,
              native_runner: Callable = run_demiurge_native,
              external_simulator: Callable | None = None) -> dict:
    context, cursor, _ = load_verified(home / "memory/beetle/CONTEXT.json",
                                       home / "memory/beetle/CURSOR.json")
    if not execute:
        return {"status": "SEQUENTIAL_DRY_RUN_NO_INFERENCE", "no_network": True,
                "context_sequence": cursor["last_sequence"]}
    if env.get("JANUS_BICAMERAL_V2_OFFLINE") != "1":
        raise ConsumptionError("sequential offline gate requires explicit opt-in")
    if not native_repo or not native_head or not SHA.fullmatch(native_head):
        raise ConsumptionError("native checkout must be fixed to a full Git commit")
    if external_simulator is None:
        raise ConsumptionError("no external simulator supplied; never auto-call a provider")
    home_core = protected_snapshot(home)
    target = home / "corpus_callosum_v2" / _receipt_filename(cursor)
    if target.is_symlink() or target.parent.is_symlink():
        raise ConsumptionError("unsafe sequential receipt path")
    if target.exists():
        verified = attest_roundtrip(home, baseline=home_core,
                                    expected_native_head=native_head)
        return {"status": "SEQUENTIAL_ALREADY_RECEIPTED_NO_INFERENCE",
                "receipt_sha256": verified["receipt_sha256"]}
    prompt = _native_prompt(context, cursor)
    first = _valid_native(native_runner(native_repo, native_head, prompt),
                          native_head, prompt)
    challenge = _external_challenge(first, context, cursor)
    external = None
    review = None
    try:
        external = _validate_external(external_simulator(challenge), challenge)
    except (ConsumptionError, ValueError, TypeError, KeyError, OSError):
        external = None
    review_prompt = _review_prompt(external["text"], cursor) if external else None
    if external is not None:
        try:
            review = _valid_native(native_runner(native_repo, native_head, review_prompt),
                                   native_head, review_prompt)
            if review["checkpoint_sha256"] != first["checkpoint_sha256"]:
                raise ConsumptionError("native weights switched between hemispheric stages")
        except (ConsumptionError, ValueError, TypeError, KeyError, OSError):
            review = None
    state = ("NATIVE_ONLY__EXTERNAL_SIMULATOR_UNAVAILABLE" if external is None else
             "NATIVE_EXTERNAL__REVIEW_UNAVAILABLE" if review is None else
             "NATIVE_EXTERNAL_NATIVE__UNVERIFIED")
    doc = {
        "schema": SCHEMA, "state": state,
        "context_sequence": cursor["last_sequence"],
        "context_sha256": cursor["context_sha256"],
        "native_initial": first, "external_simulated": external,
        "native_review": review,
        "stage_sha256": {
            "first": sha256(compact(first)),
            "external_challenge": sha256(compact(challenge)),
            "external_reply": sha256(compact(external)) if external else None,
            "review_prompt": sha256(review_prompt.encode("utf-8")) if review_prompt else None,
            "review": sha256(compact(review)) if review else None,
        },
        "disagreement": ("NOT_MEASURED_NO_EXTERNAL" if external is None else
                         "DISPUTE_REPORTED_NOT_ADJUDICATED" if external["stance"] == "DISPUTES"
                         else "NO_DISPUTE_REPORTED_NOT_CONSENSUS"),
        "quality": "NOT_EVALUATED", "ack_advanced": False,
        "scientific_authority_delta": 0, "external_effect_authority_delta": 0,
        "auto_training_allowed": False, "code_mutation_allowed": False,
    }
    doc["receipt_sha256"] = _body_hash(doc)
    if protected_snapshot(home) != home_core:
        raise ConsumptionError("HOME state changed during the sequential experiment")
    _validate(doc, context, cursor, native_head)
    _save_atomic(target, doc)
    return {"status": state, "context_sequence": cursor["last_sequence"],
            "receipt_path": str(target), "external_mode": "OFFLINE_SIMULATED",
            "quality": "NOT_EVALUATED"}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Read-only v2 protocol inspection")
    p.add_argument("--home-root", required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(roundtrip(args.home_root, {}, execute=False), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
