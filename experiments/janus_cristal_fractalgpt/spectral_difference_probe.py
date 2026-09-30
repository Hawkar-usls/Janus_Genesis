#!/usr/bin/env python3
"""Registered same-specimen visible/UV difference mapping for Janus Cristal.

NONSEMANTIC gate. Registration is performed first. A fixed-scale difference
field is then constructed from luminance, chromaticity and edge changes. Only
after that field exists do content-independent FractalGPT/baseline trajectories
sample it. No OCR, glyph search, cipher search or post-hoc region selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from statistics import median

import cv2
import numpy as np

import fractal_crystal_probe as fcp
import fractalgpt_adapter as fga

VISIBLE_ID = "petroleum_quartz_visible"
UV_ID = "petroleum_quartz_uv405"
WEIGHTS = {"luminance": 0.40, "chromaticity": 0.40, "edge": 0.20}
HOTSPOT_QUANTILE = 0.95
NULL_TRAJECTORY_COUNT = 2048
FAMILYWISE_ALPHA = 0.01


def gray_clahe(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(gray).astype(np.float32) / 255.0


def edge_map(image: np.ndarray) -> np.ndarray:
    gray = gray_clahe(image)
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(sx, sy)
    p99 = float(np.quantile(mag, 0.99))
    return np.clip(mag / max(p99, 1e-6), 0.0, 1.0)


def corr_masked(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    x = a[mask > 0].astype(np.float64)
    y = b[mask > 0].astype(np.float64)
    if x.size < 100 or x.std() <= 1e-12 or y.std() <= 1e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def resize_pair(a: np.ndarray, b: np.ndarray, max_dim: int = 1200) -> tuple[np.ndarray, np.ndarray]:
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, (w, h), interpolation=cv2.INTER_AREA)
    s = min(1.0, max_dim / max(h, w))
    if s < 1.0:
        size = (max(64, round(w * s)), max(64, round(h * s)))
        a = cv2.resize(a, size, interpolation=cv2.INTER_AREA)
        b = cv2.resize(b, size, interpolation=cv2.INTER_AREA)
    return a, b


def register_uv_to_visible(visible: np.ndarray, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    h, w = visible.shape[:2]
    template = edge_map(visible).astype(np.float32)
    moving = edge_map(uv).astype(np.float32)
    full_mask = np.ones((h, w), dtype=np.uint8)
    before = corr_masked(template, moving, full_mask)

    warp = np.eye(2, 3, dtype=np.float32)
    attempts = []
    selected_cc = None
    selected_motion = "IDENTITY"
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 150, 1e-6)

    for motion, name in (
        (cv2.MOTION_TRANSLATION, "TRANSLATION"),
        (cv2.MOTION_EUCLIDEAN, "EUCLIDEAN"),
        (cv2.MOTION_AFFINE, "AFFINE"),
    ):
        try:
            cc, candidate = cv2.findTransformECC(template, moving, warp.copy(), motion, criteria, None, 5)
            if np.all(np.isfinite(candidate)):
                warp = candidate.astype(np.float32)
                selected_cc = float(cc)
                selected_motion = name
                attempts.append({"motion": name, "status": "SUCCESS", "ecc": round(float(cc), 8)})
            else:
                attempts.append({"motion": name, "status": "NONFINITE"})
        except cv2.error as exc:
            attempts.append({"motion": name, "status": "ERROR", "message": str(exc).split("\n")[0][:180]})

    def apply(candidate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        registered = cv2.warpAffine(
            uv, candidate, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
        mask = cv2.warpAffine(
            np.ones((h, w), dtype=np.uint8), candidate, (w, h),
            flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
        mask[:4, :] = mask[-4:, :] = 0
        mask[:, :4] = mask[:, -4:] = 0
        return registered, mask

    registered, mask = apply(warp)
    after = corr_masked(template, edge_map(registered), mask)
    overlap = float((mask > 0).mean())
    a = warp[:, :2].astype(np.float64)
    det = float(np.linalg.det(a))
    translation_px = float(math.hypot(float(warp[0, 2]), float(warp[1, 2])))
    plausible = 0.70 <= abs(det) <= 1.35 and overlap >= 0.72 and translation_px <= 0.30 * max(h, w)

    if not plausible or after < before - 0.03:
        warp = np.eye(2, 3, dtype=np.float32)
        registered, mask = apply(warp)
        after = corr_masked(template, edge_map(registered), mask)
        overlap = float((mask > 0).mean())
        selected_motion = "IDENTITY_FALLBACK"
        selected_cc = None
        det = 1.0
        translation_px = 0.0

    quality = "USABLE_IMAGE_REGISTRATION" if overlap >= 0.85 and after >= 0.10 else "WEAK_REGISTRATION_USE_CAUTION"
    return registered, mask, {
        "method": "EDGE_ECC_TRANSLATION_TO_EUCLIDEAN_TO_AFFINE_WITH_IDENTITY_GUARD",
        "attempts": attempts,
        "selected_motion": selected_motion,
        "selected_ecc": None if selected_cc is None else round(selected_cc, 8),
        "warp_matrix": [[round(float(v), 9) for v in row] for row in warp.tolist()],
        "edge_correlation_before": round(before, 8),
        "edge_correlation_after": round(after, 8),
        "edge_correlation_gain": round(after - before, 8),
        "overlap_fraction": round(overlap, 8),
        "affine_determinant": round(det, 8),
        "translation_pixels_resized_frame": round(translation_px, 6),
        "quality_class": quality,
    }


def difference_channels(visible: np.ndarray, other: np.ndarray, mask: np.ndarray) -> dict[str, np.ndarray]:
    """Fixed physical image-space scales, so pair and self-control are comparable."""
    luminance = np.abs(gray_clahe(visible) - gray_clahe(other)).astype(np.float32)

    a = visible.astype(np.float32)[:, :, ::-1] / 255.0
    b = other.astype(np.float32)[:, :, ::-1] / 255.0
    ca = a / np.maximum(a.sum(axis=2, keepdims=True), 1e-5)
    cb = b / np.maximum(b.sum(axis=2, keepdims=True), 1e-5)
    chromaticity = np.clip(np.linalg.norm(ca - cb, axis=2) / math.sqrt(2.0), 0.0, 1.0).astype(np.float32)

    edge = np.abs(edge_map(visible) - edge_map(other)).astype(np.float32)
    composite = (
        WEIGHTS["luminance"] * luminance
        + WEIGHTS["chromaticity"] * chromaticity
        + WEIGHTS["edge"] * edge
    ).astype(np.float32)

    for field in (luminance, chromaticity, edge, composite):
        field[mask == 0] = 0.0
    return {"luminance": luminance, "chromaticity": chromaticity, "edge": edge, "composite": composite}


def gamma_control(image: np.ndarray, gamma: float = 0.72) -> np.ndarray:
    x = image.astype(np.float32) / 255.0
    return np.clip(np.power(np.clip(x, 0.0, 1.0), gamma) * 255.0, 0, 255).astype(np.uint8)


def summarize_field(field: np.ndarray, mask: np.ndarray) -> dict:
    vals = field[mask > 0].astype(np.float64)
    return {
        "mean": round(float(vals.mean()), 8),
        "median": round(float(np.median(vals)), 8),
        "p90": round(float(np.quantile(vals, 0.90)), 8),
        "p95": round(float(np.quantile(vals, 0.95)), 8),
        "p99": round(float(np.quantile(vals, 0.99)), 8),
    }


def hotspots(composite: np.ndarray, mask: np.ndarray, max_items: int = 16) -> tuple[np.ndarray, list[dict], float]:
    vals = composite[mask > 0]
    threshold = float(np.quantile(vals, HOTSPOT_QUANTILE))
    binary = ((composite >= threshold) & (mask > 0)).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(binary, connectivity=8)
    h, w = composite.shape
    rows = []
    for label in range(1, n):
        x, y, bw, bh, area = [int(v) for v in stats[label]]
        if area < 12:
            continue
        region = labels == label
        mean_value = float(composite[region].mean())
        score = mean_value * math.sqrt(area)
        cx, cy = cents[label]
        rows.append({
            "area_px": area,
            "bbox_norm": [round(x / w, 6), round(y / h, 6), round(bw / w, 6), round(bh / h, 6)],
            "centroid_norm": [round(float(cx) / w, 6), round(float(cy) / h, 6)],
            "mean_composite": round(mean_value, 8),
            "score": round(score, 8),
        })
    rows.sort(key=lambda r: (-r["score"], -r["area_px"]))
    return binary, rows[:max_items], threshold


def integral(field: np.ndarray) -> np.ndarray:
    return cv2.integral(field.astype(np.float64), sdepth=cv2.CV_64F)


def window_bounds(shape: tuple[int, int], window: dict) -> tuple[int, int, int, int]:
    h, w = shape
    side = max(8, int(round(min(h, w) * float(window["scale"]))))
    side = min(side, h, w)
    cx = int(round(float(window["cx"]) * (w - 1)))
    cy = int(round(float(window["cy"]) * (h - 1)))
    x0 = max(0, min(w - side, cx - side // 2))
    y0 = max(0, min(h - side, cy - side // 2))
    return x0, y0, x0 + side, y0 + side


def rect_mean(ii: np.ndarray, bounds: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = bounds
    total = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
    return float(total / max(1, (x1 - x0) * (y1 - y0)))


def sample_trajectory(fields: dict[str, np.ndarray], hotspot_binary: np.ndarray, trajectory: list[dict]) -> dict:
    shape = fields["composite"].shape
    ints = {k: integral(v) for k, v in fields.items()}
    hotspot_ii = integral(hotspot_binary.astype(np.float32))
    per_window = []
    for window in trajectory:
        b = window_bounds(shape, window)
        per_window.append({
            "window": window,
            "composite_mean": rect_mean(ints["composite"], b),
            "luminance_mean": rect_mean(ints["luminance"], b),
            "chromaticity_mean": rect_mean(ints["chromaticity"], b),
            "edge_mean": rect_mean(ints["edge"], b),
            "hotspot_fraction": rect_mean(hotspot_ii, b),
        })
    return {
        "median_composite": round(float(median(r["composite_mean"] for r in per_window)), 8),
        "median_hotspot_fraction": round(float(median(r["hotspot_fraction"] for r in per_window)), 8),
        "median_luminance": round(float(median(r["luminance_mean"] for r in per_window)), 8),
        "median_chromaticity": round(float(median(r["chromaticity_mean"] for r in per_window)), 8),
        "median_edge": round(float(median(r["edge_mean"] for r in per_window)), 8),
        "windows": per_window,
    }


def matched_random_trajectory(seed: str, template: list[dict]) -> list[dict]:
    raw = hashlib.sha256(seed.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(raw[:8], "big"))
    return [
        {
            "index": i,
            "cx": round(float(rng.uniform(0.04, 0.96)), 8),
            "cy": round(float(rng.uniform(0.04, 0.96)), 8),
            "scale": float(row["scale"]),
        }
        for i, row in enumerate(template)
    ]


def planner_null_test(fields: dict[str, np.ndarray], hotspot_binary: np.ndarray, planners: dict[str, list[dict]], seed: str) -> dict:
    shape = fields["composite"].shape
    composite_ii = integral(fields["composite"])
    hotspot_ii = integral(hotspot_binary.astype(np.float32))

    def stats(traj: list[dict]) -> tuple[float, float]:
        comp, hot = [], []
        for row in traj:
            b = window_bounds(shape, row)
            comp.append(rect_mean(composite_ii, b))
            hot.append(rect_mean(hotspot_ii, b))
        return float(median(comp)), float(median(hot))

    out = {}
    alpha = FAMILYWISE_ALPHA / max(1, len(planners))
    for name, traj in planners.items():
        observed_comp, observed_hot = stats(traj)
        null_comp, null_hot = [], []
        for i in range(NULL_TRAJECTORY_COUNT):
            c, h = stats(matched_random_trajectory(f"{seed}::{name}::{i}", traj))
            null_comp.append(c)
            null_hot.append(h)
        p_comp = (1 + sum(v >= observed_comp for v in null_comp)) / (NULL_TRAJECTORY_COUNT + 1)
        p_hot = (1 + sum(v >= observed_hot for v in null_hot)) / (NULL_TRAJECTORY_COUNT + 1)
        out[name] = {
            "observed_median_composite": round(observed_comp, 8),
            "observed_median_hotspot_fraction": round(observed_hot, 8),
            "null_median_composite": round(float(np.median(null_comp)), 8),
            "null_median_hotspot_fraction": round(float(np.median(null_hot)), 8),
            "one_sided_empirical_p_composite": round(float(p_comp), 8),
            "one_sided_empirical_p_hotspot": round(float(p_hot), 8),
            "familywise_alpha_per_planner": round(alpha, 8),
            "composite_enrichment_gate": "PASS_SINGLE_PAIR_CANDIDATE" if p_comp <= alpha else "NOT_ENRICHED",
            "hotspot_enrichment_gate": "PASS_SINGLE_PAIR_CANDIDATE" if p_hot <= alpha else "NOT_ENRICHED",
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    source_map = {s["id"]: s for s in manifest["sources"]}
    visible_meta, uv_meta = source_map[VISIBLE_ID], source_map[UV_ID]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "schema": "genesis.janus_cristal_fractalgpt.spectral_difference.v1",
        "artifact_id": "GENESIS-JANUS-CRISTAL-SPECTRAL-DIFFERENCE-v0.1",
        "pair": {"visible": VISIBLE_ID, "uv405": UV_ID, "same_specimen_group": "ALATAY"},
        "semantic_analysis": "DISABLED_BY_DESIGN",
        "difference_field_definition": "0.40*CLAHE_luminance_absdiff + 0.40*RGB_chromaticity_distance/sqrt(2) + 0.20*normalized_edge_absdiff",
        "difference_field_weights": WEIGHTS,
        "hotspot_quantile": HOTSPOT_QUANTILE,
        "null_trajectory_count_per_planner": NULL_TRAJECTORY_COUNT,
        "familywise_alpha": FAMILYWISE_ALPHA,
    }

    with tempfile.TemporaryDirectory(prefix="janus-spectral-diff-") as td:
        td = Path(td)
        vp, up = td / "visible.img", td / "uv.img"
        fcp.fetch(visible_meta["download_url"], vp)
        fcp.fetch(uv_meta["download_url"], up)
        visible = cv2.imread(str(vp), cv2.IMREAD_COLOR)
        uv = cv2.imread(str(up), cv2.IMREAD_COLOR)
        if visible is None or uv is None:
            raise RuntimeError("source image decode failed")

        report["source_receipts"] = {
            VISIBLE_ID: {"sha256": fcp.sha256_file(vp), "original_dimensions": [visible.shape[1], visible.shape[0]]},
            UV_ID: {"sha256": fcp.sha256_file(up), "original_dimensions": [uv.shape[1], uv.shape[0]]},
        }
        visible, uv = resize_pair(visible, uv, max_dim=1200)
        registered_uv, mask, reg = register_uv_to_visible(visible, uv)
        report["resized_dimensions"] = [visible.shape[1], visible.shape[0]]
        report["registration"] = reg

        fields = difference_channels(visible, registered_uv, mask)
        report["field_summary"] = {k: summarize_field(v, mask) for k, v in fields.items()}

        gamma_img = gamma_control(visible)
        gamma_fields = difference_channels(visible, gamma_img, mask)
        report["visible_gamma_self_control"] = {
            "gamma": 0.72,
            "field_summary": {k: summarize_field(v, mask) for k, v in gamma_fields.items()},
            "purpose": "Fixed-scale control for a strong monotonic exposure-like transform."
        }

        hotspot_binary, hotspot_rows, threshold = hotspots(fields["composite"], mask)
        report["hotspots"] = {
            "threshold": round(float(threshold), 8),
            "component_count_reported": len(hotspot_rows),
            "components": hotspot_rows,
            "status": "NONSEMANTIC_DIFFERENCE_REGIONS_ONLY",
        }

        cfg = manifest["trajectory"]
        count = int(cfg["window_count"])
        scales = [float(x) for x in cfg["scale_ladder"]]
        seed = cfg["seed"] + "::spectral-difference"
        recovered, recovered_receipt = fga.all_trajectories(seed, count, scales)
        planners = {
            "logistic_baseline": fcp.logistic_trajectory(seed + "::logistic", count, scales),
            "uniform_random_baseline": fcp.uniform_random_trajectory(seed + "::uniform", count, scales),
            **recovered,
        }
        report["trajectory_receipt"] = {
            "planner_count": len(planners),
            "recovered_fractalgpt": recovered_receipt,
            "planner_hashes": {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for k, v in planners.items()},
        }
        report["planner_samples"] = {name: sample_trajectory(fields, hotspot_binary, traj) for name, traj in planners.items()}
        report["planner_random_null_tests"] = planner_null_test(fields, hotspot_binary, planners, seed)

        enriched = [name for name, r in report["planner_random_null_tests"].items()
                    if r["composite_enrichment_gate"] == "PASS_SINGLE_PAIR_CANDIDATE"
                    or r["hotspot_enrichment_gate"] == "PASS_SINGLE_PAIR_CANDIDATE"]
        report["planner_enrichment_summary"] = {
            "enriched_planners": enriched,
            "enriched_planner_count": len(enriched),
            "admission": "SINGLE_PAIR_TRAJECTORY_ENRICHMENT_CANDIDATE_ONLY" if enriched else "NO_PLANNER_ENRICHMENT",
            "cross_specimen_replication": "NOT_ESTABLISHED"
        }

        pair_median = report["field_summary"]["composite"]["median"]
        ctrl_median = report["visible_gamma_self_control"]["field_summary"]["composite"]["median"]
        ratio = pair_median / max(ctrl_median, 1e-9)
        report["spectral_difference_gate"] = {
            "pair_composite_median": pair_median,
            "gamma_self_control_composite_median": ctrl_median,
            "pair_to_gamma_control_median_ratio": round(float(ratio), 8),
            "registration_quality": reg["quality_class"],
            "status": "REGISTERED_VISIBLE_UV_DIFFERENCE_FIELD_OBSERVED" if reg["quality_class"] == "USABLE_IMAGE_REGISTRATION" and ratio > 1.15 else "DIFFERENCE_FIELD_OBSERVED_WITH_LIMITATIONS"
        }

    report["formal_rules"] = [
        "REGISTRATION_PRECEDES_DIFFERENCE_FIELD",
        "DIFFERENCE_FIELD_PRECEDES_FRACTAL_SAMPLING",
        "FIXED_CHANNEL_SCALES_USED_FOR_PAIR_AND_SELF_CONTROL",
        "NO_OCR_OR_SEMANTIC_SEARCH_IN_SPECTRAL_GATE",
        "FRACTALGPT_TRAJECTORY != MATERIAL_DISCOVERY",
        "SINGLE_PAIR_ENRICHMENT != GENERAL_QUARTZ_PROPERTY",
        "VISIBLE_UV_DIFFERENCE != INTENTIONAL_MESSAGE",
    ]
    report["claim_ceiling"] = (
        "This gate can establish an image-level registered visible/UV difference field for one matched specimen and compare content-independent trajectories with random null trajectories. "
        "It cannot establish a universal quartz property, chemical identity without spectroscopy, hidden semantics, intelligence, or a supernatural cause."
    )

    (out_dir / "GENESIS-JANUS-CRISTAL-SPECTRAL-DIFFERENCE-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Registered visible ↔ UV405 same-specimen gate",
        "",
        f"Registration: **{report['registration']['quality_class']}**; edge corr {report['registration']['edge_correlation_before']} → {report['registration']['edge_correlation_after']}",
        f"Composite median: pair **{report['field_summary']['composite']['median']}** vs gamma self-control **{report['visible_gamma_self_control']['field_summary']['composite']['median']}**",
        f"Difference status: **{report['spectral_difference_gate']['status']}**",
        f"Planner enrichment: **{report['planner_enrichment_summary']['admission']}** ({report['planner_enrichment_summary']['enriched_planner_count']} planners)",
        "",
        "Semantic analysis: **DISABLED_BY_DESIGN**",
    ]
    (out_dir / "SPECTRAL_DIFFERENCE_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
