from __future__ import annotations

import ast
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import tools.janus_async_json_service as service_module
from tools.janus_async_json_service import (
    AsyncJsonService,
    CanonicalJsonError,
    JsonTooLargeError,
    TrustedObjectRequiredError,
    run_service,
)


class AsyncJsonServiceV1Tests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_round_trip_and_pretty_dump(self) -> None:
        service = AsyncJsonService()
        value = {"z": [1, True, None], "text": "Янус"}
        raw = await service.dumps_fast(value, pretty=True)
        self.assertIn(b"\n", raw)
        self.assertEqual(await service.loads_fast(raw, offload=False), value)

    async def test_canonical_fingerprint_is_key_order_independent(self) -> None:
        service = AsyncJsonService()
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(await service.canonical_bytes(left), b'{"a":1,"b":2}')
        self.assertEqual(
            await service.calculate_fingerprint(left),
            await service.calculate_fingerprint(right),
        )
        self.assertEqual(
            await service.calculate_fingerprint(left),
            hashlib.sha256(b'{"a":1,"b":2}').hexdigest(),
        )

    async def test_canonical_fingerprint_does_not_depend_on_orjson_presence(self) -> None:
        service = AsyncJsonService()
        value = {"unicode": "Янус", "nested": {"b": 2, "a": 1}, "f": 1.25}
        expected = await service.calculate_fingerprint(value)
        with patch.object(service_module, "_orjson", None):
            fallback = AsyncJsonService()
            self.assertEqual(await fallback.calculate_fingerprint(value), expected)
            self.assertEqual(fallback.backend_info.canonical_backend, service.backend_info.canonical_backend)

    async def test_nonfinite_float_and_nonstring_key_are_rejected(self) -> None:
        service = AsyncJsonService()
        for value in ({"x": math.nan}, {"x": math.inf}, {1: "not-a-json-key"}):
            with self.subTest(value=value):
                with self.assertRaises(CanonicalJsonError):
                    await service.calculate_fingerprint(value)

    async def test_custom_python_object_is_not_ordinary_json(self) -> None:
        service = AsyncJsonService()

        class Object:
            pass

        with self.assertRaises(CanonicalJsonError):
            await service.dumps_fast({"object": Object()})

    async def test_exact_parser_rejects_nonstandard_nan(self) -> None:
        service = AsyncJsonService()
        with self.assertRaises(ValueError):
            await service.loads_exact('{"x": NaN}', offload=False)

    async def test_safe_parse_is_bounded_and_does_not_echo_payload(self) -> None:
        service = AsyncJsonService(max_json_bytes=16)
        ok, value, error = await service.safe_parse('{"a":1}')
        self.assertTrue(ok)
        self.assertEqual(value, {"a": 1})
        self.assertIsNone(error)

        secret = '{"secret":"THIS-MUST-NOT-ECHO"}'
        ok, value, error = await service.safe_parse(secret)
        self.assertFalse(ok)
        self.assertIsNone(value)
        self.assertEqual(error, "JSON_INPUT_TOO_LARGE")
        self.assertNotIn("THIS-MUST-NOT-ECHO", error)

    async def test_safe_parse_invalid_json_returns_stable_code(self) -> None:
        service = AsyncJsonService()
        ok, value, error = await service.safe_parse('{"broken":')
        self.assertFalse(ok)
        self.assertIsNone(value)
        self.assertEqual(error, "JSON_DECODE_ERROR")

    async def test_jsonpickle_shaped_untrusted_json_remains_plain_data(self) -> None:
        service = AsyncJsonService()

        class FakeJsonPickle:
            def __init__(self) -> None:
                self.decode_calls = 0

            def decode(self, payload: str):
                self.decode_calls += 1
                raise AssertionError("jsonpickle decode must not be reached by safe_parse")

        fake = FakeJsonPickle()
        payload = '{"py/object":"danger.example.Type","value":7}'
        with patch.object(service_module, "_jsonpickle", fake):
            ok, value, error = await service.safe_parse(payload)
            self.assertTrue(ok)
            self.assertEqual(value["py/object"], "danger.example.Type")
            self.assertIsNone(error)
            self.assertEqual(fake.decode_calls, 0)

            with self.assertRaises(TrustedObjectRequiredError):
                await service.decode_trusted_object(payload)
            self.assertEqual(fake.decode_calls, 0)

    async def test_trusted_object_decode_requires_explicit_true_before_backend(self) -> None:
        service = AsyncJsonService()

        class FakeJsonPickle:
            def __init__(self) -> None:
                self.decode_calls = 0

            def decode(self, payload: str):
                self.decode_calls += 1
                return {"trusted-decoded": payload}

        fake = FakeJsonPickle()
        with patch.object(service_module, "_jsonpickle", fake):
            with self.assertRaises(TrustedObjectRequiredError):
                await service.decode_trusted_object("{}", trusted=False)
            self.assertEqual(fake.decode_calls, 0)
            decoded = await service.decode_trusted_object("{}", trusted=True)
            self.assertEqual(decoded, {"trusted-decoded": "{}"})
            self.assertEqual(fake.decode_calls, 1)

    async def test_builtin_diff_is_deterministic_and_json_safe(self) -> None:
        service = AsyncJsonService()
        before = {"a": 1, "b": {"x": 1}, "delete": True}
        after = {"a": 1, "b": {"x": 2}, "insert": [1, 2]}
        diff = await service.diff_states(before, after, engine="builtin")
        self.assertEqual(diff["$delete"], ["delete"])
        self.assertEqual(diff["$insert"], {"insert": [1, 2]})
        self.assertEqual(diff["$change"]["b"]["$change"]["x"], {"$replace": 2})
        json.dumps(diff, allow_nan=False)

    async def test_output_budget_fails_closed(self) -> None:
        service = AsyncJsonService(max_json_bytes=8)
        with self.assertRaises(JsonTooLargeError):
            await service.dumps_fast({"long": "0123456789"})

    async def test_small_fast_parse_avoids_thread_dispatch(self) -> None:
        service = AsyncJsonService(thread_offload_threshold=1024)
        mock = AsyncMock()
        with patch.object(service_module.asyncio, "to_thread", mock):
            self.assertEqual(await service.loads_fast(b'{"a":1}'), {"a": 1})
        mock.assert_not_awaited()

    async def test_large_known_input_auto_offloads(self) -> None:
        service = AsyncJsonService(thread_offload_threshold=1)

        async def execute(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock = AsyncMock(side_effect=execute)
        with patch.object(service_module.asyncio, "to_thread", mock):
            self.assertEqual(await service.loads_fast(b'{"a":1}'), {"a": 1})
        mock.assert_awaited_once()

    async def test_core_registration_supports_sync_and_async_hooks(self) -> None:
        sync_seen: dict[str, object] = {}

        class SyncCore:
            def register_service(self, name: str, value: object) -> None:
                sync_seen[name] = value

        sync_service = await run_service(SyncCore())
        self.assertIs(sync_seen["json_service"], sync_service)

        async_seen: dict[str, object] = {}

        class AsyncCore:
            async def register_service(self, name: str, value: object) -> None:
                async_seen[name] = value

        async_service = await run_service(AsyncCore())
        self.assertIs(async_seen["json_service"], async_service)

        bare = SimpleNamespace()
        bare_service = await run_service(bare)
        self.assertIs(bare.json_service, bare_service)

    async def test_canonical_depth_limit_fails_closed(self) -> None:
        service = AsyncJsonService(max_canonical_depth=2)
        with self.assertRaises(CanonicalJsonError):
            await service.calculate_fingerprint({"a": {"b": {"c": 1}}})

    def test_source_has_no_network_process_or_file_write_surface(self) -> None:
        path = Path(service_module.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden_import_roots = {
            "socket",
            "subprocess",
            "requests",
            "urllib",
            "http",
            "pathlib",
            "os",
        }
        imported_roots: set[str] = set()
        forbidden_calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"open", "eval", "exec", "compile", "__import__"}:
                    forbidden_calls.add(node.func.id)
        self.assertFalse(imported_roots & forbidden_import_roots)
        self.assertFalse(forbidden_calls)


if __name__ == "__main__":
    unittest.main()
