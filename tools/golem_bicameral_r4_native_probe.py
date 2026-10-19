#!/usr/bin/env python3
"""R4A native-only PUBLIC pilot: real pinned Demiurge CPU, never an LLM superiority test.

External and bicameral arms are not executed or assigned zero-valued scores.
No network/model API is contacted by this script, and the probe cannot write
Genesis HOME, ACK, training weights, or a promoted native checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable

from janus_corpus_callosum import run_demiurge_native, _valid_native
from golem_bicameral_r3_eval import digest
from genesis_beetle_model_consumption import ConsumptionError

SCHEMA = "janus.golem.bicameral.r4.native_probe.v1"
PACK_SCHEMA = "janus.golem.bicameral.r4.native_pilot.v1"
KEY_SCHEMA = "janus.golem.bicameral.r4.native_pilot_key.v1"
SPLIT = "PUBLIC_NATIVE_CPU_PILOT_NOT_HOLDOUT"
PINNED = "8873e5121a67daac5c8afb8ff297d6565dc87c32"
LABELS = {"ALLOW", "DENY", "UNKNOWN"}
FAMILIES = {"gateway", "memory", "evidence", "authority"}
EXACT_CHOICE = re.compile(r"^\s*(ALLOW|DENY|UNKNOWN)(?=\W|$)", re.ASCII)
REQUIRED_TASKS = 12


class R4Error(ValueError):
    pass


def verify_public_pilot(pack: dict, key: dict) -> dict:
    if (not isinstance(pack, dict) or set(pack) !=
            {"schema", "split", "instructions", "tasks"} or
        pack.get("schema") != PACK_SCHEMA or pack.get("split") != SPLIT or
        not isinstance(pack.get("instructions"), str) or
        not isinstance(pack.get("tasks"), list) or
        len(pack["tasks"]) != REQUIRED_TASKS):
        raise R4Error("untrusted public CPU pilot pack")
    seen = set()
    groups = {family: 0 for family in FAMILIES}
    for item in pack["tasks"]:
        if not isinstance(item, dict) or set(item) != {"id", "family", "prompt"}:
            raise R4Error("untrusted pilot task shape")
        tid, family, prompt = item["id"], item["family"], item["prompt"]
        if (not isinstance(tid, str) or not re.fullmatch(r"[A-Z]{2}[0-9]{2}", tid)
            or tid in seen or family not in FAMILIES or
            not isinstance(prompt, str) or not 12 <= len(prompt) <= 80 or
            not prompt.isascii()):
            raise R4Error("invalid, long or duplicated pilot task")
        seen.add(tid)
        groups[family] += 1
        packed = format_prompt(item)
        if len(packed.encode("utf-8")) > 96:
            raise R4Error("pilot prompt exceeds native bridge's short budget")
    if set(groups.values()) != {3}:
        raise R4Error("unbalanced native pilot cases")
    if (not isinstance(key, dict) or set(key) != {"schema", "split", "answers"} or
        key.get("schema") != KEY_SCHEMA or key.get("split") != SPLIT or
        not isinstance(key.get("answers"), dict) or set(key["answers"]) != seen or
        any(value not in LABELS for value in key["answers"].values())):
        raise R4Error("invalid public pilot reference answers")
    return {"pack_sha256": digest(pack), "reference_sha256": digest(key),
            "cases": len(seen), "public_answers": True, "native_only": True}


def format_prompt(item: dict) -> str:
    # The gold key is NEVER included in this prompt.
    return "Q:" + item["prompt"] + " A:ALLOW|DENY|UNKNOWN="


def parse_choice(text: str) -> str:
    if not isinstance(text, str):
        return "ABSTAIN"
    match = EXACT_CHOICE.match(text)
    return match.group(1) if match else "ABSTAIN"


def probe(pack: dict, key: dict, repo: Path | None = None, *,
          execute: bool = False, native_runner: Callable = run_demiurge_native,
          native_head: str = PINNED) -> dict:
    frozen = verify_public_pilot(pack, key)
    base = {
        "schema": SCHEMA,
        "status": "R4_NATIVE_CPU_NOT_EXECUTED",
        "source_type": "PINNED_NATIVE_CPU_NOT_VERIFIED" if not execute
                       else "PINNED_NATIVE_CPU_SUBPROCESS",
        "native_commit": native_head,
        "calibration": frozen,
        "scientific_authority_delta": 0,
        "external_effect_authority_delta": 0,
        "ack_advanced": False,
        "auto_training_allowed": False,
        "provider_calls_performed": 0,
        "external": {"status": "NOT_EXECUTED_NO_FREE_PROVIDER",
                     "score": None},
        "bicameral": {"status": "NOT_EXECUTED_NO_REAL_EXTERNAL",
                      "score": None},
        "comparative_superiority_admitted": False,
        "independent_holdout_tested": False,
        "records": [],
        "native_score": None,
    }
    if not execute:
        return base
    if native_head != PINNED or repo is None:
        raise R4Error("native immutable CPU source pin required")
    if repo.is_symlink() or not repo.is_dir():
        raise R4Error("native checkout missing")
    # No fallback to mocked native generation. Any crash means INCOMPLETE,
    # not a falsely low accuracy for a functioning neural network.
    real_adapter = native_runner is run_demiurge_native
    checkpoint = None
    correct = 0
    abstain = 0
    for item in pack["tasks"]:
        task_prompt = format_prompt(item)
        try:
            output = _valid_native(native_runner(repo, native_head, task_prompt),
                                   native_head, task_prompt)
        except (OSError, ConsumptionError, ValueError, TypeError, KeyError,
                RuntimeError, subprocess.SubprocessError):
            # No raw model exception (potentially includes paths/tokens) is persisted.
            base.update(status="R4_NATIVE_CPU_INCOMPLETE_RUNTIME_FAILURE",
                        failure_at_task=item["id"], native_score=None)
            return base
        observed_checkpoint = output["checkpoint_sha256"]
        if checkpoint is not None and checkpoint != observed_checkpoint:
            raise R4Error("native checkpoint changed during R4 probe")
        checkpoint = observed_checkpoint
        text = output["generated_text"]
        extracted = parse_choice(text)
        if extracted == "ABSTAIN":
            abstain += 1
        correct += extracted == key["answers"][item["id"]]
        base["records"].append({
            "task_id": item["id"],
            "task_sha256": digest(item),
            "native_prompt_sha256": output["prompt_sha256"],
            "native_generation_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "native_generation_length": len(text),
            "label_extracted": extracted,
            "source_commit": output["source_commit"],
            "checkpoint_sha256": observed_checkpoint,
        })
    base["status"] = ("R4_REAL_NATIVE_CPU_PUBLIC_PILOT__EXTERNAL_BLOCKED"
                      if real_adapter else "R4_SYNTHETIC_NATIVE_PROBE__NOT_EVIDENCE")
    base["source_type"] = ("PINNED_NATIVE_CPU_SUBPROCESS" if real_adapter
                           else "TEST_FIXTURE__NOT_REAL_NATIVE")
    base["checkpoint_sha256"] = checkpoint
    base["native_score"] = {
        "correct": correct, "denominator": REQUIRED_TASKS,
        "abstentions": abstain, "accuracy": correct / REQUIRED_TASKS,
        "sample_type": "PUBLIC_SMALL_PILOT_NOT_INDEPENDENT",
        "actual_native_inference_verified": real_adapter,
    }
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--native-repo", type=Path)
    ap.add_argument("--native-head", default=PINNED)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--execute", action="store_true")
    opts = ap.parse_args()
    pack = json.loads(opts.pack.read_text(encoding="utf-8"))
    key = json.loads(opts.key.read_text(encoding="utf-8"))
    result = probe(pack, key, opts.native_repo, execute=opts.execute,
                   native_head=opts.native_head)
    document = json.dumps(result, ensure_ascii=False, sort_keys=True,
                          indent=2) + "\n"
    if opts.out:
        if opts.native_repo and opts.out.resolve().is_relative_to(opts.native_repo.resolve()):
            raise R4Error("pilot report must not mutate the native source repository")
        opts.out.write_text(document, encoding="utf-8")
        print(json.dumps({"status": result["status"],
                          "native_score": result["native_score"],
                          "report_sha256": hashlib.sha256(document.encode()).hexdigest()},
                         sort_keys=True))
    else:
        print(document)
    return 0 if not opts.execute or result["status"] == (
        "R4_REAL_NATIVE_CPU_PUBLIC_PILOT__EXTERNAL_BLOCKED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
