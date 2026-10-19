#!/usr/bin/env python3
"""JANUS bicameral bridge: native Demiurge + permitted GOLEM free federation.

One user intent is sent to two independently labelled inference hemispheres.
This tool is disabled for execution unless explicitly opted in; its offline
tests use only fake transports and never execute third-party model code.

The bridge does NOT interpret a model vote as scientific proof or authority to
patch itself. Native and external model receipts remain separate and inspectable.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable

from genesis_beetle_model_consumption import (
    ConsumptionError, compact, load_verified, sha256,
)
from golem_free_federation import (
    federate, prior_receipt_valid, request_free_provider,
)

SCHEMA = 'janus.genesis.corpus_callosum.v1'
NATIVE_ID = 'JANUS_DEMIURGE_NATIVE_TINY_TRANSFORMER'
EXTERNAL_ID = 'GOLEM_FREE_FEDERATION'
SHA = re.compile(r'[0-9a-f]{40}\Z')
CHECKPOINT_SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_NATIVE_OUTPUT = 1000
MAX_COMBINED_BYTES = 16000


def _native_prompt(context: dict, cursor: dict) -> str:
    """Explicitly bound, very small input for Demiurge's 128-byte context."""
    first = context['recent_items'][0]
    source = str(first['context_id'])[:24]
    summary = str(first.get('summary', ''))[:60].replace('\n', ' ')
    prompt = f'JANUS:{cursor["last_sequence"]}:{source}:{summary}'
    while len(prompt.encode('utf-8')) > 96:
        prompt = prompt[:-1]
    return prompt


def _safe_native_env() -> dict[str, str]:
    """Never let native subprocess inherit GitHub, provider, or billing secrets."""
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1',
            'PYTHONPATH': '', 'OMP_NUM_THREADS': '1',
            'CUDA_VISIBLE_DEVICES': ''}


def run_demiurge_native(repo: Path, expected_head: str,
                        prompt: str) -> dict:
    """Invoke native weights from an explicitly pinned, clean local checkout.

    The checkout and its PyTorch dependency are provisioned by the operator;
    this function does not clone repos, fetch packages, or download a model.
    """
    if not SHA.fullmatch(expected_head):
        raise ConsumptionError('native Demiurge HEAD must be a full commit SHA')
    if repo.is_symlink() or not repo.is_dir():
        raise ConsumptionError('invalid native repository directory')
    head = subprocess.run(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, timeout=5, check=True,
        env=_safe_native_env(),
    ).stdout.strip()
    if head != expected_head:
        raise ConsumptionError('native Demiurge checkout changed')
    dirty = subprocess.run(
        ['git', '-C', str(repo), 'status', '--porcelain'],
        capture_output=True, text=True, timeout=5, check=True,
        env=_safe_native_env(),
    ).stdout.strip()
    if dirty:
        raise ConsumptionError('native Demiurge code is not a clean pinned tree')
    checkpoint = repo / 'janus_model/checkpoints/promoted.pt'
    if checkpoint.is_symlink() or not checkpoint.is_file():
        raise ConsumptionError('native promoted weights unavailable')
    if checkpoint.stat().st_size > 100_000_000:
        raise ConsumptionError('native checkpoint exceeds bounded size')
    checkpoint_hash = sha256(checkpoint.read_bytes())
    cmd = [sys.executable, '-m', 'janus_model.cli', 'run',
           '--checkpoint', str(checkpoint), '--prompt', prompt,
           '--max-new-tokens', '96', '--temperature', '0.65']
    result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True,
                            timeout=60, check=True, env=_safe_native_env())
    output = result.stdout.strip()
    if not output.startswith(prompt):
        raise ConsumptionError('native CLI did not return prompt-bound generation')
    generated = output[len(prompt):].strip()
    if not generated or len(generated) > MAX_NATIVE_OUTPUT:
        raise ConsumptionError('native CLI did not generate bounded new text')
    return {'hemisphere': 'NATIVE', 'model': NATIVE_ID,
            'source_repository': 'Hawkar-usls/Janus-Demiurge',
            'source_commit': expected_head,
            'checkpoint_sha256': checkpoint_hash,
            'prompt_sha256': sha256(prompt.encode('utf-8')),
            'generated_text': generated,
            'inference_attested_by': 'PINNED_LOCAL_SUBPROCESS',
            'external_llm': False}


