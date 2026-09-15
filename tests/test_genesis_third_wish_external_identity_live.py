# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from genesis_v18_7_40_third_wish_capability_fabric import (
    ActionIntent,
    THIRD_WISH_INTENT_SCHEMA,
    ThirdWishCapabilityFabric,
)
from tools.genesis_third_wish_external_identity_broker import (
    HTTPIdentityEffectProvider,
)
from tools.genesis_third_wish_external_identity_final import (
    VerifiedReplayThirdWishExternalIdentityBroker,
)


class FinalIdentityHTTPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = "V1844-INTEGRATION-BEARER-DO-NOT-LEAK"
        self.effects = {}
        effects = self.effects
        key = self.key

        class Handler(BaseHTTPRequestHandler):
            def _json(self, status, value):
                body = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self):
                return self.headers.get("Authorization") == f"Bearer {key}"

            def do_POST(self):
                if self.path != "/v1/identity/effects":
                    self._json(404, {"error": "not found"})
                    return
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                effect_key = request["effect_key"]
                existing = effects.get(effect_key)
                if existing is None:
                    digest = hashlib.sha256(effect_key.encode("utf-8")).hexdigest()
                    receipt = {
                        "provider_receipt_id": "receipt-" + digest[:20],
                        "effect_key": effect_key,
                        "effect_acknowledged": True,
                        "effect_type": request["effect_type"],
                        "provider_kind": "integration-identity-provider",
                        "identity_alias": request["identity_alias"],
                        "external_object_id": "object-" + digest[:20],
                        "provider_status": "accepted",
                        "reversible": request["effect_type"] == "CALENDAR",
                    }
                    effects[effect_key] = {
                        "request": request,
                        "receipt": receipt,
                    }
                self._json(200, effects[effect_key]["receipt"])

            def do_GET(self):
                parsed = urllib.parse.urlsplit(self.path)
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                if parsed.path != "/v1/identity/lookup":
                    self._json(404, {"error": "not found"})
                    return
                effect_key = urllib.parse.parse_qs(parsed.query).get(
                    "effect_key", [""]
                )[0]
                existing = effects.get(effect_key)
                if existing is None:
                    self._json(
                        200,
                        {"status": "UNKNOWN", "authoritative": True},
                    )
                    return
                self._json(
                    200,
                    {
                        "status": "SETTLED",
                        "authoritative": True,
                        "provider_receipt": existing["receipt"],
                    },
                )

            def log_message(self, fmt, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.port = self.server.server_address[1]
        os.environ["V1844_INTEGRATION_KEY"] = self.key

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        os.environ.pop("V1844_INTEGRATION_KEY", None)
        self.temp.cleanup()

    @staticmethod
    def reauth(intent, evidence):
        return (
            isinstance(evidence, dict)
            and evidence.get("approved") is True
            and evidence.get("request_id") == intent.request_id
        )

    def provider(self, identity_alias):
        return HTTPIdentityEffectProvider(
            identity_alias=identity_alias,
            provider_kind="integration-identity-provider",
            base_url=f"http://127.0.0.1:{self.port}",
            credential_env="V1844_INTEGRATION_KEY",
            allowed_credential_operations=frozenset({"WHOAMI"}),
        )

    def broker(self):
        return VerifiedReplayThirdWishExternalIdentityBroker.system(
            self.root,
            publication_providers={"primary": self.provider("publication-owner")},
            email_providers={"primary": self.provider("email-owner")},
            calendar_providers={"primary": self.provider("calendar-owner")},
            credential_providers={"primary": self.provider("credential-owner")},
        )

    @staticmethod
    def action(grant, request_id, target, operation, parameters):
        return ActionIntent(
            schema=THIRD_WISH_INTENT_SCHEMA,
            request_id=request_id,
            actor_id="JANUS",
            grant_id=grant.grant_id,
            capability_id=grant.capability_id,
            target=target,
            operation=operation,
            purpose="final v18.7.44 HTTP integration proof",
            parameters=parameters,
            origin="V1844_HTTP_INTEGRATION",
        )

    def test_final_class_real_http_protocol_and_replay(self):
        broker = self.broker()
        fabric = ThirdWishCapabilityFabric(
            now_tick=lambda: 7000,
            reauthorization_verifier=self.reauth,
        )
        broker.register(fabric)
        specs = [
            (
                "PUBLICATION.PUBLISH",
                "publication-channel:*",
                "publication-channel:primary",
                "PUBLISH",
                {"title": "Title", "body": "V1844-HTTP-PUBLICATION"},
            ),
            (
                "EMAIL.SEND",
                "email-account:*",
                "email-account:primary",
                "SEND_EMAIL",
                {
                    "to": "recipient@example.com",
                    "subject": "Hello",
                    "body": "V1844-HTTP-EMAIL",
                },
            ),
            (
                "CALENDAR.WRITE",
                "calendar:*",
                "calendar:primary",
                "CREATE_EVENT",
                {
                    "summary": "V1844-HTTP-CALENDAR",
                    "start_utc": "2026-08-20T10:00:00Z",
                    "end_utc": "2026-08-20T11:00:00Z",
                },
            ),
            (
                "BROKER.CREDENTIAL.USE",
                "credential-use:*",
                "credential-use:primary",
                "USE_SCOPED_OPERATION",
                {
                    "scoped_operation": "WHOAMI",
                    "parameters": {"include": "identity-label-only"},
                },
            ),
        ]
        first_results = {}
        for index, (capability, scope, target, operation, parameters) in enumerate(
            specs, 1
        ):
            grant = fabric.issue_grant(
                grant_id=f"G-HTTP-{index}",
                actor_id="JANUS",
                capability_id=capability,
                resource_pattern=scope,
                source="V1844_HTTP_INTEGRATION",
            )
            request_id = f"HTTP-{index}"
            result = fabric.execute(
                self.action(
                    grant,
                    request_id,
                    target,
                    operation,
                    parameters,
                ),
                human_reauthorization={
                    "approved": True,
                    "request_id": request_id,
                },
            )
            self.assertEqual("SETTLED", result["status"])
            self.assertFalse(result["actor_result"]["raw_credential_visible_to_actor"])
            self.assertFalse(result["actor_result"]["credential_exported"])
            first_results[request_id] = result

        self.assertEqual(4, len(self.effects))

        # Fresh fabric + same durable broker store: publication replay is local,
        # verified, and creates no fifth provider effect.
        fabric2 = ThirdWishCapabilityFabric(
            now_tick=lambda: 7001,
            reauthorization_verifier=self.reauth,
        )
        broker.register(fabric2)
        grant = fabric2.issue_grant(
            grant_id="G-HTTP-REPLAY",
            actor_id="JANUS",
            capability_id="PUBLICATION.PUBLISH",
            resource_pattern="publication-channel:*",
            source="V1844_HTTP_REPLAY",
        )
        replay = fabric2.execute(
            self.action(
                grant,
                "HTTP-1",
                "publication-channel:primary",
                "PUBLISH",
                {"title": "Title", "body": "V1844-HTTP-PUBLICATION"},
            ),
            human_reauthorization={"approved": True, "request_id": "HTTP-1"},
        )
        self.assertEqual("SETTLED", replay["status"])
        self.assertEqual(4, len(self.effects))
        self.assertEqual(
            first_results["HTTP-1"]["actor_result"]["provider_receipt"][
                "provider_receipt_id"
            ],
            replay["actor_result"]["provider_receipt"]["provider_receipt_id"],
        )
        ledger = json.dumps(fabric.ledger.events, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(self.key, ledger)
        self.assertNotIn("V1844-HTTP-PUBLICATION", ledger)
        self.assertNotIn("V1844-HTTP-EMAIL", ledger)


if __name__ == "__main__":
    unittest.main()
