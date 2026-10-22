#!/usr/bin/env python3
"""Opt-in, separate AURA -> genuine free GOLEM -> native review research lane.

Never upgrades Corpus v2's simulated external participant to a real one.
Existing upstream receipts are *read-only* inputs. A model reply is not proof.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Callable
import urllib.error

from genesis_beetle_model_consumption import ConsumptionError, compact, load_verified, sha256
from golem_adaptive_tower import (STATE_NAME, eligible_providers, load_state,
                                  record_failure, record_success, reserve_attempt, save_state)
from golem_free_federation import FREE_PROVIDERS, available, request_free_provider
from janus_corpus_callosum import _body_hash, _save_atomic, _valid_native, run_demiurge_native
from janus_corpus_callosum_v2 import _review_prompt
from janus_corpus_home_handoff import protected_snapshot

SCHEMA = "janus.genesis.corpus_aura_golem_live.v1"
REQUEST_SCHEMA = "janus.genesis.aura_golem_research_question.v1"
ENABLED_FLAG = "JANUS_CORPUS_AURA_GOLEM_LIVE_ENABLED"
FREE_ONLY_FLAG = "JANUS_GOLEM_NO_BILLING_CONFIRMED"
PROVIDER_FLAG = "JANUS_CORPUS_AURA_GOLEM_PROVIDER"
MAX_REPLY = 600
MAX_BYTES = 16000


def load_aura_evidence(home: Path) -> dict:
    """Only the already validated AURA receipt downstream of an attested v2."""
    from janus_corpus_aura_oracle import attest_oracle
    from janus_corpus_aura_oracle import _context
    baseline = protected_snapshot(home)
    witness = attest_oracle(home, baseline=baseline)
    v2, v2_sha = _context(home, baseline, None)
    # Pin a single byte snapshot. The attestor may have read this path
    # before an adversary replaced it; never consume separately read bytes.
    from janus_corpus_aura_oracle import MAX_RECEIPT, _validate_receipt
    path = Path(witness["path"])
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise ConsumptionError("AURA_RECEIPT_SNAPSHOT_PATH_UNSAFE")
    raw = path.read_bytes()
    digest = sha256(raw)
    if len(raw) > MAX_RECEIPT or digest != witness["receipt_sha256"]:
        raise ConsumptionError("AURA_RECEIPT_SNAPSHOT_HASH_CHANGED")
    try:
        aura = json.loads(raw)
        _validate_receipt(aura, v2, v2_sha)
    except (ValueError, KeyError, TypeError) as exc:
        raise ConsumptionError("AURA_RECEIPT_SNAPSHOT_INVALID") from exc
    context, cursor, _ = load_verified(home / "memory/beetle/CONTEXT.json",
                                       home / "memory/beetle/CURSOR.json")
    if (aura["v2_receipt_sha256"] != v2_sha or
            aura["oracle"]["status"] != "HEURISTIC_ONLY" or
            aura["context_sha256"] != cursor["context_sha256"] or
            aura["context_sequence"] != cursor["last_sequence"]):
        raise ConsumptionError("AURA_PROVENANCE_BINDING_INVALID")
    return {"home_baseline": baseline, "aura": aura,
            "aura_receipt_sha256": digest,
            "v2": v2, "context": context, "cursor": cursor}


def challenge(evidence: dict) -> dict:
    """No full HOME, raw native text, credentials or fake Corpus-v2 LLM output."""
    aura = evidence["aura"]
    questions = aura["oracle"]["questions"]
    if (not isinstance(questions, list) or not questions or
            any(not isinstance(q, str) or not 0 < len(q) <= 600 for q in questions)):
        raise ConsumptionError("AURA_QUESTIONS_UNSAFE_OR_EMPTY")
    cursor = evidence["cursor"]
    original_ids = [item["context_id"] for item in evidence["context"]["recent_items"]][:3]
    if not original_ids or any(not isinstance(c, str) or not c for c in original_ids):
        raise ConsumptionError("CONTEXT_IDS_REQUIRED")
    # Provider sees labels that cannot directly disclose free-form context IDs.
    context_ids = ["idsha256:" + sha256(c.encode("utf-8"))[:24] for c in original_ids]
    return {
        "schema": REQUEST_SCHEMA,
        "context_sha256": cursor["context_sha256"],
        "context_sequence": cursor["last_sequence"],
        "observed_context_ids": context_ids,
        "aura_receipt_sha256": evidence["aura_receipt_sha256"],
        "question_from_existing_oracle": questions[0][:300],
        "source_is_heuristic_not_fact": True,
        "original_corpus_v2_external_was_simulated": True,
        "request_is_instruction_or_permission": False,
        "native_input_or_home_memory_exported": False,
    }


def interpret_provider(response: object, provider_name: str, requested_model: str,
                       inquiry: dict) -> dict:
    if not isinstance(response, dict) or not isinstance(response.get("choices"), list) or not response["choices"]:
        raise ConsumptionError("REAL_PROVIDER_REPLY_STRUCTURE_INVALID")
    try:
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ConsumptionError("REAL_PROVIDER_REPLY_NOT_JSON") from exc
    if not isinstance(data, dict) or set(data) != {"intake_status", "observed_context_ids", "janus_answer"}:
        raise ConsumptionError("REAL_PROVIDER_SCHEMA_INVALID")
    ids, reply = data["observed_context_ids"], data["janus_answer"]
    if (data["intake_status"] != "UNVERIFIED_CONTEXT_SEEN" or
            not isinstance(ids, list) or not ids or
            len(set(ids)) != len(ids) or
            any(not isinstance(x, str) for x in ids) or
            not set(ids).issubset(set(inquiry["observed_context_ids"])) or
            not isinstance(reply, str) or not 0 < len(reply) <= MAX_REPLY or
            any(ord(c) < 32 and c not in "\n\t" for c in reply)):
        raise ConsumptionError("REAL_PROVIDER_CONTENT_OR_CONTEXT_INVALID")
    reported_model = str(response.get("model", ""))[:128]
    return {"provider": provider_name, "model_requested": requested_model,
            "model_reported_unverified": reported_model,
            "text": reply, "text_sha256": sha256(reply.encode("utf-8")),
            "observed_context_ids": ids, "attestation": "TLS_PROVIDER_REPLY_AS_OBSERVED_NOT_INDEPENDENT_FACT"}


def select_free_provider(env: dict[str, str]):
    if (env.get(ENABLED_FLAG) != "1" or env.get("JANUS_GOLEM_FREE_ENABLED") != "1" or
            env.get(FREE_ONLY_FLAG) != "1"):
        raise ConsumptionError("LIVE_EGRESS_REQUIRES_THREE_EXPLICIT_OPT_INS")
    selected_name = env.get(PROVIDER_FLAG, "")
    routes = [r for r in available(env) if r[0].name == selected_name]
    if len(routes) != 1:
        raise ConsumptionError("NAMED_CONFIGURED_FREE_PROVIDER_REQUIRED")
    return routes[0]


def receipt_path(home: Path, inquiry: dict) -> Path:
    return home / "corpus_aura_golem_live" / (
        f'{inquiry["context_sequence"]:08d}-{inquiry["aura_receipt_sha256"][:16]}.json')


def attest_receipt(home: Path, *, evidence_loader: Callable = load_aura_evidence) -> dict:
    """Offline recheck of the source-bound chain, not proof the API was genuine."""
    evidence = evidence_loader(home)
    inquiry = challenge(evidence)
    path = receipt_path(home, inquiry)
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ConsumptionError("AURA_GOLEM_RECEIPT_MISSING_OR_UNSAFE")
    doc = json.loads(path.read_bytes())
    if not isinstance(doc, dict) or set(doc) != {
        "schema", "status", "context_sequence", "context_sha256", "aura_receipt_sha256",
        "request_sha256", "external", "external_sha256", "native_review",
        "native_review_sha256", "native_checkpoint_same_as_initial",
        "oracle_question_is_evidence", "external_is_independent_scientific_witness",
        "model_response_as_fact", "scientific_authority_delta", "external_effect_authority_delta",
        "ack_advanced", "auto_training_allowed", "production_home_auto_publish",
        "prior_corpus_v2_external_simulated", "provider_credential_recorded", "paid_fallback",
        "receipt_sha256"}:
        raise ConsumptionError("AURA_GOLEM_RECEIPT_SCHEMA_DRIFT")
    if (doc["schema"] != SCHEMA or doc["status"] not in {
                "REAL_EXTERNAL_RESPONSE__UNVERIFIED", "TEST_TRANSPORT__NOT_REAL_EXTERNAL"} or
            doc["context_sequence"] != inquiry["context_sequence"] or
            doc["context_sha256"] != inquiry["context_sha256"] or
            doc["aura_receipt_sha256"] != inquiry["aura_receipt_sha256"] or
            doc["request_sha256"] != sha256(compact(inquiry)) or
            doc["receipt_sha256"] != _body_hash(doc) or
            doc["external_sha256"] != sha256(compact(doc["external"])) or
            doc["scientific_authority_delta"] != 0 or
            doc["external_effect_authority_delta"] != 0 or
            any(doc[key] is not False for key in (
                "oracle_question_is_evidence", "external_is_independent_scientific_witness",
                "model_response_as_fact", "ack_advanced", "auto_training_allowed",
                "production_home_auto_publish", "provider_credential_recorded", "paid_fallback")) or
            doc["prior_corpus_v2_external_simulated"] is not True):
        raise ConsumptionError("AURA_GOLEM_RECEIPT_CAUSAL_BINDING_OR_AUTHORITY_DRIFT")
    external = doc["external"]
    if (not isinstance(external, dict) or set(external) != {
                "provider", "model_requested", "model_reported_unverified", "text",
                "text_sha256", "observed_context_ids", "attestation"} or
            not any(external["provider"] == p.name and external["model_requested"] == p.model
                    for p in FREE_PROVIDERS) or
            not isinstance(external["text"], str) or not 0 < len(external["text"]) <= MAX_REPLY or
            external["text_sha256"] != sha256(external["text"].encode()) or
            external["attestation"] != "TLS_PROVIDER_REPLY_AS_OBSERVED_NOT_INDEPENDENT_FACT" or
            not isinstance(external["observed_context_ids"], list) or
            not external["observed_context_ids"] or
            any(not isinstance(x, str) for x in external["observed_context_ids"]) or
            not set(external["observed_context_ids"]).issubset(set(inquiry["observed_context_ids"]))):
        raise ConsumptionError("AURA_GOLEM_EXTERNAL_PROJECTION_INVALID")
    review = doc["native_review"]
    if review is None:
        if doc["native_review_sha256"] is not None or doc["native_checkpoint_same_as_initial"] is not False:
            raise ConsumptionError("AURA_GOLEM_NATIVE_REVIEW_FORGED")
    else:
        original = evidence["v2"]["native_initial"]
        expected = _review_prompt(external["text"], evidence["cursor"])
        if (doc["native_review_sha256"] != sha256(compact(review)) or
                _valid_native(review, original["source_commit"], expected) != review or
                review["checkpoint_sha256"] != original["checkpoint_sha256"] or
                doc["native_checkpoint_same_as_initial"] is not True):
            raise ConsumptionError("AURA_GOLEM_NATIVE_REVIEW_BINDING_INVALID")
    return {"status": "RECEIPT_REPLAY_VALIDATED_NOT_TRUTH",
            "receipt_sha256": sha256(path.read_bytes()),
            "provider_result_claimed_real": doc["status"] == "REAL_EXTERNAL_RESPONSE__UNVERIFIED",
            "provider_network_authentication_replayed_offline": False,
            "scientific_authority_delta": 0}


def consult(home: Path, env: dict[str, str], *, execute: bool = False,
            native_repo: Path | None = None, native_head: str | None = None,
            native_runner: Callable = run_demiurge_native,
            transport: Callable = request_free_provider,
            evidence_loader: Callable = load_aura_evidence,
            clock: Callable = time.time) -> dict:
    if not execute:
        return {"status": "AURA_GOLEM_LIVE_DRY_RUN__NO_NETWORK_NO_DATA_WRITES",
                "live_response_observed": False, "paid_fallback": False}
    evidence = evidence_loader(home)
    inquiry = challenge(evidence)
    target = receipt_path(home, inquiry)
    if target.is_symlink() or target.parent.is_symlink() or home.is_symlink():
        raise ConsumptionError("AURA_GOLEM_RECEIPT_PATH_UNSAFE")
    if target.exists():
        raise ConsumptionError("PREEXISTING_AURA_GOLEM_RECEIPT_NO_REPLAY")
    provider, endpoint, token = select_free_provider(env)
    if not native_repo or not native_head or native_head != evidence["v2"]["native_initial"]["source_commit"]:
        raise ConsumptionError("PINNED_NATIVE_REVIEW_CHECKOUT_REQUIRED")
    # Never label a test transport or injected provenance as real external AI.
    real = transport is request_free_provider and evidence_loader is load_aura_evidence and native_runner is run_demiurge_native
    if protected_snapshot(home) != evidence["home_baseline"]:
        raise ConsumptionError("PROTECTED_HOME_CHANGED_BEFORE_EGRESS")
    # Share existing GOLEM's durable provider reservation/cooldown rather than
    # bypassing it with a second unconstrained inference path.
    tower_path = home / "model_federation" / STATE_NAME
    now = clock()
    tower = load_state(tower_path, now)
    if not eligible_providers([(provider, endpoint, token)], tower, now):
        return {"status": "NO_ELIGIBLE_FREE_PROVIDER__NO_NETWORK",
                "live_response_observed": False, "paid_fallback": False}
    reserve_attempt(tower, provider.name)
    save_state(tower_path, tower, now)
    try:
        raw = transport(provider, endpoint, token, compact(inquiry))
        external = interpret_provider(raw, provider.name, provider.model, inquiry)
    except (ConsumptionError, OSError, ValueError, KeyError, TypeError,
            urllib.error.URLError) as exc:
        code = exc.code if isinstance(exc, urllib.error.HTTPError) else None
        record_failure(tower, provider.name, now, code)
        save_state(tower_path, tower, now)
        return {"status": "PROVIDER_UNAVAILABLE_OR_INVALID__NO_RESULT_RECEIPT",
                "live_response_observed": False, "paid_fallback": False}
    record_success(tower, provider.name, now)
    save_state(tower_path, tower, now)
    review = None
    native_prompt = _review_prompt(external["text"], evidence["cursor"])
    try:
        review = _valid_native(native_runner(native_repo, native_head, native_prompt), native_head, native_prompt)
        if review["checkpoint_sha256"] != evidence["v2"]["native_initial"]["checkpoint_sha256"]:
            raise ConsumptionError("NATIVE_REVIEW_WEIGHTS_DRIFT")
    except (ConsumptionError, ValueError, OSError, TypeError, KeyError):
        review = None
    if protected_snapshot(home) != evidence["home_baseline"]:
        raise ConsumptionError("PROTECTED_HOME_CHANGED_DURING_REVIEW")
    doc = {
        "schema": SCHEMA,
        "status": "REAL_EXTERNAL_RESPONSE__UNVERIFIED" if real else "TEST_TRANSPORT__NOT_REAL_EXTERNAL",
        "context_sequence": inquiry["context_sequence"],
        "context_sha256": inquiry["context_sha256"],
        "aura_receipt_sha256": inquiry["aura_receipt_sha256"],
        "request_sha256": sha256(compact(inquiry)),
        "external": external, "external_sha256": sha256(compact(external)),
        "native_review": review,
        "native_review_sha256": sha256(compact(review)) if review else None,
        "native_checkpoint_same_as_initial": bool(review),
        "oracle_question_is_evidence": False,
        "external_is_independent_scientific_witness": False,
        "model_response_as_fact": False,
        "scientific_authority_delta": 0,
        "external_effect_authority_delta": 0,
        "ack_advanced": False, "auto_training_allowed": False,
        "production_home_auto_publish": False,
        "prior_corpus_v2_external_simulated": True,
        "provider_credential_recorded": False,
        "paid_fallback": False,
    }
    doc["receipt_sha256"] = _body_hash(doc)
    if len(compact(doc)) > MAX_BYTES:
        raise ConsumptionError("RESEARCH_RECEIPT_OVERSIZED")
    _save_atomic(target, doc)
    return {"status": doc["status"], "receipt_path": str(target),
            "model_response_observed": real, "review_present": review is not None,
            "paid_fallback": False, "authority_delta": 0}


def main() -> int:
    p = argparse.ArgumentParser(description="Opt-in AURA -> real free GOLEM -> Demiurge research")
    p.add_argument("--home-root", type=Path, required=True)
    p.add_argument("--native-repo", type=Path)
    p.add_argument("--native-head")
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    result = consult(args.home_root, dict(os.environ), execute=args.execute,
                     native_repo=args.native_repo, native_head=args.native_head)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.execute or result["status"] == "REAL_EXTERNAL_RESPONSE__UNVERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
