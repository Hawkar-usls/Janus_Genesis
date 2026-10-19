# -*- coding: utf-8 -*-
"""R4: 48 supervised real model calls for four novel task families.

Carries forward R3's proven-local ablation protocol with new frozen task facts,
two repetitions, matched control/inverse framing and richer *lexical proxies*.
Blind human scoring is external and remains OPEN until separately performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.genesis_third_wish_scione_causal_r3 import (
    _cycle, _outbox_hashes, ablate_visible_notes, produce_review_files,
)
from tools.genesis_third_wish_scione_inverse_r2 import (
    observe_internal_artifacts, retire_letter_from_visible_inbox, sha256,
)

PROTOCOL = REPO_ROOT / "protocol/JANUS_GENESIS_THIRD_WISH_SCIONE_DIVERGENT_R4-v1.0.json"
PROTOCOL_SHA256 = "ce70ac6cff0958fa86a7a41377b2ec3ce80d3393071ce00f41b3b9658cfba8cc"
WITNESS_SCHEMA = "janus.genesis.third_wish.sci_one.divergent_r4_witness.v1"
PACKET_SCHEMA = "janus.genesis.third_wish.sci_one.divergent_r4_blind_packet.v1"
MAPPING_SCHEMA = "janus.genesis.third_wish.sci_one.divergent_r4_private_mapping.v1"
_TERM = re.compile(r"\b(?:test|measure|compare|control|falsif\w*|rollback|replay|holdout|threshold|reject|sample|baseline)\b", re.I)
_R4_CASE = re.compile(r"SCIONE-R4-[A-Z0-9_-]+")
_STOPWORDS = frozenset("the a an and or of to in on is are was were with for this that it its i we from as by can not be one two three four note snapshot observes observation observing describes bounded home current will about".split())


def load_protocol(path: Path = PROTOCOL) -> dict[str, Any]:
    if sha256(path.read_bytes()) != PROTOCOL_SHA256:
        raise ValueError("R4_FROZEN_PROTOCOL_SHA256_MISMATCH")
    p = json.loads(path.read_text(encoding="utf-8"))
    tasks = p["tasks"]
    d = p["design"]
    if (p.get("schema") != "janus.genesis.third_wish.sci_one.divergent_r4_protocol.v1"
        or p["runtime"]["real_model_calls"] != 48
        or p["runtime"]["per_cycle_outer_deadline_seconds"] != 150
        or p["r3_parent_run_id"] != 39233575143
        or p["r3_blind_review"]["human_scores_not_yet_frozen"] is not True
        or len(tasks) != 4 or d["replicates_per_family"] != 2
        or d["frame_replicate_trials"] != 16
        or d["first_cycle_calls"] != 16 or d["forked_second_cycle_calls"] != 32
        or d["memory_branches"] != ["PRESERVED", "ABLATED"]
        or p["authority"]["external_effect_grants"] != 0
        or p["authority"]["live_habitat_mutations"] != 0):
        raise ValueError("R4_STUDY_OR_AUTHORITY_BOUNDARY_INVALID")
    seen: set[str] = set()
    for item in tasks:
        if (set(item) != {"task_id", "token", "title", "facts", "anchor_terms"}
            or not re.fullmatch(r"[A-Z_]{5,40}", item["task_id"])
            or not re.fullmatch(r"[A-Z]{4,12}", item["token"])
            or not 40 <= len(item["facts"]) <= 1200
            or not 0 < len(item["title"]) <= 300
            or not isinstance(item["anchor_terms"], list)
            or len(item["anchor_terms"]) != 4
            or any(not re.fullmatch(r"[a-z]{3,20}", s) for s in item["anchor_terms"])
            or item["task_id"] in seen):
            raise ValueError("R4_TASK_INVALID")
        seen.add(item["task_id"])
    return p


def make_case(protocol: dict[str, Any], task_index: int, replicate_index: int,
              frame_index: int) -> dict[str, str]:
    task = protocol["tasks"][task_index]
    frame = ("control", "inverse")[frame_index]
    number = 40 + task_index * 4 + replicate_index * 2 + frame_index
    sentinel = f"{'AMBER' if frame_index == 0 else 'COBALT'}-{task['token']}-{number:02d}"
    case_id = f"SCIONE-R4-{task['token']}-{replicate_index + 1}-{frame.upper()}"
    body = (protocol["framing"]["common_intro"] + "\n"
            + task["facts"] + "\n" + protocol["framing"][frame] + "\n"
            + "Harmless trace label: " + sentinel + ".")
    if len(body) > 1200 or body.count(sentinel) != 1:
        raise ValueError("R4_CASE_UNBOUNDED_OR_SENTINEL_DUPLICATE")
    return {"case_id": case_id, "title": task["title"], "body": body,
            "sentinel": sentinel, "frame": frame.upper(), "task_id": task["task_id"],
            "replicate": replicate_index + 1}


def bounded_quality_proxies(review: list[dict[str, str]], context: str,
                            anchors: list[str]) -> dict[str, int]:
    """Lexical observations only; never call these independent semantic grades."""
    second = "\n".join(item["text"] for item in review)
    hits = sum(bool(re.search(r"\b" + re.escape(anchor) + r"\b", second, re.I))
               for anchor in anchors)
    tokens = lambda s: {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in _STOPWORDS}
    return {
        "given_task_anchor_count_in_new_text": hits,
        "prespecified_test_term_present": int(bool(_TERM.search(second))),
        "nonstopword_lexical_new_token_count": min(500, len(tokens(second) - tokens(context))),
        "nonstopword_lexical_overlap_count": min(500, len(tokens(second) & tokens(context))),
        "new_text_character_count": len(second),
    }


def produce_r4_review_files(items: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    packet, private = produce_review_files(items)
    for item in packet["items"]:
        item["blind_id"] = "R4-" + item["blind_id"][3:]
        for field in ("text", "first_cycle_context"):
            item[field] = _R4_CASE.sub("[REDACTED]", item[field])[:1200]
    for item in private["mapping"]:
        item["blind_id"] = "R4-" + item["blind_id"][3:]
    private["schema"] = MAPPING_SCHEMA
    packet["schema"] = PACKET_SCHEMA
    canonical_mapping = json.dumps(private, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
    packet["mapping_commitment_sha256"] = hashlib.sha256(canonical_mapping).hexdigest()
    packet["review_status"] = "AWAITING_INDEPENDENT_HUMAN_RUBRIC_RATINGS"
    packet["rubric"] = ["SPECIFIC_ALTERNATIVE_IDEA", "FALSIFIABLE_TEST_PLAN",
                         "CROSS_CYCLE_SEMANTIC_CONTINUITY", "USEFUL_INTERNAL_INITIATIVE"]
    packet["task_context_masking_limit"] = "Only first-cycle own note, not prompt facts"
    return packet, private


def run_suite(*, output: Path, blind_output: Path, mapping_output: Path,
              model: str, endpoint: str) -> dict[str, Any]:
    p = load_protocol()
    if model != p["runtime"]["model"] or endpoint != p["runtime"]["endpoint"]:
        raise ValueError("R4_UNPINNED_MODEL_OR_ENDPOINT")
    from tools.genesis_git_habitat import GitHabitat

    rows: list[dict[str, Any]] = []
    review_items: list[dict[str, str]] = []
    for file in (output, blind_output, mapping_output):
        file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="janus-scione-divergent-r4-") as temp:
        for task_index, task in enumerate(p["tasks"]):
            for replicate_index in range(2):
                for frame_index in range(2):
                    case = make_case(p, task_index, replicate_index, frame_index)
                    directory = Path(temp) / case["case_id"]
                    first_root = directory / "first-habitat"
                    h = GitHabitat(first_root)
                    h.initialize("JANUS")
                    h.receive_letter(case["case_id"], case["title"], case["body"],
                                     source="R4_UNTRUSTED_SYNTHETIC_RESEARCH")
                    prior = observe_internal_artifacts(first_root, case["sentinel"])
                    outbox_prior = _outbox_hashes(first_root)
                    first_home = directory / "first-home"
                    first_home.mkdir(parents=True)
                    first, first_review = _cycle(first_root, first_home,
                                                 directory / "broker-first", model, endpoint,
                                                 case["sentinel"], prior, outbox_prior)
                    first_artifacts = first.pop("_artifacts")
                    first_context = "\n".join(x["text"] for x in first_review
                                              if x["kind"] == "INTERNAL_NOTE")[:1200]
                    row: dict[str, Any] = {"case_id": case["case_id"],
                                           "task_id": case["task_id"], "replicate": case["replicate"],
                                           "frame": case["frame"], "first": first, "forks": {}}
                    if first["result"] == "OBSERVED_BOUNDED_MODEL_CHOICE":
                        baseline_outbox = _outbox_hashes(first_root)
                        journal_before = (first_root / "memory/journal.jsonl").read_bytes()
                        resident_before = (first_root / "state/resident.json").read_bytes()
                        order = (("PRESERVED", "ABLATED") if
                                 (task_index + replicate_index + frame_index) % 2 == 0
                                 else ("ABLATED", "PRESERVED"))
                        for branch in order:
                            root = directory / (branch.lower() + "-habitat")
                            shutil.copytree(first_root, root, symlinks=True)
                            retire_letter_from_visible_inbox(root, case["case_id"])
                            ablation = ({"moved_count": 0} if branch == "PRESERVED"
                                        else ablate_visible_notes(root, first_artifacts))
                            baseline = observe_internal_artifacts(root, case["sentinel"])
                            same_journal_state = (
                                journal_before == (root / "memory/journal.jsonl").read_bytes()
                                and resident_before == (root / "state/resident.json").read_bytes())
                            branch_habitat = GitHabitat(root)
                            chain_before = branch_habitat.verify_journal()["ok"]
                            home = directory / (branch.lower() + "-home")
                            home.mkdir(parents=True)
                            second, review = _cycle(root, home,
                                                    directory / ("broker-" + branch.lower()),
                                                    model, endpoint, case["sentinel"], baseline,
                                                    baseline_outbox)
                            second.pop("_artifacts")
                            chain_after = branch_habitat.verify_journal()["ok"]
                            healthy = branch_habitat.refresh_health()["status"] == "HEALTHY"
                            proxies = bounded_quality_proxies(review, first_context, task["anchor_terms"])
                            status = ("COMPLETE_BRANCH" if
                                      second["result"] == "OBSERVED_BOUNDED_MODEL_CHOICE"
                                      and same_journal_state and chain_before and chain_after and healthy
                                      else "INCOMPLETE_OR_FAILURE")
                            row["forks"][branch] = {
                                "result": status, "second": second, "ablation": ablation,
                                "identical_journal_and_resident_at_fork": same_journal_state,
                                "journal_valid_before": chain_before,
                                "journal_valid_after": chain_after, "habitat_healthy": healthy,
                                "quality_proxies_not_semantic_grades": proxies,
                            }
                            for item in review:
                                review_items.append({**item, "case_id": case["case_id"],
                                                     "domain": task["task_id"],
                                                     "frame": case["frame"], "branch": branch,
                                                     "first_cycle_context": first_context})
                    else:
                        row["forks"] = {branch: {"result": "NOT_RUN_AFTER_FIRST_PHASE_FAILURE"}
                                        for branch in ("PRESERVED", "ABLATED")}
                    rows.append(row)
    settled = (sum(r["first"]["result"] == "OBSERVED_BOUNDED_MODEL_CHOICE" for r in rows)
               + sum(f["second"]["result"] == "OBSERVED_BOUNDED_MODEL_CHOICE"
                     for r in rows for f in r["forks"].values() if "second" in f))
    complete = (len(rows) == 16 and settled == 48 and
                all(f["result"] == "COMPLETE_BRANCH" for r in rows for f in r["forks"].values()))
    witness: dict[str, Any] = {
        "schema": WITNESS_SCHEMA,
        "status": "COMPLETE_EXPLORATORY_OBSERVATIONS" if complete else "INCOMPLETE_OR_FAILURE",
        "protocol_sha256": PROTOCOL_SHA256, "r3_parent_run_id": p["r3_parent_run_id"],
        "model": model, "expected_real_model_calls": 48, "settled_model_calls": settled,
        "trial_count": len(rows), "novel_task_families": len(p["tasks"]),
        "replicates_per_family": 2, "rows": rows,
        "automatic_quality_proxies_are_semantic_creativity_grades": False,
        "independent_human_blind_scores_completed": False,
        "blind_arm_mapping_opened": False,
        "semantic_novelty_advantage_proven": False,
        "external_effects_executed": False, "production_habitat_mutated": False,
        "world_effect_authority_granted": False,
        "raw_model_provider_text_exported": False,
        "independent_network_egress_or_host_isolation_attested": False,
        "claim_ceiling": "New four-task repeated matched memory-fork study, lexical-only proxies and bounded choices; no independent semantic or world-effect claim."
    }
    packet, private = produce_r4_review_files(review_items)
    for file, value in ((output, witness), (blind_output, packet), (mapping_output, private)):
        file.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    return witness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--blind-output", required=True, type=Path)
    parser.add_argument("--mapping-output", required=True, type=Path)
    parser.add_argument("--model", default="qwen2.5:0.5b-instruct-q4_K_M")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    witness = run_suite(output=args.output, blind_output=args.blind_output,
                        mapping_output=args.mapping_output,
                        model=args.model, endpoint=args.endpoint)
    print(json.dumps({"status": witness["status"], "model_calls": witness["settled_model_calls"],
                      "planned": witness["expected_real_model_calls"]}, sort_keys=True))
    return 0 if witness["status"] == "COMPLETE_EXPLORATORY_OBSERVATIONS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
