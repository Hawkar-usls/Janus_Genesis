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
import os
from pathlib import Path
import re
import subprocess
import stat
import time
from typing import Callable
from urllib import request, error

from genesis_beetle_model_consumption import ConsumptionError, compact, sha256
from janus_corpus_home_handoff import protected_snapshot

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


def _generation_failure_class(entry: object) -> str | None:
    """Return only reviewed, non-sensitive failure labels; never provider text."""
    if not isinstance(entry, dict):
        return "HORDE_GENERATION_ENTRY_INVALID"
    answer = entry.get("text")
    model = entry.get("model")
    if not isinstance(answer, str):
        return "HORDE_GENERATION_TEXT_MISSING"
    if len(answer) > MAX_OUTPUT:
        return "HORDE_GENERATION_TEXT_OVERSIZE"
    if not answer or not any(c.isprintable() and not c.isspace() for c in answer):
        return "HORDE_GENERATION_TEXT_BLANK"
    if any(ord(c) < 32 and c not in "\n\t\r" for c in answer):
        return "HORDE_GENERATION_TEXT_CONTROLS"
    if not isinstance(model, str) or not model.strip():
        return "HORDE_GENERATION_MODEL_MISSING"
    if len(model) > 160:
        return "HORDE_GENERATION_MODEL_OVERSIZE"
    if any(not c.isprintable() for c in model):
        return "HORDE_GENERATION_MODEL_CONTROLS"
    return None


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
                failure = _generation_failure_class(entry)
                if failure is not None:
                    base["status"] = "INVALID_EXTERNAL_GENERATION"
                    base["failure_class"] = failure
                    break
                text, name = entry["text"], entry["model"]
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


