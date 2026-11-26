from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PrinterProfile:
    name: str = "Bambu Lab A1"
    nozzle_mm: float = 0.4
    layer_height_mm: float = 0.2
    min_wall_mm: float = 1.2
    max_overhang_deg: float = 45.0
    build_volume_mm: list[float] = field(default_factory=lambda: [256.0, 256.0, 256.0])


@dataclass(slots=True)
class MaterialProfile:
    name: str = "Generic PLA"
    density_g_cm3: float = 1.24
    elastic_modulus_mpa: float = 3000.0
    tensile_strength_mpa: float = 50.0
    poisson_ratio: float = 0.36
    calibrated: bool = False


@dataclass(slots=True)
class TransformPolicy:
    repair_mesh: bool = True
    auto_orient: bool = True
    preserve_scale: bool = True
    export_format: str = "stl"


@dataclass(slots=True)
class JanusConfig:
    printer: PrinterProfile = field(default_factory=PrinterProfile)
    material: MaterialProfile = field(default_factory=MaterialProfile)
    transform: TransformPolicy = field(default_factory=TransformPolicy)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> JanusConfig:
        return cls(
            printer=PrinterProfile(**raw.get("printer", {})),
            material=MaterialProfile(**raw.get("material", {})),
            transform=TransformPolicy(**raw.get("transform", {})),
        )

    @classmethod
    def load(cls, path: Path) -> JanusConfig:
        with path.open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, ensure_ascii=False, indent=2)
