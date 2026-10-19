"""Offline fault-injection for Corpus Callosum HOME publish-and-replay."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from genesis_beetle_model_consumption import ConsumptionError
from janus_corpus_callosum import _save_atomic, _body_hash
from janus_corpus_home_handoff import attest, protected_snapshot
import tests.test_janus_corpus_callosum as fixtures


class HomeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CorpusCallosumTests(methodName='test_dry_run_does_not_run_or_write_either_lane')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home = self.fixture.root
        (self.home / 'STATE.json').write_text(json.dumps({
            'schema': 'JANUS_HABITAT_CLOUD_HOME_STATE_V1',
            'sequence': 101,
            'source_writeback_default': 'DENY',
            'destructive_action': 'FORBIDDEN',
            'authority_delta': 0,
        }))

    def run_inference(self, **kwargs):
        return self.fixture.invoke(**kwargs)

    def test_no_model_receipt_never_promotes_staged_context(self):
        result = attest(self.home)
        self.assertEqual(result['status'], 'NO_RECEIPT_NO_COMMIT')
        self.assertFalse(result['ack_advanced'])
        with self.assertRaisesRegex(ConsumptionError, 'no independently validated'):
            attest(self.home, require_receipt=True)

    def test_full_pair_replays_after_clean_core_snapshot(self):
        baseline = protected_snapshot(self.home)
        result = self.run_inference()
        verified = attest(self.home, baseline=baseline, require_receipt=True,
                          expected_native_head=fixtures.PINNED)
        self.assertEqual(verified['status'],
                         'BICAMERAL_RECEIPT_VALIDATED__NOT_MODEL_TRUTH')
        self.assertEqual(verified['receipt_path'],
                         'corpus_callosum/' + Path(result['path']).name)
        self.assertEqual(verified['referenced_external'],
                         'model_federation/' + Path(result['path']).name)
        self.assertEqual(verified['sequence'], 42)
        self.assertFalse(verified['ack_advanced'])
        self.assertFalse(verified['self_modification_authorized'])
        self.assertEqual(verified['protected_sha256'], baseline)
        # Simulated fresh read after the model subprocess is gone.
        self.assertEqual(attest(self.home, baseline=baseline,
                                require_receipt=True), verified)

    def test_native_only_does_not_need_external_model_receipt(self):
        self.fixture.env.pop('JANUS_GOLEM_OPENROUTER_TOKEN')
        self.run_inference(external_transport=lambda *a: self.fail('network forbidden'))
        verified = attest(self.home, require_receipt=True)
        self.assertIsNone(verified['referenced_external'])

    def test_external_only_does_not_claim_native_weights(self):
        self.run_inference(native_runner=lambda *a: (_ for _ in ()).throw(OSError('torch absent')))
        verified = attest(self.home, require_receipt=True)
        self.assertTrue(verified['referenced_external'])

    def test_native_commit_pin_drift_is_rejected(self):
        self.run_inference()
        with self.assertRaisesRegex(ConsumptionError, 'commit drift'):
            attest(self.home, require_receipt=True, expected_native_head='c' * 40)

    def test_state_sequence_regression_cannot_be_hidden_by_new_model_answer(self):
        original = protected_snapshot(self.home)
        self.run_inference()
        state = self.home / 'STATE.json'
        parsed = json.loads(state.read_text())
        parsed['sequence'] = 100
        state.write_text(json.dumps(parsed))
        with self.assertRaisesRegex(ConsumptionError, 'HOME core changed'):
            attest(self.home, baseline=original, require_receipt=True)

    def test_ack_cursor_change_detected_even_if_model_receipt_still_present(self):
        original = protected_snapshot(self.home)
        self.run_inference()
        cursor = self.home / 'memory/beetle/CURSOR.json'
        cursor.write_text(cursor.read_text() + '\n')
        with self.assertRaises(ConsumptionError):
            attest(self.home, baseline=original, require_receipt=True)

    def test_forged_join_is_rejected_even_with_recomputed_checksum(self):
        outcome = self.run_inference()
        receipt_path = Path(outcome['path'])
        receipt = json.loads(receipt_path.read_text())
        receipt['joint_answer'] = 'Both hemispheres proved P=NP.'
        receipt['receipt_sha256'] = _body_hash(receipt)
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ConsumptionError, 'joined output'):
            attest(self.home, require_receipt=True)

    def test_forged_external_lane_is_rejected_even_with_recomputed_checksum(self):
        outcome = self.run_inference()
        path = Path(outcome['path'])
        body = json.loads(path.read_text())
        body['hemispheres']['external']['provider'] = 'imposter-provider'
        body['receipt_sha256'] = _body_hash(body)
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ConsumptionError, 'external model receipt differs'):
            attest(self.home, require_receipt=True)

    def test_external_source_tampering_blocks_read_after_restart(self):
        outcome = self.run_inference()
        witness = self.home / 'model_federation' / Path(outcome['path']).name
        value = json.loads(witness.read_text())
        value['janus_answer'] = 'replaced vendor response'
        witness.write_text(json.dumps(value))
        with self.assertRaisesRegex(ConsumptionError, 'invalid external model'):
            attest(self.home, require_receipt=True)

    def test_symlinked_receipt_path_is_rejected(self):
        outcome = self.run_inference()
        path = Path(outcome['path'])
        contents = path.read_bytes()
        backup = self.home / 'old-receipt.json'
        backup.write_bytes(contents)
        path.unlink()
        path.symlink_to(backup)
        with self.assertRaisesRegex(ConsumptionError, 'unsafe'):
            attest(self.home, require_receipt=True)

    def test_append_only_atomic_publisher_refuses_second_writer(self):
        candidate = self.home / 'corpus_callosum' / 'immutable.json'
        docs = [dict(key=i) for i in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.try_append, [(candidate, d) for d in docs]))
        self.assertEqual(results.count('saved'), 1)
        self.assertEqual(results.count('conflict'), 7)
        self.assertIn(json.loads(candidate.read_text()), docs)
        self.assertEqual(list(candidate.parent.glob('.janus-corpus-*.tmp')), [])

    @staticmethod
    def try_append(arg):
        path, doc = arg
        try:
            _save_atomic(path, doc)
            return 'saved'
        except ConsumptionError as exc:
            if 'concurrent' not in str(exc):
                raise
            return 'conflict'


if __name__ == '__main__':
    unittest.main()
