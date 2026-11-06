"""Bounded, reproducible digital SCOBY/PLA skin coupon study (not material validation)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

SCHEMA = "janus.genesis.scoby_pla_skin.digital_prototype.v1"
SOURCE_BRIDGE = (
    "https://github.com/Hawkar-usls/janus-meta-registry/blob/main/data/"
    "JANUS-STARLI-F41-SCOBY-PLA-SKINGPT-PHYSICAL-VALIDATION-BRIDGE-2026-11-06-v1.0.json"
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _triangle(a, b, c):
    u = tuple(b[k] - a[k] for k in range(3))
    v = tuple(c[k] - a[k] for k in range(3))
    normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(x * x for x in normal))
    if length == 0:
        raise ValueError("degenerate mesh triangle")
    return struct.pack("<12fH", *(x / length for x in normal), *a, *b, *c, 0)


def _quad(a, b, c, d):
    return (_triangle(a, b, c), _triangle(a, c, d))


def occupancy(size_mm: int, pitch_mm: int, width_mm: float, pixel_mm: float = 0.5):
    if not 30 <= size_mm <= 100 or size_mm % pitch_mm != 0:
        raise ValueError("coupon size must be 30..100 mm and divisible by pitch")
    if not 5 <= pitch_mm <= 20 or not 1.0 <= width_mm <= 2.5 or width_mm >= pitch_mm / 2:
        raise ValueError("invalid bounded lattice dimensions")
    if size_mm / pixel_mm != int(size_mm / pixel_mm):
        raise ValueError("voxel pitch must divide coupon size exactly")
    n = int(size_mm / pixel_mm)
    rows = []
    for j in range(n):
        y = (j + 0.5) * pixel_mm
        row = []
        for i in range(n):
            x = (i + 0.5) * pixel_mm
            gx = min(x % pitch_mm, pitch_mm - x % pitch_mm)
            gy = min(y % pitch_mm, pitch_mm - y % pitch_mm)
            edge = min(x, y, size_mm - x, size_mm - y)
            row.append(edge <= width_mm or gx <= width_mm / 2 or gy <= width_mm / 2)
        rows.append(row)
    return rows


def write_stl(path: Path, occupancy_map: list[list[bool]], pixel_mm: float, height_mm: float) -> int:
    if not 1.0 <= height_mm <= 3.0:
        raise ValueError("height must be 1..3 mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(occupancy_map)
    if any(len(row) != n for row in occupancy_map):
        raise ValueError("non-square occupancy map")
    count = 0
    with path.open("wb") as f:
        f.write(b"JANUS SCOBY PLA GRID; NOT STRENGTH CERTIFIED".ljust(80, b" "))
        f.write(b"\x00" * 4)
        for j, row in enumerate(occupancy_map):
            for i, present in enumerate(row):
                if not present:
                    continue
                x, y, s, h = i * pixel_mm, j * pixel_mm, pixel_mm, height_mm
                z0, z1 = 0.0, h
                quads = [
                    ((x,y,z1),(x+s,y,z1),(x+s,y+s,z1),(x,y+s,z1)),
                    ((x,y,z0),(x,y+s,z0),(x+s,y+s,z0),(x+s,y,z0)),
                ]
                if i == 0 or not row[i - 1]:
                    quads.append(((x,y,z0),(x,y,z1),(x,y+s,z1),(x,y+s,z0)))
                if i == n - 1 or not row[i + 1]:
                    quads.append(((x+s,y,z0),(x+s,y+s,z0),(x+s,y+s,z1),(x+s,y,z1)))
                if j == 0 or not occupancy_map[j - 1][i]:
                    quads.append(((x,y,z0),(x+s,y,z0),(x+s,y,z1),(x,y,z1)))
                if j == n - 1 or not occupancy_map[j + 1][i]:
                    quads.append(((x,y+s,z0),(x,y+s,z1),(x+s,y+s,z1),(x+s,y+s,z0)))
                for quad in quads:
                    for t in _quad(*quad):
                        f.write(t)
                        count += 1
        f.seek(80)
        f.write(struct.pack("<I", count))
    return count


def _manifest_digest(path: Path | None) -> dict:
    if path is None:
        return {"state": "NO_PHYSICAL_SKINGPT_SESSION_PROVIDED", "measured_frames": 0}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "skingpt.session_manifest.v0.3"
            or manifest.get("claim_ceiling") != "PROVENANCE_ONLY_NOT_PHYSICAL_VALIDATION"
            or manifest.get("hash_semantics") != "SHA256_IS_INTEGRITY_NOT_TRUTH"):
        raise ValueError("invalid or unsupported SkinGPT v0.3 manifest")
    source = manifest.get("source_log", {})
    digest = source.get("sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("missing source-log SHA-256")
    return {"state": "MANIFEST_REFERENCE_ONLY_NOT_VERIFIED_RAW_FRAMES", "manifest_sha256": _hash(path), "raw_log_declared_sha256": digest, "measured_frames": None}


def _svg(path: Path, size: int, pitch: int, width: float) -> None:
    scale = 6
    a = size * scale
    bars = []
    for t in range(0, size + 1, pitch):
        xy = t * scale
        bars.append(f'<rect x="{xy-width*scale/2:.1f}" y="0" width="{width*scale:.1f}" height="{a}" fill="#657d91"/>')
        bars.append(f'<rect x="0" y="{xy-width*scale/2:.1f}" width="{a}" height="{width*scale:.1f}" fill="#657d91"/>')
    # Exactly eight NTC reference zones; coordinates are not actual installed sensors.
    sensors = [(size * (k + 0.5) / 4, size * (0.25 if k < 4 else 0.75)) for k in range(4) for _ in (0,)]
    sensors += [(size * (k + 0.5) / 4, size * 0.75) for k in range(4)]
    glyphs = []
    for k, (x, y) in enumerate(sensors):
        glyphs.append(f'<circle cx="{x*scale:.1f}" cy="{y*scale:.1f}" r="9" fill="none" stroke="#be5c39" stroke-width="2"/>')
        glyphs.append(f'<text x="{x*scale:.1f}" y="{y*scale+3:.1f}" text-anchor="middle" font-size="8" fill="#be5c39">T{k+1}</text>')
    x = y = a/2
    glyphs.append(f'<circle cx="{x}" cy="{y}" r="12" fill="none" stroke="#225c3d" stroke-width="3"/>')
    glyphs.append(f'<text x="{x}" y="{y+4}" text-anchor="middle" font-size="8" fill="#225c3d">PZ</text>')
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{a}" height="{a}" viewBox="0 0 {a} {a}">\n'
                    f'<rect width="{a}" height="{a}" fill="#e9e2cd"/>\n'
                    f'<g opacity="0.78">{"".join(bars)}</g>\n'
                    f'<rect width="{a}" height="{a}" fill="#79b6a4" opacity="0.17"/>\n'
                    f'{"".join(glyphs)}\n</svg>\n', encoding="utf-8")


def generate(out_dir: Path, size_mm: int = 70, pitch_mm: int = 10,
             width_mm: float = 1.5, thickness_mm: float = 1.8,
             manifest_path: Path | None = None) -> dict:
    if size_mm % pitch_mm:
        raise ValueError("size must be divisible by pitch")
    pixel = 0.5
    occupied = occupancy(size_mm, pitch_mm, width_mm, pixel)
    out_dir.mkdir(parents=True, exist_ok=True)
    stl = out_dir / "B_rigid_pla_lattice_control.stl"
    svg = out_dir / "BC_skin_and_SkinGPT_concept.svg"
    faces = write_stl(stl, occupied, pixel, thickness_mm)
    _svg(svg, size_mm, pitch_mm, width_mm)
    pixels = sum(sum(row) for row in occupied)
    area = size_mm * size_mm
    occupied_area = pixels * pixel * pixel
    report = {
        "schema": SCHEMA,
        "mode": "DETERMINISTIC_GEOMETRY_ONLY_NO_FEA_NO_BIOLOGICAL_MODEL",
        "validation_level": "GEOMETRY_CREATED_NOT_PRINT_OR_PHYSICS_QUALIFIED",
        "inputs": {"size_mm":size_mm,"pitch_mm":pitch_mm,"strut_mm":width_mm,"height_mm":thickness_mm,"voxel_resolution_mm":pixel},
        "digital_prototype": {"arm":"B_BC_PLUS_RIGID_PLA_LATTICE", "actual_generated_physical_material":"NONE", "stl":stl.name,"stl_sha256":_hash(stl),"triangle_count":faces,"preview_svg":svg.name,"preview_sha256":_hash(svg),"preview_represents":"hypothetical BC drape and eight notional NTC zone footprints plus one piezo, not a manufactured sensor array"},
        "geometric_predictions": {"occupied_area_mm2":occupied_area,"open_area_fraction":round(1-occupied_area/area,6),"nominal_pla_scaffold_volume_mm3":round(occupied_area*thickness_mm,3),"source":"exact rasterized design geometry, NOT measured mass or material strength", "uncertainty":"voxel-resolution discretization, no slicer or fabrication calibration"},
        "biological_forecasts": {"BC_growth_rate":None,"BC_PLA_bond_strength_MPa":None,"wet_dry_strength_retention":None,"articulated_chainmail_locks":None,"status":"UNKNOWN_REQUIRES_BLINDED_PHYSICAL_COUPONS"},
        "sensing_forecasts": {"SkinGPT_severe_fault_recall":None,"impact_localization_mm":None,"humidity_response":None,"status":"NO_REALISED_COMPOSITE_SENSOR_DATA", "sensor_baseline":"SkinGPT v0.3 8x NTC / 1x piezo, rule_based_heuristic_not_probability"},
        "skinGPT_reference":_manifest_digest(manifest_path),
        "blocked_arms": {"C_BC_PLUS_ARTICULATED_PLA_FABRIC":"NOT_GENERATED_WITHOUT_LICENSE_CLEARED_INTERLOCKED_SOURCE_STL_AND_CLEARANCE_CHECK", "A_BC_ONLY":"PHYSICAL_SAMPLE_REQUIRED", "D_ARTICULATED_PLA_ONLY":"SAME_SOURCE_STL_REQUIRED", "E_POST_ASSEMBLED_BC_PLA":"PHYSICAL_SAMPLE_REQUIRED"},
        "requirements_before_print":["slicer review with Bambu A1 nozzle and layer profile","ensure clean connected/manifold part with independent mesh check","mechanical fit and print orientation tests","PLA filament batch/additives identified"],
        "requirements_before_claim":["independent BC identity and nonfood culture controls","blind wet/dry adhesion and cyclic flexion measurements","independent true labels for SkinGPT; humidity drift compensation","no body armor, human protective or medical claim"],
        "source_bridge":SOURCE_BRIDGE,
        "append_only":True,
    }
    (out_dir / "predictions.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate non-qualified digital SCOBY/PLA skin study coupon")
    parser.add_argument("--out",type=Path,default=Path("prototype_out"))
    parser.add_argument("--size",type=int,default=70)
    parser.add_argument("--pitch",type=int,default=10)
    parser.add_argument("--strut",type=float,default=1.5)
    parser.add_argument("--thickness",type=float,default=1.8)
    parser.add_argument("--skingpt-manifest",type=Path)
    args=parser.parse_args(argv)
    result=generate(args.out,args.size,args.pitch,args.strut,args.thickness,args.skingpt_manifest)
    print(json.dumps({"result":"DIGITAL_GEOMETRY_CREATED","out":str(args.out),"open_area_fraction":result["geometric_predictions"]["open_area_fraction"],"material_validation":"NOT_PERFORMED"}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
