"""Real local Git bare-remote reliability tests; no network/AI API usage."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from genesis_beetle_model_consumption import ConsumptionError
from janus_corpus_callosum import bridge
from janus_corpus_git_publisher import PublicationError, publish
from janus_corpus_home_handoff import attest, protected_snapshot
import tests.test_janus_corpus_callosum as fixtures


def git(*args: str) -> str:
    result = subprocess.run(['git', *map(str, args)], check=True,
                            capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


class GitPublisherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = fixtures.CorpusCallosumTests(methodName='test_dry_run_does_not_run_or_write_either_lane')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bare = self.root / 'remote.git'
        self.worker = self.root / 'worker-a'
        git('init', '--bare', '--initial-branch=janus/habitat-cloud-state', self.bare)
        git('init', '--initial-branch=janus/habitat-cloud-state', self.worker)
        git('-C', self.worker, 'remote', 'add', 'origin', self.bare)
        self.home = self.worker / 'state/habitat_cloud_home'
        self.home.mkdir(parents=True)
        shutil.copytree(self.fixture.root / 'memory', self.home / 'memory')
        (self.home / 'STATE.json').write_text(json.dumps({
            'schema': 'JANUS_HABITAT_CLOUD_HOME_STATE_V1',
            'sequence': 101, 'source_writeback_default': 'DENY',
            'destructive_action': 'FORBIDDEN', 'authority_delta': 0,
        }))
        git('-C', self.worker, 'add', 'state/habitat_cloud_home')
        git('-C', self.worker, '-c', 'user.name=janus-test',
            '-c', 'user.email=janus-test@example.invalid',
            'commit', '-m', 'frozen baseline')
        git('-C', self.worker, 'push', '-u', 'origin',
            'HEAD:refs/heads/janus/habitat-cloud-state')
        self.baseline_sha = git('-C', self.worker, 'rev-parse', 'HEAD')
        self.baseline = protected_snapshot(self.home)

    def infer(self, *, native_only=False):
        env = dict(self.fixture.env)
        if native_only:
            env.pop('JANUS_GOLEM_OPENROUTER_TOKEN')
        result = bridge(self.home, env, execute=True,
                        native_repo=self.root / 'native-not-used',
                        native_head=fixtures.PINNED,
                        native_runner=self.fixture.native,
                        external_transport=self.fixture.external)
        self.assertTrue(Path(result['path']).exists())

    def fresh_clone(self, name: str) -> Path:
        target = self.root / name
        git('clone', '--branch', 'janus/habitat-cloud-state', self.bare, target)
        return target

    def test_real_git_commit_and_clean_worker_b_replay(self):
        self.infer()
        pushed = publish(self.worker, baseline=self.baseline,
                         expected_native_head=fixtures.PINNED)
        self.assertEqual(pushed['status'],
                         'BICAMERAL_RECEIPT_COMMITTED__NOT_MODEL_TRUTH')
        self.assertNotEqual(pushed['commit'], self.baseline_sha)
        fresh = self.fresh_clone('clean-worker-b')
        observed = attest(fresh / 'state/habitat_cloud_home',
                          baseline=self.baseline, require_receipt=True,
                          expected_native_head=fixtures.PINNED)
        self.assertEqual(observed['receipt_sha256'], pushed['receipt_sha256'])
        self.assertEqual(git('-C', fresh, 'rev-parse', 'HEAD'), pushed['commit'])
        self.assertEqual(publish(self.worker, baseline=self.baseline)['status'],
                         'BICAMERAL_ALREADY_DURABLE__NO_PUSH')

    def test_native_only_published_without_invented_external_receipt(self):
        self.infer(native_only=True)
        publish(self.worker, baseline=self.baseline)
        fresh = self.fresh_clone('native-only-reader')
        checked = attest(fresh / 'state/habitat_cloud_home',
                         baseline=self.baseline, require_receipt=True)
        self.assertIsNone(checked['referenced_external'])

    def test_crash_after_local_commit_is_not_false_durability(self):
        self.infer()
        with self.assertRaisesRegex(PublicationError, 'after local Git commit'):
            publish(self.worker, baseline=self.baseline, interrupt_at='after_commit')
        clean = self.fresh_clone('after-local-crash')
        self.assertEqual(git('-C', clean, 'rev-parse', 'HEAD'), self.baseline_sha)
        with self.assertRaisesRegex(ConsumptionError, 'no independently validated'):
            attest(clean / 'state/habitat_cloud_home', require_receipt=True)

    def test_crash_after_remote_push_recovers_from_clean_runner(self):
        self.infer()
        with self.assertRaisesRegex(PublicationError, 'after durable Git push'):
            publish(self.worker, baseline=self.baseline, interrupt_at='after_push')
        recovered = self.fresh_clone('after-remote-crash')
        observed = attest(recovered / 'state/habitat_cloud_home',
                          baseline=self.baseline, require_receipt=True)
        self.assertEqual(observed['status'],
                         'BICAMERAL_RECEIPT_VALIDATED__NOT_MODEL_TRUTH')

    def test_remote_ref_advancement_refuses_overwrite(self):
        self.infer()
        other = self.fresh_clone('concurrent-other')
        (other / 'safe.txt').write_text('separate Genesis HOME work\n')
        git('-C', other, 'add', 'safe.txt')
        git('-C', other, '-c', 'user.name=janus-test',
            '-c', 'user.email=janus-test@example.invalid',
            'commit', '-m', 'other cloud worker changed remote')
        git('-C', other, 'push', 'origin',
            'HEAD:refs/heads/janus/habitat-cloud-state')
        newer = git('-C', other, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(PublicationError, 'remote moved'):
            publish(self.worker, baseline=self.baseline)
        clean = self.fresh_clone('unmodified-remote')
        self.assertEqual(git('-C', clean, 'rev-parse', 'HEAD'), newer)
        self.assertTrue((clean / 'safe.txt').is_file())
        self.assertFalse((clean / 'state/habitat_cloud_home/corpus_callosum').exists())

    def test_unrelated_source_file_never_staged(self):
        self.infer()
        (self.worker / 'unexpected-token.txt').write_text('untrusted\n')
        with self.assertRaisesRegex(PublicationError, 'untracked checkout'):
            publish(self.worker, baseline=self.baseline)
        self.assertEqual(git('-C', self.worker, 'rev-parse', 'HEAD'), self.baseline_sha)

    def test_pre_staged_unrelated_file_is_rejected(self):
        self.infer()
        (self.worker / 'source_override.py').write_text('print("bad")\n')
        git('-C', self.worker, 'add', 'source_override.py')
        with self.assertRaisesRegex(PublicationError, 'non-model HOME path'):
            publish(self.worker, baseline=self.baseline)

    def test_corrupted_provider_attempt_state_is_not_published(self):
        self.infer()
        tower = self.home / 'model_federation/GATEWAY_TOWER_STATE.json'
        data = json.loads(tower.read_text())
        data['checksum'] = '0' * 64
        tower.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            publish(self.worker, baseline=self.baseline)

    def test_remote_race_during_push_refuses_nonfast_forward(self):
        self.infer()
        other = self.fresh_clone('race-other')
        import janus_corpus_git_publisher as publisher_module
        original_git = publisher_module._git

        def moving_git(repo, *args):
            if args[:2] == ('push', 'origin'):
                (other / 'other.txt').write_text('remote moved at push\n')
                git('-C', other, 'add', 'other.txt')
                git('-C', other, '-c', 'user.name=janus-test',
                    '-c', 'user.email=janus-test@example.invalid',
                    'commit', '-m', 'concurrent winner')
                git('-C', other, 'push', 'origin',
                    'HEAD:refs/heads/janus/habitat-cloud-state')
            return original_git(repo, *args)

        with patch.object(publisher_module, '_git', side_effect=moving_git):
            with self.assertRaisesRegex(PublicationError, 'Git operation failed'):
                publish(self.worker, baseline=self.baseline)
        current = self.fresh_clone('post-race')
        self.assertTrue((current / 'other.txt').is_file())
        self.assertFalse((current / 'state/habitat_cloud_home/corpus_callosum').exists())

    def test_state_or_ack_update_blocks_publication(self):
        self.infer()
        state = self.home / 'STATE.json'
        state.write_text(state.read_text() + '\n')
        with self.assertRaisesRegex(ConsumptionError, 'HOME core changed'):
            publish(self.worker, baseline=self.baseline)
        self.assertEqual(git('-C', self.worker, 'rev-parse', 'HEAD'), self.baseline_sha)


if __name__ == '__main__':
    unittest.main()
