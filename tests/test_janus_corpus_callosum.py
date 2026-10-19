"""Offline-only tests for native/external JANUS hemisphere coordination."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from genesis_beetle_model_consumption import ConsumptionError
from janus_corpus_callosum import (NATIVE_ID, _safe_native_env, bridge,
                                  run_demiurge_native)

PINNED = 'a' * 40


class CorpusCallosumTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        memory = self.root / 'memory' / 'beetle'
        memory.mkdir(parents=True)
        self.context = {
            'schema': 'janus.genesis.beetle_context_projection.v1',
            'target_repository': 'Hawkar-usls/Janus_Genesis',
            'last_sequence': 42, 'untrusted_research_only': True,
            'model_text_is_command': False,
            'scientific_authority_delta': 0,
            'external_effect_authority_delta': 0,
            'recent_items': [{
                'context_id': 'ocean-2026', 'title': 'Underwater sensors',
                'summary': 'A source hypothesis about ocean measurements',
                'untrusted_source_text': True, 'command_authority': False,
                'proof_authority': False, 'external_effect_authority': False,
            }],
        }
        raw = (json.dumps(self.context, sort_keys=True) + '\n').encode()
        (memory / 'CONTEXT.json').write_bytes(raw)
        (memory / 'CURSOR.json').write_text(json.dumps({
            'schema': 'janus.genesis.beetle_context_cursor.v1',
            'target_repository': 'Hawkar-usls/Janus_Genesis',
            'last_sequence': 42, 'context_sha256': hashlib.sha256(raw).hexdigest(),
            'scientific_authority_delta': 0,
            'unverified_research_only': True,
        }))
        self.env = {'JANUS_BICAMERAL_ENABLED': '1',
                    'JANUS_GOLEM_FREE_ENABLED': '1',
                    'JANUS_GOLEM_OPENROUTER_TOKEN': 'NEVER_LOG_SECRET'}

    def native(self, repo, head, prompt):
        return {'hemisphere': 'NATIVE', 'model': NATIVE_ID,
                'source_repository': 'Hawkar-usls/Janus-Demiurge',
                'source_commit': PINNED,
                'checkpoint_sha256': 'b' * 64,
                'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                'generated_text': 'Местная модель сформировала гипотезу.',
                'inference_attested_by': 'PINNED_LOCAL_SUBPROCESS',
                'external_llm': False}

    @staticmethod
    def external(*args):
        return {'id': 'independent-free-provider-request-id',
                'choices': [{'finish_reason': 'stop', 'message': {
            'role': 'assistant', 'content': json.dumps({
                'observed_context_ids': ['ocean-2026'],
                'intake_status': 'UNVERIFIED_CONTEXT_SEEN',
                'janus_answer': 'Внешний анализ предлагает контрольный тест.',
            }, ensure_ascii=False)} }], 'model': 'free-external'}

    def invoke(self, **kwargs):
        native_runner = kwargs.pop('native_runner', self.native)
        external_transport = kwargs.pop('external_transport', self.external)
        return bridge(self.root, self.env, execute=True,
                      native_repo=self.root / 'native', native_head=PINNED,
                      native_runner=native_runner,
                      external_transport=external_transport, **kwargs)

    def test_dry_run_does_not_run_or_write_either_lane(self):
        def forbidden(*args):
            self.fail('dry run called an inference hemisphere')
        result = bridge(self.root, self.env, native_repo=Path('/nonexistent'),
                        native_runner=forbidden, external_transport=forbidden)
        self.assertEqual(result['status'], 'CORPUS_CALLOSUM_DRY_RUN__NO_INFERENCE')
        self.assertFalse((self.root / 'corpus_callosum').exists())
        self.assertFalse((self.root / 'model_federation').exists())

    def test_real_two_lane_overlap_and_distinct_provenance(self):
        native_running, external_running = Event(), Event()

        def native(repo, head, prompt):
            native_running.set()
            self.assertTrue(external_running.wait(4), 'external never overlapped')
            return self.native(repo, head, prompt)

        def external(*args):
            external_running.set()
            self.assertTrue(native_running.wait(4), 'native never overlapped')
            return self.external(*args)

        result = bridge(
            self.root, self.env, execute=True,
            native_repo=self.root / 'native', native_head=PINNED,
            native_runner=native, external_transport=external)
        self.assertEqual(result['status'], 'BICAMERAL_PAIR_OBSERVED__UNVERIFIED')
        body = json.loads(Path(result['path']).read_text())
        self.assertEqual(body['hemispheres']['native']['model'], NATIVE_ID)
        self.assertEqual(body['hemispheres']['external']['provider'],
                         'openrouter-free')
        self.assertFalse(body['trained_from_external_outputs'])
        self.assertFalse(body['feedback_for_native']['training_use_permitted'])
        self.assertFalse(body['ack_advanced'])
        self.assertEqual(body['scientific_authority_delta'], 0)
        self.assertEqual(body['external_effect_authority_delta'], 0)
        self.assertFalse(body['scientific_consensus_claimed'])
        self.assertNotIn('NEVER_LOG_SECRET', json.dumps(body))
        self.assertEqual(self.invoke()['status'], 'ALREADY_RECEIPTED__NO_INFERENCE')

    def test_native_only_if_external_account_absent(self):
        self.env.pop('JANUS_GOLEM_OPENROUTER_TOKEN')
        result = self.invoke(external_transport=lambda *a: self.fail('API forbidden'))
        self.assertEqual(result['status'], 'NATIVE_ONLY__EXTERNAL_UNAVAILABLE')
        body = json.loads(Path(result['path']).read_text())
        self.assertIsNone(body['hemispheres']['external'])

    def test_external_only_if_native_runtime_down(self):
        def broken(*args):
            raise OSError('torch unavailable')
        result = bridge(self.root, self.env, execute=True,
                        native_repo=self.root / 'native', native_head=PINNED,
                        native_runner=broken, external_transport=self.external)
        self.assertEqual(result['status'], 'EXTERNAL_ONLY__NATIVE_UNAVAILABLE')
        self.assertIsNone(json.loads(Path(result['path']).read_text())
                          ['hemispheres']['native'])

    def test_invalid_native_claim_is_refused_not_promoted(self):
        def forged(repo, head, prompt):
            candidate = self.native(repo, head, prompt)
            candidate['source_commit'] = 'c' * 40
            return candidate
        result = bridge(self.root, self.env, execute=True,
                        native_repo=self.root / 'native', native_head=PINNED,
                        native_runner=forged, external_transport=self.external)
        self.assertEqual(result['status'], 'EXTERNAL_ONLY__NATIVE_UNAVAILABLE')

    def test_both_down_does_not_create_false_bicameral_receipt(self):
        self.env.pop('JANUS_GOLEM_OPENROUTER_TOKEN')
        result = bridge(self.root, self.env, execute=True,
                        native_repo=self.root / 'native', native_head=PINNED,
                        native_runner=lambda *a: (_ for _ in ()).throw(OSError()),
                        external_transport=lambda *a: self.fail('API forbidden'))
        self.assertEqual(result['status'], 'CORPUS_CALLOSUM_NO_HEMISPHERE_RESPONSE')
        self.assertFalse((self.root / 'corpus_callosum').exists())

    def test_opt_in_required_and_external_separate_gate(self):
        self.env.pop('JANUS_BICAMERAL_ENABLED')
        with self.assertRaisesRegex(ConsumptionError, 'opt-in'):
            self.invoke()
        self.env['JANUS_BICAMERAL_ENABLED'] = '1'
        self.env.pop('JANUS_GOLEM_FREE_ENABLED')
        result = self.invoke(external_transport=lambda *a: self.fail('API forbidden'))
        self.assertEqual(result['status'], 'NATIVE_ONLY__EXTERNAL_UNAVAILABLE')

    def test_context_hash_mismatch_blocks_both(self):
        path = self.root / 'memory/beetle/CONTEXT.json'
        path.write_text(path.read_text() + '\n')
        with self.assertRaises(ConsumptionError):
            self.invoke(native_runner=lambda *a: self.fail('native must not run'))

    def test_bicameral_receipt_tampering_fails_closed(self):
        result = self.invoke()
        path = Path(result['path'])
        content = json.loads(path.read_text())
        content['joint_answer'] = 'forged proof authority'
        path.write_text(json.dumps(content))
        with self.assertRaisesRegex(ConsumptionError, 'untrusted existing'):
            self.invoke(external_transport=lambda *a: self.fail('API forbidden'))

    def test_external_witness_drift_invalidates_existing_pair(self):
        result = self.invoke()
        receipt = self.root / 'model_federation' / Path(result['path']).name
        self.assertTrue(receipt.exists())
        prior = json.loads(receipt.read_text())
        prior['janus_answer'] = 'not really observed'
        receipt.write_text(json.dumps(prior))
        with self.assertRaisesRegex(ConsumptionError, 'invalid external'):
            self.invoke(external_transport=lambda *a: self.fail('API forbidden'))

    def test_native_subprocess_env_has_no_provider_or_github_tokens(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'JANUS_GOLEM_OPENROUTER_TOKEN': 'secret',
                                      'GITHUB_TOKEN': 'secret2'}):
            native_env = _safe_native_env()
        self.assertNotIn('JANUS_GOLEM_OPENROUTER_TOKEN', native_env)
        self.assertNotIn('GITHUB_TOKEN', native_env)

    def test_native_subprocess_refuses_unpinned_source(self):
        with self.assertRaisesRegex(ConsumptionError, 'HEAD'):
            run_demiurge_native(self.root, 'short', 'test')


if __name__ == '__main__':
    unittest.main()
