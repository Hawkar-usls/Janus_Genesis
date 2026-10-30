# -*- coding: utf-8 -*-
"""AST drift canary for JANUS Armor effect-capable Python surfaces at v18.7.51.

v18.7.51 adds the Shabitat ↔ Aura local subprocess bridge. The bridge is
classified separately because it performs a selected direct process primitive,
but its tests must independently establish Armor-before-process ordering.
Classification alone never means admission or safety.

A separately checked-out Aura repository used by cross-repository CI is excluded
from the JANUS source inventory. Aura has its own repository CI and boundary
contract; vendored/foreign checkout contents must not be silently reclassified
as JANUS production surfaces.
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
    ("janus_genesis.py", "LEGACY_ROOT_GEMINI_NARRATOR_EGRESS"),
    (
        "tools/janus_nexus_cloud_acquire_v2.py",
        "EXPLICIT_DISPATCH_ONLY_READ_ONLY_CLOUD_SOURCE_ACQUISITION_NOT_ARMOR_ADMITTED",
    ),
    (
        "tools/janus_nexus_materializer_v2.py",
        "TRUSTED_CLOUD_INERT_GIT_SOURCE_MATERIALIZATION_NOT_ARMOR_ADMITTED",
    ),
    (
        "tools/janus_nexus_native_model_cloud_witness_v1.py",
        "READ_ONLY_SOURCE_PINNED_NATIVE_MODEL_PROVENANCE_WITNESS_NOT_ARMOR_ADMITTED",
    ),
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
    (
        "tools/janus_corpus_aura_oracle.py",
        "EXPLICIT_OPT_IN_PINNED_LOCAL_AURA_HEURISTIC_SUBPROCESS_NOT_ARMOR_ADMITTED",
    ),
    (
        "tools/janus_corpus_callosum.py",
        "EXPLICIT_OPT_IN_PINNED_NATIVE_MODEL_SUBPROCESS_NOT_ARMOR_ADMITTED",
    ),
    (
        "tools/janus_corpus_git_publisher.py",
        "EXPLICIT_OPERATOR_NONFORCE_GIT_HOME_RECEIPT_PUBLISHER_NOT_ARMOR_ADMITTED",
    ),
    (
        "tools/genesis_beetle_memory_bridge.py",
        "READ_ONLY_FIXED_PUBLIC_BEETLE_PRODUCER_MANIFEST_FETCH",
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
    "aura-oracle-tg/*",
    "tools/audit_armor_effect_drift_v18_7_50.py",
    "tools/audit_armor_effect_drift_v18_7_51.py",
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
            rows.append({
                "path": rel,
                "line": int(getattr(node, "lineno", 0)),
                "call": name,
                "classification": label,
                "classified": label is not None,
            })
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
        entry = by_path.setdefault(path, {
            "classification": row["classification"],
            "calls": [],
        })
        entry["calls"].append(str(row["call"]))  # type: ignore[union-attr]

    surfaces = {
        path: {
            "classification": entry["classification"],
            "calls": sorted(set(entry["calls"])),  # type: ignore[arg-type]
        }
        for path, entry in sorted(by_path.items())
    }
    migration_debt = sorted(
        path for path, entry in surfaces.items()
        if str(entry["classification"]).startswith("LEGACY_")
    )
    shabitat = surfaces.get("genesis_v18_7_51_shabitat_aura_oracle.py", {})
    report = {
        "schema": "janus.genesis.armor.effect_surface_drift.v1_2",
        "runtime_version": "18.7.51",
        "detected_surface_count": len(surfaces),
        "classified_surface_count": len(surfaces) - len({str(row["path"]) for row in unclassified}),
        "unclassified_surface_count": len({str(row["path"]) for row in unclassified}),
        "surfaces": surfaces,
        "shabitat_aura_surface_classified": (
            shabitat.get("classification") == "ARMOR_GATED_LOCAL_SHABITAT_AURA_HEURISTIC_BRIDGE"
        ),
        "foreign_ci_checkout_excluded": "aura-oracle-tg/*",
        "legacy_migration_debt": migration_debt,
        "unclassified": unclassified,
        "classification_is_security_certification": False,
        "classified_surface_is_armored_by_classification_alone": False,
        "repository_wide_complete_routing_coverage_proven": False,
        "claim_ceiling": (
            "This AST canary inventories selected direct network/process primitives in JANUS source. "
            "The Shabitat Aura subprocess is explicitly classified, but only executable tests can "
            "establish Armor-before-process ordering for the reference bridge. A separately checked-out "
            "Aura repository is outside this JANUS inventory and is validated by its own CI plus the "
            "cross-repository contract smoke. The canary does not prove absence of dynamic/native effects "
            "or repository-wide unbypassability."
        ),
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
