#!/usr/bin/env python3
"""P0.3: real bounded READ-ONLY consumption of staged Genesis Beetle context.

Cloud HOME's earlier CHECKPOINT_ONLY receipt is NOT an execution receipt.
This worker reads the state, verifies exact SHA-bound durable context, runs a
real deterministic contextual index query, and produces an idempotent receipt.

This is a real software consumer, NOT proof of neural-model consumption or
external scientific validation. It cannot grant phase admission, access
untrusted instructions, write to HOME, dispatch workflows or train weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "janus.genesis.beetle_readonly_consumer_receipt.v1"
QUERY_SCHEMA = "janus.genesis.beetle_lens_coverage_query.v1"
STATE = Path("state/habitat_cloud_home/STATE.json")
MEMORY = Path("state/habitat_cloud_home/memory/beetle")
RECEIPT_PATH = re.compile(r"state/habitat_cloud_home/receipts/[0-9]{8}-[0-9]{5,}-[1-9][0-9]*\.json\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
LENSES = ("FORWARD", "REVERSE", "COUNTEREVIDENCE", "CONTROL")
REPO = "Hawkar-usls/Janus_Genesis"
MAX_CTX = 180_000
MAX_CURSOR = 100_000
MAX_STATE = 100_000


class ContextHold(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_read(root, rel, limit):
    root = Path(root).resolve(strict=True)
    path = root / rel
    if not path.is_relative_to(root) or any(p.is_symlink() for p in
             (path, *(p for p in path.parents if p.is_relative_to(root)))):
        raise ContextHold("CONSUMER_UNSAFE_PATH")
    if not path.is_file():
        raise ContextHold("CONSUMER_REQUIRED_FILE_MISSING")
    raw = path.read_bytes()
    if not 0 < len(raw) <= limit:
        raise ContextHold("CONSUMER_FILE_SIZE")
    return raw


def load_json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ContextHold("DUPLICATE_JSON_KEY")
            obj[key] = value
        return obj
    def nonfinite(_):
        raise ContextHold("NONFINITE_JSON")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise ContextHold("CONSUMER_INVALID_JSON") from exc


def verified_inputs(root, state_commit):
    if type(state_commit) is not str or not HEX40.fullmatch(state_commit):
        raise ContextHold("CONSUMER_UNBOUND_STATE_COMMIT")
    state = load_json(safe_read(root, STATE, MAX_STATE))
    if (type(state) is not dict or
        state.get("schema") != "JANUS_HABITAT_CLOUD_HOME_STATE_V1" or
        state.get("status") != "CLOUD_HOME_ACTIVE" or
        state.get("durable_identity") != "JANUS_HABITAT_RESIDENT_V1" or
        state.get("authority_delta") != 0 or
        state.get("source_writeback_default") != "DENY" or
        state.get("destructive_action") != "FORBIDDEN" or
        any(state.get(k) is not False for k in (
            "pc_required", "nas_required", "remote_desktop_required",
            "lan_required", "process_uptime_required")) or
        type(state.get("sequence")) is not int or state["sequence"] < 1):
        raise ContextHold("HOME_STATE_UNVERIFIED")
    name = state.get("checkpoint_head")
    if not isinstance(name, str) or not RECEIPT_PATH.fullmatch(name) or state.get("handoff_head") != name:
        raise ContextHold("HOME_RECEIPT_POINTER_UNVERIFIED")
    receipt_raw = safe_read(root, Path(name), MAX_STATE)
    if sha(receipt_raw) != state.get("last_receipt_sha256"):
        raise ContextHold("HOME_RECEIPT_SHA_MISMATCH")
    home_receipt = load_json(receipt_raw)
    if (type(home_receipt) is not dict or
        home_receipt.get("schema") != "JANUS_HABITAT_CLOUD_HOME_RECEIPT_V1" or
        home_receipt.get("sequence") != state["sequence"] or
        home_receipt.get("execute_status") != "CHECKPOINT_ONLY" or
        home_receipt.get("source_main_sha") != state.get("source_main_sha") or
        home_receipt.get("beetle_memory") != state.get("beetle_memory") or
        home_receipt.get("authority_delta") != 0):
        raise ContextHold("HOME_PREVIOUS_RECEIPT_CONTRADICTION")
    beetle = state.get("beetle_memory")
    if (not isinstance(beetle, dict) or
        beetle.get("status") != "HASH_MATCHED_UNVERIFIED_CONTEXT_STAGED" or
        beetle.get("command_authority") is not False or
        beetle.get("external_effect_authority") is not False or
        beetle.get("scientific_authority_delta") != 0 or
        type(beetle.get("cursor_sequence")) is not int or beetle["cursor_sequence"] < 1):
        raise ContextHold("NO_VERIFIED_STAGED_CONTEXT")
    context_raw = safe_read(root, MEMORY/"CONTEXT.json", MAX_CTX)
    cursor_raw = safe_read(root, MEMORY/"CURSOR.json", MAX_CURSOR)
    if sha(context_raw) != beetle.get("context_sha256") or sha(cursor_raw) != beetle.get("cursor_sha256"):
        raise ContextHold("STAGED_CONTEXT_SHA_MISMATCH")
    context, cursor = load_json(context_raw), load_json(cursor_raw)
    if (not isinstance(context, dict) or not isinstance(cursor, dict) or
        context.get("schema") != "janus.genesis.beetle_context_projection.v1" or
        context.get("target_repository") != REPO or
        context.get("untrusted_research_only") is not True or
        context.get("model_text_is_command") is not False or
        context.get("scientific_authority_delta") != 0 or
        context.get("external_effect_authority_delta") != 0 or
        context.get("last_sequence") != beetle["cursor_sequence"] or
        cursor.get("schema") != "janus.genesis.beetle_context_cursor.v1" or
        cursor.get("target_repository") != REPO or
        cursor.get("unverified_research_only") is not True or
        cursor.get("scientific_authority_delta") != 0 or
        cursor.get("last_sequence") != context["last_sequence"] or
        cursor.get("context_sha256") != sha(context_raw) or
        not HEX64.fullmatch(str(cursor.get("rolling_sha256", "")))):
        raise ContextHold("PROJECTION_AND_CURSOR_CONTRADICTION")
    return state, context, cursor, sha(context_raw), sha(cursor_raw), sha(receipt_raw)


def execute_query(context):
    """Actually use the input to compute a bounded, non-LLM lens index.

    One source-context per item ID, no text/code execution, no publication of
    any untrusted title/summary/source URL in the result.
    """
    items = context.get("recent_items")
    if not isinstance(items, list) or not 1 <= len(items) <= 24:
        raise ContextHold("CONSUMER_ITEMS_OUT_OF_BOUNDS")
    counts = dict.fromkeys(LENSES, 0)
    unique_ids = set()
    evidence_pairs = []
    for item in items:
        if (not isinstance(item, dict) or
            item.get("mirror_lens") not in counts or
            item.get("untrusted_source_text") is not True or
            item.get("command_authority") is not False or
            item.get("proof_authority") is not False or
            item.get("external_effect_authority") is not False or
            item.get("delivery_preview_only") is not True or
            item.get("epistemic_status") != "DISCOVERY_INBOX__UNVERIFIED__NO_PROOF_AUTHORITY" or
            not isinstance(item.get("context_id"), str) or
            not 1 <= len(item["context_id"]) <= 128 or
            item["context_id"] in unique_ids):
            raise ContextHold("CONSUMER_UNTRUSTED_OR_DUPLICATE_ITEM")
        unique_ids.add(item["context_id"])
        counts[item["mirror_lens"]] += 1
        evidence_pairs.append((item["mirror_lens"], sha(item["context_id"].encode("utf-8"))))
    query = {
        "schema": QUERY_SCHEMA,
        "input_item_count": len(items),
        "lens_counts": counts,
        "distinct_context_ids": len(unique_ids),
        "lens_identity_sha256": sha(canonical(sorted(evidence_pairs))),
        "untrusted_text_treated_as_data": True,
        "action_or_model_output_used": False,
        "reproducible_read_only_query_executed": True,
    }
    return query


def receipt_from_state(root, state_commit):
    state, context, cursor, context_sha, cursor_sha, home_receipt_sha = verified_inputs(root, state_commit)
    result = execute_query(context)
    event = f"{state_commit}:{context_sha}:{cursor_sha}:{QUERY_SCHEMA}"
    receipt = {
        "schema": SCHEMA,
        "status": "READONLY_CONTEXT_QUERY_EXECUTED__NOT_MODEL_CONSUMPTION",
        "home_state_commit_sha": state_commit,
        "source_main_sha": state["source_main_sha"],
        "source_home_sequence": state["sequence"],
        "home_parent_receipt_sha256": home_receipt_sha,
        "context_sequence": cursor["last_sequence"],
        "context_sha256": context_sha,
        "cursor_sha256": cursor_sha,
        "event_id_sha256": sha(event.encode("utf-8")),
        "dedupe_key_sha256": sha(event.encode("utf-8")),
        "admission_status": "ADMITTED_READONLY_AUDIT_ONLY",
        "parse_status": "PARSED_HASH_BOUND_CONTEXT",
        "load_status": "LOADED_STRUCTURED_CONTEXT_FOR_READONLY_QUERY",
        "execute_status": "DETERMINISTIC_CONTEXT_QUERY_EXECUTED",
        "consumer_kind": "BOUNDED_DETERMINISTIC_METADATA_QUERY",
        "query_result": result,
        "query_result_sha256": sha(canonical(result)),
        "model_call_attested": False,
        "beetle_inbox_ack_is_not_model_execution": True,
        "p03_admission": False,
        "external_effects": False,
        "state_mutated": False,
        "useful_software_work_measured": True,
        "learned_improvement_attested": False,
        "external_independent_witness": False,
    }
    receipt["receipt_sha256"] = sha(canonical(receipt))
    return receipt


def save_once(path, obj):
    raw = (json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    path = Path(path)
    if path.exists():
        if path.read_bytes() == raw:
            return False
        raise ContextHold("SAME_ID_DIFFERENT_RECEIPT_HOLD")
    if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
        raise ContextHold("UNSAFE_RECEIPT_OUTPUT")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    return True


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--state-root",type=Path,required=True)
    p.add_argument("--state-commit",required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    record=receipt_from_state(args.state_root,args.state_commit)
    save_once(args.out,record)
    print(json.dumps({k:record[k] for k in ("status","event_id_sha256",
         "query_result_sha256","model_call_attested","p03_admission")},sort_keys=True))


if __name__=="__main__":
    main()
