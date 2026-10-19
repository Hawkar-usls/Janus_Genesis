#!/usr/bin/env python3
"""JANUS GOLEM BICAMERAL R3: provenance-aware *calibration* scoring, not an AI judge.

No inference, network, repository mutation, LLM voting or public research proof.
Reference answers are deliberately PUBLIC calibration data; never a blind holdout.
All submitted model provenance is untrusted until independently corroborated.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

PACK_SCHEMA = "janus.golem.bicameral.r3.calibration.v1"
KEY_SCHEMA = "janus.golem.bicameral.r3.answer_key.v1"
SUBMISSION_SCHEMA = "janus.golem.bicameral.r3.responses.v1"
REPORT_SCHEMA = "janus.golem.bicameral.r3.calibration_report.v1"
SPLIT = "PUBLIC_CALIBRATION_NOT_BLIND_HOLDOUT"
MODES = ("NATIVE", "EXTERNAL", "BICAMERAL")
ANSWERS = {"ALLOW", "DENY", "UNKNOWN"}
RESPONSES = ANSWERS | {"ABSTAIN"}
FAMILIES = {"gateway", "memory", "evidence", "authority"}
SOURCES = {"TEST_FIXTURE", "UNVERIFIED_CANDIDATE"}
SHA = re.compile(r"[0-9a-f]{64}\Z")


class EvaluationError(ValueError):
    pass


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def task_hash(task: dict) -> str:
    return digest(task)


def validate_pack(pack: dict, key: dict) -> dict:
    if not isinstance(pack, dict) or set(pack) != {
        "schema", "split", "task_language", "instructions", "tasks"
    } or pack["schema"] != PACK_SCHEMA or pack["split"] != SPLIT:
        raise EvaluationError("untrusted or mislabelled calibration pack")
    if pack["task_language"] != "en" or not isinstance(pack["instructions"], str):
        raise EvaluationError("invalid calibration instructions")
    tasks = pack["tasks"]
    if not isinstance(tasks, list) or len(tasks) != 12:
        raise EvaluationError("R3 calibration must contain exactly twelve tasks")
    seen = set()
    counts = Counter()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "family", "prompt"}:
            raise EvaluationError("unsafe calibration task shape")
        tid, family, prompt = task["id"], task["family"], task["prompt"]
        if (not isinstance(tid, str) or not re.fullmatch(r"[A-Z]{2,4}[0-9]{2}", tid)
            or tid in seen or family not in FAMILIES or
            not isinstance(prompt, str) or not 20 <= len(prompt) <= 800):
            raise EvaluationError("invalid or duplicated calibration task")
        seen.add(tid)
        counts[family] += 1
    if set(counts) != FAMILIES or any(counts[f] != 3 for f in FAMILIES):
        raise EvaluationError("R3 calibration family balance drift")
    if (not isinstance(key, dict) or set(key) != {"schema", "split", "answers"} or
        key["schema"] != KEY_SCHEMA or key["split"] != SPLIT or
        not isinstance(key["answers"], dict) or set(key["answers"]) != seen or
        any(v not in ANSWERS for v in key["answers"].values())):
        raise EvaluationError("untrusted reference answer key")
    return {"pack_sha256": digest(pack),
            "answer_key_sha256": digest(key), "cases": len(tasks),
            "families": dict(sorted(counts.items())),
            "split": SPLIT, "public_answers": True}


def _paired(a: dict[str, bool], b: dict[str, bool]) -> dict | None:
    """Two-sided exact McNemar/binomial on paired correct/incorrect outcomes."""
    if a.keys() != b.keys():
        return None
    b_better = sum((not a[k]) and b[k] for k in a)
    a_better = sum(a[k] and (not b[k]) for k in a)
    discordant = b_better + a_better
    if discordant:
        smaller = min(a_better, b_better)
        p = min(1.0, 2.0 * sum(math.comb(discordant, i)
                               for i in range(smaller + 1)) / (2 ** discordant))
    else:
        p = 1.0
    return {"b_wins": b_better, "a_wins": a_better,
            "discordant_pairs": discordant, "exact_p_two_sided": p,
            "better": "B" if b_better > a_better else
                      "A" if a_better > b_better else "TIE",
            "not_an_independent_study": True}


def evaluate(pack: dict, key: dict, submission: dict | None = None) -> dict:
    locked = validate_pack(pack, key)
    report = {
        "schema": REPORT_SCHEMA,
        "status": "NO_SUBMISSIONS__NOT_EVALUATED" if submission is None else
                  "PUBLIC_CALIBRATION_ONLY__NO_IMPROVEMENT_CLAIM",
        "calibration": locked,
        "official_benchmark_score_claimed": False,
        "independent_holdout_tested": False,
        "real_external_inference_verified": False,
        "scientific_authority_delta": 0,
        "training_permission_granted": False,
        "promotion_authorized": False,
        "improvement_claim_admitted": False,
        "source_provenance_independently_verified": False,
        "requires": [
            "independent hidden holdout and frozen dataset",
            "verified immutable native and external response receipts",
            "paired complete three-mode results from the same tasks",
            "preregistered replication, baseline budgets and reviewer independence",
        ],
    }
    if submission is None:
        report.update({"results": None, "paired": None,
                       "score_label": "NOT_EVALUATED_NO_RESPONSES"})
        return report
    if (not isinstance(submission, dict) or set(submission) != {
        "schema", "pack_sha256", "records"
    } or submission["schema"] != SUBMISSION_SCHEMA or
        submission["pack_sha256"] != locked["pack_sha256"] or
        not isinstance(submission["records"], list)):
        raise EvaluationError("submission is not bound to the frozen R3 calibration")
    tasks = {row["id"]: row for row in pack["tasks"]}
    answers = key["answers"]
    observed: dict[str, dict[str, bool]] = {mode: {} for mode in MODES}
    sources = Counter()
    abstains = Counter()
    seen = set()
    for record in submission["records"]:
        if not isinstance(record, dict) or set(record) != {
            "mode", "task_id", "task_sha256", "response", "source_kind",
            "source_receipt_sha256"
        }:
            raise EvaluationError("invalid model response record")
        mode, tid = record["mode"], record["task_id"]
        if mode not in MODES or tid not in tasks or (mode, tid) in seen:
            raise EvaluationError("unknown or duplicated model/task response")
        seen.add((mode, tid))
        if (record["task_sha256"] != task_hash(tasks[tid]) or
            record["response"] not in RESPONSES or
            record["source_kind"] not in SOURCES):
            raise EvaluationError("response is not bound to the frozen question")
        receipt = record["source_receipt_sha256"]
        if record["source_kind"] == "TEST_FIXTURE":
            if receipt is not None:
                raise EvaluationError("fixture must not impersonate real receipt")
        elif not isinstance(receipt, str) or not SHA.fullmatch(receipt):
            raise EvaluationError("declared real response lacks a receipt digest")
        sources[record["source_kind"]] += 1
        if record["response"] == "ABSTAIN":
            abstains[mode] += 1
        observed[mode][tid] = record["response"] == answers[tid]
    metrics = {}
    for mode in MODES:
        outcomes = observed[mode]
        n = len(outcomes)
        per_family = {}
        for family in sorted(FAMILIES):
            task_ids = [row["id"] for row in pack["tasks"] if row["family"] == family]
            per_family[family] = {
                "correct": sum(outcomes.get(tid, False) for tid in task_ids),
                "submitted": sum(tid in outcomes for tid in task_ids),
                "denominator": len(task_ids),
            }
        metrics[mode] = {
            "correct": sum(outcomes.values()),
            "submitted": n,
            "missing": len(tasks) - n,
            "abstained": abstains[mode],
            "denominator": len(tasks),
            "accuracy_fixed_denominator": sum(outcomes.values()) / len(tasks),
            "family_breakdown": per_family,
        }
    full = all(len(observed[mode]) == len(tasks) for mode in MODES)
    comparisons = {
        "BICAMERAL_vs_NATIVE": _paired(observed["NATIVE"], observed["BICAMERAL"]) if full else None,
        "BICAMERAL_vs_EXTERNAL": _paired(observed["EXTERNAL"], observed["BICAMERAL"]) if full else None,
    }
    report.update({
        "status": "PUBLIC_CALIBRATION_ONLY__NO_IMPROVEMENT_CLAIM" if full else
                  "INCOMPLETE_PAIRING__NO_IMPROVEMENT_CLAIM",
        "score_label": "CALIBRATION_ONLY__PUBLIC_ANSWERS",
        "provenance_type_counts": dict(sorted(sources.items())),
        "complete_paired_set": full,
        "results": metrics, "paired": comparisons,
    })
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True, type=Path)
    p.add_argument("--key", required=True, type=Path)
    p.add_argument("--submissions", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    data = evaluate(json.loads(args.pack.read_text(encoding="utf-8")),
                    json.loads(args.key.read_text(encoding="utf-8")),
                    json.loads(args.submissions.read_text(encoding="utf-8"))
                    if args.submissions else None)
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
