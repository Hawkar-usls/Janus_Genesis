#!/usr/bin/env python3
"""ESSENCE v1.8: data-only block-precision mutation and measured research selection.

Searches block widths for INT4/INT8 under v1.5 error and four-pass drift
limits. Every candidate is compared with the existing v1.5 decision. No model
loading, training, permission escalation, external execution, or deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import adaptive_quantization_v15 as base

SCHEMA = "janus.essence.block_precision_evolution/1.8"
MAGIC = b"ESQ2"
HEADER = struct.Struct("<4sBHB")
BLOCKS = (16, 32, 64, 128)
BITS = (4, 8)
MAX_GENERATION = 16

def digest(obj):
    return hashlib.sha256(base.canonical(obj)).hexdigest()

def pack(values, bits, block):
    vec, _ = base.normalized(values)
    if type(bits) is not int or bits not in BITS or type(block) is not int or block not in BLOCKS:
        raise ValueError("UNSUPPORTED_PRECISION_MUTATION")
    qmax = 7 if bits == 4 else 127
    scales = []
    codes = []
    for i in range(0, len(vec), block):
        part = vec[i:i + block]
        scale = max(abs(x) for x in part) / qmax or 1.0
        scales.append(scale)
        codes.extend(max(-qmax, min(qmax, (1 if x >= 0 else -1) * int(abs(x / scale) + 0.5))) for x in part)
    body = b"".join(struct.pack("<d", s) for s in scales)
    if bits == 8:
        body += bytes(x & 255 for x in codes)
    else:
        body += bytes((codes[i] & 15) | ((codes[i+1] & 15) << 4 if i+1 < len(codes) else 0)
                      for i in range(0, len(codes), 2))
    return HEADER.pack(MAGIC, bits, len(vec), block) + body

def unpack(packet):
    if not isinstance(packet, bytes) or len(packet) < HEADER.size:
        raise ValueError("INVALID_PRECISION_PACKET")
    magic, bits, n, block = HEADER.unpack_from(packet)
    if magic != MAGIC or bits not in BITS or block not in BLOCKS or not 1 <= n <= 4096:
        raise ValueError("INVALID_PRECISION_HEADER")
    scale_count = (n + block - 1) // block
    code_count = n if bits == 8 else (n + 1) // 2
    if len(packet) != HEADER.size + 8 * scale_count + code_count:
        raise ValueError("INVALID_PRECISION_LENGTH")
    pos = HEADER.size
    scales = struct.unpack_from("<" + "d" * scale_count, packet, pos)
    if any(not math.isfinite(s) or s <= 0 for s in scales):
        raise ValueError("INVALID_PRECISION_SCALE")
    data = packet[pos + 8 * scale_count:]
    if bits == 8:
        codes = [x - 256 if x > 127 else x for x in data]
        if -128 in codes: raise ValueError("INVALID_INT8_CODE")
    else:
        codes = []
        for x in data: codes.extend((x & 15, x >> 4))
        if n % 2 and codes[-1] != 0: raise ValueError("INVALID_INT4_PADDING")
        codes = [x - 16 if x > 7 else x for x in codes[:n]]
        if -8 in codes: raise ValueError("INVALID_INT4_CODE")
    return [x * scales[i // block] for i, x in enumerate(codes)]

def decoded(packet):
    return unpack(packet) if packet[:4] == MAGIC else base.decode(packet)

def optimize(values, role):
    if role not in base.POLICY: raise ValueError("UNKNOWN_MICROKERNEL_ROLE")
    original, exact = base.normalized(values)
    parent = base.choose(original, role)
    options = [(parent["packet"], parent["bits"], 32, "V15_PARENT")]
    attempts = 0
    for bits in BITS:
        for block in BLOCKS:
            attempts += 1
            candidate = pack(original, bits, block)
            after = unpack(candidate)
            error = max(abs(x-y) for x,y in zip(original, after))
            cycle = after
            for _ in range(3): cycle = unpack(pack(cycle, bits, block))
            drift = max(abs(x-y) for x,y in zip(original, cycle))
            if (error <= base.POLICY[role] and drift <= base.POLICY[role] * 1.5
                and len(candidate) <= len(exact) * 0.9):
                options.append((candidate, bits, block, "V18_MUTATION"))
    # Smallest measured packet wins; the old decision is always a safe fallback.
    options.sort(key=lambda row: (len(row[0]), row[1], row[2], row[3]))
    packet, bits, block, family = options[0]
    error = max(abs(x-y) for x,y in zip(original, decoded(packet)))
    return {
        "packet": packet, "exact": exact, "bits": bits, "block": block,
        "family": family, "tried_mutations": attempts,
        "error": error, "parent_packet_bytes": len(parent["packet"]),
        "improved_bytes": len(parent["packet"]) - len(packet)
    }

def run(root, fixture, *, source=None, previous=None, explicit_readonly=False):
    if explicit_readonly is not True:
        raise PermissionError("PRECISION_EVOLUTION_INERT_BY_DEFAULT")
    numeric = base.vectors(root, fixture, source)
    state_hash = digest(source if source is not None else numeric)
    parent_receipt = None
    generation = 0
    duplicate = False
    if previous is not None:
        if (not isinstance(previous, dict) or previous.get("schema") != SCHEMA
            or previous.get("repository") != root["repository"]
            or previous.get("root_sha256") != digest(root)
            or previous.get("receipt_sha256") != digest({k:v for k,v in previous.items()
                                                       if k != "receipt_sha256"})
            or previous.get("production_authority") is not False
            or previous.get("automatic_promotion") is not False
            or type(previous.get("generation")) is not int
            or not 0 <= previous["generation"] <= MAX_GENERATION):
            raise ValueError("UNTRUSTED_PARENT_PRECISION_EVIDENCE")
        parent_receipt = previous["receipt_sha256"]
        generation = previous["generation"]
        duplicate = previous.get("numeric_state_sha256") == state_hash
    packed = b""
    exact = b""
    rows = []
    total_parent = 0
    for role in (*base.ROLES, "essence_self"):
        result = optimize(numeric[role], role)
        p, backup = result["packet"], result["exact"]
        # Bit-perfect restoration comes from a sealed untouched FP32 backup.
        if backup != base.normalized(numeric[role])[1]:
            raise ValueError("FP32_BACKUP_CHANGED")
        rows.append({
            "role": role, "bits": result["bits"], "block": result["block"],
            "family": result["family"], "tried_mutations": result["tried_mutations"],
            "packed_sha256": hashlib.sha256(p).hexdigest(),
            "original_sha256": hashlib.sha256(backup).hexdigest(),
            "packed_bytes": len(p), "original_bytes": len(backup),
            "parent_packed_bytes": result["parent_packet_bytes"],
            "max_abs_error": round(result["error"], 9),
            "within_original_policy": result["error"] <= base.POLICY[role],
            "production_modified": False
        })
        total_parent += result["parent_packet_bytes"]
        packed += p
        exact += backup
    benefit = total_parent - len(packed)
    if benefit < 0 or any(not row["within_original_policy"] for row in rows):
        raise ValueError("PRECISION_CHILD_REGRESSION")
    if benefit > 0 and not duplicate and generation < MAX_GENERATION:
        generation += 1
    status = ("HOLD_DUPLICATE_NUMERIC_STATE" if duplicate
              else "RESEARCH_BLOCK_MUTATION_STAGED" if benefit > 0 and generation > 0
              else "HOLD_NO_MEASURABLE_GAIN")
    report = {
        "schema": SCHEMA, "repository": root["repository"],
        "root_sha256": digest(root), "numeric_state_sha256": state_hash,
        "source_class": source["source_class"] if source else "SYNTHETIC_FIXTURE",
        "generation": generation, "parent_receipt_sha256": parent_receipt,
        "research_status": status, "lanes": rows,
        "v15_packed_bytes": total_parent, "v18_packed_bytes": len(packed),
        "exact_fp32_backup_bytes": len(exact),
        "additional_storage_saving_bytes": benefit,
        "additional_storage_saving_fraction": round(benefit / total_parent, 7),
        "packed_sha256": hashlib.sha256(packed).hexdigest(),
        "backup_sha256": hashlib.sha256(exact).hexdigest(),
        "independent_closed_holdout": False, "target_hardware_proven": False,
        "live_service_rollback_proven": False, "model_weights_changed": False,
        "production_authority": False, "automatic_promotion": False,
        "actual_neural_training": False, "external_evidence_required": True
    }
    report["receipt_sha256"] = digest(report)
    return report, packed, exact

def main():
    p = argparse.ArgumentParser()
    for name in ("root", "fixture", "state", "previous", "out"):
        p.add_argument("--" + name)
    p.add_argument("--allow-readonly", action="store_true")
    args = p.parse_args()
    if not args.root or not args.fixture or not args.out:
        raise ValueError("ROOT_FIXTURE_AND_OUT_REQUIRED")
    result, _, _ = run(base.load(args.root), base.load(args.fixture),
                       source=base.load(args.state) if args.state else None,
                       previous=base.load(args.previous) if args.previous else None,
                       explicit_readonly=args.allow_readonly)
    dest = Path(args.out)
    if dest.exists(): raise FileExistsError("RESEARCH_RECEIPT_IMMUTABLE")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({"status": result["research_status"],
                      "additional_storage_saving_bytes": result["additional_storage_saving_bytes"],
                      "generation": result["generation"], "production_authority": False}))

if __name__ == "__main__":
    main()
