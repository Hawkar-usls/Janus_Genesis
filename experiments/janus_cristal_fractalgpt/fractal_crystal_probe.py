#!/usr/bin/env python3
"""Janus Cristal × recovered FractalGPT multi-planner probe.

FractalGPT chooses WHERE / AT WHAT SCALE to inspect. Conventional OCR/CV
measurements decide WHAT is present. Every trajectory is content-independent
and is replayed unchanged against matched null controls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import cv2
import numpy as np

import fractalgpt_adapter as fga

UA = "Janus-Genesis-FractalGPT-Crystal/0.3"
TOKEN_RE = re.compile(r"[A-Z0-9][A-Z0-9_+\-*/=^<>()[\]{}.:]{2,23}")
FORMULA_RE = re.compile(r"(?=.*\d)(?=.*[=+\-*/^])[A-Z0-9_+\-*/=^<>()[\]{}.:]{3,24}")
CODE_HINTS = ("IF", "FOR", "WHILE", "DEF", "INT", "HEX", "0X", "==", "->", "::", "{}", "[]")


def sha256_bytes(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)


def normalize_token(text: str) -> str:
    text = text.upper().replace(" ", "").replace("|", "I")
    allowed = "_+-*/=^<>()[].{}:"
    return "".join(c for c in text if c.isalnum() or c in allowed)[:24]


def classify_token(token: str) -> str:
    if FORMULA_RE.fullmatch(token):
        return "FORMULA_LIKE"
    if any(h in token for h in CODE_HINTS) or sum(c in "_{}[]():<>" for c in token) >= 2:
        return "CODE_LIKE"
    if token.isalpha():
        return "WORD_LIKE"
    return "SYMBOL_SEQUENCE"


def logistic_trajectory(seed: str, count: int, scales: list[float]) -> list[dict]:
    b = sha256_bytes(seed)
    x = (int.from_bytes(b[0:8], "big") + 1) / (2**64 + 2)
    y = (int.from_bytes(b[8:16], "big") + 1) / (2**64 + 2)
    r1 = 3.82 + (b[16] / 255.0) * 0.16
    r2 = 3.82 + (b[17] / 255.0) * 0.16
    eps = 0.015 + (b[18] / 255.0) * 0.02

    def step(xv: float, yv: float) -> tuple[float, float]:
        nx = r1 * xv * (1.0 - xv) + eps * (yv - xv)
        ny = r2 * yv * (1.0 - yv) + eps * (xv - yv)
        return min(0.999999, max(0.000001, nx)), min(0.999999, max(0.000001, ny))

    for _ in range(64):
        x, y = step(x, y)

    out = []
    for i in range(count):
        x, y = step(x, y)
        selector = int((x * 997 + y * 991 + i * 17) * 1_000_003) % len(scales)
        out.append({"index": i, "cx": round(x, 8), "cy": round(y, 8), "scale": float(scales[selector])})
    return out


def uniform_random_trajectory(seed: str, count: int, scales: list[float]) -> list[dict]:
    """Deterministic uniform spatial baseline matched to the same scale ladder."""
    raw = sha256_bytes(seed)
    rng = np.random.default_rng(int.from_bytes(raw[:8], "big"))
    out = []
    for i in range(count):
        out.append({
            "index": i,
            "cx": round(float(rng.uniform(0.04, 0.96)), 8),
            "cy": round(float(rng.uniform(0.04, 0.96)), 8),
            "scale": float(scales[int(rng.integers(0, len(scales)))]),
        })
    return out


def crop_window(image: np.ndarray, window: dict) -> np.ndarray:
    h, w = image.shape[:2]
    side = max(32, int(round(min(h, w) * float(window["scale"]))))
    side = min(side, h, w)
    cx = int(round(float(window["cx"]) * (w - 1)))
    cy = int(round(float(window["cy"]) * (h - 1)))
    x0 = max(0, min(w - side, cx - side // 2))
    y0 = max(0, min(h - side, cy - side // 2))
    return image[y0:y0 + side, x0:x0 + side]


def block_shuffle(image: np.ndarray, seed: str, block: int = 48) -> np.ndarray:
    """Preserve local texture tiles while disrupting global arrangement."""
    h, w = image.shape[:2]
    ph = int(math.ceil(h / block) * block)
    pw = int(math.ceil(w / block) * block)
    padded = cv2.copyMakeBorder(image, 0, ph - h, 0, pw - w, cv2.BORDER_REFLECT)
    tiles = [
        padded[y:y + block, x:x + block].copy()
        for y in range(0, ph, block)
        for x in range(0, pw, block)
    ]
    raw = sha256_bytes(seed)
    rng = np.random.default_rng(int.from_bytes(raw[:8], "big"))
    rng.shuffle(tiles)
    out = np.empty_like(padded)
    k = 0
    for y in range(0, ph, block):
        for x in range(0, pw, block):
            out[y:y + block, x:x + block] = tiles[k]
            k += 1
    return out[:h, :w]


def phase_scramble(image: np.ndarray, seed: str) -> np.ndarray:
    """Fourier-amplitude-preserving grayscale null with randomized spatial phase."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    spec = np.fft.rfft2(gray)
    amp = np.abs(spec)
    raw = sha256_bytes(seed)
    rng = np.random.default_rng(int.from_bytes(raw[:8], "big"))
    phases = rng.uniform(-math.pi, math.pi, size=spec.shape)
    randomized = amp * np.exp(1j * phases)
    randomized[0, 0] = spec[0, 0]
    out = np.fft.irfft2(randomized, s=gray.shape).real
    old_mean, old_std = float(gray.mean()), float(gray.std())
    new_mean, new_std = float(out.mean()), float(out.std())
    if new_std > 1e-12:
        out = (out - new_mean) * (old_std / new_std) + old_mean
    out = np.clip(out, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def resize_max(image: np.ndarray, max_dim: int = 1400) -> np.ndarray:
    h, w = image.shape[:2]
    s = min(1.0, max_dim / max(h, w))
    if s == 1.0:
        return image
    return cv2.resize(image, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def ocr_crop(crop: np.ndarray, min_conf: float) -> list[dict]:
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract binary not found")
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(6, 6)).apply(gray)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        p = Path(f.name)
    try:
        cv2.imwrite(str(p), gray)
        cmd = [
            "tesseract", str(p), "stdout", "--psm", "11", "-l", "eng", "tsv",
            "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-*/=^<>()[].{}:"
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=20)
        if r.returncode != 0:
            return []
        out = []
        for row in r.stdout.splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 12:
                continue
            try:
                conf = float(c[10])
            except ValueError:
                continue
            token = normalize_token(c[11])
            if conf < min_conf or not TOKEN_RE.fullmatch(token):
                continue
            out.append({"token": token, "class": classify_token(token), "confidence": round(conf, 2)})
        return out
    finally:
        p.unlink(missing_ok=True)


def structure_metrics(crop: np.ndarray) -> dict:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if min(gray.shape) > 320:
        s = 320 / min(gray.shape)
        gray = cv2.resize(gray, (max(1, round(gray.shape[1] * s)), max(1, round(gray.shape[0] * s))))
    edges = cv2.Canny(gray, 70, 150)
    edge_density = float((edges > 0).mean())
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180.0, threshold=35,
        minLineLength=max(12, min(gray.shape) // 8), maxLineGap=6,
    )
    line_count = 0 if lines is None else len(lines)
    left = gray[:, : gray.shape[1] // 2]
    right = gray[:, gray.shape[1] - left.shape[1]:]
    right = np.fliplr(right)
    symmetry = 0.0
    if left.size and left.std() > 0 and right.std() > 0:
        symmetry = float(np.corrcoef(left.ravel(), right.ravel())[0, 1])
    return {
        "edge_density": round(edge_density, 6),
        "line_count": int(line_count),
        "mirror_symmetry": round(symmetry, 6),
    }


def _summarize(rows: list[dict]) -> dict:
    return {
        key: round(float(median([r["metrics"][key] for r in rows])), 6)
        for key in ("edge_density", "line_count", "mirror_symmetry")
    }


def analyze_trajectory(
    image: np.ndarray,
    block_control: np.ndarray,
    phase_control: np.ndarray,
    trajectory: list[dict],
    min_conf: float,
) -> dict:
    result = {"real": [], "block_control": [], "phase_control": []}
    token_counts = {"real": Counter(), "block_control": Counter()}
    token_best_conf = {"real": defaultdict(float), "block_control": defaultdict(float)}

    for label, source in (("real", image), ("block_control", block_control)):
        for window in trajectory:
            crop = crop_window(source, window)
            metrics = structure_metrics(crop)
            tokens = ocr_crop(crop, min_conf)
            for t in tokens:
                token_counts[label][t["token"]] += 1
                token_best_conf[label][t["token"]] = max(token_best_conf[label][t["token"]], t["confidence"])
            result[label].append({"window": window, "metrics": metrics, "tokens": tokens})

    # Phase null is for image structure only; excluding OCR keeps semantic and
    # structural null hypotheses separate and avoids creating a second OCR fishing path.
    for window in trajectory:
        crop = crop_window(phase_control, window)
        result["phase_control"].append({"window": window, "metrics": structure_metrics(crop)})

    real_counts = token_counts["real"]
    ctrl_counts = token_counts["block_control"]
    escalated = []
    for token, count in real_counts.items():
        if len(token) < 3 or count < 2 or ctrl_counts[token] > 0:
            continue
        cls = classify_token(token)
        if cls not in {"WORD_LIKE", "FORMULA_LIKE", "CODE_LIKE"}:
            continue
        escalated.append({
            "token": token,
            "class": cls,
            "real_window_hits": count,
            "block_control_window_hits": 0,
            "best_confidence": round(token_best_conf["real"][token], 2),
            "status": "PLANNER_LOCAL_ESCALATION_ONLY_NOT_MESSAGE",
        })
    escalated.sort(key=lambda x: (-x["real_window_hits"], -x["best_confidence"], x["token"]))

    real_summary = _summarize(result["real"])
    block_summary = _summarize(result["block_control"])
    phase_summary = _summarize(result["phase_control"])
    delta_block = {key: round(real_summary[key] - block_summary[key], 6) for key in real_summary}
    delta_phase = {key: round(real_summary[key] - phase_summary[key], 6) for key in real_summary}

    return {
        "window_count": len(trajectory),
        "real_token_counts": dict(real_counts),
        "block_control_token_counts": dict(ctrl_counts),
        "planner_local_escalations": escalated,
        "planner_local_escalation_count": len(escalated),
        "median_structure_real": real_summary,
        "median_structure_block_control": block_summary,
        "median_structure_phase_control": phase_summary,
        "real_minus_block_control_structure": delta_block,
        "real_minus_phase_control_structure": delta_phase,
        "mirror_positive_against_both_nulls": bool(
            delta_block["mirror_symmetry"] > 0 and delta_phase["mirror_symmetry"] > 0
        ),
        "window_receipts": result,
    }


def analyze_image(image: np.ndarray, planners: dict[str, list[dict]], min_conf: float, control_seed: str) -> dict:
    image = resize_max(image)
    block_control = block_shuffle(image, control_seed + "::block")
    phase_control = phase_scramble(image, control_seed + "::phase")
    by_planner = {}
    candidate_planners = defaultdict(set)
    raw_real_planners = defaultdict(set)
    raw_control_planners = defaultdict(set)

    for name, trajectory in planners.items():
        r = analyze_trajectory(image, block_control, phase_control, trajectory, min_conf)
        by_planner[name] = r
        for token in r["real_token_counts"]:
            raw_real_planners[token].add(name)
        for token in r["block_control_token_counts"]:
            raw_control_planners[token].add(name)
        for c in r["planner_local_escalations"]:
            candidate_planners[c["token"]].add(name)

    cross_planner = []
    for token, names in sorted(candidate_planners.items()):
        if len(names) >= 2 and token not in raw_control_planners:
            cross_planner.append({
                "token": token,
                "class": classify_token(token),
                "planners": sorted(names),
                "planner_count": len(names),
                "status": "CROSS_PLANNER_ESCALATION_ONLY_NOT_MESSAGE",
            })

    raw_cross_planner = []
    for token, names in sorted(raw_real_planners.items()):
        if len(names) >= 2 and token not in raw_control_planners:
            raw_cross_planner.append({
                "token": token,
                "class": classify_token(token),
                "planners": sorted(names),
                "planner_count": len(names),
                "status": "RAW_CROSS_PLANNER_OCR_ONLY",
            })

    mirror_both = [name for name, r in by_planner.items() if r["mirror_positive_against_both_nulls"]]
    return {
        "planner_count": len(planners),
        "planners": by_planner,
        "raw_cross_planner_ocr": raw_cross_planner,
        "raw_cross_planner_ocr_count": len(raw_cross_planner),
        "cross_planner_escalation_candidates": cross_planner,
        "cross_planner_escalation_count": len(cross_planner),
        "mirror_positive_against_both_nulls_planners": sorted(mirror_both),
        "mirror_positive_against_both_nulls_count": len(mirror_both),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-ocr-confidence", type=float, default=55.0)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    cfg = manifest["trajectory"]
    count = int(cfg["window_count"])
    scales = [float(x) for x in cfg["scale_ladder"]]
    seed = cfg["seed"]

    recovered, recovered_receipt = fga.all_trajectories(seed, count, scales)
    planners = {
        "logistic_baseline": logistic_trajectory(seed + "::logistic", count, scales),
        "uniform_random_baseline": uniform_random_trajectory(seed + "::uniform", count, scales),
        **recovered,
    }
    planner_hashes = {
        name: hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        for name, rows in planners.items()
    }

    report = {
        "schema": "genesis.janus_cristal_fractalgpt.result.v3",
        "trajectory_system": {
            **cfg,
            "planner_count": len(planners),
            "planner_hashes": planner_hashes,
            "content_independent": True,
            "recovered_fractalgpt": recovered_receipt,
        },
        "null_models": {
            "semantic_and_structure": "DETERMINISTIC_48PX_BLOCK_SHUFFLE",
            "structure_only": "FOURIER_AMPLITUDE_PRESERVING_PHASE_SCRAMBLE"
        },
        "sources": [],
        "cross_modality_escalation_candidates": [],
        "semantic_admission": "NO_MESSAGE_FORMULA_CODE_OR_ALGORITHM_ADMITTED",
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    per_source_candidates = defaultdict(set)
    source_by_id = {}
    errors = 0

    with tempfile.TemporaryDirectory(prefix="genesis-fractal-crystal-") as td:
        td = Path(td)
        for i, source in enumerate(manifest["sources"]):
            entry = {k: v for k, v in source.items() if k != "download_url"}
            try:
                path = td / f"source_{i}.img"
                fetch(source["download_url"], path)
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    raise RuntimeError("image decode failed")
                entry["sha256"] = sha256_file(path)
                entry["dimensions"] = [int(image.shape[1]), int(image.shape[0])]
                entry["analysis"] = analyze_image(
                    image,
                    planners,
                    args.min_ocr_confidence,
                    control_seed=f"{seed}::{source['id']}",
                )
                for c in entry["analysis"]["cross_planner_escalation_candidates"]:
                    per_source_candidates[c["token"]].add(source["id"])
                entry["status"] = "ANALYZED"
            except Exception as exc:
                errors += 1
                entry["status"] = "ERROR"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            report["sources"].append(entry)
            source_by_id[entry["id"]] = entry

    cross = []
    for token, ids in sorted(per_source_candidates.items()):
        modalities = sorted({source_by_id[i].get("modality") for i in ids})
        if len(modalities) >= 2:
            cross.append({
                "token": token,
                "source_ids": sorted(ids),
                "modalities": modalities,
                "status": "CROSS_MODALITY_AND_CROSS_PLANNER_ESCALATION_REPLICATION_REQUIRED",
            })
    report["cross_modality_escalation_candidates"] = cross
    report["cross_modality_escalation_count"] = len(cross)

    mirror_consensus = []
    for source in report["sources"]:
        if source.get("status") != "ANALYZED":
            continue
        a = source["analysis"]
        count_pos = a["mirror_positive_against_both_nulls_count"]
        mirror_consensus.append({
            "source_id": source["id"],
            "material": source.get("material"),
            "role": source.get("role"),
            "positive_planners": count_pos,
            "planner_count": len(planners),
            "all_planners_positive": count_pos == len(planners),
        })
    report["mirror_structure_dual_null_consensus"] = mirror_consensus

    groups = defaultdict(list)
    for source in report["sources"]:
        if source.get("same_specimen_group") and source.get("status") == "ANALYZED":
            groups[source["same_specimen_group"]].append(source)
    structural_pairs = []
    for group, rows in groups.items():
        if len(rows) < 2:
            continue
        planner_rows = []
        for planner in planners:
            vals = []
            for src in rows:
                pr = src["analysis"]["planners"][planner]
                vals.append({
                    "source_id": src["id"],
                    "modality": src["modality"],
                    "real_minus_block": pr["real_minus_block_control_structure"],
                    "real_minus_phase": pr["real_minus_phase_control_structure"],
                })
            planner_rows.append({"planner": planner, "modalities": vals})
        structural_pairs.append({"same_specimen_group": group, "planner_deltas": planner_rows})
    report["same_specimen_structural_comparisons"] = structural_pairs

    report["claim_ceiling"] = (
        "Recovered FractalGPT and baseline planners can choose deterministic search paths; conventional detectors can compare real images with two matched nulls. "
        "No result establishes intentional encoding, a message, formula, code, algorithm, intelligence, supernatural cause, or intrinsic crystal material property."
    )

    result_path = out_dir / "GENESIS-JANUS-CRISTAL-FRACTALGPT-result.json"
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Janus Cristal × recovered FractalGPT CI receipt",
        "",
        f"Sources: {len(report['sources']) - errors}/{len(report['sources'])} analyzed; errors={errors}",
        f"Planners: {len(planners)} × {count} windows each",
        f"Original-library FractalGPT SHA-256: `{fga.ORIGINAL_LIBRARY_SHA256}`",
        f"Executed vendored FractalGPT SHA-256: `{fga.VENDORED_SOURCE_SHA256}`",
        f"Recovered model initial/final eval MSE: `{recovered_receipt['model_receipt']['initial_eval_mse']}` → `{recovered_receipt['model_receipt']['final_eval_mse']}`",
        "",
        "| source | modality | raw cross-planner OCR | strict cross-planner escalations | mirror + vs both nulls |",
        "|---|---|---:|---:|---:|",
    ]
    for s in report["sources"]:
        a = s.get("analysis", {})
        lines.append(
            f"| {s['id']} | {s.get('modality')} | {a.get('raw_cross_planner_ocr_count', 'error')} | {a.get('cross_planner_escalation_count', 'error')} | {a.get('mirror_positive_against_both_nulls_count', 'error')}/{len(planners)} |"
        )
    lines += [
        "",
        f"Cross-modality + cross-planner escalation candidates: **{len(cross)}**",
        "",
        "`NO_MESSAGE_FORMULA_CODE_OR_ALGORITHM_ADMITTED`",
    ]
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
