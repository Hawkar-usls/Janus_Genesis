"""ESSENCE v1.1: bounded exhaustive behavioural counterexample gate.

Compares two declarative single-tape Turing-machine transition tables over
all words in a finite predeclared alphabet, up to an explicit length limit.
No donor Python import, eval, execution privileges, network, file mutation,
model promotion, training or external authenticity claims.

A passing finite trial is NOT a proof of universal program equivalence.
It is NOT an independently held-out trial and grants no execution authority.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

import kernel
import turing_machine as tm

SCHEMA = "janus.essence.counterexample_gate/1.1"
MAX_CASES = 1024
MAX_WITNESSES = 8


def _alphabet(value, parent_blank: str, child_blank: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 3:
        raise ValueError("INVALID_ALPHABET_SIZE")
    if any(type(c) is not str or len(c) != 1 or
           not c.isascii() or not c.isprintable() for c in value):
        raise ValueError("INVALID_ALPHABET_SYMBOL")
    if len(set(value)) != len(value):
        raise ValueError("DUPLICATE_ALPHABET_SYMBOL")
    if parent_blank != child_blank or parent_blank in value:
        raise ValueError("BLANK_MISMATCH_OR_INPUT")
    # Ordering is explicit, deterministic, independent of caller's ordering.
    return tuple(sorted(value))


def evaluate(manifest: dict, fixture: dict, parent: dict, child: dict, *,
             alphabet: tuple[str, ...] = ("1",),
             max_length: int = 6, max_steps: int = 128,
             max_cells: int = 64, explicit_readonly: bool = False,
             expected_repo: str | None = None) -> dict:
    if explicit_readonly is not True:
        raise PermissionError("EXPLICIT_READONLY_REQUIRED")
    base = kernel.evaluate(manifest, fixture, explicit_readonly=True,
                           expected_repo=expected_repo)
    kernel.verify_report(base)
    _, p = tm.validate(parent)
    _, c = tm.validate(child)
    chars = _alphabet(alphabet, p["blank"], c["blank"])
    if type(max_length) is not int or not 0 <= max_length <= 8:
        raise ValueError("MAX_LENGTH_LIMIT")
    if type(max_steps) is not int or not 1 <= max_steps <= 1024:
        raise ValueError("MAX_STEPS_LIMIT")
    if type(max_cells) is not int or not 8 <= max_cells <= 256 or max_cells <= max_length:
        raise ValueError("MAX_CELLS_LIMIT")
    cases = sum(len(chars) ** n for n in range(max_length + 1))
    if cases > MAX_CASES or cases * max_steps > 524288:
        raise ValueError("TOTAL_WORK_LIMIT")

    failures = {"semantic": 0, "unresolved": 0, "slowdown": 0}
    witnesses = []
    faster = 0
    equal = 0
    parent_steps = 0
    child_steps = 0
    for width in range(max_length + 1):
        for letters in itertools.product(chars, repeat=width):
            tape = "".join(letters)
            old = tm.run(parent, tape, max_steps=max_steps, max_cells=max_cells)
            new = tm.run(child, tape, max_steps=max_steps, max_cells=max_cells)
            parent_steps += old["steps"]
            child_steps += new["steps"]
            kind = None
            if old["status"] not in ("ACCEPT", "REJECT") or new["status"] not in ("ACCEPT", "REJECT"):
                kind = "unresolved"
            elif (old["status"], old["final_tape"]) != (new["status"], new["final_tape"]):
                kind = "semantic"
            elif new["steps"] > old["steps"]:
                kind = "slowdown"
            elif new["steps"] < old["steps"]:
                faster += 1
            else:
                equal += 1
            if kind is not None:
                failures[kind] += 1
                if len(witnesses) < MAX_WITNESSES:
                    witnesses.append({
                        "input": tape, "failure": kind,
                        "parent": {"status": old["status"], "steps": old["steps"],
                                   "output": old["final_tape"]},
                        "child": {"status": new["status"], "steps": new["steps"],
                                  "output": new["final_tape"]},
                    })

    if failures["semantic"]:
        gate = "HOLD_SEMANTIC_COUNTEREXAMPLE"
    elif failures["unresolved"]:
        gate = "HOLD_UNRESOLVED_OR_RESOURCE_BOUND"
    elif failures["slowdown"]:
        gate = "HOLD_PERFORMANCE_REGRESSION"
    elif faster == 0:
        gate = "HOLD_NO_MEASURABLE_GAIN"
    else:
        gate = "RESEARCH_PASS_FINITE_DOMAIN_ONLY"
    receipt = {
        "schema": SCHEMA,
        "repository": base["repository"],
        "parent_sha256": kernel.digest(parent),
        "child_sha256": kernel.digest(child),
        "root_essence_receipt_sha256": base["report_sha256"],
        "fixture_sha256": base["fixture_sha256"],
        "input_alphabet": list(chars),
        "max_input_length": max_length,
        "max_steps_per_case": max_steps,
        "max_cells_per_machine": max_cells,
        "cases_exhausted": cases,
        "semantic_mismatches": failures["semantic"],
        "unresolved_cases": failures["unresolved"],
        "slower_child_cases": failures["slowdown"],
        "faster_child_cases": faster,
        "equal_step_cases": equal,
        "parent_total_steps": parent_steps,
        "child_total_steps": child_steps,
        "witnesses": witnesses,
        "gate": gate,
        "evidence_class": "DEVELOPMENT_FINITE_ENUMERATION_NOT_BLIND",
        "independently_validated": False,
        "universal_equivalence_proven": False,
        "model_weights_changed": False,
        "automatic_birth": False,
        "production_authority": False,
        "donor_code_executed": False,
    }
    receipt["receipt_sha256"] = kernel.digest(receipt)
    verify(receipt)
    return receipt


def verify(receipt: dict) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise ValueError("INVALID_COUNTEREXAMPLE_RECEIPT")
    seal = receipt.get("receipt_sha256")
    if seal != kernel.digest({k:v for k,v in receipt.items() if k!="receipt_sha256"}):
        raise ValueError("COUNTEREXAMPLE_RECEIPT_TAMPERED")
    for k in ("independently_validated", "universal_equivalence_proven",
              "model_weights_changed", "automatic_birth", "production_authority",
              "donor_code_executed"):
        if receipt.get(k) is not False:
            raise ValueError("COUNTEREXAMPLE_UNAUTHORIZED_CLAIM")
    if receipt.get("gate") not in (
            "HOLD_SEMANTIC_COUNTEREXAMPLE", "HOLD_UNRESOLVED_OR_RESOURCE_BOUND",
            "HOLD_PERFORMANCE_REGRESSION", "HOLD_NO_MEASURABLE_GAIN",
            "RESEARCH_PASS_FINITE_DOMAIN_ONLY"):
        raise ValueError("COUNTEREXAMPLE_UNKNOWN_GATE")
    if (type(receipt.get("cases_exhausted")) is not int or
            not 1 <= receipt["cases_exhausted"] <= MAX_CASES):
        raise ValueError("UNBOUNDED_CASE_CLAIM")
    return True


def verify_replay(receipt: dict, manifest: dict, fixture: dict, parent: dict,
                  child: dict) -> bool:
    """Strong verifier re-runs all transitions; hash-only verification is not proof."""
    verify(receipt)
    replay = evaluate(
        manifest, fixture, parent, child,
        alphabet=receipt["input_alphabet"], max_length=receipt["max_input_length"],
        max_steps=receipt["max_steps_per_case"], max_cells=receipt["max_cells_per_machine"],
        explicit_readonly=True, expected_repo=receipt["repository"])
    if replay != receipt:
        raise ValueError("COUNTEREXAMPLE_REPLAY_MISMATCH")
    return True


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "fixture", "parent", "child"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--alphabet", default="1")
    p.add_argument("--max-length", type=int, default=6)
    p.add_argument("--max-steps", type=int, default=128)
    p.add_argument("--max-cells", type=int, default=64)
    p.add_argument("--expected-repo")
    p.add_argument("--out")
    p.add_argument("--allow-readonly", action="store_true")
    a = p.parse_args()
    receipt = evaluate(
        kernel.load_json(a.manifest), kernel.load_json(a.fixture),
        kernel.load_json(a.parent), kernel.load_json(a.child),
        alphabet=tuple(a.alphabet), max_length=a.max_length,
        max_steps=a.max_steps, max_cells=a.max_cells,
        expected_repo=a.expected_repo, explicit_readonly=a.allow_readonly)
    verify_replay(
        receipt, kernel.load_json(a.manifest), kernel.load_json(a.fixture),
        kernel.load_json(a.parent), kernel.load_json(a.child))
    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if a.out:
        Path(a.out).write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
