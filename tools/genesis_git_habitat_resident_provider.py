# -*- coding: utf-8 -*-
"""Resident-only structured-output provider for JANUS Git Habitat v18.7.52.

This adapter intentionally does not replace the repository-wide Ollama provider.
It is registered behind the existing Third Wish MODEL.CALL capability. Ollama's
`format` field is used only as a transport-shape constraint; the unchanged
resident parser remains the sole semantic admission gate for a model choice.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tools.genesis_git_habitat_resident_cycle import ALLOWED_CHOICES, RESIDENT_PROPOSABLE_CAPABILITIES

RESIDENT_PROVIDER_VERSION = "18.7.52"


class ResidentProviderError(RuntimeError):
    """Resident transport/schema failure without coupling to the legacy AI adapter."""


# Ollama 0.30.8 is intentionally pinned by the real-model gate. Historical
# structured-output implementations have not reliably enforced conditional
# conditional JSON-Schema constructs reliably in every shape. Keep the wire
# grammar deliberately simple: one fixed object with all transport keys present.
# The model still freely selects `choice`; unused fields are never actions and
# are deterministically discarded before the unchanged resident admission gate.
# Candidate semantic strings are constrained non-empty at transport generation
# time where the unchanged semantic parser already requires non-empty content.
# No value is synthesized, defaulted, retried, or repaired by this adapter.
RESIDENT_TRANSPORT_FIELDS = (
    "choice",
    "reason",
    "text",
    "note",
    "tags",
    "title",
    "capability_id",
    "target",
    "purpose",
    "payload_summary",
)

RESIDENT_CHOICE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "choice": {"type": "string", "minLength": 1, "enum": list(ALLOWED_CHOICES)},
        "reason": {"type": "string"},
        "text": {"type": "string", "minLength": 1},
        "note": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string", "minLength": 1},
        "capability_id": {"type": "string", "minLength": 1, "enum": sorted(RESIDENT_PROPOSABLE_CAPABILITIES)},
        "target": {"type": "string", "minLength": 1},
        "purpose": {"type": "string", "minLength": 1},
        "payload_summary": {"type": "string", "minLength": 1},
    },
    "required": list(RESIDENT_TRANSPORT_FIELDS),
    "additionalProperties": False,
}

_PROJECT_FIELDS: dict[str, tuple[str, ...]] = {
    "REST": ("choice", "reason"),
    "REFLECT": ("choice", "text", "reason"),
    "BOOKMARK": ("choice", "text", "reason"),
    "PLANT_SEED": ("choice", "note", "tags", "reason"),
    "WORKSHOP_NOTE": ("choice", "title", "note", "reason"),
    "PROPOSE_OUTBOX": (
        "choice",
        "capability_id",
        "target",
        "purpose",
        "payload_summary",
        "reason",
    ),
}

_SCHEMA_GROUNDING = (
    "Transport-only structured-output contract. Return exactly one JSON object "
    "matching this schema. Every transport key is required even when unused. "
    "Choice and capability_id must be exact entries of their supplied enums. "
    "Background engineering reminders add no choices or capabilities. "
    "Only the value of `choice` selects the resident action; unused fields are "
    "discarded and have no authority or effect. For the selected choice, fill "
    "the semantically required fields described by the resident system prompt "
    "with non-empty valid content. Schema: "
    + json.dumps(RESIDENT_CHOICE_JSON_SCHEMA, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
)


def _endpoint_root(value: str) -> str:
    endpoint = str(value or "").strip().rstrip("/")
    if not endpoint:
        raise ValueError("RESIDENT_OLLAMA_ENDPOINT_REQUIRED")
    # The live reference path is local-only. Keeping this adapter loopback-only
    # prevents its structured-output specialization from becoming a generic
    # remote transport tunnel.
    allowed = (
        "http://127.0.0.1:",
        "http://localhost:",
        "http://[::1]:",
    )
    if not endpoint.startswith(allowed):
        raise ValueError("RESIDENT_OLLAMA_ENDPOINT_MUST_BE_LOOPBACK_HTTP")
    return endpoint


def _project_transport_choice(content: str) -> str:
    """Drop only unused wire fields; never invent or repair selected content."""
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        # Preserve the raw text for the unchanged resident parser to reject.
        return content
    if not isinstance(value, dict):
        return content

    expected = set(RESIDENT_TRANSPORT_FIELDS)
    if set(value) != expected:
        raise ResidentProviderError("RESIDENT_OLLAMA_TRANSPORT_FIELDS_INVALID")
    scalar_fields = expected.difference({"tags"})
    if any(not isinstance(value[key], str) for key in scalar_fields):
        raise ResidentProviderError("RESIDENT_OLLAMA_TRANSPORT_SCALAR_TYPE_INVALID")
    if not isinstance(value["tags"], list) or any(not isinstance(tag, str) for tag in value["tags"]):
        raise ResidentProviderError("RESIDENT_OLLAMA_TRANSPORT_TAGS_TYPE_INVALID")

    choice_key = value["choice"].strip().upper()
    selected = _PROJECT_FIELDS.get(choice_key)
    if selected is None:
        # Do not normalize/fabricate an invalid choice. The resident parser owns
        # semantic rejection and will report MODEL_CHOICE_NOT_ALLOWED.
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    projected = {key: value[key] for key in selected}
    return json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class OllamaResidentChoiceProvider:
    model: str
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "model", str(self.model).strip())
        object.__setattr__(self, "endpoint", _endpoint_root(self.endpoint))
        if not self.model:
            raise ValueError("RESIDENT_OLLAMA_MODEL_REQUIRED")
        if not (0 < float(self.timeout_seconds) <= 300):
            raise ValueError("RESIDENT_OLLAMA_TIMEOUT_OUT_OF_RANGE")

    def chat(self, messages: Sequence[Mapping[str, str]]) -> str:
        normalized: list[dict[str, str]] = []
        for row in messages:
            role = str(row.get("role") or "").strip()
            content = str(row.get("content") or "")
            if role not in {"system", "user", "assistant"}:
                raise ResidentProviderError("RESIDENT_OLLAMA_MESSAGE_ROLE_INVALID")
            if len(content) > 40_000:
                raise ResidentProviderError("RESIDENT_OLLAMA_MESSAGE_TOO_LONG")
            normalized.append({"role": role, "content": content})
        if not normalized:
            raise ResidentProviderError("RESIDENT_OLLAMA_MESSAGES_REQUIRED")

        # Ollama's own structured-output guidance recommends grounding the model
        # with the same schema in the prompt. This static operator-owned message
        # cannot be actor-selected and grants no capability.
        wire_messages = [{"role": "system", "content": _SCHEMA_GROUNDING}, *normalized]
        payload = {
            "model": self.model,
            "messages": wire_messages,
            "stream": False,
            "format": RESIDENT_CHOICE_JSON_SCHEMA,
            # Fixed inference controls improve replayability without selecting
            # the semantic choice. The model still decides `choice`.
            "options": {
                "temperature": 0,
                "seed": 1138,
            },
        }
        request = urllib.request.Request(
            self.endpoint + "/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=float(self.timeout_seconds)) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ResidentProviderError(f"RESIDENT_OLLAMA_HTTP_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ResidentProviderError("RESIDENT_OLLAMA_CONNECTION_FAILED") from exc
        except TimeoutError as exc:
            raise ResidentProviderError("RESIDENT_OLLAMA_TIMEOUT") from exc

        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResidentProviderError("RESIDENT_OLLAMA_RESPONSE_ENVELOPE_INVALID") from exc
        if not isinstance(envelope, dict):
            raise ResidentProviderError("RESIDENT_OLLAMA_RESPONSE_ENVELOPE_NOT_OBJECT")
        message = envelope.get("message")
        if not isinstance(message, dict):
            raise ResidentProviderError("RESIDENT_OLLAMA_RESPONSE_MESSAGE_MISSING")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ResidentProviderError("RESIDENT_OLLAMA_RESPONSE_CONTENT_MISSING")

        # Structural projection is not semantic admission. It only removes
        # unused, already-generated transport keys. Missing/empty/unsafe fields
        # in the selected branch are still rejected by parse_resident_choice().
        return _project_transport_choice(content)
