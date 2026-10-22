#!/usr/bin/env python3
"""Zero-account, zero-payment AI Horde public-question adapter for JANUS AURA.

The provider's documented anonymous API key 0000000000 is NOT a secret and
cannot authorize billing. Volunteer worker hosts may see all prompt text.
Only one of the upstream AURA's frozen, generic public *card* questions may
be sent. No context IDs/hashes, HOME memory, personalities or transcripts.

Research-only, bounded one-request protocol; no schedule, account creation,
quota circumvention, production HOME publisher, training or action authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib import request, error

from genesis_beetle_model_consumption import ConsumptionError, compact, sha256

SCHEMA = "janus.golem.ai_horde_public_anonymous.v1"
API = "https://aihorde.net/api/v2"
ANON_KEY = "0000000000"
MAX_OUTPUT = 650
MAX_POLLS = 6
POLL_SECONDS = 4
ID = re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9-]{27,40}\Z")

# Only official pre-reviewed refusal codes may be included in public receipts.
# Never print an upstream message, HTML body, header, URL or arbitrary string.
SAFE_REJECTION_CODES = frozenset({
    "AnonForbidden", "BadClientAgent", "InvalidAPIKey", "KudosUpfront",
    "TimeoutIP", "TooManySameIPs", "UnsafeIP", "NotTrusted",
})

# Exact immutable card questions from AURA's reviewed Shabitat heuristic v1.
# Anything containing user content, metadata, a customized prompt or a new
# card not explicitly audited is NOT eligible for anonymous volunteer egress.
PUBLIC_AURA_QUESTIONS = frozenset({
    "Which assumption would change the reading most if it were false?",
    "What is the smallest move that preserves the most future choices?",
    "What single observation would most reduce uncertainty?",
    "What would a reasonable person who disagrees examine first?",
    "Which part of the goal is actually non-negotiable?",
    "Can the same help be offered with an easy refusal or exit?",
    "Where is the first point where lineage becomes uncertain?",
    "Would a lighter neutral bridge restore perspective here?",
})
DEFAULT_PUBLIC_QUESTION = "What single observation would most reduce uncertainty?"


def _http(method: str, path: str, body: dict | None = None) -> dict:
    """A very small no-redirect HTTPS client with a fixed API prefix."""
    if method not in {"GET", "POST", "DELETE"}:
        raise ConsumptionError("HORDE_UNREVIEWED_HTTP_METHOD")
    if path != "/generate/text/async" and not re.fullmatch(
        r"/generate/text/status/[0-9a-fA-F-]{36}", path
    ):
        raise ConsumptionError("HORDE_UNREVIEWED_ENDPOINT")
    url = API + path
    data = compact(body) if body is not None else None
    headers = {
        "Accept": "application/json",
        # Official integration guidance requires name:version:contact_details.
        # Identify this client truthfully; do not imitate a browser.
        "Client-Agent": "JANUS-AURA-GOLEM:0.2:github.com/Hawkar-usls/Janus_Genesis/issues",
        "User-Agent": "JANUS-AURA-GOLEM/0.2 (+https://github.com/Hawkar-usls/Janus_Genesis/issues)",
        "apikey": ANON_KEY,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ConsumptionError("HORDE_REDIRECT_FORBIDDEN")
    opener = request.build_opener(NoRedirect)
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=12) as response:
            content = response.read(32001)
        if len(content) > 32000:
            raise ConsumptionError("HORDE_RESPONSE_OVERSIZE")
        decoded = json.loads(content)
        if not isinstance(decoded, dict):
            raise ConsumptionError("HORDE_BAD_JSON_OBJECT")
        return decoded
    except error.HTTPError as exc:
        label = f"HORDE_HTTP_{exc.code}"
        try:
            # Bounded diagnostic read; never echo the provider's message.
            raw_error = exc.read(2049)
            if len(raw_error) <= 2048:
                parsed = json.loads(raw_error)
                if isinstance(parsed, dict) and parsed.get("rc") in SAFE_REJECTION_CODES:
                    label += "_" + parsed["rc"]
        except (ValueError, UnicodeError, OSError, TypeError):
            pass
        raise ConsumptionError(label) from exc
    except error.URLError as exc:
        raise ConsumptionError("HORDE_TRANSPORT_UNREACHABLE") from exc
    except (TimeoutError, ValueError, UnicodeDecodeError) as exc:
        raise ConsumptionError("HORDE_NETWORK_OR_JSON_FAILED") from exc


def _public_prompt(question: str) -> str:
    if question not in PUBLIC_AURA_QUESTIONS:
        raise ConsumptionError("HORDE_QUESTION_NOT_FROZEN_PUBLIC_AURA_CARD")
    return (
        "This is an openly published, generic AURA Oracle research exercise. "
        "Provide one alternative hypothesis or falsifying observation, "
        "in no more than two short sentences. No commands, personal data, "
        "accounts, secrets or predictions.\nPublic question: " + question
    )


def query_public(question: str = DEFAULT_PUBLIC_QUESTION, *,
                 execute: bool = False, transport: Callable = _http,
                 sleeper: Callable = time.sleep) -> dict:
    """At most one generation POST, six low-frequency status polls.

    Fixture calls MUST NOT be reported as genuine network inference. A failed
    or unfinished request returns UNKNOWN, never a substitute model answer.
    """
    prompt = _public_prompt(question)
    base = {
        "schema": SCHEMA, "provider": "ai-horde-anonymous",
        "provider_free_no_account_documented": True,
        "money_payment_authorized": False, "paid_fallback": False,
        "private_context_exported": False, "prompt_source": "FROZEN_PUBLIC_AURA_CARD",
        "prompt_sha256": sha256(prompt.encode("utf-8")),
        "prompt_sent": False, "network_model_response_observed": False,
        "source": "ACTUAL_ANONYMOUS_HTTP" if transport is _http
                  else "INJECTED_FIXTURE_NOT_REAL_AI",
        "status": "DRY_RUN_NO_NETWORK",
        "attempts": 0, "polls": 0, "model_reported_unverified": None,
        "response": None, "response_sha256": None, "job_id": None,
        "failure_class": None,
        "scientific_authority_delta": 0, "ack_advanced": False,
        "auto_training_allowed": False,
    }
    if not execute:
        return base
    params = {"max_length": 64, "max_context_length": 256, "n": 1}
    payload = {"prompt": prompt, "params": params, "nsfw": False}
    # Sending over HTTPS can disclose the request even when POST fails
    # or returns HTTP 403. None = indeterminate, NEVER falsely report False.
    base.update(status="SUBMISSION_UNCONFIRMED", attempts=1,
                prompt_sent=None if transport is _http else False)
    try:
        accepted = transport("POST", "/generate/text/async", payload)
        if transport is _http:
            base["prompt_sent"] = True
        job = accepted.get("id") if isinstance(accepted, dict) else None
        if not isinstance(job, str) or not ID.fullmatch(job):
            base["status"] = "SUBMISSION_REJECTED_OR_UNVERIFIED"
            return base
        base.update(status="QUEUED_NO_COMPLETED_ANSWER", job_id=job,
                    prompt_sent=transport is _http)
        path = "/generate/text/status/" + job
        for index in range(MAX_POLLS):
            # AI Horde caches status for 1s; no burst polling.
            sleeper(POLL_SECONDS)
            status = transport("GET", path, None)
            base["polls"] = index + 1
            if not isinstance(status, dict):
                base["status"] = "INVALID_STATUS_NO_ANSWER"
                break
            generations = status.get("generations")
            if status.get("done") is True:
                if not isinstance(generations, list) or len(generations) != 1:
                    base["status"] = "COMPLETED_WITHOUT_ONE_VALID_GENERATION"
                    break
                entry = generations[0]
                text = entry.get("text") if isinstance(entry, dict) else None
                name = entry.get("model") if isinstance(entry, dict) else None
                if (not isinstance(text, str) or not 0 < len(text) <= MAX_OUTPUT
                    or not isinstance(name, str) or not 0 < len(name) <= 160):
                    base["status"] = "INVALID_EXTERNAL_GENERATION"
                    break
                base.update({
                    "status": ("REAL_ANONYMOUS_RESPONSE__UNVERIFIED"
                               if transport is _http else
                               "MOCKED_HORDE_RESPONSE__NOT_REAL"),
                    "network_model_response_observed": transport is _http,
                    "model_reported_unverified": name, "response": text,
                    "response_sha256": sha256(text.encode("utf-8")),
                })
                return base
            if status.get("faulted") is True or status.get("is_possible") is False:
                base["status"] = "PROVIDER_FAULT_OR_NO_AVAILABLE_WORKER"
                break
        # Best-effort cancellation: do not start a second generation.
        try:
            transport("DELETE", path, None)
        except (ConsumptionError, OSError, ValueError):
            pass
        return base
    except (ConsumptionError, OSError, ValueError, KeyError, TypeError) as exc:
        base["status"] = "PROVIDER_UNAVAILABLE__NO_RESPONSE"
        label = str(exc) if isinstance(exc, ConsumptionError) else ""
        base["failure_class"] = (label if label.startswith("HORDE_") and
                                  len(label) <= 64 else "UNCLASSIFIED_NETWORK_FAILURE")
        return base


def query_attested_aura(home: Path, *, execute: bool = False,
                        transport: Callable = _http,
                        sleeper: Callable = time.sleep,
                        native_repo: Path | None = None,
                        native_head: str | None = None,
                        native_runner: Callable | None = None) -> dict:
    """Reuse the merged AURA→Corpus verifier; volunteer sees only a generic card."""
    if not execute:
        return query_public(execute=False)
    from janus_corpus_aura_golem_live import load_aura_evidence
    evidence = load_aura_evidence(home)
    questions = evidence["aura"]["oracle"]["questions"]
    if not isinstance(questions, list) or not questions:
        raise ConsumptionError("HORDE_VERIFIED_AURA_HAS_NO_QUESTIONS")
    candidate = questions[0]
    if candidate not in PUBLIC_AURA_QUESTIONS:
        # Do NOT fall back to an unapproved AURA-generated question.
        raise ConsumptionError("HORDE_AURA_QUESTION_NOT_A_FROZEN_PUBLIC_CARD")
    result = query_public(candidate, execute=True,
                          transport=transport, sleeper=sleeper)
    # Bind locally without disclosing these SHA digests to volunteers.
    result["aura_receipt_sha256_local_only"] = evidence["aura_receipt_sha256"]
    result["verified_context_sha256_local_only"] = evidence["cursor"]["context_sha256"]
    result["native_review_status"] = "NOT_EXECUTED_OR_NO_MODEL_RESULT"
    if result["response"] is not None and native_repo is not None:
        from janus_corpus_callosum import _valid_native, run_demiurge_native
        from janus_corpus_callosum_v2 import _review_prompt
        runner = native_runner or run_demiurge_native
        original = evidence["v2"]["native_initial"]
        if native_head != original["source_commit"]:
            raise ConsumptionError("HORDE_NATIVE_COMMIT_DOES_NOT_MATCH_ORIGINAL")
        prompt = _review_prompt(result["response"], evidence["cursor"])
        try:
            review = _valid_native(runner(native_repo, native_head, prompt),
                                   native_head, prompt)
            if review["checkpoint_sha256"] != original["checkpoint_sha256"]:
                raise ConsumptionError("HORDE_NATIVE_REVIEW_CHECKPOINT_CHANGED")
            result["native_review_status"] = (
                "REAL_PINNED_NATIVE_CPU_UNVERIFIED" if (
                    runner is run_demiurge_native and result["network_model_response_observed"]
                ) else "MOCK_OR_PARTIAL_REVIEW_NOT_SCIENTIFIC_EVIDENCE")
            result["native_review_sha256_local_only"] = sha256(compact(review))
        except (ConsumptionError, OSError, ValueError, KeyError, TypeError):
            result["native_review_status"] = "NATIVE_REVIEW_UNAVAILABLE"
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--execute-public-demo", action="store_true")
    p.add_argument("--require-real-answer", action="store_true",
                   help="fail the availability canary unless real text arrived")
    p.add_argument("--home-root", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.require_real_answer and not args.execute_public_demo:
        p.error("--require-real-answer requires --execute-public-demo")
    if args.home_root is not None:
        report = query_attested_aura(args.home_root, execute=args.execute_public_demo)
    else:
        report = query_public(execute=args.execute_public_demo)
    body = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out is not None:
        args.out.write_text(body, encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "network_model_response_observed": report["network_model_response_observed"],
        "source": report["source"],
        "model": report["model_reported_unverified"],
        "failure_class": report["failure_class"],
        "sha256": sha256(body.encode("utf-8")),
    }, sort_keys=True))
    # An offline contract PASS is separate from a live-model response PASS.
    if args.require_real_answer and (
        report["status"] != "REAL_ANONYMOUS_RESPONSE__UNVERIFIED"
        or report["network_model_response_observed"] is not True
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
