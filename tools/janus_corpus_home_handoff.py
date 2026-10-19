#!/usr/bin/env python3
"""Read-only pre-commit / fresh-checkout gate for bicameral HOME receipts.

This attests *record integrity*, not model truth or independent anti-rollback.
It does not perform inference, alter HOME sequence, call providers, or git push.
The caller must serialize the HOME branch and use a non-force Git push.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis_beetle_model_consumption import ConsumptionError, load_verified, sha256
from janus_corpus_callosum import (
    MAX_COMBINED_BYTES, NATIVE_ID, SCHEMA, SHA, _body_hash,
    _native_prompt, _read_external_receipt, _valid_native, _validate_existing,
)

ATTESTATION_SCHEMA = 'janus.genesis.corpus_home_handoff.v1'
CORE_PATHS = ('STATE.json', 'memory/beetle/CONTEXT.json',
              'memory/beetle/CURSOR.json')
DOC_FIELDS = {
    'schema', 'state', 'context_sequence', 'context_sha256',
    'hemispheres', 'hemisphere_statuses', 'joint_answer',
    'feedback_for_native', 'scientific_authority_delta',
    'external_effect_authority_delta', 'ack_advanced',
    'scientific_consensus_claimed', 'trained_from_external_outputs',
    'provenance_separated', 'receipt_sha256',
}


def _load_bounded_json(path: Path, limit: int) -> dict:
    if (path.is_symlink() or not path.is_file() or
            any(parent.is_symlink() for parent in path.parents)):
        raise ConsumptionError('unsafe or missing HOME file')
    raw = path.read_bytes()
    if not 0 < len(raw) <= limit:
        raise ConsumptionError('unbounded HOME file')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ConsumptionError('invalid HOME JSON')
    return value


def protected_snapshot(home: Path) -> dict:
    """Capture immutable-before/after files; model receipts are separate."""
    if home.is_symlink() or not home.is_dir():
        raise ConsumptionError('unsafe HOME directory')
    state = _load_bounded_json(home / 'STATE.json', 250_000)
    if (state.get('schema') != 'JANUS_HABITAT_CLOUD_HOME_STATE_V1' or
            type(state.get('sequence')) is not int or state['sequence'] < 0 or
            state.get('authority_delta') != 0 or
            state.get('source_writeback_default') != 'DENY' or
            state.get('destructive_action') != 'FORBIDDEN'):
        raise ConsumptionError('HOME core does not satisfy sovereignty contract')
    context, cursor, _ = load_verified(home / CORE_PATHS[1], home / CORE_PATHS[2])
    # No gate is relaxed merely because a model answers. These three files
    # must be byte-identical before and after the receipt publication.
    snapshot = {rel: sha256((home / rel).read_bytes()) for rel in CORE_PATHS}
    if (context['last_sequence'] != cursor['last_sequence'] or
            cursor['last_sequence'] < 1):
        raise ConsumptionError('invalid Beetle cursor')
    return snapshot


def attest(home: Path, *, baseline: dict | None = None,
           require_receipt: bool = False, expected_native_head: str | None = None) -> dict:
    protected = protected_snapshot(home)
    if baseline is not None and (not isinstance(baseline, dict) or
                                  baseline != protected):
        raise ConsumptionError('HOME core changed during bicameral inference')
    context, cursor, _ = load_verified(home / CORE_PATHS[1], home / CORE_PATHS[2])
    filename = f"{cursor['last_sequence']:08d}-{cursor['context_sha256'][:16]}.json"
    path = home / 'corpus_callosum' / filename
    if path.is_symlink() or path.parent.is_symlink():
        raise ConsumptionError('unsafe bicameral receipt location')
    if not path.exists():
        if require_receipt:
            raise ConsumptionError('no independently validated hemisphere receipt to persist')
        return {'schema': ATTESTATION_SCHEMA, 'status': 'NO_RECEIPT_NO_COMMIT',
                'sequence': cursor['last_sequence'], 'protected_sha256': protected,
                'scientific_authority_delta': 0, 'ack_advanced': False}

    doc = _load_bounded_json(path, MAX_COMBINED_BYTES)
    if (set(doc) != DOC_FIELDS or not _validate_existing(doc, context, cursor) or
            doc.get('provenance_separated') is not True or
            doc.get('receipt_sha256') != _body_hash(doc)):
        raise ConsumptionError('untrusted bicameral receipt content')
    lanes = doc['hemispheres']
    native, external = lanes['native'], lanes['external']
    if native is None and external is None:
        raise ConsumptionError('empty bicameral receipt')
    expected_state = (
        'BICAMERAL_PAIR_OBSERVED__UNVERIFIED' if native and external else
        'NATIVE_ONLY__EXTERNAL_UNAVAILABLE' if native else
        'EXTERNAL_ONLY__NATIVE_UNAVAILABLE')
    if doc['state'] != expected_state:
        raise ConsumptionError('claimed bicameral state differs from actual lanes')
    if native is not None:
        head = native.get('source_commit') if isinstance(native, dict) else None
        if not isinstance(head, str) or not SHA.fullmatch(head):
            raise ConsumptionError('native source commit not pinned')
        if expected_native_head is not None and head != expected_native_head:
            raise ConsumptionError('native source commit drift since execution')
        if _valid_native(native, head, _native_prompt(context, cursor)) != native:
            raise ConsumptionError('native evidence contains unreviewed data')
        if native.get('model') != NATIVE_ID:
            raise ConsumptionError('native model identity drift')

    witness_path = None
    if external is not None:
        independent = _read_external_receipt(home, context, cursor)
        if external != independent:
            raise ConsumptionError('external model receipt differs from independent witness')
        witness_path = f'model_federation/{filename}'

    segments = []
    if native is not None:
        segments.append('Личное полушарие (малая модель): ' + native['generated_text'])
    if external is not None:
        segments.append('Внешнее полушарие (' + external['provider'] + '): ' +
                        external['generated_text'])
    segments.append('Выводы моделей не являются научным доказательством.')
    if doc['joint_answer'] != '\n'.join(segments):
        raise ConsumptionError('joined output diverges from provenance lanes')
    if doc['feedback_for_native'] != {
            'external_text_is_untrusted': True,
            'external_response_sha256': external['answer_sha256'] if external else None,
            'training_use_permitted': False}:
        raise ConsumptionError('untrusted model feedback attempted privilege escalation')
    statuses = doc['hemisphere_statuses']
    if (not isinstance(statuses, dict) or
            set(statuses) != {'native', 'external_gateway'} or
            any(not isinstance(s, str) or len(s) > 200 for s in statuses.values())):
        raise ConsumptionError('invalid hemisphere availability report')

    # The return value is advisory metadata. The caller must still enforce
    # Git HEAD/ref compare-and-swap and clean fresh-checkout replay.
    return {'schema': ATTESTATION_SCHEMA,
            'status': 'BICAMERAL_RECEIPT_VALIDATED__NOT_MODEL_TRUTH',
            'sequence': cursor['last_sequence'],
            'context_sha256': cursor['context_sha256'],
            'receipt_path': f'corpus_callosum/{filename}',
            'receipt_sha256': sha256(path.read_bytes()),
            'referenced_external': witness_path,
            'protected_sha256': protected,
            'scientific_authority_delta': 0, 'ack_advanced': False,
            'self_modification_authorized': False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--home-root', required=True, type=Path)
    parser.add_argument('--baseline', type=Path,
                        help='trusted capture file from before any inference')
    parser.add_argument('--capture-baseline', type=Path,
                        help='write the core snapshot outside the HOME git checkout')
    parser.add_argument('--require-receipt', action='store_true')
    parser.add_argument('--expected-native-head')
    args = parser.parse_args()
    if args.capture_baseline:
        if args.capture_baseline.resolve().is_relative_to(args.home_root.resolve()):
            raise ConsumptionError('baseline must not be written into HOME')
        snap = protected_snapshot(args.home_root)
        args.capture_baseline.write_text(json.dumps(snap, sort_keys=True) + '\n',
                                         encoding='utf-8')
        print(json.dumps({'status': 'HOME_CORE_BASELINE_CAPTURED__NO_INFERENCE',
                          'sequence': json.loads((args.home_root / 'memory/beetle/CURSOR.json').read_text())['last_sequence']}))
        return 0
    baseline = _load_bounded_json(args.baseline, 4000) if args.baseline else None
    value = attest(args.home_root, baseline=baseline,
                   require_receipt=args.require_receipt,
                   expected_native_head=args.expected_native_head)
    print(json.dumps(value, sort_keys=True, ensure_ascii=False))
    return 0 if value['status'] != 'NO_RECEIPT_NO_COMMIT' or not args.require_receipt else 2


if __name__ == '__main__':
    raise SystemExit(main())
