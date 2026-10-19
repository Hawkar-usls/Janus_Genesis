"""Free-tier federation gate never performs an API call by default."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from genesis_beetle_model_consumption import ConsumptionError
from golem_free_federation import FREE_PROVIDERS, available, federate
from golem_adaptive_tower import (DAILY_ATTEMPT_CAPS, STATE_NAME, TowerError,
    blank_state, eligible_providers, load_state, record_failure,
    reserve_attempt, save_state)


class GolemFreeFederationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        memory = self.home / 'memory' / 'beetle'
        memory.mkdir(parents=True)
        context = {
            'schema': 'janus.genesis.beetle_context_projection.v1',
            'target_repository': 'Hawkar-usls/Janus_Genesis',
            'last_sequence': 17, 'untrusted_research_only': True,
            'model_text_is_command': False,
            'scientific_authority_delta': 0,
            'external_effect_authority_delta': 0,
            'recent_items': [{
                'context_id': 'source-123', 'title': 'Ocean sensing',
                'summary': 'unverified hypothesis',
                'untrusted_source_text': True, 'command_authority': False,
                'proof_authority': False, 'external_effect_authority': False,
            }],
        }
        raw = (json.dumps(context, sort_keys=True) + '\n').encode()
        (memory / 'CONTEXT.json').write_bytes(raw)
        (memory / 'CURSOR.json').write_text(json.dumps({
            'schema': 'janus.genesis.beetle_context_cursor.v1',
            'target_repository': 'Hawkar-usls/Janus_Genesis',
            'last_sequence': 17,
            'context_sha256': hashlib.sha256(raw).hexdigest(),
            'scientific_authority_delta': 0,
            'unverified_research_only': True,
        }))

    @staticmethod
    def good_response():
        return {'id': 'provider-secret-request-id', 'model': 'some-upstream-model',
                'choices': [{'finish_reason': 'stop', 'message': {
                    'role': 'assistant', 'content': json.dumps({
                        'observed_context_ids': ['source-123'],
                        'intake_status': 'UNVERIFIED_CONTEXT_SEEN',
                        'janus_answer': 'Гипотеза требует независимой проверки.',
                    }),
                }}]}

    def test_zero_keys_or_opt_in_means_zero_network_calls(self):
        calls = []
        fake = lambda *args: calls.append(args)
        plan = federate(self.home, {}, transport=fake)
        self.assertEqual(plan['status'], 'FREE_FEDERATION_DRY_RUN__NO_NETWORK')
        self.assertEqual(plan['configured_free_providers'], [])
        self.assertGreaterEqual(plan['allowlisted_provider_count'], 4)
        self.assertFalse((self.home / 'model_federation').exists())
        with self.assertRaisesRegex(ConsumptionError, 'opt-in'):
            federate(self.home, {'JANUS_GOLEM_OPENROUTER_TOKEN': 'secret'},
                     execute=True, transport=fake)
        with self.assertRaisesRegex(ConsumptionError, 'no explicitly configured'):
            federate(self.home, {'JANUS_GOLEM_FREE_ENABLED': '1'},
                     execute=True, transport=fake)
        self.assertEqual(calls, [])

    def test_strict_no_paid_model_or_arbitrary_endpoint(self):
        for p in FREE_PROVIDERS:
            self.assertTrue(p.endpoint.startswith('https://'))
            self.assertTrue(p.model == 'openrouter/free' or
                            p.free_plan_confirmation_env)
        self.assertEqual([p.name for p, _, _ in available({
            'JANUS_GOLEM_OPENROUTER_TOKEN': 'key1',
            'JANUS_GOLEM_GROQ_TOKEN': 'key2',
            'JANUS_GOLEM_CLOUDFLARE_TOKEN': 'key3',
            'JANUS_GOLEM_CLOUDFLARE_FREE_PLAN': '1',
            'JANUS_GOLEM_CLOUDFLARE_ACCOUNT_ID': 'http://bad.example',
        })], ['openrouter-free'])

    def test_429_falls_forward_once_within_budget_and_binds_receipt(self):
        calls = []

        def mock(provider, endpoint, token, payload):
            calls.append(provider.name)
            if provider.name == 'openrouter-free':
                raise urllib.error.HTTPError(endpoint, 429, 'rate limited', {}, None)
            return self.good_response()

        env = {'JANUS_GOLEM_FREE_ENABLED': '1',
               'JANUS_GOLEM_OPENROUTER_TOKEN': 'secret1',
               'JANUS_GOLEM_GROQ_TOKEN': 'secret2',
               'JANUS_GOLEM_GROQ_FREE_PLAN': '1'}
        out = federate(self.home, env, execute=True, transport=mock)
        self.assertEqual(calls, ['openrouter-free', 'groq-free'])
        self.assertEqual(out['provider'], 'groq-free')
        receipt = json.loads(Path(out['path']).read_text())
        self.assertEqual(receipt['provider'], 'groq-free')
        self.assertEqual(receipt['observed_context_ids'], ['source-123'])
        self.assertEqual(receipt['context_sequence'], 17)
        self.assertEqual(receipt['janus_answer'], 'Гипотеза требует независимой проверки.')
        self.assertFalse(receipt['consensus_claimed'])
        self.assertFalse(receipt['ack_advanced'])
        self.assertEqual(receipt['scientific_authority_delta'], 0)
        self.assertTrue(receipt['no_paid_fallback'])
        self.assertNotIn('secret1', json.dumps(receipt))
        self.assertNotIn('provider-secret-request-id', json.dumps(receipt))
        self.assertEqual(federate(self.home, env, execute=True, transport=mock)
                         ['status'], 'ALREADY_RECEIPTED__NO_NETWORK')
        self.assertEqual(len(calls), 2)

    def test_invalid_context_or_provider_claims_never_promote(self):
        env = {'JANUS_GOLEM_FREE_ENABLED': '1',
               'JANUS_GOLEM_OPENROUTER_TOKEN': 'x'}
        for content in [
            {'observed_context_ids': ['made-up'], 'intake_status': 'UNVERIFIED_CONTEXT_SEEN',
             'janus_answer': 'Proof!'},
            {'observed_context_ids': ['source-123'], 'intake_status': 'PROVED',
             'janus_answer': 'Proof!'},
            {'observed_context_ids': ['source-123'],
             'intake_status': 'UNVERIFIED_CONTEXT_SEEN', 'janus_answer': ''},
        ]:
            fake = self.good_response()
            fake['choices'][0]['message']['content'] = json.dumps(content)
            try:
                outcome = federate(self.home, env, execute=True,
                                   transport=lambda *args: fake)
                self.assertEqual(outcome['status'],
                                 'FREE_FEDERATION_NO_ELIGIBLE_GATEWAY__NO_NETWORK')
            except ConsumptionError as exc:
                self.assertIn('all permitted', str(exc))
        self.assertEqual(list((self.home / 'model_federation').glob('000*.json')), [])

    def test_attempt_budget_fails_closed(self):
        with self.assertRaisesRegex(ConsumptionError, 'unbounded'):
            federate(self.home, {}, max_attempts=99)

    def test_tampered_prior_answer_never_suppresses_new_validation(self):
        env = {'JANUS_GOLEM_FREE_ENABLED': '1',
               'JANUS_GOLEM_OPENROUTER_TOKEN': 'secret'}
        output = federate(self.home, env, execute=True,
                          transport=lambda *args: self.good_response())
        path = Path(output['path'])
        receipt = json.loads(path.read_text())
        receipt['janus_answer'] = 'A forged independent scientific discovery'
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ConsumptionError, 'untrusted existing'):
            federate(self.home, env, execute=True,
                     transport=lambda *args: self.fail('never call model'))

    def test_cloudflare_host_cannot_be_redirected_via_account_id(self):
        env = {'JANUS_GOLEM_CLOUDFLARE_TOKEN': 'x',
               'JANUS_GOLEM_CLOUDFLARE_FREE_PLAN': '1',
               'JANUS_GOLEM_CLOUDFLARE_ACCOUNT_ID': 'a' * 32}
        p, endpoint, _ = available(env)[0]
        self.assertEqual(p.name, 'cloudflare-free')
        self.assertEqual(endpoint, 'https://api.cloudflare.com/client/v4/accounts/' +
                         'a' * 32 + '/ai/v1/chat/completions')

    def test_429_is_durable_and_next_context_skips_cooling_provider(self):
        env = {'JANUS_GOLEM_FREE_ENABLED': '1',
               'JANUS_GOLEM_OPENROUTER_TOKEN': 'topsecret',
               'JANUS_GOLEM_GROQ_TOKEN': 'topsecret2',
               'JANUS_GOLEM_GROQ_FREE_PLAN': '1'}
        calls = []

        def mock(provider, endpoint, token, payload):
            calls.append(provider.name)
            if provider.name == 'openrouter-free':
                raise urllib.error.HTTPError(endpoint, 429, 'limited', {}, None)
            return self.good_response()

        result = federate(self.home, env, execute=True, transport=mock,
                          clock=lambda: 1735689600)
        self.assertEqual(result['provider'], 'groq-free')
        state_path = self.home / 'model_federation' / STATE_NAME
        state = load_state(state_path, 1735689600)
        self.assertEqual(state['providers']['openrouter-free']['day_attempts'], 1)
        self.assertEqual(state['providers']['groq-free']['day_success'], 1)
        self.assertGreater(state['providers']['openrouter-free']['cooldown_until'],
                           1735689600)
        raw = state_path.read_text()
        self.assertNotIn('topsecret', raw)
        self.assertNotIn('limited', raw)

        self._bump_context(18)
        calls.clear()
        later = federate(self.home, env, execute=True, transport=mock,
                         clock=lambda: 1735689601)
        self.assertEqual(later['provider'], 'groq-free')
        self.assertEqual(calls, ['groq-free'])

    def _bump_context(self, sequence):
        memory = self.home / 'memory' / 'beetle'
        context_path = memory / 'CONTEXT.json'
        context = json.loads(context_path.read_text())
        context['last_sequence'] = sequence
        raw = (json.dumps(context, sort_keys=True) + '\n').encode()
        context_path.write_bytes(raw)
        cursor_path = memory / 'CURSOR.json'
        cursor = json.loads(cursor_path.read_text())
        cursor['last_sequence'] = sequence
        cursor['context_sha256'] = hashlib.sha256(raw).hexdigest()
        cursor_path.write_text(json.dumps(cursor))

    def test_no_success_is_degraded_without_receipt_and_cools_down(self):
        env = {'JANUS_GOLEM_FREE_ENABLED': '1',
               'JANUS_GOLEM_OPENROUTER_TOKEN': 'secret'}
        calls = []

        def reject(*args):
            calls.append(1)
            raise urllib.error.HTTPError('https://example.invalid', 429, '', {}, None)

        result = federate(self.home, env, execute=True, transport=reject,
                          clock=lambda: 1735689600, degraded_ok=True)
        self.assertEqual(result['status'], 'FREE_FEDERATION_DEGRADED__NO_RECEIPT')
        self.assertEqual(calls, [1])
        again = federate(self.home, env, execute=True, transport=reject,
                         clock=lambda: 1735689601, degraded_ok=True)
        self.assertEqual(again['status'],
                         'FREE_FEDERATION_NO_ELIGIBLE_GATEWAY__NO_NETWORK')
        self.assertEqual(calls, [1])
        self.assertFalse(list((self.home / 'model_federation').glob('000*.json')))

    def test_tower_rejects_tampered_counters_without_network(self):
        env = {'JANUS_GOLEM_FREE_ENABLED': '1',
               'JANUS_GOLEM_OPENROUTER_TOKEN': 'secret'}
        state_path = self.home / 'model_federation' / STATE_NAME
        save_state(state_path, blank_state(1735689600), 1735689600)
        state = json.loads(state_path.read_text())
        state['providers']['openrouter-free']['day_attempts'] = 99999
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(TowerError, 'untrusted'):
            federate(self.home, env, execute=True, clock=lambda: 1735689600,
                     transport=lambda *args: self.fail('network forbidden'))

    def test_internal_daily_cap_and_rollover(self):
        epoch = 1735689600
        state_path = self.home / 'model_federation' / STATE_NAME
        state = blank_state(epoch)
        for _ in range(DAILY_ATTEMPT_CAPS['openrouter-free']):
            reserve_attempt(state, 'openrouter-free')
        save_state(state_path, state, epoch)
        configured = available({'JANUS_GOLEM_OPENROUTER_TOKEN': 'x'})
        self.assertEqual(eligible_providers(configured, load_state(state_path, epoch),
                                            epoch), [])
        next_day = load_state(state_path, epoch + 86400)
        self.assertEqual(next_day['providers']['openrouter-free']['day_attempts'], 0)
        self.assertEqual(len(eligible_providers(configured, next_day,
                                                epoch + 86400)), 1)

    def test_unauthorized_provider_is_not_a_route(self):
        env = {'JANUS_GOLEM_OPENROUTER_TOKEN': 'a',
               'JANUS_GOLEM_GEMINI_TOKEN': 'b',
               'JANUS_GOLEM_CLOUDFLARE_TOKEN': 'c'}
        self.assertEqual([x[0].name for x in available(env)], ['openrouter-free'])


if __name__ == '__main__':
    unittest.main()
