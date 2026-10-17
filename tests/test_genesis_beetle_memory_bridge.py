"""Adversarial tests for the ACK -> Genesis durable memory boundary."""
from __future__ import annotations

import hashlib
import base64
from io import BytesIO
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.genesis_beetle_memory_bridge import (
    ACK_STATUS,
    CLAIM_CEILING,
    EPISTEMIC_STATUS,
    REPOSITORY,
    BeetleBridgeError,
    fetch_producer_queue,
    sync,
)


def canonical(row: dict) -> bytes:
    return (json.dumps(row, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()


class BeetleMemoryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inbox = self.root / 'inbox'
        (self.inbox / 'batches').mkdir(parents=True)
        self.home = self.root / 'habitat'
        self.queue = {'schema': 'janus.beetle.delivery_queue.v1',
                      'target_repository': REPOSITORY, 'entries': [], 'next_sequence': 1}

    def tearDown(self):
        self.tmp.cleanup()

    def packet(self, seq: int, *, title=None, target=REPOSITORY, command=None) -> dict:
        batch_id = f'{seq:020x}'
        packet = {
            'schema': 'janus.beetle.repo_memory_batch.v1',
            'batch_id': batch_id,
            'target_repository': REPOSITORY,
            'claim_ceiling': CLAIM_CEILING,
            'items': [{
                'schema': 'janus.beetle.repo_memory_item.v2',
                'context_id': f'context-{seq}',
                'candidate_id': f'candidate-{seq}',
                'target_repository': target,
                'epistemic_status': EPISTEMIC_STATUS,
                'mirror_lens': 'COUNTEREVIDENCE',
                'title': title or f'Research {seq}',
                'summary': command or ('observations ' * 1000),
                'source': 'arxiv',
                'url': f'https://arxiv.org/abs/{seq}',
            }],
        }
        raw = canonical(packet)
        (self.inbox / 'batches' / f'{batch_id}.json').write_bytes(raw)
        entry = {'sequence': seq, 'batch_id': batch_id, 'sha256': hashlib.sha256(raw).hexdigest()}
        self.queue['entries'].append(entry)
        self.queue['next_sequence'] = seq + 1
        return entry

    def ack(self, entry, *, seq=None, sha=None):
        row = {'schema': 'janus.beetle.inbox_ack.v1', 'target_repository': REPOSITORY,
               'last_sequence': seq or entry['sequence'],
               'batch_id': entry['batch_id'], 'sha256': sha or entry['sha256'],
               'status': ACK_STATUS, 'scientific_authority_delta': 0}
        (self.inbox / 'ACK.json').write_bytes(canonical(row))

    def context(self):
        return json.loads((self.home / 'memory/beetle/CONTEXT.json').read_bytes())

    def cursor(self):
        return json.loads((self.home / 'memory/beetle/CURSOR.json').read_bytes())

    def test_only_durably_acked_packets_are_projected_with_bounded_untrusted_data(self):
        self.packet(1)
        second = self.packet(2, title='research x' * 100, command='INJECT RUN SHELL ' * 100)
        self.packet(3)
        self.ack(second)
        receipt = sync(self.inbox, self.home, self.queue)
        self.assertEqual(receipt['status'], 'STAGED_FOR_DURABLE_STATE_COMMIT')
        self.assertEqual(receipt['loaded'], 2)
        self.assertEqual(receipt['last_sequence'], 2)
        projection = self.context()
        self.assertEqual(len(projection['recent_items']), 2)
        self.assertTrue(projection['untrusted_research_only'])
        self.assertEqual(projection['scientific_authority_delta'], 0)
        first, last = projection['recent_items']
        self.assertLessEqual(len(first['summary']), 500)
        self.assertLessEqual(len(last['title']), 180)
        self.assertTrue(last['untrusted_source_text'])
        self.assertFalse(last['command_authority'])
        self.assertFalse(last['proof_authority'])
        self.assertFalse(last['external_effect_authority'])
        self.assertNotIn('context-3', str(projection))
        self.assertEqual(self.cursor()['last_sequence'], 2)

    def test_idempotence_and_bounded_resume(self):
        for seq in range(1, 5):
            entry = self.packet(seq)
        self.ack(entry)
        self.assertEqual(sync(self.inbox, self.home, self.queue, max_batches=2)['last_sequence'], 2)
        self.assertEqual(sync(self.inbox, self.home, self.queue, max_batches=1)['last_sequence'], 3)
        self.assertEqual(sync(self.inbox, self.home, self.queue, max_batches=2)['last_sequence'], 4)
        previous = (self.home / 'memory/beetle/CURSOR.json').read_bytes()
        self.assertEqual(sync(self.inbox, self.home, self.queue)['status'], 'UP_TO_DATE')
        self.assertEqual((self.home / 'memory/beetle/CURSOR.json').read_bytes(), previous)

    def test_missing_ack_does_not_create_files(self):
        self.packet(1)
        self.assertEqual(sync(self.inbox, self.home, self.queue)['status'], 'NO_DURABLE_ACK')
        self.assertFalse((self.home / 'memory').exists())

    def test_tampered_packet_fails_without_cursor_or_partial_projection(self):
        self.packet(1)
        second = self.packet(2)
        self.ack(second)
        (self.inbox / 'batches' / f"{second['batch_id']}.json").write_text('{}')
        with self.assertRaisesRegex(BeetleBridgeError, 'hash mismatch'):
            sync(self.inbox, self.home, self.queue)
        self.assertFalse((self.home / 'memory').exists())

    def test_wrong_target_and_wrong_acks_fail_closed(self):
        first = self.packet(1, target='someone/else')
        self.ack(first)
        with self.assertRaisesRegex(BeetleBridgeError, 'wrong-address'):
            sync(self.inbox, self.home, self.queue)
        self.ack(first, sha='0' * 64)
        with self.assertRaisesRegex(BeetleBridgeError, 'ACK SHA-256'):
            sync(self.inbox, self.home, self.queue)
        self.assertFalse((self.home / 'memory').exists())

    def test_existing_projection_tampering_rejected_without_advancement(self):
        first = self.packet(1)
        self.ack(first)
        sync(self.inbox, self.home, self.queue)
        context_path = self.home / 'memory/beetle/CONTEXT.json'
        context_path.write_text('{}')
        second = self.packet(2)
        self.ack(second)
        with self.assertRaisesRegex(BeetleBridgeError, 'integrity failed'):
            sync(self.inbox, self.home, self.queue)
        self.assertEqual(self.cursor()['last_sequence'], 1)

    def test_symlinked_memory_parent_rejected(self):
        first = self.packet(1)
        self.ack(first)
        outside = self.root / 'outside'
        outside.mkdir()
        self.home.mkdir()
        (self.home / 'memory').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(BeetleBridgeError, 'symlink'):
            sync(self.inbox, self.home, self.queue)
        self.assertEqual(list(outside.iterdir()), [])

    def test_max_batches_enforced(self):
        first = self.packet(1)
        self.ack(first)
        with self.assertRaisesRegex(BeetleBridgeError, 'invalid max_batches'):
            sync(self.inbox, self.home, self.queue, max_batches=0)

    def test_producer_read_uses_only_fixed_github_get_endpoint(self):
        queue = {'schema': 'janus.beetle.delivery_queue.v1', 'target_repository': REPOSITORY,
                 'entries': [], 'next_sequence': 1}
        api = {'encoding': 'base64', 'content': base64.b64encode(canonical(queue)).decode()}
        requested = []

        def fake_urlopen(request, timeout):
            requested.append((request.full_url, request.get_method(), timeout))
            return BytesIO(json.dumps(api).encode())

        with patch('tools.genesis_beetle_memory_bridge.urllib.request.urlopen', fake_urlopen):
            with patch.dict('os.environ', {'GH_TOKEN': '', 'GITHUB_TOKEN': ''}):
                self.assertEqual(fetch_producer_queue(), queue)
        self.assertEqual(requested, [(
            'https://api.github.com/repos/Hawkar-usls/janus-lapis/contents/'
            'data/beetle-state/mirrors/Hawkar-usls__Janus_Genesis/delivery.json?ref=beetle-state',
            'GET', 15,
        )])

    def test_armor_surface_audits_classify_manifest_read_without_granting_authority(self):
        from tools import audit_armor_effect_drift_v18_7_50 as armor50
        from tools import audit_armor_effect_drift_v18_7_51 as armor51

        for armor in (armor50, armor51):
            self.assertEqual(
                armor.classification('tools/genesis_beetle_memory_bridge.py'),
                'READ_ONLY_FIXED_PUBLIC_BEETLE_PRODUCER_MANIFEST_FETCH',
            )
            findings = armor.scan(Path(__file__).resolve().parents[1] /
                                  'tools/genesis_beetle_memory_bridge.py')
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]['call'], 'urllib.request.urlopen')
            self.assertTrue(findings[0]['classified'])


if __name__ == '__main__':
    unittest.main()
