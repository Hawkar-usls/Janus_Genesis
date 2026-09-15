# -*- coding: utf-8 -*-
"""AST drift canary for JANUS Armor effect-capable Python surfaces.

This is a source-level inventory guard, not a sandbox. It detects direct use of
selected network/process primitives and requires every containing file to have
an explicit semantic classification. A newly introduced direct effect surface
therefore fails CI until reviewed.

Classification is deliberately NOT admission. A file may be classified as a
legacy unarmored adapter, evaluation harness, simulation or archived origin and
still remain outside canonical Armor coverage.
"""
from __future__ import annotations

import ast
import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DIRECT_EFFECT_CALLS = {
    "urllib.request.urlopen",
    "http.client.HTTPConnection",
    "http.client.HTTPSConnection",
    "socket.socket",
    "socket.create_connection",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.system",
    "os.popen",
}

# Ordered most-specific first. Classification != Armor admission.
SURFACE_CLASSIFICATIONS = (
    (
        "ops/live_nas_intent_sovereignty_v1_2/deploy_live_nas.py",
        "EXPLICIT_OPERATOR_LIVE_NAS_DEPLOYMENT_TOOL",
    ),
    (
        "genesis_v18_7_51_shabitat_aura_oracle.py",
        "ARMOR_GATED_LOCAL_SHABITAT_AURA_HEURISTIC_BRIDGE",
    ),
    ("genesis_v18_7_ai.py", "LEGACY_DIRECT_PROVIDER_EGRESS"),
    ("genesis_v18_7_network.py", "LEGACY_DIRECT_NETWORK_ADAPTER"),
    ("genesis_v18_7_38_durable_network_outbox.py", "LEGACY_DURABLE_NETWORK_ADAPTER"),
    ("genesis_v18_7_51_shabitat_aura_oracle.py", "ARMOR_GATED_LOCAL_ORACLE_SUBPROCESS"),
    ("janus_genesis.py", "LEGACY_ROOT_GEMINI_NARRATOR_EGRESS"),
    ("tools/janus_habitat_process_death_gauntlet_v1.py", "CONTROLLED_FRESH_PROCESS_DEATH_GAUNTLET"),
    (
        "tools/janus_handoff_reliability_reference_gauntlet.py",
        "CONTROLLED_HANDOFF_RELIABILITY_FAILURE_INJECTION_GAUNTLET",
    ),
    (
        "tools/janus_receiver_identity_probe.py",
        "READ_ONLY_OPERATOR_LIVE_RECEIVER_IDENTITY_PROBE",
    ),
    (
        "tools/habitat_scout_agent.py",
        "CONSTRAINED_COPILOT_CLI_SCOUT_PROVIDER_BRIDGE",
    ),
    (
        "tools/trump_habitat_research_agent.py",
        "READ_ONLY_TRUMP_COPILOT_RESEARCH_HYPOTHESIS_BRIDGE",
    ),
    (
        "tools/janus_secret_persistence_guard.py",
        "SECURITY_SECRET_PERSISTENCE_INSPECTION_GUARD",
    ),
    (
        "tools/genesis_git_habitat_resident_provider.py",
        "LOOPBACK_ONLY_RESIDENT_MODEL_PROVIDER_BEHIND_MODEL_CALL",
    ),
    ("tools/genesis_third_wish_*.py", "THIRD_WISH_EFFECT_BROKER_ARMOR_SUBCLASS_COMPATIBLE"),
    ("tools/genesis_api_server.py", "LEGACY_LOCAL_MUTATION_SERVICE"),
    ("tools/genesis_hosted_gateway.py", "HOSTED_LOCAL_MUTATION_SERVICE"),
    ("tools/genesis_network_hub.py", "NETWORK_HUB_SERVICE"),
    ("tools/bootstrap_genesis_hosted.py", "HOSTED_BOOTSTRAP_PROCESS_WRAPPER"),
    ("tools/run_top100_round1_stratified.py", "EVALUATION_ONLY_PROVIDER_HARNESS"),
    ("experiments/*", "RESEARCH_EXPERIMENT"),
    ("gauntlet/*", "FROZEN_GAUNTLET_RESEARCH_ARTIFACT"),
    ("sim/*", "SIMULATION_RESEARCH_ARTIFACT"),
    ("origins/*", "ARCHIVED_ORIGIN_ARTIFACT"),
)

EXCLUDED_PATTERNS = (
    "tests/*",
    "test_*",
    "examples/*",
    "tools/audit_armor_effect_drift_v18_7_50.py",
)


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def excluded(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXCLUDED_PATTERNS)


def classification(path: str) -> str | None:
    for pattern, label in SURFACE_CLASSIFICATIONS:
        if fnmatch.fnmatch(path, pattern):
            return label
    return None


def scan(path: Path) -> list[dict[str, object]]:
    rel = path.relative_to(ROOT).as_posix()
    if excluded(rel):
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    label = classification(rel)
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        if name in DIRECT_EFFECT_CALLS:
            rows.append(
                {
                    "path": rel,
                    "line": int(getattr(node, "lineno", 0)),
                    "call": name,
                    "classification": label,
                    "classified": label is not None,
                }
            )
    return rows


def main() -> int:
    findings: list[dict[str, object]] = []
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        findings.extend(scan(path))

    unclassified = [row for row in findings if not row["classified"]]
    by_path: dict[str, dict[str, object]] = {}
    for row in findings:
        path = str(row["path"])
        entry = by_path.setdefault(
            path,
            {
                "classification": row["classification"],
                "calls": [],
            },
        )
        entry["calls"].append(str(row["call"]))  # type: ignore[union-attr]

    surfaces = {
        path: {
            "classification": entry["classification"],
            "calls": sorted(set(entry["calls"])),  # type: ignore[arg-type]
        }
        for path, entry in sorted(by_path.items())
    }
    migration_debt = sorted(
        path
        for path, entry in surfaces.items()
        if str(entry["classification"]).startswith("LEGACY_")
    )

    report = {
        "schema": "janus.genesis.armor.effect_surface_drift.v1_1",
        "runtime_version": "18.7.50",
        "detected_surface_count": len(surfaces),
        "classified_surface_count": len(surfaces) - len({str(row["path"]) for row in unclassified}),
        "unclassified_surface_count": len({str(row["path"]) for row in unclassified}),
        "surfaces": surfaces,
        "legacy_migration_debt": migration_debt,
        "unclassified": unclassified,
        "classification_is_security_certification": False,
        "classified_legacy_surface_is_armored_by_classification_alone": False,
        "research_or_archive_classification_grants_runtime_authority": False,
        "repository_wide_complete_routing_coverage_proven": False,
        "claim_ceiling": (
            "This AST canary detects selected direct network/process primitives and "
            "fails on newly unclassified Python files. Semantic classification is an "
            "inventory property only; it does not prove Armor admission, absence of "
            "dynamic/native effects, or repository-wide unbypassability."
        ),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
