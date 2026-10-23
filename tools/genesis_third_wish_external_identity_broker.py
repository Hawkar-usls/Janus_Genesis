# -*- coding: utf-8 -*-
"""JANUS Genesis v18.7.44 — Third Wish external identity-effect broker.

This layer makes four already-declared high-impact capabilities concrete without
turning operator identity or credentials into actor-owned secrets:

- PUBLICATION.PUBLISH
- EMAIL.SEND
- CALENDAR.WRITE
- BROKER.CREDENTIAL.USE

All four still rely on the frozen v18.7.40 core fresh-human-reauthorization gate.
The actor selects an operator-registered alias and typed payload. Endpoint,
authentication material, account identity and provider transport remain broker
custody. Every external effect has a durable request/effect identity so process
restart cannot silently duplicate a post, message, calendar event or scoped
credential-backed provider action.

A provider may reconcile EFFECT_ENTERING via lookup(effect_key): authoritative
SETTLED recovers the receipt, authoritative NO_EFFECT may reopen execution on a
new freshly reauthorized call, UNKNOWN/non-authoritative evidence remains
OUTCOME_UNDETERMINED.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from genesis_v18_7_35_windows_safe_durable_writer import WindowsSafeDurableJsonWriter
from genesis_v18_7_40_third_wish_capability_fabric import (
    ActionIntent,
    ThirdWishCapabilityFabric,
)
from janus_portable_lock_v2 import PortableProcessLockV2

EXTERNAL_IDENTITY_VERSION = "18.7.44"
IDENTITY_EFFECT_STORE_SCHEMA = "janus.genesis.third_wish.identity_effects.v1"
MAX_PUBLICATION_TITLE_BYTES = 1024
MAX_PUBLICATION_BODY_BYTES = 128 * 1024
MAX_EMAIL_ADDRESS_BYTES = 320
MAX_EMAIL_SUBJECT_BYTES = 2048
MAX_EMAIL_BODY_BYTES = 128 * 1024
MAX_CALENDAR_TEXT_BYTES = 16 * 1024
MAX_CALENDAR_ATTENDEES = 50
MAX_CREDENTIAL_PARAMETERS_BYTES = 32 * 1024


class ExternalIdentityError(RuntimeError):
    pass


class IdentityEffectRequestConflict(ExternalIdentityError):
    pass


class IdentityEffectOutcomeUndetermined(ExternalIdentityError):
    pass


class IdentityEffectReceiptIntegrityError(ExternalIdentityError):
    pass


class IdentityEffectProvider(Protocol):
    identity_alias: str
    provider_kind: str

    def preflight(
        self,
        *,
        effect_type: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def execute(
        self,
        *,
        effect_type: str,
        operation: str,
        payload: Mapping[str, Any],
        effect_key: str,
    ) -> Mapping[str, Any]: ...

    def lookup(self, effect_key: str) -> Mapping[str, Any]: ...


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json_size(value: Any) -> int:
    return len(_canonical(value).encode("utf-8"))


def _require(parameters: Mapping[str, Any], key: str) -> Any:
    if key not in parameters:
        raise ExternalIdentityError(f"MISSING_PARAMETER:{key}")
    return parameters[key]


_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _target_alias(target: str, prefix: str) -> str:
    marker = prefix + ":"
    value = str(target).strip()
    if not value.startswith(marker):
        raise ExternalIdentityError(f"TARGET_PREFIX_REQUIRED:{marker}")
    alias = value[len(marker):]
    if not _ALIAS_RE.fullmatch(alias):
        raise ExternalIdentityError("INVALID_IDENTITY_ALIAS")
    return alias


def _bounded_text(value: Any, *, name: str, max_bytes: int, allow_empty: bool = False) -> str:
    text = str(value)
    size = len(text.encode("utf-8"))
    if (not allow_empty and not text.strip()) or size > max_bytes:
        raise ExternalIdentityError(f"{name}_INVALID")
    return text


def _email_address(value: Any, *, name: str) -> str:
    text = _bounded_text(value, name=name, max_bytes=MAX_EMAIL_ADDRESS_BYTES)
    if not _EMAIL_RE.fullmatch(text):
        raise ExternalIdentityError(f"{name}_INVALID")
    return text


def _validate_publication_payload(parameters: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"title", "body", "content_format"}
    unknown = set(parameters).difference(allowed)
    if unknown:
        raise ExternalIdentityError(
            "PUBLICATION_PARAMETERS_NOT_ALLOWED:" + ",".join(sorted(unknown))
        )
    title = _bounded_text(
        _require(parameters, "title"),
        name="PUBLICATION_TITLE",
        max_bytes=MAX_PUBLICATION_TITLE_BYTES,
    )
    body = _bounded_text(
        _require(parameters, "body"),
        name="PUBLICATION_BODY",
        max_bytes=MAX_PUBLICATION_BODY_BYTES,
    )
    content_format = str(parameters.get("content_format", "text/plain")).strip().lower()
    if content_format not in {"text/plain", "text/markdown"}:
        raise ExternalIdentityError("PUBLICATION_CONTENT_FORMAT_NOT_ALLOWED")
    return {"title": title, "body": body, "content_format": content_format}


def _validate_email_payload(parameters: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"to", "subject", "body", "content_format"}
    unknown = set(parameters).difference(allowed)
    if unknown:
        raise ExternalIdentityError(
            "EMAIL_PARAMETERS_NOT_ALLOWED:" + ",".join(sorted(unknown))
        )
    to = _email_address(_require(parameters, "to"), name="EMAIL_TO")
    subject = _bounded_text(
        _require(parameters, "subject"),
        name="EMAIL_SUBJECT",
        max_bytes=MAX_EMAIL_SUBJECT_BYTES,
        allow_empty=True,
    )
    body = _bounded_text(
        _require(parameters, "body"),
        name="EMAIL_BODY",
        max_bytes=MAX_EMAIL_BODY_BYTES,
    )
    content_format = str(parameters.get("content_format", "text/plain")).strip().lower()
    if content_format not in {"text/plain", "text/html"}:
        raise ExternalIdentityError("EMAIL_CONTENT_FORMAT_NOT_ALLOWED")
    return {
        "to": to,
        "subject": subject,
        "body": body,
        "content_format": content_format,
    }


def _parse_time(value: Any, *, name: str) -> str:
    from datetime import datetime, timezone

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ExternalIdentityError(f"{name}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ExternalIdentityError(f"{name}_MUST_BE_OFFSET_AWARE")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_calendar_payload(parameters: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"summary", "description", "start_utc", "end_utc", "attendees"}
    unknown = set(parameters).difference(allowed)
    if unknown:
        raise ExternalIdentityError(
            "CALENDAR_PARAMETERS_NOT_ALLOWED:" + ",".join(sorted(unknown))
        )
    summary = _bounded_text(
        _require(parameters, "summary"),
        name="CALENDAR_SUMMARY",
        max_bytes=MAX_CALENDAR_TEXT_BYTES,
    )
    description = _bounded_text(
        parameters.get("description", ""),
        name="CALENDAR_DESCRIPTION",
        max_bytes=MAX_CALENDAR_TEXT_BYTES,
        allow_empty=True,
    )
    start = _parse_time(_require(parameters, "start_utc"), name="CALENDAR_START")
    end = _parse_time(_require(parameters, "end_utc"), name="CALENDAR_END")
    from datetime import datetime

    if datetime.fromisoformat(end.replace("Z", "+00:00")) <= datetime.fromisoformat(
        start.replace("Z", "+00:00")
    ):
        raise ExternalIdentityError("CALENDAR_END_MUST_FOLLOW_START")
    attendees_value = parameters.get("attendees", [])
    if not isinstance(attendees_value, list) or len(attendees_value) > MAX_CALENDAR_ATTENDEES:
        raise ExternalIdentityError("CALENDAR_ATTENDEES_INVALID")
    attendees = [_email_address(row, name="CALENDAR_ATTENDEE") for row in attendees_value]
    if len(set(address.lower() for address in attendees)) != len(attendees):
        raise ExternalIdentityError("CALENDAR_DUPLICATE_ATTENDEE")
    return {
        "summary": summary,
        "description": description,
        "start_utc": start,
        "end_utc": end,
        "attendees": attendees,
    }


def _validate_credential_payload(
    parameters: Mapping[str, Any],
    *,
    allowed_operations: frozenset[str],
) -> tuple[str, dict[str, Any]]:
    allowed = {"scoped_operation", "parameters"}
    unknown = set(parameters).difference(allowed)
    if unknown:
        raise ExternalIdentityError(
            "CREDENTIAL_PARAMETERS_NOT_ALLOWED:" + ",".join(sorted(unknown))
        )
    operation = str(_require(parameters, "scoped_operation")).strip().upper()
    if operation not in allowed_operations:
        raise ExternalIdentityError("CREDENTIAL_SCOPED_OPERATION_NOT_ALLOWED")
    nested = _require(parameters, "parameters")
    if not isinstance(nested, Mapping) or _json_size(nested) > MAX_CREDENTIAL_PARAMETERS_BYTES:
        raise ExternalIdentityError("CREDENTIAL_SCOPED_PARAMETERS_INVALID")
    return operation, copy.deepcopy(dict(nested))


class DurableIdentityEffectStore:
    """Stable external-effect lineage shared by publication/email/calendar/credential use."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "third_wish_identity_effects_v18_7_44.json"
        self.lock = PortableProcessLockV2(
            self.root / "third_wish_identity_effects_v18_7_44.lock"
        )
        self.writer = WindowsSafeDurableJsonWriter()
        with self.lock.exclusive():
            if not self.path.exists():
                self._save({
                    "schema": IDENTITY_EFFECT_STORE_SCHEMA,
                    "requests": {},
                    "invariants": {
                        "effect_entering_auto_retry": False,
                        "unknown_lookup_opens_retry": False,
                        "credential_export_supported": False,
                        "external_identity_ownership_transferred": False,
                    },
                })
            else:
                self._load()

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IdentityEffectReceiptIntegrityError(
                "IDENTITY_EFFECT_STORE_UNREADABLE"
            ) from exc
        if (
            not isinstance(state, dict)
            or state.get("schema") != IDENTITY_EFFECT_STORE_SCHEMA
            or not isinstance(state.get("requests"), dict)
        ):
            raise IdentityEffectReceiptIntegrityError(
                "IDENTITY_EFFECT_STORE_SCHEMA_INVALID"
            )
        return state

    def _save(self, state: Mapping[str, Any]) -> None:
        self.writer.write(self.path, dict(state))

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self.lock.exclusive():
            value = self._load()["requests"].get(str(request_id))
        return copy.deepcopy(value) if isinstance(value, dict) else None

    def bind(
        self,
        *,
        request_id: str,
        capability_id: str,
        binding_sha256: str,
        effect_key: str,
    ) -> dict[str, Any]:
        with self.lock.exclusive():
            state = self._load()
            existing = state["requests"].get(str(request_id))
            if existing is not None:
                if (
                    not isinstance(existing, dict)
                    or existing.get("capability_id") != capability_id
                    or existing.get("binding_sha256") != binding_sha256
                    or existing.get("effect_key") != effect_key
                ):
                    raise IdentityEffectRequestConflict(str(request_id))
                return copy.deepcopy(existing)
            value = {
                "capability_id": capability_id,
                "binding_sha256": binding_sha256,
                "effect_key": effect_key,
                "state": "BOUND",
                "provider_receipt": None,
                "actor_result": None,
            }
            state["requests"][str(request_id)] = value
            self._save(state)
            return copy.deepcopy(value)

    def update(self, request_id: str, **fields: Any) -> dict[str, Any]:
        with self.lock.exclusive():
            state = self._load()
            value = state["requests"].get(str(request_id))
            if not isinstance(value, dict):
                raise IdentityEffectReceiptIntegrityError(
                    "IDENTITY_EFFECT_REQUEST_BINDING_MISSING"
                )
            value.update(copy.deepcopy(fields))
            state["requests"][str(request_id)] = value
            self._save(state)
            return copy.deepcopy(value)


