#!/usr/bin/env python3
"""JANUS async JSON service v1.

Fast JSON serialization/deserialization with a deliberately separate trusted-
object codec boundary. The normal JSON surface is suitable for untrusted input
subject to configured byte limits; jsonpickle is never reachable through that
surface.

Security/semantic boundaries:
- JSON != Python object graph.
- PARSE_SUCCESS != TRUST.
- JSONPICKLE_DECODE != SAFE_UNTRUSTED_DESERIALIZATION.
- FAST_PARSE != IDENTITY_CANONICALIZATION.
- FINGERPRINT == SHA256(canonical strict JSON bytes), not ordinary dump bytes.
- ASYNC_API != THREAD_OFFLOAD_REQUIRED_FOR_EVERY_CALL.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Literal

try:  # Optional accelerator; stdlib JSON remains a complete safe fallback.
    import orjson as _orjson  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    _orjson = None

try:  # Trusted-object codec only; never used by safe JSON ingress.
    import jsonpickle as _jsonpickle  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    _jsonpickle = None

try:  # Optional diff engine; builtin deterministic diff remains available.
    import jsondiff as _jsondiff  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    _jsondiff = None

logger = logging.getLogger("JANUS_JSON")

DEFAULT_MAX_JSON_BYTES = 16 * 1024 * 1024
DEFAULT_THREAD_OFFLOAD_THRESHOLD = 256 * 1024
DEFAULT_MAX_CANONICAL_DEPTH = 128
CANONICAL_BACKEND = "python-stdlib-json-sortkeys-v1"


class JsonServiceError(RuntimeError):
    """Base fail-closed service error."""


class JsonTooLargeError(JsonServiceError):
    """Input or output exceeded the configured JSON byte budget."""


class CanonicalJsonError(JsonServiceError):
    """Value is outside the strict canonical JSON domain."""


class TrustedObjectRequiredError(JsonServiceError):
    """Trusted-object codec was requested without explicit trust admission."""


class OptionalBackendUnavailableError(JsonServiceError):
    """An explicitly requested optional backend is unavailable."""


@dataclass(frozen=True)
class JsonBackendInfo:
    json_backend: str
    canonical_backend: str
    jsonpickle_available: bool
    jsondiff_available: bool
    max_json_bytes: int
    thread_offload_threshold: int


class AsyncJsonService:
    """Bounded asynchronous JSON service.

    The coroutine API is integration-friendly, but small JSON calls are executed
    directly because dispatching every micro-operation through ``to_thread`` is
    usually slower. Large *known-size input* may be offloaded automatically;
    callers can explicitly request offload for serialization when event-loop
    latency matters more than per-call overhead.
    """

    def __init__(
        self,
        *,
        max_json_bytes: int = DEFAULT_MAX_JSON_BYTES,
        thread_offload_threshold: int = DEFAULT_THREAD_OFFLOAD_THRESHOLD,
        max_canonical_depth: int = DEFAULT_MAX_CANONICAL_DEPTH,
    ) -> None:
        if type(max_json_bytes) is not int or max_json_bytes <= 0:
            raise ValueError("max_json_bytes must be a positive integer")
        if type(thread_offload_threshold) is not int or thread_offload_threshold < 0:
            raise ValueError("thread_offload_threshold must be a non-negative integer")
        if type(max_canonical_depth) is not int or max_canonical_depth <= 0:
            raise ValueError("max_canonical_depth must be a positive integer")
        self.max_json_bytes = max_json_bytes
        self.thread_offload_threshold = thread_offload_threshold
        self.max_canonical_depth = max_canonical_depth

    @property
    def backend_info(self) -> JsonBackendInfo:
        return JsonBackendInfo(
            json_backend="orjson" if _orjson is not None else "stdlib-json",
            canonical_backend=CANONICAL_BACKEND,
            jsonpickle_available=_jsonpickle is not None,
            jsondiff_available=_jsondiff is not None,
            max_json_bytes=self.max_json_bytes,
            thread_offload_threshold=self.thread_offload_threshold,
        )

    def _bounded_input_bytes(self, json_data: bytes | bytearray | memoryview | str) -> bytes:
        if isinstance(json_data, str):
            raw = json_data.encode("utf-8")
        elif isinstance(json_data, (bytes, bytearray, memoryview)):
            raw = bytes(json_data)
        else:
            raise TypeError("JSON input must be str or bytes-like")
        if len(raw) > self.max_json_bytes:
            raise JsonTooLargeError("JSON_INPUT_TOO_LARGE")
        return raw

    def _bounded_output(self, raw: bytes) -> bytes:
        if len(raw) > self.max_json_bytes:
            raise JsonTooLargeError("JSON_OUTPUT_TOO_LARGE")
        return raw

    def _validate_json_domain(self, value: Any, *, depth: int = 0) -> None:
        """Reject values with unstable/lossy JSON semantics before canonical use."""
        if depth > self.max_canonical_depth:
            raise CanonicalJsonError("CANONICAL_JSON_MAX_DEPTH_EXCEEDED")
        if value is None or type(value) is bool or type(value) is str:
            return
        if type(value) is int:
            return
        if type(value) is float:
            if not math.isfinite(value):
                raise CanonicalJsonError("CANONICAL_JSON_NONFINITE_FLOAT_REJECTED")
            return
        if type(value) is list:
            for item in value:
                self._validate_json_domain(item, depth=depth + 1)
            return
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise CanonicalJsonError("CANONICAL_JSON_NONSTRING_KEY_REJECTED")
                self._validate_json_domain(item, depth=depth + 1)
            return
        raise CanonicalJsonError(
            f"CANONICAL_JSON_UNSUPPORTED_TYPE:{type(value).__name__}"
        )

    @staticmethod
    def _reject_nonstandard_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant rejected:{value}")

    @classmethod
    def _stdlib_loads(cls, raw: bytes) -> Any:
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=cls._reject_nonstandard_constant,
        )

    @staticmethod
    def _stdlib_dumps(value: Any, *, pretty: bool, canonical: bool) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=canonical,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def _loads_sync(self, raw: bytes) -> Any:
        if _orjson is not None:
            return _orjson.loads(raw)
        return self._stdlib_loads(raw)

    def _loads_exact_sync(self, raw: bytes) -> Any:
        """Stable strict parser for identity/protocol-sensitive inputs.

        It intentionally avoids optional accelerator-dependent number semantics.
        """
        value = self._stdlib_loads(raw)
        self._validate_json_domain(value)
        return value

    def _dumps_sync(self, value: Any, *, pretty: bool) -> bytes:
        self._validate_json_domain(value)
        if _orjson is not None:
            option = _orjson.OPT_INDENT_2 if pretty else 0
            raw = _orjson.dumps(value, option=option)
        else:
            raw = self._stdlib_dumps(value, pretty=pretty, canonical=False)
        return self._bounded_output(raw)

    def _canonical_dumps_sync(self, value: Any) -> bytes:
        """Backend-independent canonicalizer used for fingerprints/bindings."""
        self._validate_json_domain(value)
        raw = self._stdlib_dumps(value, pretty=False, canonical=True)
        return self._bounded_output(raw)

    async def loads_fast(
        self,
        json_data: bytes | bytearray | memoryview | str,
        *,
        offload: bool | None = None,
    ) -> Any:
        """Parse bounded JSON through the fastest available JSON backend.

        ``offload=None`` automatically offloads only large known-size inputs.
        Parse success grants no trust or command authority. Identity-sensitive
        protocol inputs should use :meth:`loads_exact` instead.
        """
        raw = self._bounded_input_bytes(json_data)
        should_offload = (
            len(raw) >= self.thread_offload_threshold if offload is None else bool(offload)
        )
        if should_offload:
            return await asyncio.to_thread(self._loads_sync, raw)
        return self._loads_sync(raw)

    async def loads_exact(
        self,
        json_data: bytes | bytearray | memoryview | str,
        *,
        offload: bool | None = None,
    ) -> Any:
        """Parse strict JSON using the frozen canonical stdlib semantics."""
        raw = self._bounded_input_bytes(json_data)
        should_offload = (
            len(raw) >= self.thread_offload_threshold if offload is None else bool(offload)
        )
        if should_offload:
            return await asyncio.to_thread(self._loads_exact_sync, raw)
        return self._loads_exact_sync(raw)

    async def dumps_fast(
        self,
        python_obj: Any,
        *,
        pretty: bool = False,
        offload: bool = False,
    ) -> bytes:
        """Serialize a strict JSON-domain value.

        Serialization defaults to direct execution to avoid thread-dispatch cost.
        Large CPU-heavy callers may request ``offload=True`` for loop latency.
        """
        if offload:
            return await asyncio.to_thread(
                self._dumps_sync,
                python_obj,
                pretty=pretty,
            )
        return self._dumps_sync(python_obj, pretty=pretty)

    async def canonical_bytes(self, data: Any, *, offload: bool = False) -> bytes:
        """Return strict deterministic JSON bytes for hashing/binding.

        This path intentionally ignores the optional orjson accelerator so the
        same value receives the same service-level fingerprint on nodes with or
        without optional performance packages.
        """
        if offload:
            return await asyncio.to_thread(self._canonical_dumps_sync, data)
        return self._canonical_dumps_sync(data)

    async def calculate_fingerprint(self, data: Any, *, offload: bool = False) -> str:
        """SHA-256 over strict canonical JSON bytes."""
        raw = await self.canonical_bytes(data, offload=offload)
        return hashlib.sha256(raw).hexdigest()

    async def safe_parse(
        self,
        json_data: bytes | bytearray | memoryview | str,
    ) -> tuple[bool, Any, str | None]:
        """Fail-soft bounded parse for untrusted ingress.

        Error text intentionally returns stable codes rather than echoing payloads.
        """
        try:
            result = await self.loads_fast(json_data)
            return True, result, None
        except JsonTooLargeError:
            return False, None, "JSON_INPUT_TOO_LARGE"
        except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            return False, None, "JSON_DECODE_ERROR"

    async def encode_trusted_object(self, obj: Any, *, trusted: bool = False) -> str:
        """Encode a trusted Python object graph with jsonpickle.

        This output is not canonical JSON and must never be used as a cryptographic
        identity surface. Explicit trust admission is required even for encode,
        because custom object handlers may execute Python code.
        """
        if trusted is not True:
            raise TrustedObjectRequiredError("TRUSTED_OBJECT_ADMISSION_REQUIRED")
        if _jsonpickle is None:
            raise OptionalBackendUnavailableError("JSONPICKLE_BACKEND_UNAVAILABLE")
        return await asyncio.to_thread(_jsonpickle.encode, obj, make_refs=False)

    async def decode_trusted_object(self, payload: str, *, trusted: bool = False) -> Any:
        """Decode jsonpickle only after explicit trusted-data admission.

        Never call this method for user/network/repository text merely because the
        text is valid JSON. JSON syntax validity does not make an object graph safe.
        """
        if trusted is not True:
            raise TrustedObjectRequiredError("TRUSTED_OBJECT_ADMISSION_REQUIRED")
        if _jsonpickle is None:
            raise OptionalBackendUnavailableError("JSONPICKLE_BACKEND_UNAVAILABLE")
        raw = self._bounded_input_bytes(payload)
        return await asyncio.to_thread(_jsonpickle.decode, raw.decode("utf-8"))

    async def diff_states(
        self,
        before: Any,
        after: Any,
        *,
        engine: Literal["auto", "builtin", "jsondiff"] = "auto",
        offload: bool = False,
    ) -> dict[str, Any]:
        """Return a JSON-safe state difference.

        ``jsondiff`` is requested with ``marshal=True`` so symbol keys are mapped
        onto JSON-safe string keys. The builtin engine is deterministic and has
        no optional dependency.
        """
        if engine not in {"auto", "builtin", "jsondiff"}:
            raise ValueError("unsupported diff engine")
        use_jsondiff = engine == "jsondiff" or (engine == "auto" and _jsondiff is not None)
        if use_jsondiff:
            if _jsondiff is None:
                raise OptionalBackendUnavailableError("JSONDIFF_BACKEND_UNAVAILABLE")
            if offload:
                result = await asyncio.to_thread(_jsondiff.diff, before, after, marshal=True)
            else:
                result = _jsondiff.diff(before, after, marshal=True)
            if not isinstance(result, dict):
                result = {"$replace": result}
            self._validate_json_domain(result)
            return result
        return self._builtin_diff(before, after)

    def _builtin_diff(self, before: Any, after: Any) -> dict[str, Any]:
        self._validate_json_domain(before)
        self._validate_json_domain(after)
        if before == after:
            return {}
        if type(before) is dict and type(after) is dict:
            before_keys = set(before)
            after_keys = set(after)
            result: dict[str, Any] = {}
            removed = sorted(before_keys - after_keys)
            if removed:
                result["$delete"] = removed
            inserted = {key: after[key] for key in sorted(after_keys - before_keys)}
            if inserted:
                result["$insert"] = inserted
            changed: dict[str, Any] = {}
            for key in sorted(before_keys & after_keys):
                child = self._builtin_diff(before[key], after[key])
                if child:
                    changed[key] = child
            if changed:
                result["$change"] = changed
            return result
        return {"$replace": after}


async def run_service(core: Any) -> AsyncJsonService:
    """Register the service with a JANUS core without assuming sync/async registry."""
    service = AsyncJsonService()
    register = getattr(core, "register_service", None)
    if callable(register):
        outcome = register("json_service", service)
        if inspect.isawaitable(outcome):
            await outcome
    else:
        setattr(core, "json_service", service)
    logger.info(
        "AsyncJsonService activated backend=%s canonical=%s jsonpickle=%s jsondiff=%s",
        service.backend_info.json_backend,
        service.backend_info.canonical_backend,
        service.backend_info.jsonpickle_available,
        service.backend_info.jsondiff_available,
    )
    return service
