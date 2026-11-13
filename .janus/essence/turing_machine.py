"""Bounded deterministic single-tape Turing-machine simulator for ESSENCE.

A data interpreter, not Python code execution. Every transition is explicit.
It cannot execute shell commands, call the network or change repository files.
All runs are deterministic and stop at declared step/tape budgets.
"""
from __future__ import annotations

import hashlib
import json
import re


def _label(x: object) -> bool:
    return type(x) is str and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,31}", x) is not None


def _symbol(x: object) -> bool:
    return type(x) is str and len(x) == 1 and x.isascii() and x.isprintable()


def validate(spec: dict) -> tuple[dict, dict]:
    if type(spec) is not dict or set(spec) != {
        "blank", "start", "accept", "reject", "transitions"
    }:
        raise ValueError("INVALID_MACHINE_SCHEMA")
    blank, start = spec["blank"], spec["start"]
    accept, reject = spec["accept"], spec["reject"]
    if not _symbol(blank) or not _label(start):
        raise ValueError("BAD_START_OR_BLANK")
    if not isinstance(accept, list) or not isinstance(reject, list):
        raise ValueError("INVALID_HALTS")
    if not 1 <= len(accept) <= 16 or len(reject) > 16:
        raise ValueError("HALT_STATE_LIMIT")
    if any(not _label(s) for s in accept + reject) or set(accept) & set(reject):
        raise ValueError("HALT_STATE_COLLISION")
    if len(set(accept)) != len(accept) or len(set(reject)) != len(reject):
        raise ValueError("DUPLICATE_HALT")
    if start in accept or start in reject:
        raise ValueError("START_ALREADY_HALTED")
    rows = spec["transitions"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2048:
        raise ValueError("TRANSITION_LIMIT")
    transitions = {}
    all_states = {start, *accept, *reject}
    for row in rows:
        if type(row) is not dict or set(row) != {"state", "read", "write", "move", "next"}:
            raise ValueError("BAD_TRANSITION")
        state, read, write, move, nex = (row[k] for k in ("state", "read", "write", "move", "next"))
        if not _label(state) or not _label(nex) or not _symbol(read) or not _symbol(write):
            raise ValueError("INVALID_TRANSITION_TOKEN")
        if move not in ("L", "R", "S"):
            raise ValueError("BAD_HEAD_MOVE")
        if state in accept or state in reject:
            raise ValueError("HALT_HAS_OUTGOING_TRANSITION")
        key = (state, read)
        if key in transitions:
            raise ValueError("NONDETERMINISTIC_DUPLICATE")
        transitions[key] = (write, move, nex)
        all_states.update((state, nex))
    if len(all_states) > 128:
        raise ValueError("STATE_LIMIT")
    return transitions, {"blank": blank, "start": start, "accept": set(accept), "reject": set(reject)}


def run(spec: dict, symbols: str, *, max_steps: int = 1024,
        max_cells: int = 256) -> dict:
    transitions, p = validate(spec)
    if type(symbols) is not str or len(symbols) > max_cells or not all(_symbol(x) for x in symbols):
        raise ValueError("INVALID_INPUT_TAPE")
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise ValueError("STEP_BUDGET_LIMIT")
    if type(max_cells) is not int or not 1 <= max_cells <= 1024:
        raise ValueError("TAPE_BUDGET_LIMIT")
    tape = {i: c for i, c in enumerate(symbols) if c != p["blank"]}
    state = p["start"]
    head = 0
    steps = 0
    status = "LIMIT"
    chain = "0" * 64
    while steps < max_steps:
        if state in p["accept"]:
            status = "ACCEPT"
            break
        if state in p["reject"]:
            status = "REJECT"
            break
        if abs(head) >= max_cells or len(tape) >= max_cells:
            status = "TAPE_LIMIT"
            break
        read = tape.get(head, p["blank"])
        action = transitions.get((state, read))
        if action is None:
            status = "STUCK"
            break
        write, move, nex = action
        if write == p["blank"]:
            tape.pop(head, None)
        else:
            tape[head] = write
        record = json.dumps([chain, steps, state, head, read, write, move, nex],
                            separators=(",", ":"), ensure_ascii=True).encode("ascii")
        chain = hashlib.sha256(record).hexdigest()
        head += {"L": -1, "R": 1, "S": 0}[move]
        state = nex
        steps += 1
    else:
        if state in p["accept"]:
            status = "ACCEPT"
        elif state in p["reject"]:
            status = "REJECT"
    if tape and max(tape) - min(tape) <= max_cells:
        final_tape = "".join(tape.get(i, p["blank"]) for i in range(min(tape), max(tape) + 1))
    else:
        final_tape = ""
    return {
        "schema": "janus.essence.turing/0.1",
        "status": status,
        "steps": steps,
        "state": state,
        "head": head,
        "final_tape": final_tape,
        "trace_sha256": chain,
        "budget": {"max_steps": max_steps, "max_cells": max_cells},
        "side_effects": False,
        "execution_authority": False,
    }


def unary_increment() -> dict:
    """Known-good finite transition table: append a unary digit '1'."""
    return {
        "blank": "_", "start": "scan", "accept": ["accept"], "reject": [],
        "transitions": [
            {"state": "scan", "read": "1", "write": "1", "move": "R", "next": "scan"},
            {"state": "scan", "read": "_", "write": "1", "move": "S", "next": "accept"},
        ],
    }
