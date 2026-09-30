#!/usr/bin/env python3
"""Adapter that uses the recovered user FractalGPT as a search-path generator.

The recovered FractalGPT is not used as a semantic oracle. It only proposes
content-independent multiscale image coordinates. Conventional OCR/CV metrics
then measure those windows, and the exact same windows are applied to matched
negative controls.

Two byte identities are kept deliberately separate:
- ORIGINAL_LIBRARY_SHA256 binds the original prior file recovered from the user's library.
- VENDORED_SOURCE_SHA256 binds the GitHub text mirror used by CI.
The connector text serialization produced a different byte stream, so CI never
pretends the mirror is byte-identical to the original library object.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import random
from pathlib import Path
from typing import List

import numpy as np

HERE = Path(__file__).resolve().parent
RECOVERED_PATH = HERE / "recovered" / "FractalGPT.py"
ORIGINAL_LIBRARY_SHA256 = "11e6c97ae7169a0fae4e0ad17f2fb7fb23b10265b04b4b057e3c968d6d0a3662"
VENDORED_SOURCE_SHA256 = "1dfc5bb1dabcb256d569de30dbe4431f6901c8dcddbe15fb76634fd57d9146e8"
# Compatibility name now always refers to the bytes actually executed in CI.
RECOVERED_SHA256 = VENDORED_SOURCE_SHA256


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_recovered_module():
    got = _sha256_file(RECOVERED_PATH)
    if got != VENDORED_SOURCE_SHA256:
        raise RuntimeError(f"Vendored FractalGPT SHA-256 mismatch: {got}")
    spec = importlib.util.spec_from_file_location("recovered_fractalgpt", RECOVERED_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load recovered FractalGPT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_int(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")


def _normalize_states(states: list[list[float]], count: int, scales: List[float]) -> list[dict]:
    """Map arbitrary FractalGPT x/y state ranges to stable normalized image ROIs."""
    finite = []
    for s in states:
        if len(s) < 2:
            continue
        x, y = float(s[0]), float(s[1])
        if math.isfinite(x) and math.isfinite(y):
            phase = float(s[2]) if len(s) > 2 and math.isfinite(float(s[2])) else 0.0
            latent_scale = float(s[3]) if len(s) > 3 and math.isfinite(float(s[3])) else 0.0
            finite.append((x, y, phase, latent_scale))
    if not finite:
        return []

    xs = [r[0] for r in finite]
    ys = [r[1] for r in finite]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = max(1e-9, xmax - xmin)
    dy = max(1e-9, ymax - ymin)

    if len(finite) == 1:
        idxs = [0] * count
    else:
        idxs = np.linspace(0, len(finite) - 1, count, dtype=int).tolist()

    out = []
    for j, idx in enumerate(idxs):
        x, y, phase, latent_scale = finite[idx]
        cx = 0.06 + 0.88 * ((x - xmin) / dx)
        cy = 0.06 + 0.88 * ((y - ymin) / dy)
        key = int(abs(phase) * 1000.0 + abs(latent_scale) * 100.0 + j * 17)
        out.append({
            "index": j,
            "cx": round(float(cx), 8),
            "cy": round(float(cy), 8),
            "scale": float(scales[key % len(scales)]),
        })
    return out


def koch_trajectory(seed: str, count: int, scales: List[float]) -> list[dict]:
    del seed
    m = load_recovered_module()
    states = m.FractalGPT.koch_curve(iterations=4, step_size=2.0)
    return _normalize_states(states, count, scales)


def sierpinski_trajectory(seed: str, count: int, scales: List[float]) -> list[dict]:
    m = load_recovered_module()
    random.seed(_seed_int(seed) & 0xFFFFFFFF)
    np.random.seed(_seed_int(seed + "::np") & 0xFFFFFFFF)
    states = m.FractalGPT.sierpinski_triangle(iterations=4, size=2.0)
    return _normalize_states(states, count, scales)


def fbm_trajectory(seed: str, count: int, scales: List[float]) -> list[dict]:
    m = load_recovered_module()
    random.seed(_seed_int(seed) & 0xFFFFFFFF)
    np.random.seed(_seed_int(seed + "::fbm") & 0xFFFFFFFF)
    raw = m.FractalGPT.fractal_brownian_motion(steps=220, hurst=0.8, scale=0.18)
    # Original states are [x, 0, value, hurst, 0]. Promote value to y so the
    # 1-D fractal series becomes a 2-D content-independent scan trajectory.
    states = [[s[0], s[2], s[3], s[4], 0.0] for s in raw]
    return _normalize_states(states, count, scales)


def model_trajectory(seed: str, count: int, scales: List[float]) -> tuple[list[dict], dict]:
    """Actually train/run a tiny instance of the recovered autoregressive model."""
    m = load_recovered_module()
    py_seed = _seed_int(seed) & 0xFFFFFFFF
    np_seed = _seed_int(seed + "::model") & 0xFFFFFFFF
    random.seed(py_seed)
    np.random.seed(np_seed)

    model = m.FractalGPT(state_dim=5, n_layer=1, n_embd=8, block_size=16, n_head=2)
    train = []
    for iterations in (2, 3):
        seq = m.FractalGPT.koch_curve(iterations=iterations, step_size=2.0)
        for i in range(0, max(0, len(seq) - 16), 8):
            train.append(seq[i:i + 16])

    random.seed(py_seed)
    initial_loss = model.evaluate(train[:4])
    losses = []
    for _ in range(8):
        seq = random.choice(train)
        losses.append(model.train_step(seq, lr=0.0005))
    final_loss = model.evaluate(train[:4])

    np.random.seed(np_seed)
    generated = model.generate([0.0, 0.0, 0.0, 0.1, 0.0], max_len=max(40, count * 2), temperature=0.015)
    trajectory = _normalize_states(generated, count, scales)
    receipt = {
        "implementation": "RECOVERED_FRACTALGPT_MICRO_AUTOREGRESSIVE_MODEL",
        "original_library_sha256": ORIGINAL_LIBRARY_SHA256,
        "executed_vendored_sha256": VENDORED_SOURCE_SHA256,
        "python_seed": py_seed,
        "numpy_seed": np_seed,
        "train_sequence_count": len(train),
        "train_steps": 8,
        "initial_eval_mse": round(float(initial_loss), 8),
        "final_eval_mse": round(float(final_loss), 8),
        "last_train_loss": round(float(losses[-1]), 8) if losses else None,
        "generated_state_count": len(generated),
    }
    return trajectory, receipt


def all_trajectories(seed: str, count: int, scales: List[float]) -> tuple[dict[str, list[dict]], dict]:
    model_path, model_receipt = model_trajectory(seed + "::model", count, scales)
    trajectories = {
        "fractalgpt_koch": koch_trajectory(seed + "::koch", count, scales),
        "fractalgpt_sierpinski": sierpinski_trajectory(seed + "::sierpinski", count, scales),
        "fractalgpt_fbm": fbm_trajectory(seed + "::fbm", count, scales),
        "fractalgpt_model": model_path,
    }
    hashes = {
        name: hashlib.sha256(str(rows).encode("utf-8")).hexdigest()
        for name, rows in trajectories.items()
    }
    return trajectories, {
        "original_library_sha256": ORIGINAL_LIBRARY_SHA256,
        "executed_vendored_sha256": VENDORED_SOURCE_SHA256,
        "trajectory_hashes": hashes,
        "model_receipt": model_receipt,
    }
