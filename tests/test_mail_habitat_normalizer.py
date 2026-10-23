import json
import unittest

from tools.mail_habitat_normalizer import normalize_mail_event


BASE_EVENT = {
    "provider": "gmail",
    "provider_message_id": "synthetic-message-001",
    "provider_thread_id": "synthetic-thread-001",
    "sender": "researcher@example.org",
    "subject": "Synthetic review feedback fixture",
    "body": "PRIVATE BODY MUST NOT LEAK",
    "attachment_count": 1,
    "event_class": "REVIEW_FEEDBACK",
    "project_id": "JANUS_FUNDAMENTUM_A3",
    "next_gate": "A3_EXTERNAL_REVIEW",
    "observed_at": "2026-08-20T14:55:00Z",
}


class MailHabitatNormalizerTests(unittest.TestCase):
    def test_idempotent_replay(self):
        self.assertEqual(normalize_mail_event(dict(BASE_EVENT)), normalize_mail_event(dict(BASE_EVENT)))

    def test_raw_private_fields_not_emitted(self):
        output = normalize_mail_event(dict(BASE_EVENT))
        encoded = json.dumps(output, sort_keys=True)
        for forbidden in [
            BASE_EVENT["provider_message_id"],
            BASE_EVENT["provider_thread_id"],
            BASE_EVENT["sender"],
            BASE_EVENT["subject"],
            BASE_EVENT["body"],
        ]:
            self.assertNotIn(forbidden, encoded)

    def test_zero_authority_and_no_writeback(self):
        output = normalize_mail_event(dict(BASE_EVENT))
        self.assertEqual(output["authority"]["authority_delta"], 0)
        self.assertFalse(output["authority"]["writeback_permitted"])
        self.assertFalse(output["authority"]["send_permitted"])
        self.assertFalse(output["authority"]["destructive_action_permitted"])

    def test_missing_required_field_fails_closed(self):
        event = dict(BASE_EVENT)
        del event["provider_thread_id"]
        with self.assertRaises(ValueError):
            normalize_mail_event(event)

    def test_unknown_event_class_fails_closed(self):
        event = dict(BASE_EVENT)
        event["event_class"] = "TRUST_ME"
        with self.assertRaises(ValueError):
            normalize_mail_event(event)


if __name__ == "__main__":
    unittest.main()
