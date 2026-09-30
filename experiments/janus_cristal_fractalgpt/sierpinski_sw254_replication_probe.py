#!/usr/bin/env python3
"""Independent-specimen replication gate for the Sierpinski/SW254 lead.

The target specimen and pass rule are loaded from the preregistered manifest.
FMDB image URLs are resolved from captioned media within one specimen record.
Remote image bytes are used transiently by the inherited frozen measurement and
are never copied to GitHub artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import fms_page_media
import spectral_replication_probe as frozen_replay

TARGET_PLANNER = "fractalgpt_sierpinski"
EXPECTED_ALPHA = 0.00166667
EXPECTED_NULLS = 2048
EXPECTED_WINDOWS = 20
ALLOWED_PREREG_STATUSES = {
    "PREREGISTERED_BEFORE_OUTCOME",
    "PREREGISTERED_BEFORE_OUTCOME_WITH_PRE_OUTCOME_PROTOCOL_CORRECTION",
}


def assert_preregistered(manifest: dict, trajectory_manifest: dict) -> None:
    if manifest.get("status") not in ALLOWED_PREREG_STATUSES:
        raise AssertionError("replication manifest must be preregistered")
    correction = manifest.get("pre_outcome_correction")
    if correction is not None and correction.get("outcome_seen_before_correction") is not False:
        raise AssertionError("protocol correction is only admissible before outcome acquisition")
    cfg = manifest["frozen_measurement"]
    if cfg["planner"] != TARGET_PLANNER:
        raise AssertionError("target planner moved")
    if int(cfg["matched_random_trajectories"]) != EXPECTED_NULLS:
        raise AssertionError("null count moved")
    if int(cfg["window_count"]) != EXPECTED_WINDOWS:
        raise AssertionError("window count moved")
    if abs(float(cfg["replication_alpha"]) - EXPECTED_ALPHA) > 1e-12:
        raise AssertionError("replication alpha moved")
    if cfg.get("retuning_allowed") is not False:
        raise AssertionError("retuning must remain forbidden")
    if int(trajectory_manifest["trajectory"]["window_count"]) != EXPECTED_WINDOWS:
        raise AssertionError("trajectory window count no longer matches corrected preregistration")


def build_pair(manifest: dict) -> tuple[dict, dict]:
    s = manifest["independent_specimen"]
    normal = fms_page_media.resolve_labeled_media(s["source_record_url"], s["normal_label"])
    sw = fms_page_media.resolve_labeled_media(s["source_record_url"], s["shortwave_label"])
    if normal["url"] == sw["url"]:
        raise RuntimeError("normal and SW254 labels resolved to the same media URL")
    pair = {
        "id": s["id"],
        "role": "TARGETED_SIERPINSKI_SW254_INDEPENDENT_REPLICATION",
        "material": s["material"],
        "same_specimen_status": s["same_specimen_status"],
        "provenance_reason": "Normal and SW254 media are resolved from captioned images inside one preregistered FMDB specimen record.",
        "visible": {
            "id": s["id"] + "::normal",
            "page_url": s["source_record_url"],
            "download_url": normal["url"],
            "author": s["source_author"],
            "license": "SOURCE_COPYRIGHT_RETAINED; TRANSIENT_ANALYSIS_ONLY",
        },
        "uv": {
            "id": s["id"] + "::sw254",
            "page_url": s["source_record_url"],
            "download_url": sw["url"],
            "author": s["source_author"],
            "license": "SOURCE_COPYRIGHT_RETAINED; TRANSIENT_ANALYSIS_ONLY",
            "modality": s["shortwave_modality"],
        },
    }
    resolver_receipt = {
        "page_url": s["source_record_url"],
        "normal": normal,
        "shortwave": sw,
        "media_bytes_persisted": False,
    }
    return pair, resolver_receipt


def evaluate(entry: dict, manifest: dict) -> dict:
    cfg = manifest["frozen_measurement"]
    alpha = float(cfg["replication_alpha"])
    planner = entry["planner_random_null_tests"][TARGET_PLANNER]
    registration_ok = entry["registration"]["quality_class"] == "USABLE_IMAGE_REGISTRATION"
    field_ok = entry["image_level_gate"]["status"] == "REGISTERED_MODALITY_DIFFERENCE_OBSERVED"
    p_comp = float(planner["one_sided_empirical_p_composite"])
    p_hot = float(planner["one_sided_empirical_p_hotspot"])
    comp_pass = p_comp <= alpha
    hot_pass = p_hot <= alpha
    passed = registration_ok and field_ok and comp_pass and hot_pass
    sensitivity_threshold = float(manifest["sensitivity_only_not_authoritative"]["experiment_wide_12_test_threshold"])
    return {
        "target_planner": TARGET_PLANNER,
        "registration_usable": registration_ok,
        "registered_modality_difference_observed": field_ok,
        "replication_alpha": alpha,
        "p_composite": p_comp,
        "p_hotspot": p_hot,
        "composite_pass": comp_pass,
        "hotspot_pass": hot_pass,
        "replication_gate": "PASS_INDEPENDENT_SPECIMEN_REPLICATION" if passed else "FAIL_TO_REPLICATE",
        "sensitivity_only_not_authoritative": {
            "threshold": sensitivity_threshold,
            "composite_pass": p_comp <= sensitivity_threshold,
            "hotspot_pass": p_hot <= sensitivity_threshold,
        },
        "claim_ceiling": "A PASS would establish replication of this fixed planner/statistical effect in the tested image-level protocol only, not semantic content or a general material-discovery capability."
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--trajectory-manifest", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    trajectory_manifest = json.loads(Path(args.trajectory_manifest).read_text(encoding="utf-8"))
    assert_preregistered(manifest, trajectory_manifest)
    pair, resolver = build_pair(manifest)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = frozen_replay.analyze_pair(pair, trajectory_manifest["trajectory"], out_dir)
    decision = evaluate(entry, manifest)

    report = {
        "schema": "genesis.janus_cristal.sierpinski_sw254_independent_replication.v1",
        "artifact_id": "GENESIS-JANUS-CRISTAL-FRACTALGPT-SIERPINSKI-SW254-REPLICATION-v0.1",
        "preregistered_manifest": manifest["artifact_id"],
        "pre_outcome_correction": manifest.get("pre_outcome_correction"),
        "resolver_receipt": resolver,
        "measurement": entry,
        "decision": decision,
        "semantic_content_admitted": 0,
        "formal_rules": manifest["formal_rules"] + [
            "TARGET_PLANNER_ONLY_IS_AUTHORITATIVE_FOR_THIS_REPLICATION_DECISION",
            "OTHER_PLANNER_RESULTS_ARE_CONTEXT_ONLY",
            "FAIL_TO_REPLICATE_IS_A_VALID_RESULT",
        ],
    }
    (out_dir / "GENESIS-JANUS-CRISTAL-FRACTALGPT-SIERPINSKI-SW254-REPLICATION-result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = [
        "# Sierpinski SW254 independent-specimen replication",
        "",
        f"Specimen: `{pair['id']}`",
        f"Windows: **{EXPECTED_WINDOWS}**",
        f"Registration: **{entry['registration']['quality_class']}**",
        f"Pair/gamma-control median ratio: **{entry['pair_to_gamma_control_median_ratio']}**",
        f"Sierpinski p(composite): **{decision['p_composite']}**",
        f"Sierpinski p(hotspot): **{decision['p_hotspot']}**",
        f"Frozen alpha: **{decision['replication_alpha']}**",
        f"Replication decision: **{decision['replication_gate']}**",
        "",
        "Semantic analysis: **DISABLED_BY_DESIGN**",
    ]
    (out_dir / "SIERPINSKI_SW254_REPLICATION_SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
