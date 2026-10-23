# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path

from genesis_v18_7_40_third_wish_capability_fabric import (
    ActionIntent,
    CapabilityOutcomeUndetermined,
    SecretMaterialLeak,
    THIRD_WISH_INTENT_SCHEMA,
    ThirdWishCapabilityFabric,
)
from tools.genesis_third_wish_external_identity_broker import (
    EXTERNAL_IDENTITY_CLAIM_BOUNDARY,
    DurableIdentityEffectStore,
)
from tools.genesis_third_wish_external_identity_recovery import (
    EXTERNAL_IDENTITY_RECOVERY_CLAIMS,
    RecoverableThirdWishExternalIdentityBroker,
)


class FakeIdentityProvider:
    def __init__(self, *, alias="owner-primary", kind="fake-identity"):
        self.identity_alias = alias
        self.provider_kind = kind
        self.allowed_credential_operations = frozenset({"WHOAMI", "SCOPED_STATUS"})
        self.preflight_calls = 0
        self.execute_calls = 0
        self.lookup_calls = 0
        self.receipts = {}
        self.lookup_overrides = {}
        self.crash_after_effect = False
        self.fail_before_effect = False
        self.return_secret_field = False
        self.execute_delay = 0.0

    def preflight(self, *, effect_type, operation, payload):
        self.preflight_calls += 1
        return {
            "validated": True,
            "effect_type": effect_type,
            "operation": operation,
            "identity_alias": self.identity_alias,
        }

    def _receipt(self, effect_type, effect_key):
        receipt = {
            "provider_receipt_id": f"receipt-{len(self.receipts) + 1}",
            "effect_key": effect_key,
            "effect_acknowledged": True,
            "effect_type": effect_type,
            "provider_kind": self.provider_kind,
            "identity_alias": self.identity_alias,
            "external_object_id": f"object-{len(self.receipts) + 1}",
            "provider_status": "accepted",
            "reversible": effect_type == "CALENDAR",
        }
        if self.return_secret_field:
            receipt["access_token"] = "SHOULD-NEVER-REACH-ACTOR"
        return receipt

    def execute(self, *, effect_type, operation, payload, effect_key):
        self.execute_calls += 1
        if self.execute_delay:
            time.sleep(self.execute_delay)
        if self.fail_before_effect:
            self.fail_before_effect = False
            raise RuntimeError("injected provider failure before known effect")
        receipt = self._receipt(effect_type, effect_key)
        self.receipts[effect_key] = copy.deepcopy(receipt)
        if self.crash_after_effect:
            self.crash_after_effect = False
            raise RuntimeError("injected process loss after provider effect")
        return receipt

    def lookup(self, effect_key):
        self.lookup_calls += 1
        if effect_key in self.lookup_overrides:
            return copy.deepcopy(self.lookup_overrides[effect_key])
        if effect_key in self.receipts:
            return {
                "status": "SETTLED",
                "authoritative": True,
                "provider_receipt": copy.deepcopy(self.receipts[effect_key]),
            }
        return {"status": "UNKNOWN", "authoritative": True}


class ThirdWishExternalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.provider = FakeIdentityProvider()
        self.broker = RecoverableThirdWishExternalIdentityBroker(
            data_dir=self.root,
            publication_providers={"primary": self.provider},
            email_providers={"primary": self.provider},
            calendar_providers={"primary": self.provider},
            credential_providers={"primary": self.provider},
            effect_store=DurableIdentityEffectStore(self.root),
        )
        self.fabric = self.new_fabric(5000)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def reauth(intent, evidence):
        return (
            isinstance(evidence, dict)
            and evidence.get("approved") is True
            and evidence.get("request_id") == intent.request_id
            and evidence.get("witness") == "V1844_OPERATOR"
        )

    def new_fabric(self, tick):
        fabric = ThirdWishCapabilityFabric(
            now_tick=lambda: tick,
            reauthorization_verifier=self.reauth,
        )
        self.broker.register(fabric)
        return fabric

    @staticmethod
    def approval(request_id):
        return {
            "approved": True,
            "request_id": request_id,
            "witness": "V1844_OPERATOR",
        }

    def grant(self, capability, scope, suffix, *, fabric=None):
        fabric = fabric or self.fabric
        return fabric.issue_grant(
            grant_id=f"G-{suffix}",
            actor_id="JANUS",
            capability_id=capability,
            resource_pattern=scope,
            source="V1844_TEST",
        )

    @staticmethod
    def intent(grant, request_id, target, operation, parameters):
        return ActionIntent(
            schema=THIRD_WISH_INTENT_SCHEMA,
            request_id=request_id,
            actor_id="JANUS",
            grant_id=grant.grant_id,
            capability_id=grant.capability_id,
            target=target,
            operation=operation,
            purpose="exercise Third Wish v18.7.44 external identity boundary",
            parameters=parameters,
            origin="V1844_TEST",
        )

    def test_registered_surface_and_claim_ceiling(self):
        expected = {
            "PUBLICATION.PUBLISH",
            "EMAIL.SEND",
            "CALENDAR.WRITE",
            "BROKER.CREDENTIAL.USE",
        }
        self.assertEqual(expected, set(self.fabric.handlers))
        self.assertEqual(expected, set(self.fabric.preflights))
        self.assertEqual(
            4,
            EXTERNAL_IDENTITY_CLAIM_BOUNDARY[
                "registered_protocol_capability_count"
            ],
        )
        self.assertTrue(
            EXTERNAL_IDENTITY_CLAIM_BOUNDARY[
                "all_registered_capabilities_require_fresh_human_reauthorization"
            ]
        )
        self.assertFalse(
            EXTERNAL_IDENTITY_CLAIM_BOUNDARY["credential_export_supported"]
        )
        self.assertFalse(
            EXTERNAL_IDENTITY_CLAIM_BOUNDARY[
                "generic_http_post_authority_granted"
            ]
        )
        self.assertFalse(
            EXTERNAL_IDENTITY_RECOVERY_CLAIMS[
                "provider_receipt_can_return_raw_credential_field"
            ]
        )
        self.assertFalse(
            EXTERNAL_IDENTITY_RECOVERY_CLAIMS[
                "cross_host_exactly_once_claimed"
            ]
        )

    def test_fresh_reauthorization_precedes_provider_preflight(self):
        grant = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-REAUTH",
        )
        request_id = "PUB-REAUTH-1"
        intent = self.intent(
            grant,
            request_id,
            "publication-channel:primary",
            "PUBLISH",
            {"title": "Title", "body": "Body"},
        )
        result = self.fabric.execute(intent)
        self.assertEqual("FRESH_HUMAN_REAUTHORIZATION_REQUIRED", result["status"])
        self.assertEqual(0, self.provider.preflight_calls)
        self.assertEqual(0, self.provider.execute_calls)

    def test_publication_settles_without_truth_or_endorsement_claim(self):
        grant = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB",
        )
        request_id = "PUB-1"
        result = self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "publication-channel:primary",
                "PUBLISH",
                {"title": "Third Wish", "body": "typed freedom"},
            ),
            human_reauthorization=self.approval(request_id),
        )
        actor = result["actor_result"]
        self.assertEqual("SETTLED", result["status"])
        self.assertFalse(actor["publication_is_truth_certification"])
        self.assertFalse(actor["publication_is_operator_endorsement_proof"])
        self.assertFalse(actor["raw_credential_visible_to_actor"])
        self.assertFalse(actor["identity_ownership_transferred"])

    def test_email_provider_acceptance_is_not_read_or_consent(self):
        grant = self.grant("EMAIL.SEND", "email-account:*", "MAIL")
        request_id = "MAIL-1"
        result = self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "email-account:primary",
                "SEND_EMAIL",
                {
                    "to": "recipient@example.com",
                    "subject": "Hello",
                    "body": "External identity test",
                },
            ),
            human_reauthorization=self.approval(request_id),
        )
        actor = result["actor_result"]
        self.assertFalse(actor["provider_acceptance_is_recipient_read_receipt"])
        self.assertFalse(actor["provider_acceptance_is_recipient_consent"])

    def test_email_cannot_override_operator_from_identity(self):
        grant = self.grant("EMAIL.SEND", "email-account:*", "MAIL-FROM")
        request_id = "MAIL-FROM-1"
        result = self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "email-account:primary",
                "SEND_EMAIL",
                {
                    "from": "spoof@example.com",
                    "to": "recipient@example.com",
                    "subject": "Hello",
                    "body": "Body",
                },
            ),
            human_reauthorization=self.approval(request_id),
        )
        self.assertEqual("PRE_EFFECT_REJECTED", result["status"])
        self.assertFalse(result["external_call_entered"])

    def test_calendar_creation_is_not_attendance_or_acceptance(self):
        grant = self.grant("CALENDAR.WRITE", "calendar:*", "CAL")
        request_id = "CAL-1"
        result = self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "calendar:primary",
                "CREATE_EVENT",
                {
                    "summary": "Third Wish review",
                    "description": "review typed authority",
                    "start_utc": "2026-08-16T10:00:00Z",
                    "end_utc": "2026-08-16T11:00:00Z",
                    "attendees": ["one@example.com"],
                },
            ),
            human_reauthorization=self.approval(request_id),
        )
        actor = result["actor_result"]
        self.assertFalse(actor["event_creation_is_attendee_acceptance"])
        self.assertFalse(actor["event_creation_is_attendance"])

    def test_credential_use_is_scoped_and_does_not_export_secret_or_ownership(self):
        grant = self.grant(
            "BROKER.CREDENTIAL.USE",
            "credential-use:*",
            "CRED",
        )
        request_id = "CRED-1"
        result = self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "credential-use:primary",
                "USE_SCOPED_OPERATION",
                {
                    "scoped_operation": "WHOAMI",
                    "parameters": {"include": "account-label-only"},
                },
            ),
            human_reauthorization=self.approval(request_id),
        )
        actor = result["actor_result"]
        self.assertFalse(actor["authenticated_use_transfers_account_ownership"])
        self.assertFalse(actor["authenticated_use_exports_credential"])
        self.assertFalse(actor["authenticated_use_grants_generic_api_authority"])
        self.assertFalse(actor["raw_credential_visible_to_actor"])

    def test_secret_like_actor_parameter_is_rejected_by_core_before_provider(self):
        grant = self.grant(
            "BROKER.CREDENTIAL.USE",
            "credential-use:*",
            "CRED-SECRET",
        )
        request_id = "CRED-SECRET-1"
        with self.assertRaises(SecretMaterialLeak):
            self.fabric.execute(
                self.intent(
                    grant,
                    request_id,
                    "credential-use:primary",
                    "USE_SCOPED_OPERATION",
                    {
                        "scoped_operation": "WHOAMI",
                        "parameters": {"access_token": "actor-supplied-secret"},
                    },
                ),
                human_reauthorization=self.approval(request_id),
            )
        self.assertEqual(0, self.provider.preflight_calls)
        self.assertEqual(0, self.provider.execute_calls)

    def test_settled_replay_survives_fresh_fabric_without_second_external_effect(self):
        request_id = "PUB-STABLE"
        params = {"title": "Stable", "body": "one external object"}
        grant = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-STABLE",
        )
        first = self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "publication-channel:primary",
                "PUBLISH",
                params,
            ),
            human_reauthorization=self.approval(request_id),
        )
        receipt_id = first["actor_result"]["provider_receipt"]["provider_receipt_id"]
        self.assertEqual(1, self.provider.execute_calls)

        fabric2 = self.new_fabric(5001)
        grant2 = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-STABLE-2",
            fabric=fabric2,
        )
        second = fabric2.execute(
            self.intent(
                grant2,
                request_id,
                "publication-channel:primary",
                "PUBLISH",
                params,
            ),
            human_reauthorization=self.approval(request_id),
        )
        self.assertEqual(
            receipt_id,
            second["actor_result"]["provider_receipt"]["provider_receipt_id"],
        )
        self.assertEqual(1, self.provider.execute_calls)

    def test_same_request_changed_effect_is_pre_effect_rejected(self):
        request_id = "MAIL-CONFLICT"
        grant = self.grant("EMAIL.SEND", "email-account:*", "MAIL-C1")
        self.fabric.execute(
            self.intent(
                grant,
                request_id,
                "email-account:primary",
                "SEND_EMAIL",
                {
                    "to": "a@example.com",
                    "subject": "One",
                    "body": "same request",
                },
            ),
            human_reauthorization=self.approval(request_id),
        )
        fabric2 = self.new_fabric(5002)
        grant2 = self.grant(
            "EMAIL.SEND",
            "email-account:*",
            "MAIL-C2",
            fabric=fabric2,
        )
        result = fabric2.execute(
            self.intent(
                grant2,
                request_id,
                "email-account:primary",
                "SEND_EMAIL",
                {
                    "to": "b@example.com",
                    "subject": "Two",
                    "body": "changed effect",
                },
            ),
            human_reauthorization=self.approval(request_id),
        )
        self.assertEqual("PRE_EFFECT_REJECTED", result["status"])
        self.assertFalse(result["external_call_entered"])
        self.assertEqual(1, self.provider.execute_calls)

    def test_crash_after_provider_effect_recovers_receipt_without_duplicate(self):
        self.provider.crash_after_effect = True
        request_id = "PUB-CRASH"
        params = {"title": "Crash", "body": "provider already accepted"}
        grant = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-CRASH",
        )
        with self.assertRaises(CapabilityOutcomeUndetermined):
            self.fabric.execute(
                self.intent(
                    grant,
                    request_id,
                    "publication-channel:primary",
                    "PUBLISH",
                    params,
                ),
                human_reauthorization=self.approval(request_id),
            )
        self.assertEqual(1, self.provider.execute_calls)

        fabric2 = self.new_fabric(5003)
        grant2 = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-CRASH-2",
            fabric=fabric2,
        )
        recovered = fabric2.execute(
            self.intent(
                grant2,
                request_id,
                "publication-channel:primary",
                "PUBLISH",
                params,
            ),
            human_reauthorization=self.approval(request_id),
        )
        self.assertEqual("SETTLED", recovered["status"])
        self.assertTrue(recovered["actor_result"]["recovered_from_provider_lookup"])
        self.assertEqual(1, self.provider.execute_calls)

    def test_unknown_effect_never_blindly_reexecutes(self):
        self.provider.fail_before_effect = True
        request_id = "MAIL-UNKNOWN"
        params = {
            "to": "recipient@example.com",
            "subject": "Unknown",
            "body": "do not duplicate",
        }
        grant = self.grant("EMAIL.SEND", "email-account:*", "MAIL-U1")
        with self.assertRaises(CapabilityOutcomeUndetermined):
            self.fabric.execute(
                self.intent(
                    grant,
                    request_id,
                    "email-account:primary",
                    "SEND_EMAIL",
                    params,
                ),
                human_reauthorization=self.approval(request_id),
            )
        self.assertEqual(1, self.provider.execute_calls)

        fabric2 = self.new_fabric(5004)
        grant2 = self.grant(
            "EMAIL.SEND",
            "email-account:*",
            "MAIL-U2",
            fabric=fabric2,
        )
        with self.assertRaises(CapabilityOutcomeUndetermined):
            fabric2.execute(
                self.intent(
                    grant2,
                    request_id,
                    "email-account:primary",
                    "SEND_EMAIL",
                    params,
                ),
                human_reauthorization=self.approval(request_id),
            )
        self.assertEqual(1, self.provider.execute_calls)

    def test_authoritative_no_effect_reopens_only_on_fresh_reauthorized_call(self):
        self.provider.fail_before_effect = True
        request_id = "CAL-NO-EFFECT"
        params = {
            "summary": "No effect",
            "start_utc": "2026-08-17T10:00:00Z",
            "end_utc": "2026-08-17T11:00:00Z",
        }
        grant = self.grant("CALENDAR.WRITE", "calendar:*", "CAL-NO1")
        with self.assertRaises(CapabilityOutcomeUndetermined):
            self.fabric.execute(
                self.intent(
                    grant,
                    request_id,
                    "calendar:primary",
                    "CREATE_EVENT",
                    params,
                ),
                human_reauthorization=self.approval(request_id),
            )
        stored = self.broker.effect_store.get(request_id)
        effect_key = stored["effect_key"]
        self.provider.lookup_overrides[effect_key] = {
            "status": "NO_EFFECT",
            "authoritative": True,
        }

        fabric2 = self.new_fabric(5005)
        grant2 = self.grant(
            "CALENDAR.WRITE",
            "calendar:*",
            "CAL-NO2",
            fabric=fabric2,
        )
        retry_intent = self.intent(
            grant2,
            request_id,
            "calendar:primary",
            "CREATE_EVENT",
            params,
        )
        blocked = fabric2.execute(retry_intent)
        self.assertEqual("FRESH_HUMAN_REAUTHORIZATION_REQUIRED", blocked["status"])
        self.assertEqual(1, self.provider.execute_calls)

        settled = fabric2.execute(
            retry_intent,
            human_reauthorization=self.approval(request_id),
        )
        self.assertEqual("SETTLED", settled["status"])
        self.assertEqual(2, self.provider.execute_calls)

    def test_provider_receipt_secret_field_is_rejected_and_never_returned(self):
        self.provider.return_secret_field = True
        request_id = "CRED-LEAK"
        grant = self.grant(
            "BROKER.CREDENTIAL.USE",
            "credential-use:*",
            "CRED-LEAK",
        )
        with self.assertRaises(CapabilityOutcomeUndetermined):
            self.fabric.execute(
                self.intent(
                    grant,
                    request_id,
                    "credential-use:primary",
                    "USE_SCOPED_OPERATION",
                    {
                        "scoped_operation": "WHOAMI",
                        "parameters": {"include": "label"},
                    },
                ),
                human_reauthorization=self.approval(request_id),
            )
        self.assertNotIn("SHOULD-NEVER-REACH-ACTOR", str(self.fabric.ledger.events))
        self.assertEqual(1, self.provider.execute_calls)

        fabric2 = self.new_fabric(5006)
        grant2 = self.grant(
            "BROKER.CREDENTIAL.USE",
            "credential-use:*",
            "CRED-LEAK-2",
            fabric=fabric2,
        )
        with self.assertRaises(CapabilityOutcomeUndetermined):
            fabric2.execute(
                self.intent(
                    grant2,
                    request_id,
                    "credential-use:primary",
                    "USE_SCOPED_OPERATION",
                    {
                        "scoped_operation": "WHOAMI",
                        "parameters": {"include": "label"},
                    },
                ),
                human_reauthorization=self.approval(request_id),
            )
        self.assertEqual(1, self.provider.execute_calls)

    def test_two_local_callers_same_request_converge_to_one_provider_effect(self):
        self.provider.execute_delay = 0.05
        request_id = "PUB-CONCURRENT"
        params = {"title": "Concurrent", "body": "one effect only"}
        fabric1 = self.new_fabric(5100)
        fabric2 = self.new_fabric(5101)
        grant1 = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-T1",
            fabric=fabric1,
        )
        grant2 = self.grant(
            "PUBLICATION.PUBLISH",
            "publication-channel:*",
            "PUB-T2",
            fabric=fabric2,
        )
        results = []
        errors = []

        def worker(fabric, grant):
            try:
                results.append(
                    fabric.execute(
                        self.intent(
                            grant,
                            request_id,
                            "publication-channel:primary",
                            "PUBLISH",
                            params,
                        ),
                        human_reauthorization=self.approval(request_id),
                    )
                )
            except BaseException as exc:  # test harness only
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=(fabric1, grant1))
        t2 = threading.Thread(target=worker, args=(fabric2, grant2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertTrue(all(row["status"] == "SETTLED" for row in results))
        self.assertEqual(1, self.provider.execute_calls)
        receipt_ids = {
            row["actor_result"]["provider_receipt"]["provider_receipt_id"]
            for row in results
        }
        self.assertEqual(1, len(receipt_ids))


if __name__ == "__main__":
    unittest.main()
