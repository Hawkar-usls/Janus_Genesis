# -*- coding: utf-8 -*-
"""Typed source-pin contract for JANUS Nexus / SWARM integration.

The central rule is intentionally strict: a value's *shape* never determines
its semantics. A 40-hex string tagged as OPAQUE_VERSION_TOKEN remains opaque;
only an explicitly tagged GIT_COMMIT_SHA1 may satisfy exact Git replay.

This module is transport-neutral and performs no repository acquisition,
source mutation, execution, or write-back.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

PINSET_SCHEMA = "janus.source_pin_set.v1"
PUBLIC_PROJECTION_SCHEMA = "janus.source_pin_set.public_projection.v1"
GIT_COMMIT_SHA1 = "GIT_COMMIT_SHA1"
OPAQUE_VERSION_TOKEN = "OPAQUE_VERSION_TOKEN"
ALLOWED_PIN_KINDS = frozenset({GIT_COMMIT_SHA1, OPAQUE_VERSION_TOKEN})
ALLOWED_VISIBILITY = frozenset({"public", "private"})
ALLOWED_SOURCE_KINDS = frozenset({"GIT_REPOSITORY", "OPAQUE_RESOURCE"})
PINSET_FIELDS = frozenset({"schema", "pinset_id", "sources"})
SOURCE_FIELDS = frozenset({"source_id", "visibility", "source_kind", "pin"})
PIN_FIELDS = frozenset({"kind", "value"})
SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,239}$")
PRIVATE_SOURCE_ID = re.compile(r"^[0-9]{1,32}$")
FULL_GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")
OPAQUE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@=-]{0,255}$")


class SourcePinContractError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_pin(pin: Any) -> dict[str, str]:
    if not isinstance(pin, dict) or set(pin) != PIN_FIELDS:
        raise SourcePinContractError("SOURCE_PIN_FIELDS_INVALID")
    kind = pin.get("kind")
    value = pin.get("value")
    if kind not in ALLOWED_PIN_KINDS or not isinstance(value, str):
        raise SourcePinContractError("SOURCE_PIN_KIND_OR_VALUE_INVALID")
    if kind == GIT_COMMIT_SHA1:
        if not FULL_GIT_SHA1.fullmatch(value):
            raise SourcePinContractError("GIT_COMMIT_SHA1_MUST_BE_LOWERCASE_40_HEX")
    elif not OPAQUE_TOKEN.fullmatch(value):
        raise SourcePinContractError("OPAQUE_VERSION_TOKEN_INVALID")
    return {"kind": kind, "value": value}


def validate_pinset(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PINSET_FIELDS:
        raise SourcePinContractError("SOURCE_PINSET_FIELDS_INVALID")
    if value.get("schema") != PINSET_SCHEMA:
        raise SourcePinContractError("SOURCE_PINSET_SCHEMA_INVALID")
    pinset_id = value.get("pinset_id")
    if not isinstance(pinset_id, str) or not 1 <= len(pinset_id) <= 200:
        raise SourcePinContractError("SOURCE_PINSET_ID_INVALID")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourcePinContractError("SOURCE_PINSET_SOURCES_REQUIRED")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in sources:
        if not isinstance(row, dict) or set(row) != SOURCE_FIELDS:
            raise SourcePinContractError("SOURCE_PIN_ROW_FIELDS_INVALID")
        source_id = row.get("source_id")
        visibility = row.get("visibility")
        source_kind = row.get("source_kind")
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            raise SourcePinContractError("SOURCE_PIN_SOURCE_ID_INVALID")
        if ".." in source_id:
            raise SourcePinContractError("SOURCE_PIN_SOURCE_ID_TRAVERSAL_REJECTED")
        if source_id in seen:
            raise SourcePinContractError("SOURCE_PIN_SOURCE_ID_DUPLICATE")
        if visibility not in ALLOWED_VISIBILITY:
            raise SourcePinContractError("SOURCE_PIN_VISIBILITY_INVALID")
        if visibility == "private" and not PRIVATE_SOURCE_ID.fullmatch(source_id):
            raise SourcePinContractError("PRIVATE_SOURCE_ID_MUST_BE_OPAQUE_NUMERIC")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise SourcePinContractError("SOURCE_PIN_SOURCE_KIND_INVALID")
        normalized.append(
            {
                "source_id": source_id,
                "visibility": visibility,
                "source_kind": source_kind,
                "pin": _validate_pin(row.get("pin")),
            }
        )
        seen.add(source_id)

    normalized.sort(key=lambda row: row["source_id"])
    return {
        "schema": PINSET_SCHEMA,
        "pinset_id": pinset_id,
        "sources": normalized,
    }


def pinset_digest(value: Any) -> str:
    """Local canonical digest. Do not publish if private exact pins are present."""
    return canonical_digest(validate_pinset(value))


def require_exact_git_replay(value: Any) -> dict[str, Any]:
    """Require every source to be explicitly typed as an exact Git commit pin."""
    normalized = validate_pinset(value)
    for row in normalized["sources"]:
        if row["source_kind"] != "GIT_REPOSITORY":
            raise SourcePinContractError(
                f"EXACT_GIT_REPLAY_SOURCE_KIND_INVALID:{row['source_id']}"
            )
        if row["pin"]["kind"] != GIT_COMMIT_SHA1:
            raise SourcePinContractError(
                f"EXACT_GIT_REPLAY_REQUIRES_GIT_COMMIT_SHA1:{row['source_id']}"
            )
    return normalized


def adapt_legacy_source_pins(
    source_pins: Mapping[str, str],
    *,
    pin_kind: str,
    source_kind: str,
    visibility_by_source: Mapping[str, str],
    pinset_id: str,
) -> dict[str, Any]:
    """Adapt legacy SWARM ``source_pins`` only with explicit semantics.

    ``pin_kind`` and ``source_kind`` are mandatory. The adapter never guesses
    them from the values, even when every value happens to look like a Git SHA.
    Visibility must also be supplied for every source so private rows cannot be
    accidentally projected as public.
    """
    if pin_kind not in ALLOWED_PIN_KINDS:
        raise SourcePinContractError("LEGACY_ADAPTER_PIN_KIND_REQUIRED")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise SourcePinContractError("LEGACY_ADAPTER_SOURCE_KIND_REQUIRED")
    if not isinstance(source_pins, Mapping) or not source_pins:
        raise SourcePinContractError("LEGACY_ADAPTER_SOURCE_PINS_REQUIRED")
    if set(source_pins) != set(visibility_by_source):
        raise SourcePinContractError("LEGACY_ADAPTER_VISIBILITY_SET_MISMATCH")

    candidate = {
        "schema": PINSET_SCHEMA,
        "pinset_id": pinset_id,
        "sources": [
            {
                "source_id": str(source_id),
                "visibility": visibility_by_source[source_id],
                "source_kind": source_kind,
                "pin": {"kind": pin_kind, "value": str(pin_value)},
            }
            for source_id, pin_value in source_pins.items()
        ],
    }
    return validate_pinset(candidate)


def public_projection(value: Any) -> dict[str, Any]:
    """Project a validated local pinset without exposing private pin values.

    The projection intentionally omits both the whole-pinset digest and the
    local ``pinset_id``. Either could become an accidental public fingerprint
    or carry caller-supplied private naming metadata.
    """
    normalized = validate_pinset(value)
    projected: list[dict[str, Any]] = []
    for row in normalized["sources"]:
        base = {
            "source_id": row["source_id"],
            "visibility": row["visibility"],
            "source_kind": row["source_kind"],
            "pin_kind": row["pin"]["kind"],
        }
        if row["visibility"] == "public":
            base["pin_value"] = row["pin"]["value"]
        else:
            base["pin_value_public"] = False
            base["local_pin_validated"] = True
            base["exact_git_replay_eligible_locally"] = (
                row["source_kind"] == "GIT_REPOSITORY"
                and row["pin"]["kind"] == GIT_COMMIT_SHA1
            )
        projected.append(base)
    return {
        "schema": PUBLIC_PROJECTION_SCHEMA,
        "source_count": len(projected),
        "local_pinset_id_published": False,
        "private_pin_values_published": False,
        "whole_pinset_digest_published": False,
        "sources": projected,
    }


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JANUS typed source-pin contract v1")
    parser.add_argument("path")
    parser.add_argument("command", choices=("validate", "exact-git", "public-project"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    value = _read_json(args.path)
    if args.command == "validate":
        result = validate_pinset(value)
    elif args.command == "exact-git":
        result = require_exact_git_replay(value)
    else:
        result = public_projection(value)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
