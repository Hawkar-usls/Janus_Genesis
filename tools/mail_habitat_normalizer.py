#!/usr/bin/env python3
"""JANUS MAIL Habitat v0.1 offline normalizer.

This module intentionally performs no network calls and has no Gmail write path.
It converts an already-authorized runtime mail event into a privacy-bounded
MAIL_OBSERVATION receipt suitable for deterministic replay and public fixtures.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

SCHEMA = "janus.mail_observation.v0.1"
EVENT_CLASSES = {
    "INTEREST",
    "QUESTION",
    "REFERRAL",
    "DECLINE",
    "DATA_OFFER",
    "REVIEW_FEEDBACK",
    "EXPERIMENTAL_RESULT",
    "INSTITUTIONAL_RESPONSE",
    "MUSEUM_RESPONSE",
    "OTHER",
}

_REQUIRED_INPUT = {
    "provider",
    "provider_message_id",
    "provider_thread_id",
    "sender",
    "subject",
    "event_class",
    "project_id",
    "next_gate",
    "observed_at",
}


def _sha(label: str, value: str) -> str:
    payload = f"JANUS_MAIL_HABITAT_V0_1::{label}::{value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_time(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_mail_event(event: Dict[str, Any]) -> Dict[str, Any]:
    missing = sorted(_REQUIRED_INPUT - set(event))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    if event["provider"] not in {"gmail", "other_mail_provider"}:
        raise ValueError("unsupported provider")
    if event["event_class"] not in EVENT_CLASSES:
        raise ValueError("unsupported event_class")

    observed_at = _validate_time(str(event["observed_at"]))
    message_ref = _sha("MESSAGE", str(event["provider_message_id"]))
    thread_ref = _sha("THREAD", str(event["provider_thread_id"]))
    sender_ref = _sha("SENDER", str(event["sender"]).strip().lower())
    subject_ref = _sha("SUBJECT", str(event["subject"]))

    observation_seed = "|".join(
        [
            SCHEMA,
            str(event["provider"]),
            message_ref,
            thread_ref,
            str(event["event_class"]),
            str(event["project_id"]),
            str(event["next_gate"]),
            observed_at,
        ]
    )
    observation_id = "MAILOBS-" + hashlib.sha256(observation_seed.encode("utf-8")).hexdigest()[:32]

    return {
        "schema": SCHEMA,
        "observation_id": observation_id,
        "observed_at": observed_at,
        "provider": event["provider"],
        "message_ref_sha256": message_ref,
        "thread_ref_sha256": thread_ref,
        "sender_ref_sha256": sender_ref,
        "subject_ref_sha256": subject_ref,
        "event_class": event["event_class"],
        "project_id": str(event["project_id"]),
        "next_gate": str(event["next_gate"]),
        "body_present": bool(event.get("body")),
        "attachment_count": int(event.get("attachment_count", 0)),
        "semantic_status": "OBSERVATION_ONLY",
        "privacy": {
            "raw_body_mirrored": False,
            "raw_subject_mirrored": False,
            "raw_sender_mirrored": False,
            "provider_ids_mirrored": False,
        },
        "authority": {
            "authority_delta": 0,
            "writeback_permitted": False,
            "send_permitted": False,
            "destructive_action_permitted": False,
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Normalize one local mail-event JSON file")
    parser.add_argument("input", help="path to private/runtime input fixture")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as fh:
        event = json.load(fh)
    print(json.dumps(normalize_mail_event(event), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