def _valid_native(value: dict, expected_head: str, prompt: str) -> dict:
    if not isinstance(value, dict) or (
        value.get('hemisphere') != 'NATIVE' or
        value.get('model') != NATIVE_ID or
        value.get('source_repository') != 'Hawkar-usls/Janus-Demiurge' or
        value.get('source_commit') != expected_head or
        value.get('prompt_sha256') != sha256(prompt.encode('utf-8')) or
        value.get('inference_attested_by') != 'PINNED_LOCAL_SUBPROCESS' or
        value.get('external_llm') is not False or
        not isinstance(value.get('checkpoint_sha256'), str) or
        not CHECKPOINT_SHA.fullmatch(value['checkpoint_sha256']) or
        not isinstance(value.get('generated_text'), str) or
        not 0 < len(value['generated_text']) <= MAX_NATIVE_OUTPUT
    ):
        raise ConsumptionError('native inference output is not bound to pinned source')
    # Return an allowlisted projection; no arbitrary model-provided fields.
    return {key: value[key] for key in (
        'hemisphere', 'model', 'source_repository', 'source_commit',
        'checkpoint_sha256', 'prompt_sha256', 'generated_text',
        'inference_attested_by', 'external_llm')}


def _external_result(home: Path, env: dict[str, str], now: Callable,
                     transport: Callable) -> dict:
    return federate(home, env, execute=True, clock=now,
                    transport=transport, degraded_ok=True)


def _read_external_receipt(home: Path, context: dict, cursor: dict) -> dict | None:
    path = home / 'model_federation' / (
        f"{cursor['last_sequence']:08d}-{cursor['context_sha256'][:16]}.json")
    if path.is_symlink() or path.parent.is_symlink():
        raise ConsumptionError('unsafe external receipt path')
    if not path.is_file():
        return None
    if path.stat().st_size > 16000:
        raise ConsumptionError('oversized external receipt')
    doc = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(doc, dict) or not prior_receipt_valid(doc, cursor, context):
        raise ConsumptionError('invalid external model receipt in bicameral bridge')
    return {'hemisphere': 'EXTERNAL', 'model': doc['model_requested'],
            'provider': doc['provider'], 'model_reported': doc['model_reported'],
            'observed_context_ids': doc['observed_context_ids'],
            'generated_text': doc['janus_answer'],
            'answer_sha256': doc['janus_answer_sha256'],
            'inference_attested_by': 'GOLEM_CONTEXT_BOUND_RECEIPT',
            'external_llm': True}


def _body_hash(doc: dict) -> str:
    return sha256(compact({k: v for k, v in doc.items()
                           if k != 'receipt_sha256'}))


def _validate_existing(doc: dict, context: dict, cursor: dict) -> bool:
    return bool(isinstance(doc, dict) and
                doc.get('schema') == SCHEMA and
                doc.get('context_sequence') == cursor['last_sequence'] and
                doc.get('context_sha256') == cursor['context_sha256'] and
                doc.get('receipt_sha256') == _body_hash(doc) and
                doc.get('scientific_authority_delta') == 0 and
                doc.get('external_effect_authority_delta') == 0 and
                doc.get('ack_advanced') is False and
                doc.get('trained_from_external_outputs') is False and
                doc.get('scientific_consensus_claimed') is False and
                isinstance(doc.get('hemispheres'), dict) and
                set(doc['hemispheres']) == {'native', 'external'} and
                doc.get('state') in {
                    'BICAMERAL_PAIR_OBSERVED__UNVERIFIED',
                    'NATIVE_ONLY__EXTERNAL_UNAVAILABLE',
                    'EXTERNAL_ONLY__NATIVE_UNAVAILABLE',
                })