@dataclass(frozen=True)
class HTTPIdentityEffectProvider:
    """Operator-configured fixed-endpoint provider with broker-side bearer custody.

    Actor parameters never select ``base_url`` or ``credential_env``. The
    provider endpoint is deliberately a fixed typed service rather than generic
    API.CALL/WEB.HTTP.POST authority.
    """

    identity_alias: str
    provider_kind: str
    base_url: str
    credential_env: str
    timeout_seconds: float = 15.0
    allowed_credential_operations: frozenset[str] = frozenset({"WHOAMI"})

    def _token(self) -> str:
        token = os.getenv(self.credential_env, "").strip()
        if not token:
            raise ExternalIdentityError(
                f"BROKER_CREDENTIAL_ENV_MISSING:{self.credential_env}"
            )
        return token

    def preflight(
        self,
        *,
        effect_type: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if str(operation).upper() not in {
            "PUBLISH",
            "SEND_EMAIL",
            "CREATE_EVENT",
            *self.allowed_credential_operations,
        }:
            raise ExternalIdentityError("PROVIDER_OPERATION_NOT_ALLOWED")
        if _json_size(payload) > 256 * 1024:
            raise ExternalIdentityError("PROVIDER_PAYLOAD_TOO_LARGE")
        return {
            "validated": True,
            "identity_alias": self.identity_alias,
            "provider_kind": self.provider_kind,
            "raw_credential_visible_to_actor": False,
            "generic_http_authority": False,
        }

    def _request(
        self,
        *,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if body is None else _canonical(body).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self._token(),
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(512 * 1024 + 1)
                if len(raw) > 512 * 1024:
                    raise ExternalIdentityError("IDENTITY_PROVIDER_RESPONSE_TOO_LARGE")
                value = json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ExternalIdentityError("IDENTITY_PROVIDER_TRANSPORT_ERROR") from exc
        if not isinstance(value, dict):
            raise ExternalIdentityError("IDENTITY_PROVIDER_RESPONSE_NOT_OBJECT")
        return value

    def execute(
        self,
        *,
        effect_type: str,
        operation: str,
        payload: Mapping[str, Any],
        effect_key: str,
    ) -> Mapping[str, Any]:
        self.preflight(effect_type=effect_type, operation=operation, payload=payload)
        return self._request(
            method="POST",
            path="/v1/identity/effects",
            body={
                "effect_type": str(effect_type),
                "operation": str(operation).upper(),
                "effect_key": str(effect_key),
                "identity_alias": self.identity_alias,
                "payload": copy.deepcopy(dict(payload)),
            },
        )

    def lookup(self, effect_key: str) -> Mapping[str, Any]:
        return self._request(
            method="GET",
            path="/v1/identity/lookup",
            query={"effect_key": str(effect_key)},
        )


@dataclass
class ThirdWishExternalIdentityBroker:
    data_dir: Path
    publication_providers: Mapping[str, IdentityEffectProvider]
    email_providers: Mapping[str, IdentityEffectProvider]
    calendar_providers: Mapping[str, IdentityEffectProvider]
    credential_providers: Mapping[str, IdentityEffectProvider]
    effect_store: DurableIdentityEffectStore

    REGISTERED_CAPABILITIES = (
        "PUBLICATION.PUBLISH",
        "EMAIL.SEND",
        "CALENDAR.WRITE",
        "BROKER.CREDENTIAL.USE",
    )

    @classmethod
    def system(
        cls,
        data_dir: str | Path,
        *,
        publication_providers: Mapping[str, IdentityEffectProvider] | None = None,
        email_providers: Mapping[str, IdentityEffectProvider] | None = None,
        calendar_providers: Mapping[str, IdentityEffectProvider] | None = None,
        credential_providers: Mapping[str, IdentityEffectProvider] | None = None,
    ) -> "ThirdWishExternalIdentityBroker":
        root = Path(data_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return cls(
            data_dir=root,
            publication_providers=dict(publication_providers or {}),
            email_providers=dict(email_providers or {}),
            calendar_providers=dict(calendar_providers or {}),
            credential_providers=dict(credential_providers or {}),
            effect_store=DurableIdentityEffectStore(root),
        )

    def register(self, fabric: ThirdWishCapabilityFabric) -> None:
        for capability_id, handler in {
            "PUBLICATION.PUBLISH": self.publish,
            "EMAIL.SEND": self.send_email,
            "CALENDAR.WRITE": self.calendar_write,
            "BROKER.CREDENTIAL.USE": self.credential_use,
        }.items():
            fabric.register_handler(
                capability_id,
                handler,
                preflight=self.preflight,
            )

    def _provider_and_payload(
        self,
        intent: ActionIntent,
    ) -> tuple[IdentityEffectProvider, str, dict[str, Any], str]:
        cap = intent.capability_id
        operation = intent.operation.upper()
        if cap == "PUBLICATION.PUBLISH":
            alias = _target_alias(intent.target, "publication-channel")
            provider = self.publication_providers.get(alias)
            if provider is None:
                raise ExternalIdentityError("PUBLICATION_ALIAS_NOT_REGISTERED")
            if operation != "PUBLISH":
                raise ExternalIdentityError("PUBLICATION_OPERATION_NOT_ALLOWED")
            payload = _validate_publication_payload(intent.parameters)
            effect_type = "PUBLICATION"
        elif cap == "EMAIL.SEND":
            alias = _target_alias(intent.target, "email-account")
            provider = self.email_providers.get(alias)
            if provider is None:
                raise ExternalIdentityError("EMAIL_ALIAS_NOT_REGISTERED")
            if operation != "SEND_EMAIL":
                raise ExternalIdentityError("EMAIL_OPERATION_NOT_ALLOWED")
            payload = _validate_email_payload(intent.parameters)
            effect_type = "EMAIL"
        elif cap == "CALENDAR.WRITE":
            alias = _target_alias(intent.target, "calendar")
            provider = self.calendar_providers.get(alias)
            if provider is None:
                raise ExternalIdentityError("CALENDAR_ALIAS_NOT_REGISTERED")
            if operation != "CREATE_EVENT":
                raise ExternalIdentityError("CALENDAR_OPERATION_NOT_ALLOWED")
            payload = _validate_calendar_payload(intent.parameters)
            effect_type = "CALENDAR"
        elif cap == "BROKER.CREDENTIAL.USE":
            alias = _target_alias(intent.target, "credential-use")
            provider = self.credential_providers.get(alias)
            if provider is None:
                raise ExternalIdentityError("CREDENTIAL_ALIAS_NOT_REGISTERED")
            if operation != "USE_SCOPED_OPERATION":
                raise ExternalIdentityError("CREDENTIAL_OPERATION_NOT_ALLOWED")
            allowed_ops = getattr(provider, "allowed_credential_operations", frozenset())
            scoped_operation, nested = _validate_credential_payload(
                intent.parameters,
                allowed_operations=frozenset(allowed_ops),
            )
            operation = scoped_operation
            payload = nested
            effect_type = "CREDENTIAL_USE"
        else:
            raise ExternalIdentityError(
                "CAPABILITY_NOT_INSTALLED_BY_EXTERNAL_IDENTITY_BROKER"
            )
        return provider, operation, payload, effect_type

    @staticmethod
    def _binding(
        intent: ActionIntent,
        *,
        provider: IdentityEffectProvider,
        operation: str,
        payload: Mapping[str, Any],
        effect_type: str,
    ) -> tuple[str, str]:
        binding = {
            "actor_id": intent.actor_id,
            "capability_id": intent.capability_id,
            "target": intent.target,
            "provider_kind": str(provider.provider_kind),
            "identity_alias": str(provider.identity_alias),
            "effect_type": effect_type,
            "operation": operation,
            "payload": copy.deepcopy(dict(payload)),
        }
        binding_sha256 = _sha256(binding)
        effect_key = "THIRD-WISH-IDENTITY:" + _sha256({
            "request_id": intent.request_id,
            **binding,
        })
        return binding_sha256, effect_key

    def preflight(self, intent: ActionIntent) -> Mapping[str, Any]:
        provider, operation, payload, effect_type = self._provider_and_payload(intent)
        provider_check = provider.preflight(
            effect_type=effect_type,
            operation=operation,
            payload=payload,
        )
        if not isinstance(provider_check, Mapping) or provider_check.get("validated") is not True:
            raise ExternalIdentityError("PROVIDER_PREFLIGHT_NOT_VALIDATED")
        binding_sha256, effect_key = self._binding(
            intent,
            provider=provider,
            operation=operation,
            payload=payload,
            effect_type=effect_type,
        )
        existing = self.effect_store.get(intent.request_id)
        if existing is not None and (
            existing.get("capability_id") != intent.capability_id
            or existing.get("binding_sha256") != binding_sha256
            or existing.get("effect_key") != effect_key
        ):
            raise IdentityEffectRequestConflict(intent.request_id)
        return {
            "validated": True,
            "capability_id": intent.capability_id,
            "effect_type": effect_type,
            "operation": operation,
            "identity_alias": str(provider.identity_alias),
            "provider_kind": str(provider.provider_kind),
            "raw_credential_visible_to_actor": False,
            "credential_exported": False,
            "identity_ownership_transferred": False,
            "durable_request_state": existing.get("state") if existing else "UNBOUND",
            "external_call_entered": False,
        }

    @staticmethod
    def _validate_receipt(
        receipt: Mapping[str, Any],
        *,
        effect_key: str,
        provider: IdentityEffectProvider,
        effect_type: str,
    ) -> dict[str, Any]:
        value = copy.deepcopy(dict(receipt))
        required = {
            "provider_receipt_id",
            "effect_key",
            "effect_acknowledged",
            "effect_type",
            "provider_kind",
            "identity_alias",
            "external_object_id",
        }
        if not required.issubset(value):
            raise IdentityEffectReceiptIntegrityError(
                "IDENTITY_PROVIDER_RECEIPT_INCOMPLETE"
            )
        if str(value["effect_key"]) != effect_key:
            raise IdentityEffectReceiptIntegrityError("IDENTITY_EFFECT_KEY_MISMATCH")
        if value["effect_acknowledged"] is not True:
            raise IdentityEffectReceiptIntegrityError("IDENTITY_EFFECT_NOT_ACKNOWLEDGED")
        if str(value["effect_type"]) != effect_type:
            raise IdentityEffectReceiptIntegrityError("IDENTITY_EFFECT_TYPE_MISMATCH")
        if str(value["provider_kind"]) != str(provider.provider_kind):
            raise IdentityEffectReceiptIntegrityError("IDENTITY_PROVIDER_KIND_MISMATCH")
        if str(value["identity_alias"]) != str(provider.identity_alias):
            raise IdentityEffectReceiptIntegrityError("IDENTITY_ALIAS_MISMATCH")
        if not str(value["provider_receipt_id"]).strip() or not str(
            value["external_object_id"]
        ).strip():
            raise IdentityEffectReceiptIntegrityError("IDENTITY_RECEIPT_ID_INVALID")
        return value

    def _recover(
        self,
        *,
        provider: IdentityEffectProvider,
        effect_key: str,
        effect_type: str,
    ) -> tuple[str, dict[str, Any] | None]:
        observation = provider.lookup(effect_key)
        if not isinstance(observation, Mapping) or observation.get("authoritative") is not True:
            raise IdentityEffectOutcomeUndetermined(
                "IDENTITY_PROVIDER_LOOKUP_NOT_AUTHORITATIVE"
            )
        status = str(observation.get("status") or "UNKNOWN").upper()
        if status == "SETTLED":
            receipt = observation.get("provider_receipt")
            if not isinstance(receipt, Mapping):
                raise IdentityEffectReceiptIntegrityError(
                    "SETTLED_LOOKUP_REQUIRES_PROVIDER_RECEIPT"
                )
            return "SETTLED", self._validate_receipt(
                receipt,
                effect_key=effect_key,
                provider=provider,
                effect_type=effect_type,
            )
        if status == "NO_EFFECT":
            return "NO_EFFECT", None
        raise IdentityEffectOutcomeUndetermined("IDENTITY_EFFECT_OUTCOME_UNKNOWN")

    @staticmethod
    def _actor_result(
        *,
        provider: IdentityEffectProvider,
        effect_type: str,
        operation: str,
        receipt: Mapping[str, Any],
        recovered: bool,
    ) -> dict[str, Any]:
        base = {
            "effect_type": effect_type,
            "operation": operation,
            "provider_kind": str(provider.provider_kind),
            "identity_alias": str(provider.identity_alias),
            "provider_receipt": copy.deepcopy(dict(receipt)),
            "raw_credential_visible_to_actor": False,
            "credential_exported": False,
            "identity_ownership_transferred": False,
            "fresh_human_reauthorization_was_core_gate": True,
            "recovered_from_provider_lookup": recovered,
        }
        if effect_type == "PUBLICATION":
            base.update({
                "publication_is_truth_certification": False,
                "publication_is_operator_endorsement_proof": False,
            })
        elif effect_type == "EMAIL":
            base.update({
                "provider_acceptance_is_recipient_read_receipt": False,
                "provider_acceptance_is_recipient_consent": False,
            })
        elif effect_type == "CALENDAR":
            base.update({
                "event_creation_is_attendee_acceptance": False,
                "event_creation_is_attendance": False,
            })
        else:
            base.update({
                "authenticated_use_transfers_account_ownership": False,
                "authenticated_use_exports_credential": False,
                "authenticated_use_grants_generic_api_authority": False,
            })
        return base

    def _execute_effect(self, intent: ActionIntent) -> Mapping[str, Any]:
        provider, operation, payload, effect_type = self._provider_and_payload(intent)
        binding_sha256, effect_key = self._binding(
            intent,
            provider=provider,
            operation=operation,
            payload=payload,
            effect_type=effect_type,
        )
        stored = self.effect_store.bind(
            request_id=intent.request_id,
            capability_id=intent.capability_id,
            binding_sha256=binding_sha256,
            effect_key=effect_key,
        )
        if stored.get("state") == "SETTLED":
            actor_result = stored.get("actor_result")
            if not isinstance(actor_result, Mapping):
                raise IdentityEffectReceiptIntegrityError(
                    "SETTLED_IDENTITY_EFFECT_HAS_NO_ACTOR_RESULT"
                )
            return copy.deepcopy(dict(actor_result))

        if stored.get("state") == "EFFECT_ENTERING":
            status, receipt = self._recover(
                provider=provider,
                effect_key=effect_key,
                effect_type=effect_type,
            )
            if status == "SETTLED" and receipt is not None:
                actor_result = self._actor_result(
                    provider=provider,
                    effect_type=effect_type,
                    operation=operation,
                    receipt=receipt,
                    recovered=True,
                )
                self.effect_store.update(
                    intent.request_id,
                    state="SETTLED",
                    provider_receipt=receipt,
                    actor_result=actor_result,
                )
                return actor_result
            self.effect_store.update(
                intent.request_id,
                state="BOUND",
                authoritative_no_effect_reconciled=True,
            )

        self.effect_store.update(intent.request_id, state="EFFECT_ENTERING")
        receipt = provider.execute(
            effect_type=effect_type,
            operation=operation,
            payload=payload,
            effect_key=effect_key,
        )
        if not isinstance(receipt, Mapping):
            raise IdentityEffectReceiptIntegrityError(
                "IDENTITY_PROVIDER_RECEIPT_NOT_OBJECT"
            )
        verified = self._validate_receipt(
            receipt,
            effect_key=effect_key,
            provider=provider,
            effect_type=effect_type,
        )
        actor_result = self._actor_result(
            provider=provider,
            effect_type=effect_type,
            operation=operation,
            receipt=verified,
            recovered=False,
        )
        self.effect_store.update(
            intent.request_id,
            state="SETTLED",
            provider_receipt=verified,
            actor_result=actor_result,
        )
        return actor_result

    def publish(self, intent: ActionIntent) -> Mapping[str, Any]:
        return self._execute_effect(intent)

    def send_email(self, intent: ActionIntent) -> Mapping[str, Any]:
        return self._execute_effect(intent)

    def calendar_write(self, intent: ActionIntent) -> Mapping[str, Any]:
        return self._execute_effect(intent)

    def credential_use(self, intent: ActionIntent) -> Mapping[str, Any]:
        return self._execute_effect(intent)


EXTERNAL_IDENTITY_CLAIM_BOUNDARY = {
    "registered_protocol_capability_count": len(
        ThirdWishExternalIdentityBroker.REGISTERED_CAPABILITIES
    ),
    "all_registered_capabilities_require_fresh_human_reauthorization": True,
    "actor_selects_raw_credentials": False,
    "raw_credential_visible_to_actor": False,
    "credential_export_supported": False,
    "identity_ownership_transferred": False,
    "generic_http_post_authority_granted": False,
    "generic_api_call_authority_granted": False,
    "durable_request_binding": True,
    "effect_entering_auto_retry": False,
    "authoritative_settled_lookup_recovers_receipt": True,
    "authoritative_no_effect_lookup_may_reopen_execution": True,
    "unknown_lookup_opens_retry": False,
    "publication_proves_truth": False,
    "email_provider_acceptance_proves_recipient_read": False,
    "email_provider_acceptance_proves_recipient_consent": False,
    "calendar_creation_proves_attendance": False,
    "credential_use_transfers_account_ownership": False,
    "live_real_external_account_effects_established_by_reference_ci": False,
    "capability_is_command": False,
}
