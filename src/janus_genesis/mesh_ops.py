from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import trimesh

SUPPORTED_SUFFIXES = {".stl", ".obj", ".ply"}


@dataclass(slots=True)
class MeshMetrics:
    vertices: int
    faces: int
    watertight: bool
    winding_consistent: bool
    volume_mm3: float | None
    area_mm2: float
    extents_mm: list[float]
    bounds_mm: list[list[float]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def discover_models(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise ValueError(f"Модель не содержит геометрии: {path}")
        mesh = loaded.to_geometry()
        if isinstance(mesh, trimesh.Scene):
            mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    else:
        mesh = loaded
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Неподдерживаемый тип геометрии: {type(mesh)!r}")
    if mesh.is_empty:
        raise ValueError(f"Пустая модель: {path}")
    return mesh


def metrics(mesh: trimesh.Trimesh) -> MeshMetrics:
    volume = float(abs(mesh.volume)) if mesh.is_watertight else None
    return MeshMetrics(
        vertices=len(mesh.vertices),
        faces=len(mesh.faces),
        watertight=bool(mesh.is_watertight),
        winding_consistent=bool(mesh.is_winding_consistent),
        volume_mm3=volume,
        area_mm2=float(mesh.area),
        extents_mm=[float(value) for value in mesh.extents],
        bounds_mm=[[float(value) for value in row] for row in mesh.bounds],
    )


def conservative_repair(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    repaired = mesh.copy()
    repaired.process(validate=True)
    trimesh.repair.fix_normals(repaired, multibody=True)
    trimesh.repair.fix_inversion(repaired, multibody=True)
    repaired.remove_unreferenced_vertices()
    return repaired


def _orientation_transforms() -> list[tuple[str, np.ndarray]]:
    half_turn = np.pi
    quarter_turn = np.pi / 2.0
    euler = trimesh.transformations.euler_matrix
    return [
        ("original", np.eye(4)),
        ("x+90", euler(quarter_turn, 0.0, 0.0)),
        ("x-90", euler(-quarter_turn, 0.0, 0.0)),
        ("x180", euler(half_turn, 0.0, 0.0)),
        ("y+90", euler(0.0, quarter_turn, 0.0)),
        ("y-90", euler(0.0, -quarter_turn, 0.0)),
    ]


def _place_on_bed(mesh: trimesh.Trimesh) -> None:
    z_shift = -float(mesh.bounds[0, 2])
    mesh.apply_translation([0.0, 0.0, z_shift])


def orientation_score(mesh: trimesh.Trimesh, max_overhang_deg: float) -> dict[str, float]:
    # Эвристика foundation-этапа, не замена слайсеру.
    downward_limit = -float(np.sin(np.radians(max_overhang_deg)))
    support_mask = mesh.face_normals[:, 2] < downward_limit
    support_area = float(mesh.area_faces[support_mask].sum())
    height = float(mesh.extents[2])
    footprint = float(mesh.extents[0] * mesh.extents[1])
    score = support_area + height * 0.25 - footprint * 0.0005
    return {
        "score": score,
        "estimated_support_area_mm2": support_area,
        "height_mm": height,
        "footprint_mm2": footprint,
    }


def choose_orientation(
    mesh: trimesh.Trimesh,
    max_overhang_deg: float,
) -> tuple[trimesh.Trimesh, dict[str, object]]:
    ranked: list[tuple[float, str, trimesh.Trimesh, dict[str, float]]] = []
    for name, transform in _orientation_transforms():
        candidate = mesh.copy()
        candidate.apply_transform(transform)
        _place_on_bed(candidate)
        result = orientation_score(candidate, max_overhang_deg)
        ranked.append((result["score"], name, candidate, result))
    ranked.sort(key=lambda item: item[0])
    _, name, best, result = ranked[0]
    report: dict[str, object] = {"selected": name, **result}
    report["candidates"] = [
        {"name": candidate_name, **candidate_result}
        for _, candidate_name, _, candidate_result in ranked
    ]
    return best, report
