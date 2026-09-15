#!/usr/bin/env python3
"""Final admission layer for cross-specimen spectral replication receipts.

The raw replay preserves measurements separately from admission. The AKAZE
geometry heuristic is calibrated against the known Alatay same-specimen positive
control. If it rejects that positive control it is invalidated as a necessary
identity gate. Multiple UV modalities from one physical specimen are also kept
from double-counting an independent replication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CONFIRMATORY_ROLE = "CONFIRMATORY_MODALITY_SAME_SPECIMEN_NOT_INDEPENDENT_REPLICATION_COUNT"


def admit(raw: dict) -> dict:
    pairs = raw.get("pairs", [])
    anchor = next((p for p in pairs if p.get("role") == "FROZEN_DISCOVERY_ANCHOR_NOT_REPLICATION"), None)
    if anchor is None:
        geometry_status = "NOT_EVALUABLE_NO_POSITIVE_CONTROL"
        geometry_usable = False
    else:
        anchor_geo = anchor.get("geometry_corroboration", {}).get("status")
        geometry_usable = anchor_geo == "IMAGE_GEOMETRY_SUPPORTS_SAME_SCENE"
        geometry_status = (
            "VALIDATED_ON_CONFIRMED_SAME_SPECIMEN_POSITIVE_CONTROL"
            if geometry_usable
            else "INVALIDATED_FALSE_NEGATIVE_ON_CONFIRMED_SAME_SPECIMEN_POSITIVE_CONTROL"
        )

    decisions = []
    formal = []
    candidates = []
    confirmatory = []
    for p in pairs:
        pid = p.get("pair_id")
        role = p.get("role")
        observed = p.get("image_level_gate", {}).get("status") == "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"
        provenance = p.get("same_specimen_status", "")

        if role == "FROZEN_DISCOVERY_ANCHOR_NOT_REPLICATION":
            decision = "DISCOVERY_ANCHOR_EXCLUDED_FROM_REPLICATION_COUNT"
        elif p.get("replication_admission") == "ERROR_NOT_ADMITTED":
            decision = "ERROR_NOT_ADMITTED"
        elif role == CONFIRMATORY_ROLE:
            decision = (
                "CONFIRMATORY_SAME_SPECIMEN_MODALITY_DIFFERENCE_OBSERVED_NOT_INDEPENDENT_COUNT"
                if observed else "CONFIRMATORY_MODALITY_REPLICATION_NOT_ESTABLISHED"
            )
            if observed:
                confirmatory.append(pid)
        elif observed and provenance.startswith("CONFIRMED"):
            decision = "FORMAL_INDEPENDENT_SAME_SPECIMEN_IMAGE_LEVEL_REPLICATION"
            formal.append(pid)
        elif observed and provenance.startswith("PROBABLE"):
            decision = "IMAGE_LEVEL_MODALITY_DIFFERENCE_REPLICATION_CANDIDATE_PROVENANCE_UNCONFIRMED"
            candidates.append(pid)
        elif observed:
            decision = "IMAGE_LEVEL_MODALITY_DIFFERENCE_OBSERVED_IDENTITY_UNRESOLVED"
        else:
            decision = "REPLICATION_NOT_ESTABLISHED"

        decisions.append({
            "pair_id": pid,
            "role": role,
            "same_specimen_status": provenance,
            "registered_difference_status": p.get("image_level_gate", {}).get("status"),
            "geometry_raw_status": p.get("geometry_corroboration", {}).get("status"),
            "geometry_used_for_admission": geometry_usable,
            "planner_enrichment": p.get("planner_enrichment", {}).get("status"),
            "decision": decision,
        })

    planner_hits = [
        p.get("pair_id") for p in pairs
        if p.get("planner_enrichment", {}).get("status") == "SINGLE_PAIR_PLANNER_ENRICHMENT_CANDIDATE"
    ]
    return {
        "schema": "genesis.janus_cristal.spectral_replication_admission.v1",
        "artifact_id": "GENESIS-JANUS-CRISTAL-SPECTRAL-REPLICATION-ADMISSION-v0.2",
        "authority": "FINAL_REPLICATION_CLASSIFICATION_LAYER",
        "geometry_validator": {
            "status": geometry_status,
            "usable_for_admission": geometry_usable,
            "reason": "A necessary identity validator must accept the confirmed Alatay same-specimen positive control before it may be used on independent candidates."
        },
        "pair_decisions": decisions,
        "formal_independent_replications": formal,
        "formal_independent_replication_count": len(formal),
        "provenance_unconfirmed_image_level_candidates": candidates,
        "candidate_count": len(candidates),
        "confirmatory_same_specimen_modalities": confirmatory,
        "confirmatory_modality_count": len(confirmatory),
        "planner_enrichment_pair_count": len(planner_hits),
        "planner_enrichment_pairs": planner_hits,
        "cross_specimen_replication_gate": "PASS" if formal else "OPEN_NOT_ESTABLISHED",
        "semantic_content_admitted": 0,
        "status": (
            "FORMAL_REPLICATION_ESTABLISHED" if formal
            else "IMAGE_LEVEL_CANDIDATE_ONLY_PROVENANCE_BLOCKS_FORMAL_REPLICATION" if candidates
            else "NO_INDEPENDENT_REPLICATION_CANDIDATE_ADMITTED"
        ),
        "formal_rules": [
            "RAW_PRE_ADMISSION_CLASSIFICATION != FINAL_ADMISSION",
            "A_VALIDATOR_THAT_FAILS_THE_POSITIVE_CONTROL_IS_NOT_ADMISSIBLE_AS_A_NECESSARY_GATE",
            "PRIMARY_AND_CONFIRMATORY_MODALITIES_FROM_ONE_SPECIMEN_COUNT_AS_AT_MOST_ONE_INDEPENDENT_REPLICATION",
            "PROBABLE_SAME_SPECIMEN != CONFIRMED_SAME_SPECIMEN",
            "REGISTERED_MODALITY_DIFFERENCE != CHEMICAL_IDENTITY",
            "REGISTERED_MODALITY_DIFFERENCE != HIDDEN_MESSAGE",
            "FRACTALGPT_TRAJECTORY != MATERIAL_DISCOVERY",
            "NO_POST_HOC_REGION_OR_CIPHER_SEARCH"
        ]
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    result = admit(raw)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "formal": result["formal_independent_replication_count"],
        "candidates": result["candidate_count"],
        "confirmatory": result["confirmatory_modality_count"],
        "geometry_validator": result["geometry_validator"]["status"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