def _save_atomic(path: Path, doc: dict) -> None:
    if (path.is_symlink() or path.parent.is_symlink() or
            any(p.is_symlink() for p in path.parents)):
        raise ConsumptionError('unsafe Corpus Callosum receipt path')
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                     indent=2).encode('utf-8') + b'\n'
    if len(raw) > MAX_COMBINED_BYTES:
        raise ConsumptionError('oversized Corpus Callosum receipt')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never replace a previously witnessed result (even when two local
    # invocations raced through the initial existence check). A unique temp
    # file plus an exclusive same-directory hard-link is append-only on Linux.
    fd, temp_name = tempfile.mkstemp(prefix='.janus-corpus-', suffix='.tmp',
                                     dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_name, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise ConsumptionError('concurrent Corpus Callosum receipt exists; no overwrite') from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def bridge(home: Path, env: dict[str, str], *, execute: bool = False,
           native_repo: Path | None = None, native_head: str | None = None,
           native_runner: Callable = run_demiurge_native,
           external_transport: Callable = request_free_provider,
           clock: Callable = time.time) -> dict:
    context, cursor, _ = load_verified(
        home / 'memory/beetle/CONTEXT.json',
        home / 'memory/beetle/CURSOR.json')
    if not execute:
        return {'status': 'CORPUS_CALLOSUM_DRY_RUN__NO_INFERENCE',
                'native_configured': native_repo is not None,
                'context_sequence': cursor['last_sequence'],
                'no_network': True, 'no_state_write': True}
    if env.get('JANUS_BICAMERAL_ENABLED') != '1':
        raise ConsumptionError('Corpus Callosum needs explicit operator opt-in')
    if native_repo is None or native_head is None or not SHA.fullmatch(native_head):
        raise ConsumptionError('a pinned Demiurge repository is required')
    target = home / 'corpus_callosum' / (
        f"{cursor['last_sequence']:08d}-{cursor['context_sha256'][:16]}.json")
    if target.is_symlink() or target.parent.is_symlink():
        raise ConsumptionError('unsafe Corpus Callosum path')
    if target.exists():
        existing = json.loads(target.read_text(encoding='utf-8'))
        if not _validate_existing(existing, context, cursor):
            raise ConsumptionError('untrusted existing Corpus Callosum receipt')
        referenced_external = existing.get('hemispheres', {}).get('external')
        if referenced_external is not None:
            independent = _read_external_receipt(home, context, cursor)
            if (independent is None or
                    independent.get('answer_sha256') !=
                    referenced_external.get('answer_sha256') or
                    independent.get('provider') != referenced_external.get('provider')):
                raise ConsumptionError('bicameral external witness drift')
        return {'status': 'ALREADY_RECEIPTED__NO_INFERENCE',
                'context_sequence': cursor['last_sequence']}

    prompt = _native_prompt(context, cursor)
    statuses: dict[str, str] = {}
    native = None
    external = None
    # These independent calls overlap in wall-clock time. Each has its own
    # provenance and fault boundary. Only GOLEM may use external network I/O.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='janus-hemisphere') as pool:
        native_job = pool.submit(native_runner, native_repo, native_head, prompt)
        external_job = pool.submit(_external_result, home, env, clock,
                                   external_transport)
        try:
            native = _valid_native(native_job.result(), native_head, prompt)
            statuses['native'] = 'NATIVE_MODEL_RESPONDED'
        except (ConsumptionError, OSError, ValueError, subprocess.SubprocessError,
                TypeError, KeyError):
            statuses['native'] = 'NATIVE_UNAVAILABLE_OR_INVALID'
        external_status = None
        try:
            external_status = external_job.result()
            statuses['external_gateway'] = external_status['status']
        except (ConsumptionError, OSError, ValueError, TypeError, KeyError):
            statuses['external_gateway'] = 'EXTERNAL_UNAVAILABLE_OR_INVALID'

    # A malformed existing external receipt is a provenance attack, not an
    # availability failure. Always inspect and fail closed on tampering.
    external = _read_external_receipt(home, context, cursor)

    if not native and not external:
        return {'status': 'CORPUS_CALLOSUM_NO_HEMISPHERE_RESPONSE',
                'context_sequence': cursor['last_sequence'],
                'hemisphere_statuses': statuses, 'model_response_observed': False}
    state = ('BICAMERAL_PAIR_OBSERVED__UNVERIFIED' if native and external else
             'NATIVE_ONLY__EXTERNAL_UNAVAILABLE' if native else
             'EXTERNAL_ONLY__NATIVE_UNAVAILABLE')
    doc = {'schema': SCHEMA, 'state': state,
           'context_sequence': cursor['last_sequence'],
           'context_sha256': cursor['context_sha256'],
           'hemispheres': {'native': native, 'external': external},
           'hemisphere_statuses': statuses,
           'joint_answer': '\n'.join(part for part in [
               ('Личное полушарие (малая модель): ' + native['generated_text'])
               if native else '',
               ('Внешнее полушарие (' + external['provider'] + '): ' +
                external['generated_text']) if external else '',
               'Выводы моделей не являются научным доказательством.',
           ] if part),
           'feedback_for_native': {
               'external_text_is_untrusted': True,
               'external_response_sha256': external['answer_sha256']
               if external else None,
               'training_use_permitted': False,
           },
           'scientific_authority_delta': 0,
           'external_effect_authority_delta': 0,
           'ack_advanced': False,
           'scientific_consensus_claimed': False,
           'trained_from_external_outputs': False,
           'provenance_separated': True}
    doc['receipt_sha256'] = _body_hash(doc)
    _save_atomic(target, doc)
    return {'status': state, 'context_sequence': cursor['last_sequence'],
            'hemisphere_statuses': statuses, 'path': str(target),
            'model_response_observed': True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--home-root', required=True, type=Path)
    parser.add_argument('--native-repo', type=Path)
    parser.add_argument('--native-head')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    result = bridge(args.home_root, dict(os.environ), execute=args.execute,
                    native_repo=args.native_repo, native_head=args.native_head)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if not args.execute or result['status'] in {
        'BICAMERAL_PAIR_OBSERVED__UNVERIFIED',
        'ALREADY_RECEIPTED__NO_INFERENCE',
    } else 2


if __name__ == '__main__':
    raise SystemExit(main())
