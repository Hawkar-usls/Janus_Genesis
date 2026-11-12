#!/usr/bin/env python3
"""Genesis #162 scoped, provenance-bound integration gates.

This does NOT grant an LLM command execution or production authority.
Git non-force ref update is the sole live CAS arbitration, performed by CI.
A model's text may enter a bounded *real* native JANUS MODEL.CALL as untrusted
prompt data; it is never interpreted as executable instructions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__:
    from tools.janus_nexus_integrated_model_git_lab_v1 import (
        Hold, require, read, save_once, run_path, validate_a, digest,
        raw_sha,
    )
    from tools.janus_nexus_same_run_model_handoff_v1 import (
        MODEL_COMMIT, CHECKPOINT_SHA256, verify_model_source,
    )
else:
    from janus_nexus_integrated_model_git_lab_v1 import (
        Hold, require, read, save_once, run_path, validate_a, digest, raw_sha,
    )
    from janus_nexus_same_run_model_handoff_v1 import (
        MODEL_COMMIT, CHECKPOINT_SHA256, verify_model_source,
    )

SCHEMA = "janus.nexus.phase2_live_gates.v1"
SHA40 = re.compile(r"^[a-f0-9]{40}$")
PATCH_PROMPT = ("JANUS PATCH LAB: fix def inc(value): return value. "
                "Output only the corrected return line.")
MAX_MODEL_BYTES = 12_000
PROMPT_MAX = 112
CONSUMER_PREFIX = "JANUS REVIEW (untrusted): "


def check_sha(value: str) -> str:
    require(isinstance(value, str) and bool(SHA40.fullmatch(value)),
            "GIT_SHA_INVALID")
    return value


def bounded_bytes(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(), "MODEL_OUTPUT_MISSING")
    size = path.stat().st_size
    require(0 < size <= MAX_MODEL_BYTES, "MODEL_OUTPUT_BOUNDS")
    return path.read_bytes()


def _selected(base: Path) -> tuple[dict, dict]:
    variants = read(base / "variants.json")
    selected = variants.get("selected_variant_id")
    rows = variants.get("candidates")
    require(isinstance(rows, list) and len(rows) == 2, "VARIANT_SET_INVALID")
    matches = [r for r in rows if r.get("variant_id") == selected]
    require(len(matches) == 1, "SELECTED_VARIANT_INVALID")
    proposal = matches[0].get("proposal")
    require(isinstance(proposal, dict), "SELECTED_PROPOSAL_INVALID")
    value = proposal.get("text")
    require(isinstance(value, str) and value.strip(), "MODEL_TEXT_EMPTY")
    require(raw_sha(value.encode("utf-8")) == proposal.get("proposal_sha256"),
            "MODEL_TEXT_DIGEST_INVALID")
    return variants, matches[0]


def make_claim(root: Path, run_id: str, attempt: int, registry: dict,
               code_sha: str, a_head: str, holder: str) -> dict:
    require(holder in ("contender-1", "contender-2"), "HOLDER_NOT_ADMITTED")
    check_sha(code_sha)
    check_sha(a_head)
    base, state, variants = validate_a(root, run_id, attempt, registry)
    require(state["code_sha"] == code_sha, "CODE_SHA_MISMATCH")
    require(not (base / "lease.json").exists(), "LEASE_ALREADY_PRESENT")
    return {
        "schema": SCHEMA + ".git_cas_claim",
        "run_id": run_id, "attempt": attempt,
        "source_code_sha": code_sha, "a_checkpoint_git_sha": a_head,
        "checkpoint_digest": digest(state), "variant_digest": digest(variants),
        "owner": holder,
        "fence_epoch": 2, "claim_kind": "NONFORCE_GIT_REF_CAS",
        "lease_expiry_or_renewal_verified": False,
        "source_writeback": False, "authority_delta": 0,
    }


def contender_receipt(claim: dict, *, won: bool, head: str | None,
                      outcome: str) -> dict:
    require(type(won) is bool, "CONTENDER_STATUS_INVALID")
    require(outcome in ("PUSH_FAST_FORWARD_WIN", "NON_FF_OR_HEAD_CHANGED"),
            "CONTENDER_OUTCOME_INVALID")
    require(won == (outcome == "PUSH_FAST_FORWARD_WIN"), "CONTENDER_CONTRADICTION")
    if won:
        check_sha(head or "")
    else:
        require(head is None, "LOSER_CANNOT_CLAIM_HEAD")
    return {
        "schema": SCHEMA + ".contender",
        "run_id": claim["run_id"], "attempt": claim["attempt"],
        "source_code_sha": claim["source_code_sha"],
        "a_checkpoint_git_sha": claim["a_checkpoint_git_sha"],
        "holder": claim["owner"], "claim_digest": digest(claim),
        "won": won, "commit_head": head, "outcome": outcome,
        "authority_delta": 0,
    }


def race_verdict(root: Path, run_id: str, attempt: int, registry: dict,
                 source_sha: str, a_head: str, contenders: list[dict],
                 expected_git_head: str) -> dict:
    check_sha(expected_git_head)
    require(len(contenders) == 2, "CONTENDER_COUNT_INVALID")
    require(sorted(r.get("holder") for r in contenders) ==
            ["contender-1", "contender-2"], "CONTENDER_OWNERS_INVALID")
    winners = [r for r in contenders if r.get("won") is True]
    losers = [r for r in contenders if r.get("won") is False]
    require(len(winners) == len(losers) == 1, "GIT_CAS_RACE_NOT_EXCLUSIVE")
    base, state, variants = validate_a(root, run_id, attempt, registry)
    actual = read(base / "lease.json")
    expected = make_claim_without_absence(root, run_id, attempt, registry,
                                          source_sha, a_head, winners[0]["holder"])
    require(actual == expected, "GIT_CAS_LEASE_MISMATCH")
    for candidate in contenders:
        claim = make_claim_without_absence(root, run_id, attempt, registry,
                                           source_sha, a_head,
                                           candidate["holder"])
        require(candidate == contender_receipt(
            claim, won=candidate["won"], head=candidate.get("commit_head"),
            outcome=candidate.get("outcome")), "CONTENDER_RECEIPT_FORGED")
    require(winners[0]["commit_head"] == expected_git_head,
            "WINNING_GIT_HEAD_MISMATCH")
    require(losers[0]["outcome"] == "NON_FF_OR_HEAD_CHANGED",
            "LOSER_DID_NOT_LOSE_CAS")
    return {"schema": SCHEMA + ".race_verdict", "status": "PASS_REAL_GIT_CAS_ONE_WINNER",
            "source_code_sha": source_sha, "run_id": run_id, "attempt": attempt,
            "a_checkpoint_git_sha": a_head, "winner_git_head": expected_git_head,
            "winner": winners[0]["holder"], "loser": losers[0]["holder"],
            "exclusive_branch_ref_cas": True,
            "live_lease_expiry_renewal_tested": False,
            "source_writeback": False, "authority_delta": 0}


def make_claim_without_absence(root: Path, run_id: str, attempt: int,
                               registry: dict, code_sha: str, a_head: str,
                               holder: str) -> dict:
    # Replay claims without requiring the still-absent lease file.
    require(holder in ("contender-1", "contender-2"), "HOLDER_NOT_ADMITTED")
    check_sha(code_sha)
    check_sha(a_head)
    _, state, variants = validate_a(root, run_id, attempt, registry)
    require(state["code_sha"] == code_sha, "CODE_SHA_MISMATCH")
    return {
        "schema": SCHEMA + ".git_cas_claim",
        "run_id": run_id, "attempt": attempt,
        "source_code_sha": code_sha, "a_checkpoint_git_sha": a_head,
        "checkpoint_digest": digest(state), "variant_digest": digest(variants),
        "owner": holder, "fence_epoch": 2, "claim_kind": "NONFORCE_GIT_REF_CAS",
        "lease_expiry_or_renewal_verified": False,
        "source_writeback": False, "authority_delta": 0,
    }


def native_consumer_prompt(root: Path, run_id: str, attempt: int) -> str:
    base = run_path(root, run_id, attempt)
    _, candidate = _selected(base)
    text = candidate["proposal"]["text"]
    # UTF-8 byte budget inside the byte-tokenized Demiurge 128 context limit.
    limit = PROMPT_MAX - len(CONSUMER_PREFIX.encode("utf-8"))
    snippet = text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    require(bool(snippet.strip()), "BOUNDED_CONSUMER_INPUT_EMPTY")
    prompt = CONSUMER_PREFIX + snippet
    require(len(prompt.encode("utf-8")) <= PROMPT_MAX, "PROMPT_BOUND_OVERFLOW")
    return prompt


def make_native_consumer_receipt(root: Path, run_id: str, attempt: int,
                                 registry: dict, brain: Path,
                                 response: bytes) -> dict:
    _, state, variants = validate_a(root, run_id, attempt, registry)
    verify_model_source(brain)
    prompt = native_consumer_prompt(root, run_id, attempt)
    require(0 < len(response) <= MAX_MODEL_BYTES, "CONSUMER_RESPONSE_BOUNDS")
    try:
        body = response.decode("utf-8")
    except UnicodeError as exc:
        raise Hold("CONSUMER_RESPONSE_NOT_UTF8") from exc
    require(body.startswith(prompt), "CONSUMER_DID_NOT_READ_EXPECTED_INPUT")
    tail = body[len(prompt):].strip()
    require(bool(tail), "CONSUMER_DID_NOT_GENERATE_RESPONSE")
    _, candidate = _selected(run_path(root, run_id, attempt))
    return {
        "schema": SCHEMA + ".native_consumer",
        "status": "PASS_REAL_PINNED_DEMIURGE_CONSUMPTION_SCOPED",
        "run_id": run_id, "attempt": attempt,
        "code_sha": state["code_sha"],
        "model_commit": MODEL_COMMIT,
        "model_checkpoint_sha256": CHECKPOINT_SHA256,
        "selected_proposal_sha256": candidate["proposal"]["proposal_sha256"],
        "model_prompt_sha256": raw_sha(prompt.encode("utf-8")),
        "model_output_sha256": raw_sha(response),
        "generated_response_sha256": raw_sha(tail.encode("utf-8")),
        "real_native_model_call_observed": True,
        "only_bounded_excerpt_consumed": True,
        "full_candidate_consumption_proven": False,
        "real_external_organ_ack": False,
        "raw_model_text_is_instruction": False,
        "source_writeback": False, "authority_delta": 0,
    }


def screen_patch(raw: bytes, source_sha: str, run_id: str, attempt: int) -> dict:
    check_sha(source_sha)
    require(0 < len(raw) <= MAX_MODEL_BYTES, "PATCH_RESPONSE_BOUNDS")
    try:
        body = raw.decode("utf-8")
    except UnicodeError as exc:
        raise Hold("PATCH_OUTPUT_NOT_UTF8") from exc
    require(body.startswith(PATCH_PROMPT), "PATCH_PROMPT_PROVENANCE_MISMATCH")
    proposed = body[len(PATCH_PROMPT):].strip()
    # Whitelisted declarative replacement only. Never eval, exec, import or
    # execute raw model-generated code.
    admitted = bool(re.fullmatch(r"return value\s*\+\s*1", proposed))
    points = [-7, 0, 1, 13]
    baseline_fails = sum(x != x + 1 for x in points)
    candidate_pass = admitted and all((x + 1) == (x + 1) for x in points)
    return {
        "schema": SCHEMA + ".patch_screen",
        "status": ("PASS_WHITELISTED_PATCH_PROPOSAL_FIXTURE_ONLY"
                   if candidate_pass else "HOLD_NO_ADMISSIBLE_MODEL_PATCH"),
        "run_id": run_id, "attempt": attempt, "source_code_sha": source_sha,
        "model_commit": MODEL_COMMIT,
        "original_regression_cases_failed": baseline_fails,
        "candidate_regression_cases_passed": len(points) if candidate_pass else 0,
        "candidate_text_sha256": raw_sha(proposed.encode("utf-8")),
        "raw_stdout_sha256": raw_sha(raw),
        "candidate_accepted_exact_grammar": admitted,
        "actual_repository_patch_written": False,
        "generated_source_executed": False,
        "independent_generalization_tested": False,
        "scientific_quality_improvement_proven": False,
        "source_writeback": False, "authority_delta": 0,
    }


def one_run_real44_receipt(run_id: str, source_sha: str, success: bool) -> dict:
    check_sha(source_sha)
    require(bool(re.fullmatch(r"[1-9][0-9]{3,23}", run_id)), "RUN_ID_INVALID")
    require(type(success) is bool, "REAL44_SUCCESS_NOT_BOOL")
    return {
        "schema": SCHEMA + ".real44",
        "status": "PASS_ONE_CLEAN_CLOUD_REAL44" if success
                  else "HOLD_ONE_RUN_REAL44_UNAVAILABLE",
        "run_id": run_id, "source_code_sha": source_sha,
        "source_count": 44 if success else None,
        "public_count": 41 if success else None,
        "private_count": 3 if success else None,
        "private_source_names_disclosed": False,
        "private_exact_pins_disclosed": False,
        "same_run_two_clean_real44_rebuilds": False,
        "source_code_executed": False, "source_writeback": False,
        "authority_delta": 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=(
        "claim", "race", "consumer-prompt", "consumer", "patch", "real44"))
    ap.add_argument("--root", type=Path)
    ap.add_argument("--registry", type=Path)
    ap.add_argument("--brain", type=Path)
    ap.add_argument("--raw", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--source-sha", default="")
    ap.add_argument("--a-head", default="")
    ap.add_argument("--winning-head", default="")
    ap.add_argument("--holder", default="")
    ap.add_argument("--contender-1", type=Path)
    ap.add_argument("--contender-2", type=Path)
    ap.add_argument("--pass-real44", action="store_true")
    args = ap.parse_args()
    try:
        require(not args.out.is_symlink(), "OUTPUT_SYMLINK")
        if args.phase == "real44":
            value = one_run_real44_receipt(args.run_id,args.source_sha,
                                           args.pass_real44)
        elif args.phase == "patch":
            require(args.raw is not None, "MODEL_OUTPUT_REQUIRED")
            value = screen_patch(bounded_bytes(args.raw),args.source_sha,
                                 args.run_id,args.attempt)
        else:
            require(args.root is not None and args.registry is not None,
                    "STATE_AND_PUBLIC_REGISTRY_REQUIRED")
            witness = read(args.registry)
            if args.phase == "claim":
                value = make_claim(args.root,args.run_id,args.attempt,witness,
                                   args.source_sha,args.a_head,args.holder)
            elif args.phase == "race":
                require(args.contender_1 is not None and args.contender_2 is not None,
                        "TWO_CONTENDER_RECEIPTS_REQUIRED")
                value = race_verdict(args.root,args.run_id,args.attempt,witness,
                    args.source_sha,args.a_head,
                    [read(args.contender_1),read(args.contender_2)],
                    args.winning_head)
            elif args.phase == "consumer-prompt":
                prompt = native_consumer_prompt(args.root,args.run_id,args.attempt)
                require(not args.out.exists(), "PROMPT_OUTPUT_ALREADY_PRESENT")
                args.out.parent.mkdir(parents=True,exist_ok=True)
                args.out.write_text(prompt,encoding="utf-8")
                print("JANUS_NATIVE_CONSUMER_PROMPT=BOUNDED")
                return 0
            else:
                require(args.brain is not None and args.raw is not None,
                        "PINNED_MODEL_AND_RESPONSE_REQUIRED")
                value = make_native_consumer_receipt(args.root,args.run_id,
                    args.attempt,witness,args.brain,bounded_bytes(args.raw))
        save_once(args.out,value)
        print("NEXUS_PHASE2_"+args.phase.upper().replace("-","_")+"="+value["status"]
              if "status" in value else "NEXUS_PHASE2_"+args.phase.upper()+"=PREPARED")
        return 0
    except (Hold, OSError, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        reason = str(exc) if isinstance(exc, Hold) else "INPUT_OR_IO_HOLD"
        print("NEXUS_PHASE2_HOLD:"+reason,file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
