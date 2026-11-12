#!/usr/bin/env python3
"""ESSENCE gene-bank v0.2: offline, provenance-bound JANUS JSON archaeology.

This is reference learning / proposal formation, NOT gradient training, remote
code loading, production authority, or a proof of scientific generalization.
Only allowlisted JSON fields are extracted. Model outputs remain untrusted data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import kernel

SCHEMA = "janus.essence.gene_bank/0.2"
MAX_FILE_BYTES = 300_000
MAX_TOTAL_BYTES = 1_400_000
GATES = ("SOURCE_HASH", "LICENSE_AND_DEPENDENCIES", "STATIC_REVIEW",
         "ISOLATED_TEST", "FROZEN_BASELINE", "INDEPENDENT_VERIFICATION",
         "PR_REVIEW", "BOUNDED_CANARY", "ROLLBACK")
SRC = (
    ("registry", "data/JANUS-ESSENCE-REPOSITORY-MICROKERNEL-GENOME-RESEARCH-2026-11-12-v1.json"),
    ("registry", "data/JANUS-NEURAL-KOMBUCHA-HISTORICAL-TRANSFORMER-SOURCES-2026-11-12.json"),
    ("registry", "data/JANUS-COOLING-TOWER-LEGACY-MICROKERNEL-LINEAGE-2026-11-12.json"),
    ("archive", "audits/JANUS_GPT_MODEL_ZOO_ARCHAEOLOGY_2026-08-25.json"),
    ("archive", "audits/JANUS_GPT_MICROMODEL_FAMILY_LINEAGE_2026-08-25.json"),
    ("archive", "audits/JANUS_JGPT_TRI_BRAIN_GEX_LINEAGE_2026-08-25.json"),
    ("archive", "audits/JANUS_SPIRAL_ARCHAEOLOGY_PASS2_AIENGINE_GEX_TRIUMVIRATE_YAKSA_JGPT_HOLOGPT_2026-08-25.json"),
)
GENE_ROLES = {
    "autodiff_attention": ("sensing", "coding"),
    "adaptive_quantization": ("coding", "recovery"),
    "tri_brain_disagreement": ("planning", "verification"),
    "memory_checkpoint": ("memory", "recovery"),
    "multiscale_forecast": ("sensing", "planning"),
    "bounded_hard_example_replay": ("memory", "recovery"),
    "gradient_guard": ("recovery", "verification"),
    "routing_proposals": ("planning",),
    "verification_and_provenance": ("memory", "verification"),
}
# Mappings are explicitly reviewed design analogies, not source-code imports.
MODEL_GENE = {
    "MicroGPT": "autodiff_attention",
    "MicroGPTSlime": "adaptive_quantization",
    "MicroGPTSlime_quantized": "adaptive_quantization",
    "All_starsGPT": "memory_checkpoint",
    "CatGPT": "memory_checkpoint",
    "FractalGPT": "multiscale_forecast",
    "JGPT1": "tri_brain_disagreement",
    "NonceMapGPT": "verification_and_provenance",
    "LightGPT": "multiscale_forecast",
    "WaterGPT": "multiscale_forecast",
    "AtomGPT": "multiscale_forecast",
    "VacuumGPT": "multiscale_forecast",
    "SHA256-GPT": "verification_and_provenance",
    "IR_GPT_PhysicsLab": "verification_and_provenance",
    "PIP-BOY GPT": "tri_brain_disagreement",
    "Physarious Movement Tachyon GPT v2": "routing_proposals",
    "HoloGPT": "multiscale_forecast",
    "HoloGPT_TEST2": "multiscale_forecast",
    "Yaksa+12": "gradient_guard",
    "Physarum": "routing_proposals",
    "GEX": "gradient_guard",
    "Trinity": "tri_brain_disagreement",
}
EXTERNAL_KNOWN = {
    "karpathy/micrograd": "MIT",
    "karpathy/nanoGPT": "MIT",
    "TheAlgorithms/Python": "MIT",
    "huggingface/transformers": "Apache-2.0",
}
SHA = re.compile(r"^[a-f0-9]{64}$")
REF = re.compile(r"^[a-f0-9]{40}$")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_bounded(root, relative):
    root = Path(root).resolve(strict=True)
    target = root / relative
    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved.suffix != ".json" or target.is_symlink():
        raise ValueError("UNSAFE_JSON_PATH")
    raw = resolved.read_bytes()
    if not 2 <= len(raw) <= MAX_FILE_BYTES:
        raise ValueError("BOUNDED_JSON_REQUIRED")
    obj = json.loads(raw.decode("utf-8"),
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    if not isinstance(obj, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return obj, sha(raw), len(raw)


def normalized_model(label):
    if not isinstance(label, str) or len(label) > 120:
        return None
    if label in MODEL_GENE:
        return label
    # Model name aliases in archived filenames, not arbitrary string similarity.
    for prefix in ("JGPT1", "MicroGPTSlime_quantized", "MicroGPTSlime",
                   "MicroGPT", "CatGPT", "FractalGPT", "All_starsGPT",
                   "NonceMapGPT", "VacuumGPT", "HoloGPT_TEST2", "HoloGPT"):
        if label == prefix + ".py" or label.startswith(prefix + "("):
            return prefix
    return None


def extract_evidence(path, obj):
    """Allowlist structured declarations; never repeat raw narrative or private paths."""
    evidence = set()
    if path.endswith("GENOME-RESEARCH-2026-11-12-v1.json"):
        for item in obj.get("gene_candidates", [])[:64]:
            if isinstance(item, dict) and item.get("gene") in GENE_ROLES:
                evidence.add((item["gene"], "genome_design", None))
    if path.endswith("HISTORICAL-TRANSFORMER-SOURCES-2026-11-12.json"):
        for item in obj.get("selected_patterns", [])[:64]:
            if isinstance(item, dict):
                name = normalized_model(item.get("source"))
                if name:
                    evidence.add((MODEL_GENE[name], name, None))
    if path.endswith("JANUS_GPT_MODEL_ZOO_ARCHAEOLOGY_2026-08-25.json"):
        records = (obj.get("core_lineage", []) + obj.get("hash_bound_model_zoo", []))
        for item in records[:80]:
            if isinstance(item, dict):
                name = normalized_model(item.get("name"))
                content_sha = item.get("sha256")
                if name and isinstance(content_sha, str) and SHA.fullmatch(content_sha):
                    evidence.add((MODEL_GENE[name], name, content_sha))
    if path.endswith("JANUS_GPT_MICROMODEL_FAMILY_LINEAGE_2026-08-25.json"):
        for item in obj.get("members", [])[:80]:
            if isinstance(item, dict):
                name = normalized_model(item.get("name"))
                content_sha = item.get("sha256")
                if name and isinstance(content_sha, str) and SHA.fullmatch(content_sha):
                    evidence.add((MODEL_GENE[name], name, content_sha))
    if path.endswith("JANUS_JGPT_TRI_BRAIN_GEX_LINEAGE_2026-08-25.json"):
        for item in obj.get("content_identities", [])[:80]:
            if isinstance(item, dict):
                label = item.get("source") or next(iter(item.get("source_aliases") or []), None)
                name = normalized_model(label)
                content_sha = item.get("sha256")
                if name and isinstance(content_sha, str) and SHA.fullmatch(content_sha):
                    evidence.add((MODEL_GENE[name], name, content_sha))
    return evidence


def validate_external_catalog(obj):
    if not isinstance(obj, dict) or obj.get("schema") != "janus.essence.legal_sources/0.1":
        raise ValueError("EXTERNAL_CATALOG_SCHEMA")
    out = []
    items = obj.get("repositories")
    if not isinstance(items, list) or not 1 <= len(items) <= 12:
        raise ValueError("EXTERNAL_CATALOG_SIZE")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("EXTERNAL_SOURCE_INVALID")
        repo, license_id = item.get("repository"), item.get("observed_spdx")
        if repo in seen or not isinstance(repo, str):
            raise ValueError("EXTERNAL_SOURCE_DUPLICATE")
        seen.add(repo)
        match = EXTERNAL_KNOWN.get(repo) == license_id
        if item.get("auto_fetch_code") is not False or item.get("auto_import_code") is not False:
            raise ValueError("UNTRUSTED_EXECUTION_REQUEST")
        out.append({"repository": repo if repo in EXTERNAL_KNOWN else "UNKNOWN_SOURCE",
                    "observed_spdx": license_id if license_id in ("MIT", "Apache-2.0") else "UNKNOWN",
                    "status": "METADATA_MATCH_REVIEW_REQUIRED" if match else "LICENSE_HOLD",
                    "code_reused": False, "attribution_and_dependency_review_required": True})
    return out


def evaluate(manifest, registry_root, archive_root, catalog, *,
             registry_sha, archive_sha, expected_repo):
    kernel.validate_manifest(manifest, expected_repo=expected_repo)
    if not REF.fullmatch(registry_sha) or not REF.fullmatch(archive_sha):
        raise ValueError("UNPINNED_SOURCE_REF")
    external = validate_external_catalog(catalog)
    inputs = []
    all_evidence = set()
    missing = []
    total = 0
    for kind, relative in SRC:
        root = registry_root if kind == "registry" else archive_root
        try:
            obj, blob_sha, byte_count = load_bounded(root, relative)
            total += byte_count
            if total > MAX_TOTAL_BYTES:
                raise ValueError("TOTAL_ARCHIVE_LIMIT")
            all_evidence.update(extract_evidence(relative, obj))
            inputs.append({"origin": kind, "relative_path": relative,
                           "commit_sha": registry_sha if kind == "registry" else archive_sha,
                           "raw_sha256": blob_sha, "bytes": byte_count})
        except (FileNotFoundError, OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
            missing.append({"origin": kind, "relative_path": relative,
                            "error": type(exc).__name__})
    candidate_sources = {}
    for gene, donor, raw_sha in sorted(all_evidence, key=lambda r:(r[0],r[1],r[2] or "")):
        row = candidate_sources.setdefault(gene, {"models": set(), "source_hashes": set()})
        row["models"].add(donor)
        if raw_sha:
            row["source_hashes"].add(raw_sha)
    proposal_items = []
    for cell in manifest["microkernels"]:
        roles = cell["role"]
        for gene in sorted(candidate_sources):
            if roles in GENE_ROLES[gene]:
                data = candidate_sources[gene]
                proposal_items.append({
                    "microkernel_id": cell["id"], "role": roles, "gene": gene,
                    "donor_models": sorted(data["models"])[:14],
                    "distinct_historical_source_hashes": len(data["source_hashes"]),
                    "state": "PROPOSED_ONLY", "action_authority": False,
                    "requires": list(GATES),
                })
    critical = {SRC[0][1], SRC[3][1]}
    observed = {x["relative_path"] for x in inputs}
    gate = "RESEARCH_READY_PROPOSAL_ONLY" if critical.issubset(observed) and not missing else "HOLD_INCOMPLETE_ARCHIVE"
    result = {
        "schema": SCHEMA, "repository": manifest["repository"],
        "manifest_sha256": kernel.digest(manifest),
        "archive_inventory": inputs, "missing_sources": missing,
        "historical_gene_count": len(candidate_sources),
        "candidate_genes": sorted(candidate_sources),
        "proposals": proposal_items[:80],
        "external_repository_license_review": external,
        "gate": gate,
        "weights_updated": False,
        "real_world_learning_verified": False,
        "historical_learning_kind": "EVIDENCE_EXTRACTION_AND_CANDIDATE_PRIORITIZATION_ONLY",
        "raw_external_code_executed": False,
        "raw_external_code_downloaded": False,
        "self_installation": False,
        "production_promotion": False,
        "security_rights_changed": False,
        "privacy_note": "Raw archive fields, operational paths and secrets not emitted.",
    }
    result["report_sha256"] = sha(canonical(result))
    return result


def verify(result):
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise ValueError("REPORT_SCHEMA")
    stamp = result.get("report_sha256")
    if stamp != sha(canonical({k:v for k,v in result.items() if k != "report_sha256"})):
        raise ValueError("REPORT_DIGEST")
    if any(result.get(k) is not False for k in ("weights_updated","raw_external_code_executed",
           "raw_external_code_downloaded","self_installation","production_promotion",
           "security_rights_changed","real_world_learning_verified")):
        raise ValueError("AUTHORITY_ESCALATION")
    if any(p.get("state") != "PROPOSED_ONLY" or p.get("action_authority") is not False
           for p in result.get("proposals", [])):
        raise ValueError("ACTIVE_CHILD_FORBIDDEN")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--registry-root")
    ap.add_argument("--archive-root")
    ap.add_argument("--catalog")
    ap.add_argument("--registry-sha")
    ap.add_argument("--archive-sha")
    ap.add_argument("--expected-repo")
    ap.add_argument("--out")
    ap.add_argument("--verify")
    a = ap.parse_args()
    if a.verify:
        obj = kernel.load_json(a.verify)
        print(json.dumps({"verified": verify(obj)}))
        return
    for key in ("manifest", "registry_root", "archive_root", "catalog",
                "registry_sha", "archive_sha", "expected_repo", "out"):
        if not getattr(a, key):
            ap.error("missing --" + key.replace("_", "-"))
    manifest = kernel.load_json(a.manifest)
    catalog = kernel.load_json(a.catalog)
    report = evaluate(manifest, a.registry_root, a.archive_root, catalog,
                      registry_sha=a.registry_sha, archive_sha=a.archive_sha,
                      expected_repo=a.expected_repo)
    verify(report)
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"gate":report["gate"], "archive_sources":len(report["archive_inventory"]),
                      "candidate_genes":report["historical_gene_count"],
                      "proposals":len(report["proposals"])}, sort_keys=True))


if __name__ == "__main__":
    main()
