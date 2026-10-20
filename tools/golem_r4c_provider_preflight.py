#!/usr/bin/env python3
"""GOLEM R4C no-network readiness witness: no secret values or paid provider calls.

This module is intentionally a *preflight only*, not a live model runner.
Credentials in a process environment do NOT independently prove free-tier
eligibility or that the user's GitHub Actions secrets exist.
"""
from __future__ import annotations

import json
import os

from golem_free_federation import FREE_PROVIDERS, available

SCHEMA = "janus.golem.r4c.free_provider_preflight.v1"


def preflight(env: dict[str, str]) -> dict:
    # available is the production allowlist. Never print endpoint/token/account ID.
    enrolled = {provider.name for provider, _, _ in available(env)}
    provider_statuses = []
    for provider in FREE_PROVIDERS:
        token_present = bool(env.get(provider.token_env))
        confirmation_present = bool(
            provider.free_plan_confirmation_env is None or
            env.get(provider.free_plan_confirmation_env) == "1")
        provider_statuses.append({
            "provider": provider.name,
            "credential_present_in_current_process": token_present,
            "free_plan_operator_flag": confirmation_present,
            "allowlisted_configuration_eligible": provider.name in enrolled,
            "billing_free_tier_independently_verified": False,
        })
    bicameral_opt_in = env.get("JANUS_BICAMERAL_ENABLED") == "1"
    free_opt_in = env.get("JANUS_GOLEM_FREE_ENABLED") == "1"
    status = ("R4C_BLOCKED_NO_CREDENTIALS" if not any(
        p["credential_present_in_current_process"] for p in provider_statuses)
        else "R4C_BLOCKED_MANUAL_OPT_IN" if not bicameral_opt_in or not free_opt_in
        else "R4C_BLOCKED_INDEPENDENT_FREE_ACCOUNT_EVIDENCE")
    return {
        "schema": SCHEMA,
        "status": status,
        "candidate_provider_names": sorted(enrolled),
        "provider_checks": provider_statuses,
        "bicameral_opt_in_in_current_process": bicameral_opt_in,
        "free_federation_opt_in_in_current_process": free_opt_in,
        "can_inspect_github_actions_secret_store": False,
        "external_model_response_verified": False,
        "billing_plan_independently_verified": False,
        "live_inference_admitted": False,
        "paid_fallback_admitted": False,
        "network_requests_performed": 0,
        "api_spend_claimed": None,
        "scientific_authority_delta": 0,
        "ack_advanced": False,
        "next_gate": "operator-approved genuinely-free account + independently verifiable billing settings + separately reviewed provider integration",
    }


def main() -> int:
    print(json.dumps(preflight(dict(os.environ)), ensure_ascii=False,
                     sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
