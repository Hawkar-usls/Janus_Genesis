#!/usr/bin/env python3
"""Cross-specimen replay of the frozen Janus Cristal visible/UV protocol.

This module intentionally imports the already-frozen v0.4 registration and
image-difference functions rather than redefining or tuning them for a new pair.
A second open quartz pair may become an image-level replication candidate, but
uncertain same-specimen provenance remains uncertain even if geometry agrees.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path

import cv2
import numpy as np

import fractal_crystal_probe as fcp
import fractalgpt_adapter as fga
import spectral_difference_probe as frozen

EXPECTED_WEIGHTS = {"luminance": 0.40, "chromaticity": 0.40, "edge": 0.20}
EXPECTED_HOTSPOT_QUANTILE = 0.95
EXPECTED_GAMMA = 0.72


def assert_frozen_protocol(manifest: dict) -> None:
    cfg = manifest["frozen_protocol"]
    if cfg.get("retuning_allowed") is not False:
        raise AssertionError("replication protocol must forbid per-pair retuning")
    got = {k: float(v) for k, v in cfg["difference_weights"].items()}
    if got != EXPECTED_WEIGHTS or frozen.WEIGHTS != EXPECTED_WEIGHTS:
        raise AssertionError(f"difference weights moved: manifest={got} runtime={frozen.WEIGHTS}")
    if float(cfg["hotspot_quantile"]) != EXPECTED_HOTSPOT_QUANTILE:
        raise AssertionError("hotspot quantile moved")
    if float(cfg["gamma_self_control"]) != EXPECTED_GAMMA:
        raise AssertionError("gamma self-control moved")
    if frozen.HOTSPOT_QUANTILE != EXPECTED_HOTSPOT_QUANTILE:
        raise AssertionError("runtime hotspot quantile moved")


def _gray_features(image: np.ndarray) -> tuple[list, np.ndarray | None]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector = cv2.AKAZE_create()
    return detector.detectAndCompute(gray, None)


def geometry_corroboration(visible: np.ndarray, uv: np.ndarray) -> dict:
    """Fixed AKAZE/RANSAC scene-geometry check; never used to tune the field."""
    kp1, d1 = _gray_features(visible)
    kp2, d2 = _gray_features(uv)
    if d1 is None or d2 is None or len(kp1) < 8 or len(kp2) < 8:
        return {
            "status": "INSUFFICIENT_FEATURES",
            "keypoints_visible": len(kp1),
            "keypoints_uv": len(kp2),
            "good_matches": 0,
            "homography_inliers": 0,
            "inlier_ratio": 0.0,
        }

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(d1, d2, k=2)
    good = [m for m, n in knn if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return {
            "status": "INSUFFICIENT_MATCHES",
            "keypoints_visible": len(kp1),
            "keypoints_uv": len(kp2),
            "good_matches": len(good),
            "homography_inliers": 0,
            "inlier_ratio": 0.0,
        }

    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
    inliers = int(mask.sum()) if mask is not None else 0
    ratio = inliers / max(1, len(good))
    plausible = False
    det2 = None
    if H is not None and np.all(np.isfinite(H)) and abs(float(H[2, 2])) > 1e-12:
        H = H / H[2, 2]
        det2 = float(np.linalg.det(H[:2, :2]))
        plausible = 0.05 <= abs(det2) <= 20.0
    status = "IMAGE_GEOMETRY_SUPPORTS_SAME_SCENE" if inliers >= 12 and ratio >= 0.25 and plausible else "IMAGE_GEOMETRY_NOT_DECISIVE"
    return {
        "status": status,
        "keypoints_visible": len(kp1),
        "keypoints_uv": len(kp2),
        "good_matches": len(good),
        "homography_inliers": inliers,
        "inlier_ratio": round(float(ratio), 8),
        "homography_linear_det": None if det2 is None else round(float(det2), 8),
        "note": "Geometry can corroborate a shared photographed scene; it cannot by itself prove specimen identity or source provenance."
    }


def _pair_trajectories(seed: str, count: int, scales: list[float]) -> tuple[dict, dict]:
    recovered, receipt = fga.all_trajectories(seed, count, scales)
    planners = {
        "logistic_baseline": fcp.logistic_trajectory(seed + "::logistic", count, scales),
        "uniform_random_baseline": fcp.uniform_random_trajectory(seed + "::uniform", count, scales),
        **recovered,
    }
    return planners, receipt


def analyze_pair(pair: dict, trajectory_cfg: dict, out_dir: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="janus-spectral-repl-") as td:
        td = Path(td)
        vp, up = td / "visible.img", td / "uv.img"
        fcp.fetch(pair["visible"]["download_url"], vp)
        fcp.fetch(pair["uv"]["download_url"], up)
        visible_raw = cv2.imread(str(vp), cv2.IMREAD_COLOR)
        uv_raw = cv2.imread(str(up), cv2.IMREAD_COLOR)
        if visible_raw is None or uv_raw is None:
            raise RuntimeError("pair source decode failed")

        entry = {
            "pair_id": pair["id"],
            "role": pair["role"],
            "material": pair["material"],
            "same_specimen_status": pair["same_specimen_status"],
            "provenance_reason": pair.get("provenance_reason"),
            "semantic_analysis": "DISABLED_BY_DESIGN",
            "source_receipts": {
                "visible": {
                    "sha256": fcp.sha256_file(vp),
                    "dimensions": [visible_raw.shape[1], visible_raw.shape[0]],
                    "page_url": pair["visible"]["page_url"],
                },
                "uv": {
                    "sha256": fcp.sha256_file(up),
                    "dimensions": [uv_raw.shape[1], uv_raw.shape[0]],
                    "page_url": pair["uv"]["page_url"],
                    "modality": pair["uv"].get("modality"),
                },
            },
        }

        # Geometry check uses independent, equally downscaled copies and cannot
        # alter registration parameters or difference-field thresholds.
        geo_v, geo_u = frozen.resize_pair(visible_raw, uv_raw, max_dim=1000)
        entry["geometry_corroboration"] = geometry_corroboration(geo_v, geo_u)

        visible, uv = frozen.resize_pair(visible_raw, uv_raw, max_dim=1200)
        registered_uv, mask, reg = frozen.register_uv_to_visible(visible, uv)
        entry["resized_dimensions"] = [visible.shape[1], visible.shape[0]]
        entry["registration"] = reg

        fields = frozen.difference_channels(visible, registered_uv, mask)
        entry["field_summary"] = {k: frozen.summarize_field(v, mask) for k, v in fields.items()}

        gamma = frozen.gamma_control(visible, gamma=EXPECTED_GAMMA)
        gamma_fields = frozen.difference_channels(visible, gamma, mask)
        entry["gamma_self_control"] = {
            "gamma": EXPECTED_GAMMA,
            "field_summary": {k: frozen.summarize_field(v, mask) for k, v in gamma_fields.items()},
        }
        pair_median = float(entry["field_summary"]["composite"]["median"])
        ctrl_median = float(entry["gamma_self_control"]["field_summary"]["composite"]["median"])
        ratio = pair_median / max(ctrl_median, 1e-9)
        entry["pair_to_gamma_control_median_ratio"] = round(ratio, 8)

        hotspot_binary, hotspot_rows, threshold = frozen.hotspots(fields["composite"], mask)
        entry["hotspots"] = {
            "threshold": round(float(threshold), 8),
            "component_count_reported": len(hotspot_rows),
            "components": hotspot_rows,
            "status": "NONSEMANTIC_DIFFERENCE_REGIONS_ONLY",
        }

        count = int(trajectory_cfg["window_count"])
        scales = [float(v) for v in trajectory_cfg["scale_ladder"]]
        seed = trajectory_cfg["seed"] + "::replication::" + pair["id"]
        planners, recovered_receipt = _pair_trajectories(seed, count, scales)
        entry["trajectory_receipt"] = {
            "planner_count": len(planners),
            "recovered_fractalgpt": recovered_receipt,
            "planner_hashes": {
                name: hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
                for name, rows in planners.items()
            },
        }
        entry["planner_random_null_tests"] = frozen.planner_null_test(fields, hotspot_binary, planners, seed)
        enriched = [
            name for name, r in entry["planner_random_null_tests"].items()
            if r["composite_enrichment_gate"] == "PASS_SINGLE_PAIR_CANDIDATE"
            or r["hotspot_enrichment_gate"] == "PASS_SINGLE_PAIR_CANDIDATE"
        ]
        entry["planner_enrichment"] = {
            "enriched_planners": enriched,
            "enriched_planner_count": len(enriched),
            "status": "SINGLE_PAIR_PLANNER_ENRICHMENT_CANDIDATE" if enriched else "NO_PLANNER_ENRICHMENT",
        }

        usable = reg["quality_class"] == "USABLE_IMAGE_REGISTRATION"
        difference_observed = usable and ratio > 1.15
        geo_support = entry["geometry_corroboration"]["status"] == "IMAGE_GEOMETRY_SUPPORTS_SAME_SCENE"
        entry["image_level_gate"] = {
            "registration_usable": usable,
            "pair_exceeds_fixed_gamma_control": bool(ratio > 1.15),
            "geometry_supports_same_scene": geo_support,
            "status": "REGISTERED_MODALITY_DIFFERENCE_OBSERVED" if difference_observed else "NOT_ADMITTED_AS_REGISTERED_MODALITY_DIFFERENCE",
        }

        if pair["role"] == "FROZEN_DISCOVERY_ANCHOR_NOT_REPLICATION":
            replication = "DISCOVERY_ANCHOR_EXCLUDED_FROM_REPLICATION_COUNT"
        elif difference_observed and geo_support and pair["same_specimen_status"].startswith("CONFIRMED"):
            replication = "FORMAL_INDEPENDENT_SAME_SPECIMEN_REPLICATION"
        elif difference_observed and geo_support:
            replication = "IMAGE_LEVEL_REPLICATION_CANDIDATE_PROVENANCE_UNCONFIRMED"
        elif difference_observed:
            replication = "MODALITY_DIFFERENCE_CANDIDATE_IDENTITY_NOT_CORROBORATED"
        else:
            replication = "REPLICATION_NOT_ESTABLISHED"
        entry["replication_admission"] = replication
        return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--trajectory-manifest", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    trajectory_manifest = json.loads(Path(args.trajectory_manifest).read_text(encoding="utf-8"))
    assert_frozen_protocol(manifest)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "schema": "genesis.janus_cristal.spectral_cross_specimen_replication.v1",
        "artifact_id": "GENESIS-JANUS-CRISTAL-SPECTRAL-REPLICATION-v0.1",
        "protocol_status": "FROZEN_NO_PAIR_SPECIFIC_RETUNING",
        "semantic_analysis": "DISABLED_BY_DESIGN",
        "pairs": [],
    }
    errors = []
    for pair in manifest["pairs"]:
        try:
            report["pairs"].append(analyze_pair(pair, trajectory_manifest["trajectory"], out_dir))
        except Exception as exc:
            errors.append({"pair_id": pair["id"], "error": f"{type(exc).__name__}: {exc}"})
            report["pairs"].append({
                "pair_id": pair["id"],
                "role": pair["role"],
                "same_specimen_status": pair["same_specimen_status"],
                "replication_admission": "ERROR_NOT_ADMITTED",
                "error": f"{type(exc).__name__}: {exc}",
            })

    formal = [p["pair_id"] for p in report["pairs"] if p.get("replication_admission") == "FORMAL_INDEPENDENT_SAME_SPECIMEN_REPLICATION"]
    candidates = [p["pair_id"] for p in report["pairs"] if p.get("replication_admission") == "IMAGE_LEVEL_REPLICATION_CANDIDATE_PROVENANCE_UNCONFIRMED"]
    report["summary"] = {
        "pair_count": len(manifest["pairs"]),
        "pair_errors": len(errors),
        "formal_independent_replications": formal,
        "formal_independent_replication_count": len(formal),
        "provenance_unconfirmed_image_level_candidates": candidates,
        "candidate_count": len(candidates),
        "cross_specimen_replication_gate": "PASS" if formal else "OPEN_NOT_ESTABLISHED",
    }
    report["formal_rules"] = manifest["admission_rules"] + [
        "GEOMETRY_CORROBORATION_DOES_NOT_OVERRIDE_PROVENANCE_UNCERTAINTY",
        "DISCOVERY_ANCHOR_CANNOT_SELF_REPLICATE",
        "NO_OCR_GLYPH_FORMULA_OR_CIPHER_SEARCH_IN_THIS_GATE",
    ]
    report["claim_ceiling"] = (
        "This gate can replay a frozen image-level visible/UV protocol on additional open pairs. "
        "It cannot convert probable specimen identity into confirmed provenance, identify chemistry without spectroscopy, "
        "or establish hidden semantic content, intelligence, or supernatural causation."
    )

    path = out_dir / "GENESIS-JANUS-CRISTAL-SPECTRAL-REPLICATION-result.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Cross-specimen visible/UV replication gate",
        "",
        f"Pairs executed: **{len(manifest['pairs']) - len(errors)}/{len(manifest['pairs'])}**",
        f"Formal independent replications: **{len(formal)}**",
        f"Provenance-unconfirmed image-level candidates: **{len(candidates)}**",
        f"Gate: **{report['summary']['cross_specimen_replication_gate']}**",
        "",
        "| pair | registration | geometry | ratio vs gamma control | admission |",
        "|---|---|---|---:|---|",
    ]
    for p in report["pairs"]:
        reg = p.get("registration", {}).get("quality_class", "ERROR")
        geo = p.get("geometry_corroboration", {}).get("status", "ERROR")
        ratio = p.get("pair_to_gamma_control_median_ratio", "-")
        lines.append(f"| {p['pair_id']} | {reg} | {geo} | {ratio} | {p.get('replication_admission')} |")
    lines += ["", "Semantic analysis: **DISABLED_BY_DESIGN**"]
    (out_dir / "SPECTRAL_REPLICATION_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
