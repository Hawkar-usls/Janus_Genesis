# -*- coding: utf-8 -*-
"""Final v18.7.44 identity-effect replay integrity descendant.

A durable SETTLED row is not trusted merely because it is local. Before a
settled replay can cross into the handler, this layer revalidates the stored
provider receipt against the current request/provider binding and reconstructs
the exact actor result. Local store tampering is therefore a known pre-effect
rejection rather than a trusted replay or false remote uncertainty.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from genesis_v18_7_40_third_wish_capability_fabric import ActionIntent
from tools.genesis_third_wish_external_identity_broker import (
    IdentityEffectReceiptIntegrityError,
)
from tools.genesis_third_wish_external_identity_recovery import (
    RecoverableThirdWishExternalIdentityBroker,
)


class VerifiedReplayThirdWishExternalIdentityBroker(
    RecoverableThirdWishExternalIdentityBroker
):
    """Final reference class for v18.7.44."""

    def preflight(self, intent: ActionIntent) -> Mapping[str, Any]:
        result = dict(super().preflight(intent))
        existing = self.effect_store.get(intent.request_id)
        if not isinstance(existing, Mapping) or existing.get("state") != "SETTLED":
            return result

        provider, operation, payload, effect_type = self._provider_and_payload(intent)
        binding_sha256, effect_key = self._binding(
            intent,
            provider=provider,
            operation=operation,
            payload=payload,
            effect_type=effect_type,
        )
        if (
            existing.get("capability_id") != intent.capability_id
            or existing.get("binding_sha256") != binding_sha256
            or existing.get("effect_key") != effect_key
        ):
            raise IdentityEffectReceiptIntegrityError(
                "SETTLED_IDENTITY_EFFECT_BINDING_TAMPER"
            )

        receipt = existing.get("provider_receipt")
        actor_result = existing.get("actor_result")
        if not isinstance(receipt, Mapping) or not isinstance(actor_result, Mapping):
            raise IdentityEffectReceiptIntegrityError(
                "SETTLED_IDENTITY_EFFECT_LOCAL_RECEIPT_MISSING"
            )
        verified_receipt = self._validate_receipt(
            receipt,
            effect_key=effect_key,
            provider=provider,
            effect_type=effect_type,
        )
        recovered = bool(actor_result.get("recovered_from_provider_lookup", False))
        expected_actor_result = self._actor_result(
            provider=provider,
            effect_type=effect_type,
            operation=operation,
            receipt=verified_receipt,
            recovered=recovered,
        )
        if copy.deepcopy(dict(actor_result)) != expected_actor_result:
            raise IdentityEffectReceiptIntegrityError(
                "SETTLED_IDENTITY_EFFECT_ACTOR_RESULT_TAMPER"
            )
        result["settled_local_replay_integrity_verified"] = True
        return result


EXTERNAL_IDENTITY_FINAL_CLAIMS = {
    "final_reference_class": "VerifiedReplayThirdWishExternalIdentityBroker",
    "settled_local_receipt_revalidated_before_replay": True,
    "settled_actor_result_reconstructed_before_replay": True,
    "local_settled_store_tamper_trusted": False,
    "local_settled_store_tamper_is_pre_effect_rejection": True,
}
