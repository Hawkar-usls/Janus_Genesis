#!/usr/bin/env python3
"""R4B: separate continuation, instruction and multiple-choice CPU diagnostics.

The nine PUBLIC tasks are NOT R4A, not a hidden holdout and never a model
training source. Real-source provenance requires invoking the exact existing
Demiurge native subprocess adapter; injected test runners remain fixtures.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Callable

from genesis_beetle_model_consumption import ConsumptionError
from golem_bicameral_r3_eval import digest
from janus_corpus_callosum import _valid_native, run_demiurge_native
from golem_bicameral_r4_native_probe import PINNED

SCHEMA = "janus.golem.bicameral.r4b.diagnostic_report.v1"
PACK_SCHEMA = "janus.golem.bicameral.r4b.native_diagnostics.v1"
KEY_SCHEMA = "janus.golem.bicameral.r4b.key.v1"
SPLIT = "PUBLIC_DIAGNOSTICS_NOT_BLIND_OR_R4A"
GROUPS = {"CONTINUATION", "INSTRUCTION", "MULTIPLE_CHOICE"}
MAX_EXCERPT = 160
MAX_PROMPT_BYTES = 96


class R4BDiagnosticError(ValueError):
    pass


def validate(pack: dict, key: dict) -> dict:
    if (not isinstance(pack, dict) or set(pack) !=
        {"schema", "split", "purpose", "prompts"} or
        pack.get("schema") != PACK_SCHEMA or pack.get("split") != SPLIT or
        not isinstance(pack.get("purpose"), str) or
        not isinstance(pack.get("prompts"), list) or len(pack["prompts"]) != 9):
        raise R4BDiagnosticError("invalid R4B public task pack")
    ids, counts = set(), Counter()
    for item in pack["prompts"]:
        if not isinstance(item, dict) or set(item) != {"id", "group", "prompt"}:
            raise R4BDiagnosticError("R4B task field drift")
        tid, group, prompt = item["id"], item["group"], item["prompt"]
        if (not isinstance(tid, str) or not re.fullmatch(r"(CT|IN|MC)\d\d", tid) or
            tid in ids or group not in GROUPS or
            not isinstance(prompt, str) or not prompt.isascii() or
            len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES or len(prompt) < 12):
            raise R4BDiagnosticError("invalid duplicate or out-of-context task")
        if not tid.startswith({"CONTINUATION":"CT","INSTRUCTION":"IN",
                               "MULTIPLE_CHOICE":"MC"}[group]):
            raise R4BDiagnosticError("R4B task group prefix mismatch")
        ids.add(tid)
        counts[group] += 1
    if set(counts) != GROUPS or set(counts.values()) != {3}:
        raise R4BDiagnosticError("R4B task strata unbalanced")
    expected_ids = ids - {row["id"] for row in pack["prompts"]
                          if row["group"] == "CONTINUATION"}
    if (not isinstance(key, dict) or set(key) != {"schema", "split", "expected"} or
        key.get("schema") != KEY_SCHEMA or key.get("split") != SPLIT or
        not isinstance(key.get("expected"), dict) or
        set(key["expected"]) != expected_ids):
        raise R4BDiagnosticError("R4B answer key drift")
    for task in pack["prompts"]:
        if task["group"] == "INSTRUCTION" and key["expected"][task["id"]] not in {
            "YES", "NO", "READY"}:
            raise R4BDiagnosticError("untrusted instruction key")
        if task["group"] == "MULTIPLE_CHOICE" and key["expected"][task["id"]] not in {
            "A", "B"}:
            raise R4BDiagnosticError("untrusted multiple-choice key")
    return {"pack_sha256": digest(pack), "key_sha256": digest(key),
            "tasks": len(ids), "strata": dict(sorted(counts.items())),
            "public_only": True}


def measured_excerpt(text: str) -> str:
    """Only public fixture generated text, bounded and with control chars escaped."""
    safe = "".join(ch if ch.isprintable() or ch in "\n\t" else "\uFFFD"
                   for ch in text)
    return safe[:MAX_EXCERPT]


def run_diagnostics(pack: dict, key: dict, native_repo: Path | None = None,
                    *, execute: bool = False,
                    native_head: str = PINNED,
                    native_runner: Callable = run_demiurge_native) -> dict:
    frozen = validate(pack, key)
    real_adapter = native_runner is run_demiurge_native
    result = {
        "schema": SCHEMA, "status": "R4B_NOT_EXECUTED",
        "source_type": "NOT_EXECUTED",
        "model_source_commit": native_head,
        "calibration": frozen,
        "groups": None,
        "records": [],
        "external": "NOT_EXECUTED",
        "bicameral": "NOT_EXECUTED",
        "r4a_result_unchanged": True,
        "raw_generated_text_is_training_data": False,
        "improvement_claim_admitted": False,
        "scientific_authority_delta": 0,
        "external_effect_authority_delta": 0,
        "ack_advanced": False,
    }
    if not execute:
        return result
    if native_head != PINNED or native_repo is None or not native_repo.is_dir():
        raise R4BDiagnosticError("pinned Demiurge checkout required")
    result["source_type"] = ("PINNED_NATIVE_CPU_SUBPROCESS" if real_adapter else
                             "TEST_FIXTURE__NOT_REAL_CPU")
    counters = {g: {"tasks": 3, "completed": 0, "exact_matches": None,
                     "nonempty": 0, "printable": 0} for g in GROUPS}
    for group in ("CONTINUATION", "INSTRUCTION", "MULTIPLE_CHOICE"):
        if group != "CONTINUATION":
            counters[group]["exact_matches"] = 0
        for item in pack["prompts"]:
            if item["group"] != group:
                continue
            prompt = item["prompt"]
            try:
                output = _valid_native(native_runner(native_repo, native_head, prompt),
                                       native_head, prompt)
            except (ConsumptionError, OSError, ValueError, TypeError, KeyError,
                    RuntimeError, subprocess.SubprocessError):
                result.update(status="R4B_INCOMPLETE_NATIVE_FAILURE",
                              failed_task=item["id"], groups=None)
                return result
            chk = output["checkpoint_sha256"]
            if result.get("checkpoint_sha256") not in (None, chk):
                raise R4BDiagnosticError("Demiurge checkpoint changed during diagnostic")
            result["checkpoint_sha256"] = chk
            text = output["generated_text"]
            exact = (text.strip() == key["expected"][item["id"]]) if (
                group != "CONTINUATION") else None
            counts = counters[group]
            counts["completed"] += 1
            counts["nonempty"] += bool(text.strip())
            counts["printable"] += bool(text and
                sum(ch.isprintable() for ch in text) / len(text) >= 0.9)
            if exact is not None:
                counts["exact_matches"] += int(exact)
            result["records"].append({
                "task_id": item["id"], "group": group,
                "prompt_sha256": output["prompt_sha256"],
                "generation_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "generation_length": len(text),
                "excerpt": measured_excerpt(text),
                "exact_format_match": exact,
                "checkpoint_sha256": chk,
            })
    result["status"] = ("R4B_REAL_NATIVE_CPU_DIAGNOSTIC__NO_EXTERNAL" if real_adapter
                        else "R4B_SYNTHETIC_NATIVE_DIAGNOSTIC__NOT_EVIDENCE")
    result["groups"] = {group: counters[group] for group in (
        "CONTINUATION", "INSTRUCTION", "MULTIPLE_CHOICE")}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--native-repo", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()
    pack = json.loads(options.pack.read_text(encoding="utf-8"))
    key = json.loads(options.key.read_text(encoding="utf-8"))
    report = run_diagnostics(pack, key, options.native_repo, execute=options.execute)
    body = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if options.out:
        if options.native_repo and options.out.resolve().is_relative_to(
                options.native_repo.resolve()):
            raise R4BDiagnosticError("report cannot be saved into native model repository")
        options.out.write_text(body, encoding="utf-8")
        print(json.dumps({"status": report["status"],
                          "groups": report["groups"],
                          "report_sha256": hashlib.sha256(body.encode()).hexdigest()},
                         sort_keys=True, ensure_ascii=False))
    else:
        print(body)
    return 0 if not options.execute or report["status"] == (
        "R4B_REAL_NATIVE_CPU_DIAGNOSTIC__NO_EXTERNAL") else 2


if __name__ == "__main__":
    raise SystemExit(main())
