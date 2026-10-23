# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from genesis_v18_7_40_third_wish_capability_fabric import (
    ActionIntent,
    THIRD_WISH_INTENT_SCHEMA,
    ThirdWishCapabilityFabric,
)
from tools.genesis_third_wish_external_identity_broker import (
    DurableIdentityEffectStore,
)
from tools.genesis_third_wish_external_identity_final import (
    EXTERNAL_IDENTITY_FINAL_CLAIMS,
    VerifiedReplayThirdWishExternalIdentityBroker,
)


class MinimalProvider:
    identity_alias = "owner-primary"
    provider_kind = "minimal-provider"
    allowed_credential_operations = frozenset({"WHOAMI"})

    def __init__(self):
        self.execute_calls = 0
        self.receipts = {}

    def preflight(self, *, effect_type, operation, payload):
        return {"validated": True}

    def execute(self, *, effect_type, operation, payload, effect_key):
        self.execute_calls += 1
        receipt = {
            "provider_receipt_id": "receipt-1",
            "effect_key": effect_key,
            "effect_acknowledged": True,
            "effect_type": effect_type,
            "provider_kind": self.provider_kind,
            "identity_alias": self.identity_alias,
            "external_object_id": "object-1",
            "provider_status": "accepted",
            "reversible": False,
        }
        self.receipts[effect_key] = copy.deepcopy(receipt)
        return receipt

    def lookup(self, effect_key):
        if effect_key in self.receipts:
            return {
                "status": "SETTLED",
                "authoritative": True,
                "provider_receipt": copy.deepcopy(self.receipts[effect_key]),
            }
        return {"status": "UNKNOWN", "authoritative": True}


class ExternalIdentityReplayIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.provider = MinimalProvider()
        self.broker = VerifiedReplayThirdWishExternalIdentityBroker(
            data_dir=self.root,
            publication_providers={"primary": self.provider},
            email_providers={},
            calendar_providers={},
            credential_providers={},
            effect_store=DurableIdentityEffectStore(self.root),
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def reauth(intent, evidence):
        return (
            isinstance(evidence, dict)
            and evidence.get("approved") is True
            and evidence.get("request_id") == intent.request_id
        )

    def fabric(self, tick):
        fabric = ThirdWishCapabilityFabric(
            now_tick=lambda: tick,
            reauthorization_verifier=self.reauth,
        )
        self.broker.register(fabric)
        return fabric

    @staticmethod
    def approval(request_id):
        return {"approved": True, "request_id": request_id}

    @staticmethod
    def intent(grant, request_id="PUB-INTEGRITY"):
        return ActionIntent(
            schema=THIRD_WISH_INTENT_SCHEMA,
            request_id=request_id,
            actor_id="JANUS",
            grant_id=grant.grant_id,
            capability_id="PUBLICATION.PUBLISH",
            target="publication-channel:primary",
            operation="PUBLISH",
            purpose="verify settled replay integrity",
            parameters={"title": "Integrity", "body": "one effect"},
            origin="V1844_INTEGRITY_TEST",
        )

    def settle_once(self):
        fabric = self.fabric(6100)
        grant = fabric.issue_grant(
            grant_id="G-INTEGRITY-1",
            actor_id="JANUS",
            capability_id="PUBLICATION.PUBLISH",
            resource_pattern="publication-channel:*",
            source="V1844_INTEGRITY_TEST",
        )
        result = fabric.execute(
            self.intent(grant),
            human_reauthorization=self.approval("PUB-INTEGRITY"),
        )
        self.assertEqual("SETTLED", result["status"])
        self.assertEqual(1, self.provider.execute_calls)
        return result

    def replay(self):
        fabric = self.fabric(6101)
        grant = fabric.issue_grant(
            grant_id="G-INTEGRITY-2",
            actor_id="JANUS",
            capability_id="PUBLICATION.PUBLISH",
            resource_pattern="publication-channel:*",
            source="V1844_INTEGRITY_REPLAY",
        )
        return fabric.execute(
            self.intent(grant),
            human_reauthorization=self.approval("PUB-INTEGRITY"),
        )

    def test_final_claims_require_revalidation(self):
        self.assertTrue(
            EXTERNAL_IDENTITY_FINAL_CLAIMS[
                "settled_local_receipt_revalidated_before_replay"
            ]
        )
        self.assertTrue(
            EXTERNAL_IDENTITY_FINAL_CLAIMS[
                "settled_actor_result_reconstructed_before_replay"
            ]
        )
        self.assertFalse(
            EXTERNAL_IDENTITY_FINAL_CLAIMS[
                "local_settled_store_tamper_trusted"
            ]
        )

    def test_clean_settled_replay_is_accepted_without_second_provider_effect(self):
        first = self.settle_once()
        second = self.replay()
        self.assertEqual("SETTLED", second["status"])
        self.assertEqual(1, self.provider.execute_calls)
        self.assertEqual(
            first["actor_result"]["provider_receipt"]["provider_receipt_id"],
            second["actor_result"]["provider_receipt"]["provider_receipt_id"],
        )

    def test_actor_result_tamper_is_pre_effect_rejected(self):
        self.settle_once()
        state = json.loads(self.broker.effect_store.path.read_text(encoding="utf-8"))
        row = state["requests"]["PUB-INTEGRITY"]
        row["actor_result"]["raw_credential_visible_to_actor"] = True
        self.broker.effect_store.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = self.replay()
        self.assertEqual("PRE_EFFECT_REJECTED", result["status"])
        self.assertFalse(result["external_call_entered"])
        self.assertEqual(1, self.provider.execute_calls)

    def test_provider_receipt_unknown_secret_field_is_pre_effect_rejected(self):
        self.settle_once()
        state = json.loads(self.broker.effect_store.path.read_text(encoding="utf-8"))
        row = state["requests"]["PUB-INTEGRITY"]
        row["provider_receipt"]["access_token"] = "LOCAL-TAMPER-SECRET"
        row["actor_result"]["provider_receipt"]["access_token"] = "LOCAL-TAMPER-SECRET"
        self.broker.effect_store.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = self.replay()
        self.assertEqual("PRE_EFFECT_REJECTED", result["status"])
        self.assertFalse(result["external_call_entered"])
        self.assertNotIn("LOCAL-TAMPER-SECRET", str(result))
        self.assertEqual(1, self.provider.execute_calls)


if __name__ == "__main__":
    unittest.main()
