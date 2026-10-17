# -*- coding: utf-8 -*-
"""Run one bounded model-backed JANUS Git Habitat resident cycle."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Keep direct-script execution equivalent to package/module execution. GitHub
# Actions and the NAS operator path both invoke this file directly; without the
# repository root on sys.path, Python resolves only the tools/ directory and the
# canonical Genesis modules cannot be imported. This bootstrap changes import
# context only; it grants no capability and performs no external effect.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from genesis_v18_7_40_third_wish_capability_fabric import ThirdWishCapabilityFabric
from genesis_v18_7_ai import AIProviderConfig
from tools.genesis_git_habitat import GitHabitat
from tools.genesis_git_habitat_resident_cycle import (
    ResidentChoiceError,
    ThirdWishResidentModelCaller,
    run_awake_resident_cycle,
)
from tools.genesis_git_habitat_resident_provider import OllamaResidentChoiceProvider, ResidentProviderError
from tools.genesis_third_wish_sensor_model_schedule_broker import (
    ModelAlias,
    ThirdWishSensorModelScheduleBroker,
)

RUNNER_VERSION = "18.7.52"

# Public, constant error identifiers only. Never log an arbitrary exception body.
_SAFE_PROVIDER_CODES = frozenset({
    "RESIDENT_OLLAMA_TRANSPORT_FIELDS_INVALID", "RESIDENT_OLLAMA_TRANSPORT_SCALAR_TYPE_INVALID",
    "RESIDENT_OLLAMA_TRANSPORT_TAGS_TYPE_INVALID", "RESIDENT_OLLAMA_MESSAGE_ROLE_INVALID",
    "RESIDENT_OLLAMA_MESSAGE_TOO_LONG", "RESIDENT_OLLAMA_MESSAGES_REQUIRED",
    "RESIDENT_OLLAMA_CONNECTION_FAILED", "RESIDENT_OLLAMA_TIMEOUT",
    "RESIDENT_OLLAMA_RESPONSE_ENVELOPE_INVALID", "RESIDENT_OLLAMA_RESPONSE_ENVELOPE_NOT_OBJECT",
    "RESIDENT_OLLAMA_RESPONSE_MESSAGE_MISSING", "RESIDENT_OLLAMA_RESPONSE_CONTENT_MISSING",
    *{f"RESIDENT_OLLAMA_HTTP_{code}" for code in range(400, 600)},
})


def _safe_provider_failure_code(exc: BaseException) -> str | None:
    for _ in range(8):
        if type(exc) is ResidentProviderError and str(exc) in _SAFE_PROVIDER_CODES:
            return str(exc)
        if exc.__cause__ is None:
            return None
        exc = exc.__cause__
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JANUS Git Habitat model-backed resident cycle")
    parser.add_argument("--root", default="habitat")
    parser.add_argument("--resident-id", default="JANUS")
    parser.add_argument("--broker-dir", default=".resident-cycle-broker")
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--model", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model-alias", default="habitat-resident")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--source", default="MODEL_RESIDENT")
    parser.add_argument("--require-valid-choice", action="store_true")
    return parser


def _model_alias(args: argparse.Namespace) -> ModelAlias:
    """Bind the resident-specific structured provider without widening authority."""
    normalized = str(args.provider).strip().lower()
    if normalized == "ollama":
        provider = OllamaResidentChoiceProvider(
            model=args.model,
            endpoint=args.endpoint,
            timeout_seconds=args.timeout_seconds,
        )
        return ModelAlias(
            alias=args.model_alias,
            provider=provider,
            provider_name="ollama-resident-structured",
            model_name=args.model,
            endpoint_label="operator_registered_loopback",
        )

    # Preserve the existing provider-neutral path for explicitly selected
    # non-Ollama adapters. Credentials/endpoints remain operator configuration,
    # not actor-selected parameters.
    config = AIProviderConfig(
        provider=args.provider,
        model=args.model,
        endpoint=args.endpoint,
        api_key_env=None,
        timeout_seconds=args.timeout_seconds,
    )
    return ModelAlias.from_config(args.model_alias, config)


def _underlying_outcome_exception_type(fabric: ThirdWishCapabilityFabric) -> str | None:
    """Return only the non-sensitive exception class recorded by the fabric."""
    for event in reversed(fabric.ledger.events):
        if event.get("event_type") != "CAPABILITY_ACTION_OUTCOME_UNDETERMINED":
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            value = payload.get("exception_type")
            if isinstance(value, str) and value:
                return value[:120]
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    habitat = GitHabitat(Path(args.root))
    habitat.initialize(args.resident_id)
    wake = habitat.wake(reason="MODEL_RESIDENT", source=args.source)
    cycle_id = str(wake["cycle_id"])

    alias = _model_alias(args)
    broker = ThirdWishSensorModelScheduleBroker.system(
        Path(args.broker_dir),
        models={args.model_alias: alias},
    )
    fabric = ThirdWishCapabilityFabric()
    broker.register(fabric)
    caller = ThirdWishResidentModelCaller(
        fabric=fabric,
        model_alias=args.model_alias,
        actor_id=args.resident_id,
    )

    try:
        choice_receipt = run_awake_resident_cycle(habitat, caller.call)
        if args.require_valid_choice and not choice_receipt["choice_valid"]:
            raise ResidentChoiceError(
                "VALID_MODEL_CHOICE_REQUIRED_FOR_THIS_RUN:"
                + str(choice_receipt.get("rejection_code") or "unknown")
            )
        pulse = habitat.pulse(source="MODEL_RESIDENT_POST_CHOICE")
        sleep = habitat.sleep(outcome="MODEL_RESIDENT_CYCLE_COMPLETE")
        verification = habitat.verify_journal()
        health = habitat.refresh_health()
        if not verification["ok"] or health["status"] != "HEALTHY":
            raise RuntimeError("HABITAT_INTEGRITY_FAILED_AFTER_RESIDENT_CYCLE")
    except Exception as exc:
        # Best-effort close of the local lifecycle. Callers performing a remote
        # Git transaction must not push this failed worktree as a successful
        # resident cycle.
        try:
            habitat.pulse(source="MODEL_RESIDENT_FAILED")
            habitat.sleep(outcome="MODEL_RESIDENT_CYCLE_FAILED")
        except Exception:
            pass
        safe_failure_code = (
            str(exc)[:240]
            if isinstance(exc, ResidentChoiceError)
            else type(exc).__name__
        )
        failure = {
            "schema": "janus.genesis.git_habitat.resident_cycle_failure.v1",
            "runner_version": RUNNER_VERSION,
            "cycle_id": cycle_id,
            "status": "FAILED_NOT_FOR_REMOTE_PROMOTION",
            "exception_type": type(exc).__name__,
            "failure_code": safe_failure_code,
            "exception_sha256": hashlib.sha256(
                f"{type(exc).__name__}:{exc}".encode("utf-8")
            ).hexdigest(),
            "capability_outcome_underlying_exception_type": _underlying_outcome_exception_type(fabric),
            "provider_failure_code": _safe_provider_failure_code(exc),
            "raw_exception_message_logged": False,
            "raw_model_output_stored": False,
            "raw_model_output_logged": False,
            "model_provider_call_may_have_been_entered": True,
            "resident_choice_external_effect_executed": False,
            "automatic_retry_permission": False,
        }
        print(json.dumps(failure, sort_keys=True, indent=2))
        return 3

    result = {
        "schema": "janus.genesis.git_habitat.resident_cycle_run.v1",
        "runner_version": RUNNER_VERSION,
        "cycle_id": cycle_id,
        "status": "RESIDENT_CYCLE_SETTLED",
        "choice": choice_receipt,
        "pulse": {
            "status": pulse["status"],
            "pulse_id": pulse["pulse_id"],
        },
        "sleep": {
            "status": sleep["status"],
            "cycle_id": sleep["cycle_id"],
        },
        "journal_event_count": verification["event_count"],
        "journal_last_event_hash": verification["last_event_hash"],
        "habitat_health": health["status"],
        "model_call_crossed_third_wish_capability": True,
        "model_provider_call_executed": True,
        "model_output_directly_executed": False,
        "resident_choice_external_effect_executed": False,
        "outbox_auto_execution": False,
        "consciousness_claimed": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