def preflight_native_checkout(repo: Path, head: str, checkpoint_sha256: str) -> None:
    """Reject invalid/dirty/unpinned native checkout before any external egress."""
    from janus_corpus_callosum import SHA, CHECKPOINT_SHA, _safe_native_env

    if (not isinstance(head, str) or not SHA.fullmatch(head)
            or not isinstance(checkpoint_sha256, str)
            or not CHECKPOINT_SHA.fullmatch(checkpoint_sha256)
            or repo.is_symlink() or not repo.is_dir()):
        raise ConsumptionError("HORDE_PINNED_NATIVE_CHECKOUT_INVALID")
    # The native checkout is data, not an authority for process policy.
    # Disable Git's optional lock writes, system/global configuration, hooks
    # and fsmonitor commands; explicitly inspect all *unignored* untracked
    # files, regardless of the checkout's status.showUntrackedFiles setting.
    git_env = dict(_safe_native_env(), GIT_OPTIONAL_LOCKS="0",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    git = ["git", "-c", "core.fsmonitor=false", "-c",
           "core.hooksPath=" + os.devnull,
           "-c", "status.showUntrackedFiles=all", "-C", str(repo)]
    try:
        actual_head = subprocess.run(
            git + ["rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
            env=git_env).stdout.strip()
        dirty = subprocess.run(
            git + ["status", "--porcelain=v1", "--untracked-files=all",
                   "--ignore-submodules=none"],
            capture_output=True, text=True, timeout=5, check=True,
            env=git_env).stdout.strip()
        # A clean status excludes ignored files. Those can still override
        # Python imports or native modules if a caller added them locally.
        # Git lists ignored paths NUL-delimited, so filename escaping and
        # embedded newlines cannot conceal an executable file.
        ignored = subprocess.run(
            git + ["ls-files", "--others", "--ignored",
                   "--exclude-standard", "-z"],
            capture_output=True, text=True, timeout=5, check=True,
            env=git_env).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_GIT_FAILED") from exc
    if actual_head != head or dirty:
        raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_TREE_OR_WEIGHTS_INVALID")
    if len(ignored) > 65536:
        raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_IGNORED_INVENTORY_OVERSIZE")
    executable_suffixes = (".py", ".pyc", ".pyo", ".so", ".pyd",
                           ".pth", ".dll", ".dylib", ".egg-link")
    for name in ignored.split("\0"):
        if name and (name.lower().endswith(executable_suffixes)
                     or name.rsplit("/", 1)[-1] == "pyvenv.cfg"):
            raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_IGNORED_EXECUTABLE")
    if not all(hasattr(os, flag) for flag in
               ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
        raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_NOFOLLOW_UNSUPPORTED")

    # Anchor all relative opens to descriptors and reject a symlink/FIFO swap
    # after an earlier stat, including symlinked model/weights directories.
    fds = []
    try:
        root = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(root)
        parent = root
        for segment in ("janus_model", "checkpoints"):
            parent = os.open(segment,
                             os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent)
            fds.append(parent)
        leaf = os.open("promoted.pt",
                       os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=parent)
        fds.append(leaf)
        meta = os.fstat(leaf)
        if (not stat.S_ISREG(meta.st_mode)
                or meta.st_size > 100_000_000):
            raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_TREE_OR_WEIGHTS_INVALID")
        with os.fdopen(leaf, "rb", closefd=False) as source:
            weights = source.read(100_000_001)
        if len(weights) > 100_000_000:
            raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_TREE_OR_WEIGHTS_INVALID")
    except OSError as exc:
        raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_CHECKPOINT_OPEN_UNSAFE") from exc
    finally:
        for fd in reversed(fds):
            os.close(fd)
    if sha256(weights) != checkpoint_sha256:
        raise ConsumptionError("HORDE_NATIVE_PREFLIGHT_CHECKPOINT_MISMATCH")


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
    from janus_corpus_callosum import _valid_native, run_demiurge_native
    from janus_corpus_callosum_v2 import _review_prompt

    evidence = load_aura_evidence(home)
    questions = evidence["aura"]["oracle"]["questions"]
    if not isinstance(questions, list) or not questions:
        raise ConsumptionError("HORDE_VERIFIED_AURA_HAS_NO_QUESTIONS")
    candidate = questions[0]
    if candidate not in PUBLIC_AURA_QUESTIONS:
        # Do NOT fall back to an unapproved AURA-generated question.
        raise ConsumptionError("HORDE_AURA_QUESTION_NOT_A_FROZEN_PUBLIC_CARD")
    if (transport is _http and
            evidence["aura"].get("oracle_source_type") != "PINNED_LOCAL_AURA_CLI"):
        raise ConsumptionError("HORDE_REAL_EGRESS_REQUIRES_REAL_PINNED_AURA")

    runner = native_runner or run_demiurge_native
    native_original = None
    if native_repo is not None or native_head is not None:
        native_original = evidence["v2"]["native_initial"]
        if (native_repo is None or native_head is None
                or native_head != native_original["source_commit"]):
            raise ConsumptionError("HORDE_NATIVE_COMMIT_DOES_NOT_MATCH_ORIGINAL")
        # Real subprocess check is completed BEFORE the request reaches anyone.
        # Injected test runners never impersonate this real checkout proof.
        if runner is run_demiurge_native:
            preflight_native_checkout(native_repo, native_head,
                                      native_original["checkpoint_sha256"])

    baseline = evidence.get("home_baseline")
    if baseline is None or protected_snapshot(home) != baseline:
        raise ConsumptionError("HORDE_PROTECTED_HOME_CHANGED_BEFORE_EGRESS")

    # Network is permitted only after all local provenance/pin checks pass.
    result = query_public(candidate, execute=True,
                          transport=transport, sleeper=sleeper)
    if protected_snapshot(home) != baseline:
        raise ConsumptionError("HORDE_PROTECTED_HOME_CHANGED_AFTER_EGRESS")

    # Bind locally without disclosing these SHA digests to volunteers.
    result["aura_receipt_sha256_local_only"] = evidence["aura_receipt_sha256"]
    result["verified_context_sha256_local_only"] = evidence["cursor"]["context_sha256"]
    result["native_review_status"] = "NOT_EXECUTED_OR_NO_MODEL_RESULT"
    if result["response"] is not None and native_repo is not None:
        prompt = _review_prompt(result["response"], evidence["cursor"])
        try:
            review = _valid_native(runner(native_repo, native_head, prompt),
                                   native_head, prompt)
            if review["checkpoint_sha256"] != native_original["checkpoint_sha256"]:
                raise ConsumptionError("HORDE_NATIVE_REVIEW_CHECKPOINT_CHANGED")
            result["native_review_status"] = (
                "REAL_PINNED_NATIVE_CPU_UNVERIFIED" if (
                    runner is run_demiurge_native
                    and result["network_model_response_observed"]
                ) else "MOCK_OR_PARTIAL_REVIEW_NOT_SCIENTIFIC_EVIDENCE")
            result["native_review_sha256_local_only"] = sha256(compact(review))
        except (ConsumptionError, OSError, ValueError, KeyError, TypeError):
            result["native_review_status"] = "NATIVE_REVIEW_UNAVAILABLE"
        if protected_snapshot(home) != baseline:
            raise ConsumptionError("HORDE_PROTECTED_HOME_CHANGED_DURING_REVIEW")
    return result


def real_answer_observed(report: dict) -> bool:
    """Strict canary predicate: independently bind response bytes to receipt.

    A green workflow is evidence of external inference only when the public
    built-in HTTPS transport observed one well-formed, digest-bound answer.
    """
    if not isinstance(report, dict):
        return False
    answer = report.get("response")
    model = report.get("model_reported_unverified")
    return (
        _generation_failure_class({"text": answer, "model": model}) is None
        and report.get("failure_class") is None
        and report.get("status") == "REAL_ANONYMOUS_RESPONSE__UNVERIFIED"
        and report.get("network_model_response_observed") is True
        and report.get("source") == "ACTUAL_ANONYMOUS_HTTP"
        and report.get("prompt_sent") is True
        and report.get("attempts") == 1
        and isinstance(answer, str) and 0 < len(answer) <= MAX_OUTPUT
        and any(c.isprintable() and not c.isspace() for c in answer)
        and isinstance(model, str) and bool(model.strip()) and len(model) <= 160
        and report.get("response_sha256") == sha256(answer.encode("utf-8"))
    )


def native_end_to_end_observed(report: dict) -> bool:
    """Strict real-external + pinned-native status, not a science verdict."""
    native_hash = report.get("native_review_sha256_local_only")
    return (
        real_answer_observed(report)
        and report.get("native_review_status") == "REAL_PINNED_NATIVE_CPU_UNVERIFIED"
        and isinstance(native_hash, str)
        and re.fullmatch(r"[0-9a-f]{64}", native_hash) is not None
        and isinstance(report.get("aura_receipt_sha256_local_only"), str)
        and re.fullmatch(r"[0-9a-f]{64}",
                         report["aura_receipt_sha256_local_only"]) is not None
        and isinstance(report.get("verified_context_sha256_local_only"), str)
        and re.fullmatch(r"[0-9a-f]{64}",
                         report["verified_context_sha256_local_only"]) is not None
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--execute-public-demo", action="store_true")
    p.add_argument("--require-real-answer", action="store_true",
                   help="fail the availability canary unless real text arrived")
    p.add_argument("--home-root", type=Path)
    p.add_argument("--native-repo", type=Path)
    p.add_argument("--native-head")
    p.add_argument("--require-native-review", action="store_true",
                   help="fail unless real keyless + pinned native CPU review succeed")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.require_real_answer and not args.execute_public_demo:
        p.error("--require-real-answer requires --execute-public-demo")
    if bool(args.native_repo) != bool(args.native_head):
        p.error("--native-repo and --native-head must both be set")
    if (args.native_repo is not None and
            (args.home_root is None or not args.execute_public_demo)):
        p.error("native review requires --home-root and --execute-public-demo")
    if (args.require_native_review and
            (args.home_root is None or not args.execute_public_demo
             or args.native_repo is None or args.native_head is None)):
        p.error("--require-native-review requires real execution, HOME and pinned native")
    if args.home_root is not None:
        report = query_attested_aura(
            args.home_root, execute=args.execute_public_demo,
            native_repo=args.native_repo, native_head=args.native_head)
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
        "response_sha256": report.get("response_sha256"),
        "native_review_status": report.get("native_review_status"),
        "native_review_sha256": report.get("native_review_sha256_local_only"),
        "sha256": sha256(body.encode("utf-8")),
    }, sort_keys=True))
    # An offline contract PASS is separate from a live-model response PASS.
    if args.require_real_answer and not real_answer_observed(report):
        return 2
    if args.require_native_review and not native_end_to_end_observed(report):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
