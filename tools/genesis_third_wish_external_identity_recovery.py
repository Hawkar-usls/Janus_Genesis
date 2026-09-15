# -*- coding: utf-8 -*-
"""Final v18.7.44 recovery/custody layer for external identity effects.

The lower broker provides durable request/effect lineage. This descendant adds:

- one process/host execution lock spanning bind -> reconcile/execute -> receipt
  persistence, preventing two local callers from racing the same or different
  operator-identity effects through one provider boundary;
- strict provider-receipt field allowlisting so a provider cannot accidentally
  smuggle credential material back to the actor under an unreviewed field;
- explicit preservation that the lock is local process/host coordination, not
  cross-host exactly-once consensus.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from genesis_v18_7_40_third_wish_capability_fabric import ActionIntent
from janus_portable_lock_v2 import PortableProcessLockV2
from tools.genesis_third_wish_external_identity_broker import (
    IdentityEffectProvider,
    IdentityEffectReceiptIntegrityError,
    ThirdWishExternalIdentityBroker,
)

_ALLOWED_RECEIPT_FIELDS = frozenset(
    {
        "provider_receipt_id",
        "effect_key",
        "effect_acknowledged",
        "effect_type",
        "provider_kind",
        "identity_alias",
        "external_object_id",
        "external_url",
        "provider_status",
        "reversible",
    }
)


class RecoverableThirdWishExternalIdentityBroker(ThirdWishExternalIdentityBroker):
    """Final reference broker for v18.7.44."""

    @property
    def identity_effect_lock(self) -> PortableProcessLockV2:
        return PortableProcessLockV2(
            Path(self.data_dir) / "third_wish_identity_effect_execution_v18_7_44.lock"
        )

    @staticmethod
    def _validate_receipt(
        receipt: Mapping[str, Any],
        *,
        effect_key: str,
        provider: IdentityEffectProvider,
        effect_type: str,
    ) -> dict[str, Any]:
        value = copy.deepcopy(dict(receipt))
        unknown = set(value).difference(_ALLOWED_RECEIPT_FIELDS)
        if unknown:
            raise IdentityEffectReceiptIntegrityError(
                "IDENTITY_PROVIDER_RECEIPT_FIELDS_NOT_ALLOWED:"
                + ",".join(sorted(str(item) for item in unknown))
            )
        validated = ThirdWishExternalIdentityBroker._validate_receipt(
            value,
            effect_key=effect_key,
            provider=provider,
            effect_type=effect_type,
        )
        if "external_url" in validated:
            external_url = str(validated["external_url"])
            if len(external_url.encode("utf-8")) > 4096:
                raise IdentityEffectReceiptIntegrityError(
                    "IDENTITY_EXTERNAL_URL_TOO_LARGE"
                )
        if "provider_status" in validated:
            provider_status = str(validated["provider_status"])
            if len(provider_status.encode("utf-8")) > 1024:
                raise IdentityEffectReceiptIntegrityError(
                    "IDENTITY_PROVIDER_STATUS_TOO_LARGE"
                )
        if "reversible" in validated and not isinstance(
            validated["reversible"], bool
        ):
            raise IdentityEffectReceiptIntegrityError(
                "IDENTITY_REVERSIBLE_FLAG_NOT_BOOLEAN"
            )
        return validated

    def _execute_effect(self, intent: ActionIntent) -> Mapping[str, Any]:
        # Serialize the full local lifecycle. The durable effect_key/provider
        # lookup remains the crash-recovery authority after process restart.
        with self.identity_effect_lock.exclusive():
            return super()._execute_effect(intent)


EXTERNAL_IDENTITY_RECOVERY_CLAIMS = {
    "final_reference_class": "RecoverableThirdWishExternalIdentityBroker",
    "full_local_effect_lifecycle_serialized": True,
    "provider_receipt_fields_allowlisted": True,
    "provider_receipt_can_return_raw_credential_field": False,
    "effect_entering_auto_retry": False,
    "authoritative_settled_lookup_recovers_without_second_execute": True,
    "authoritative_no_effect_may_reopen_on_freshly_reauthorized_call": True,
    "unknown_lookup_can_open_retry": False,
    "cross_host_exactly_once_claimed": False,
}
