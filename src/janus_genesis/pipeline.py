from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from janus_genesis.config import JanusConfig
from janus_genesis.mesh_ops import (
    choose_orientation,
    conservative_repair,
    discover_models,
    load_mesh,
    metrics,
)


def analyze_model(path: Path, config: JanusConfig) -> dict[str, object]:
    mesh = load_mesh(path)
    return {
        "schema_version": "0.1",
        "source": str(path),
        "printer": asdict(config.printer),
        "material": asdict(config.material),
        "metrics": metrics(mesh).to_dict(),
    }


def transform_model(
    source: Path,
    output_dir: Path,
    report_dir: Path,
    config: JanusConfig,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    original = load_mesh(source)
    original_metrics = metrics(original)
    candidate = conservative_repair(original) if config.transform.repair_mesh else original.copy()

    orientation: dict[str, object] = {"selected": "original", "enabled": False}
    if config.transform.auto_orient:
        candidate, orientation = choose_orientation(
            candidate,
            max_overhang_deg=config.printer.max_overhang_deg,
        )
        orientation["enabled"] = True

    candidate_metrics = metrics(candidate)
    suffix = config.transform.export_format.lower().lstrip(".")
    output_path = output_dir / f"{source.stem}__janus_candidate.{suffix}"
    candidate.export(output_path)

    report: dict[str, object] = {
        "schema_version": "0.1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "claim_level": "mesh_repair_and_orientation_only",
        "source": str(source),
        "output": str(output_path),
        "printer": asdict(config.printer),
        "material": asdict(config.material),
        "transform": asdict(config.transform),
        "original": original_metrics.to_dict(),
        "candidate": candidate_metrics.to_dict(),
        "orientation": orientation,
        "warnings": [
            "FEA and topology optimization are not active in Foundation MVP.",
            "This candidate has no certified strength advantage over the source model.",
        ],
    }

    report_path = report_dir / f"{source.stem}__janus_report.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    report["report"] = str(report_path)
    return report


def run_workspace(
    input_dir: Path,
    output_dir: Path,
    report_dir: Path,
    config: JanusConfig,
) -> list[dict[str, object]]:
    models = discover_models(input_dir)
    return [transform_model(path, output_dir, report_dir, config) for path in models]
