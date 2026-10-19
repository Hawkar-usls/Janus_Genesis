#!/usr/bin/env python3
"""Explicit, non-force HOME Git publisher for validated bicameral receipts.

Works on a disposable checkout of the durable HOME branch. No inference or
network call is made unless --publish is passed, and that flag performs only
the configured Git origin push. The remote update is optimistic/non-force:
remote movement aborts rather than rebasing or losing somebody else's work.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
import time

from genesis_beetle_model_consumption import ConsumptionError
from golem_adaptive_tower import load_state
from janus_corpus_home_handoff import attest

STATE_SUBDIR = 'state/habitat_cloud_home'
STATE_REF = 'refs/heads/janus/habitat-cloud-state'
ALLOWED = ('state/habitat_cloud_home/corpus_callosum/',
           'state/habitat_cloud_home/model_federation/')


class PublicationError(ConsumptionError):
    pass


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(['git', '-C', str(repo), *args],
                             capture_output=True, text=True, check=True,
                             timeout=20)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Git errors can contain credential-bearing origin URLs. Suppress them.
        raise PublicationError('HOME Git operation failed or timed out') from None
    return out.stdout.strip()


def _remote_head(repo: Path) -> str:
    rows = _git(repo, 'ls-remote', '--heads', 'origin',
                'janus/habitat-cloud-state').splitlines()
    if len(rows) != 1:
        raise PublicationError('durable HOME remote ref absent or ambiguous')
    parts = rows[0].split('\t')
    if len(parts) != 2 or parts[1] != STATE_REF or len(parts[0]) != 40:
        raise PublicationError('durable HOME remote ref malformed')
    return parts[0]


def _paths(repo: Path, *args: str) -> list[str]:
    return [s for s in _git(repo, *args).splitlines() if s]


def publish(repo: Path, *, baseline: dict,
            expected_native_head: str | None = None,
            interrupt_at: str | None = None) -> dict:
    """Validate, stage, commit, CAS-push, and independently check remote HEAD.

    `interrupt_at` exists solely for deterministic local crash-injection tests.
    The only production CLI entrypoint does not expose this argument.
    """
    if repo.is_symlink() or not (repo / '.git').is_dir():
        raise PublicationError('HOME publishing requires a real local Git checkout')
    home = repo / STATE_SUBDIR
    witness = attest(home, baseline=baseline, require_receipt=True,
                     expected_native_head=expected_native_head)
    original = _git(repo, 'rev-parse', 'HEAD')
    if original != _remote_head(repo):
        raise PublicationError('HOME remote moved before append-only publication')

    # Reject every modification outside the two model-specific append-only
    # directories, including pre-staged changes. Never stage STATE or ACK.
    for name in _paths(repo, 'diff', '--name-only') + _paths(repo, 'diff', '--cached', '--name-only'):
        if not name.startswith(ALLOWED):
            raise PublicationError('non-model HOME path changed during inference')
    for name in _paths(repo, 'ls-files', '--others', '--exclude-standard'):
        if not name.startswith(ALLOWED):
            raise PublicationError('unexpected untracked checkout artifact')
    receipt_relative = f"{STATE_SUBDIR}/{witness['receipt_path']}"
    if not (repo / receipt_relative).is_file():
        raise PublicationError('bicameral receipt disappeared before staging')
    stage = [receipt_relative]
    if witness['referenced_external']:
        stage.append(f"{STATE_SUBDIR}/{witness['referenced_external']}")
    tower = repo / STATE_SUBDIR / 'model_federation/GATEWAY_TOWER_STATE.json'
    if tower.is_file():
        load_state(tower, time.time())  # Corrupt or tampered free-tier counters fail closed.
        stage.append(f'{STATE_SUBDIR}/model_federation/GATEWAY_TOWER_STATE.json')
    if any(name not in stage for name in
           _paths(repo, 'ls-files', '--others', '--exclude-standard')):
        raise PublicationError('unexpected untracked model artifact')
    for name in _paths(repo, 'diff', '--name-only') + _paths(repo, 'diff', '--cached', '--name-only'):
        if name not in stage:
            raise PublicationError('unexpected tracked model artifact')
    _git(repo, 'add', '--', *stage)
    cached = _paths(repo, 'diff', '--cached', '--name-only')
    if any(name not in stage for name in cached):
        raise PublicationError('unreviewed file staged for HOME commit')
    if receipt_relative not in cached:
        if original != _remote_head(repo):
            raise PublicationError('remote moved during idempotent replay')
        return {'status': 'BICAMERAL_ALREADY_DURABLE__NO_PUSH',
                'commit': original, 'receipt_sha256': witness['receipt_sha256'],
                'ack_advanced': False, 'scientific_authority_delta': 0}
    # Recheck after Git staging; neither STATE nor Beetle cursor may drift.
    attest(home, baseline=baseline, require_receipt=True,
           expected_native_head=expected_native_head)
    _git(repo, '-c', 'user.name=janus-corpus[bot]',
         '-c', 'user.email=janus-corpus[bot]@users.noreply.github.com',
         'commit', '-m',
         f"JANUS bicameral receipt seq {witness['sequence']} (unverified)")
    committed = _git(repo, 'rev-parse', 'HEAD')
    if interrupt_at == 'after_commit':
        raise PublicationError('simulated runner death after local Git commit')
    _git(repo, 'push', 'origin', f'HEAD:{STATE_REF}')
    if interrupt_at == 'after_push':
        raise PublicationError('simulated runner death after durable Git push')
    if _remote_head(repo) != committed:
        raise PublicationError('remote HOME did not confirm model commit')
    return {'status': 'BICAMERAL_RECEIPT_COMMITTED__NOT_MODEL_TRUTH',
            'commit': committed, 'receipt_sha256': witness['receipt_sha256'],
            'ack_advanced': False, 'scientific_authority_delta': 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--expected-native-head')
    parser.add_argument('--publish', action='store_true',
                        help='explicitly commit and push only validated model receipts')
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    home = args.checkout / STATE_SUBDIR
    if not args.publish:
        outcome = attest(home, baseline=baseline,
                         expected_native_head=args.expected_native_head)
        outcome['git_push_performed'] = False
        print(json.dumps(outcome, sort_keys=True, ensure_ascii=False))
        return 0
    outcome = publish(args.checkout, baseline=baseline,
                      expected_native_head=args.expected_native_head)
    print(json.dumps(outcome, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
