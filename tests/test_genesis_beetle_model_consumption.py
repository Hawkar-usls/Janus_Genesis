"""Provider-model consumption requires a real, context-bound response."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from genesis_beetle_model_consumption import (ConsumptionError, consume,
                                               load_verified, make_receipt)


class ModelConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.memory = self.home / 'memory' / 'beetle'
        self.memory.mkdir(parents=True)
        self.context = {'schema': 'janus.genesis.beetle_context_projection.v1',
                        'target_repository': 'Hawkar-usls/Janus_Genesis',
                        'last_sequence': 17, 'untrusted_research_only': True,
                        'model_text_is_command': False,
                        'scientific_authority_delta': 0,
                        'external_effect_authority_delta': 0,
                        'recent_items': [{
                            'context_id': 'source-123',
                            'title': 'Ocean sensing',
                            'summary': 'unverified hypothesis',
                            'untrusted_source_text': True,
                            'command_authority': False,
                            'proof_authority': False,
                            'external_effect_authority': False,
                        }]}
        self.write(self.context)
        self.receipts = self.home / 'model_consumption'

    def write(self, context):
        raw = (json.dumps(context, sort_keys=True) + '\n').encode()
        (self.memory / 'CONTEXT.json').write_bytes(raw)
        self.cursor = {'schema': 'janus.genesis.beetle_context_cursor.v1',
                       'target_repository': 'Hawkar-usls/Janus_Genesis',
                       'last_sequence': 17, 'context_sha256': hashlib.sha256(raw).hexdigest(),
                       'scientific_authority_delta': 0,
                       'unverified_research_only': True}
        (self.memory / 'CURSOR.json').write_text(json.dumps(self.cursor))

    @staticmethod
    def good_response():
        return {'id': 'api-request-secret', 'choices': [
            {'finish_reason': 'stop', 'message': {'role': 'assistant', 'content':
             json.dumps({'observed_context_ids': ['source-123'],
                         'intake_status': 'UNVERIFIED_CONTEXT_SEEN'})}}]}

    def test_real_response_creates_hash_bound_receipt_and_replay_skips_api(self):
        calls = []

        def fake_api(url, token, model, payload):
            calls.append(json.loads(payload))
            return self.good_response()

        result = consume(self.memory / 'CONTEXT.json', self.memory / 'CURSOR.json',
                         self.receipts, endpoint='https://model.example/v1/chat/completions',
                         token='secret', model='configured-model', transport=fake_api)
        self.assertEqual(result['context_sequence'], 17)
        receipt = json.loads(Path(result['path']).read_text())
        self.assertEqual(receipt['context_sha256'], self.cursor['context_sha256'])
        self.assertEqual(receipt['observed_context_ids'], ['source-123'])
        self.assertEqual(receipt['scientific_authority_delta'], 0)
        self.assertFalse(receipt['ack_advanced'])
        self.assertNotIn('api-request-secret', json.dumps(receipt))
        self.assertEqual(consume(self.memory / 'CONTEXT.json', self.memory / 'CURSOR.json',
                         self.receipts, endpoint='', token='', model='configured-model',
                         transport=fake_api)['status'], 'ALREADY_RECEIPTED')
        self.assertEqual(len(calls), 1)

    def test_staging_only_never_creates_consumption_receipt(self):
        load_verified(self.memory / 'CONTEXT.json', self.memory / 'CURSOR.json')
        self.assertFalse(self.receipts.exists())

    def test_response_must_name_actual_context(self):
        context, cursor, prompt = load_verified(self.memory / 'CONTEXT.json',
                                                self.memory / 'CURSOR.json')
        for content in ['{}', '{"observed_context_ids": ["invented"], "intake_status": "UNVERIFIED_CONTEXT_SEEN"}',
                        '{"observed_context_ids": ["source-123"], "intake_status": "PROVED"}']:
            response = self.good_response()
            response['choices'][0]['message']['content'] = content
            with self.assertRaises(ConsumptionError):
                make_receipt(context, cursor, prompt, response, 'model')

    def test_no_receipt_on_truncated_or_invalid_response(self):
        bad = self.good_response()
        bad['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ConsumptionError):
            consume(self.memory / 'CONTEXT.json', self.memory / 'CURSOR.json',
                    self.receipts, endpoint='https://model.example', token='x',
                    model='m', transport=lambda *args: bad)
        self.assertFalse(self.receipts.exists())

    def test_hash_mismatch_and_unsafe_context_refused(self):
        self.context['recent_items'][0]['command_authority'] = True
        self.write(self.context)
        with self.assertRaises(ConsumptionError):
            load_verified(self.memory / 'CONTEXT.json', self.memory / 'CURSOR.json')
        self.assertFalse(self.receipts.exists())


if __name__ == '__main__':
    unittest.main()
