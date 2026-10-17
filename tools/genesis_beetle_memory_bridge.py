#!/usr/bin/env python3
"""Load ACKed Beetle discoveries into bounded, durable Genesis context.

This is data ingestion, never proof admission or external-effect authority.
The source inbox and the resident/HOME state are separate Git branches; the
calling workflow commits the cursor, projection and tick receipt together.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from typing import Any

REPOSITORY = 'Hawkar-usls/Janus_Genesis'
ACK_STATUS = 'INBOX_DURABLE_UNVERIFIED__NOT_RUNTIME_CONSUMPTION'
CLAIM_CEILING = 'DISCOVERY_MEMORY_ONLY__TARGET_REPO_MUST_VERIFY_INDEPENDENTLY'
EPISTEMIC_STATUS = 'DISCOVERY_INBOX__UNVERIFIED__NO_PROOF_AUTHORITY'
CURSOR_SCHEMA = 'janus.genesis.beetle_context_cursor.v1'
PROJECTION_SCHEMA = 'janus.genesis.beetle_context_projection.v1'
QUEUE_SCHEMA = 'janus.beetle.delivery_queue.v1'
ZERO = '0' * 64
MAX_MANIFEST_BYTES = 32_000_000
MAX_BATCH_BYTES = 4_000_000
MAX_RECENT_ITEMS = 24


class BeetleBridgeError(ValueError):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def _load(path: Path, default=None):
    _assert_safe_parents(path)
    if not path.exists():
        return default
    if path.is_symlink() or not path.is_file():
        raise BeetleBridgeError(f'unsafe memory path: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def _assert_safe_parents(path: Path):
    # Existing ancestors are checked as well as the leaf. The workflow's
    # writeback cannot be redirected outside its isolated checked-out HOME.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise BeetleBridgeError(f'unsafe symlink component: {parent}')


def _json_bytes(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def _atomic(path: Path, data: bytes):
    _assert_safe_parents(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    _assert_safe_parents(temp)
    temp.write_bytes(data)
    temp.replace(path)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clip(value: Any, n: int) -> str:
    return ' '.join(str(value or '').split())[:n]


def _project(item: dict, batch_id: str) -> dict:
    return {
        'context_id': _clip(item.get('context_id'), 128),
        'candidate_id': _clip(item.get('candidate_id'), 128),
        'batch_id': batch_id,
        'mirror_lens': _clip(item.get('mirror_lens'), 32),
        'title': _clip(item.get('title'), 180),
        'summary': _clip(item.get('summary'), 500),
        'source': _clip(item.get('source'), 80),
        'url': _clip(item.get('url'), 300),
        'source_context_sha256': item.get('source_context_sha256'),
        'delivery_preview_only': True,
        'delivery_preview_truncated': item.get('delivery_preview_truncated') is True,
        'epistemic_status': EPISTEMIC_STATUS,
        'untrusted_source_text': True,
        'command_authority': False,
        'proof_authority': False,
        'external_effect_authority': False,
    }


def sync(inbox: Path, home: Path, queue: dict, *, max_batches: int = 96) -> dict:
    if max_batches < 1 or max_batches > 256:
        raise BeetleBridgeError('invalid max_batches')
    ack = _load(inbox / 'ACK.json')
    if not isinstance(ack, dict):
        return {'status': 'NO_DURABLE_ACK', 'loaded': 0, 'scientific_authority_delta': 0}
    if (ack.get('schema') != 'janus.beetle.inbox_ack.v1' or
        ack.get('target_repository') != REPOSITORY or
        ack.get('status') != ACK_STATUS or
        ack.get('scientific_authority_delta') != 0):
        raise BeetleBridgeError('receiver ACK not admissible for context loading')
    if not isinstance(queue, dict):
        raise BeetleBridgeError('producer queue is not an object')
    entries = queue.get('entries')
    if (queue.get('schema') != QUEUE_SCHEMA or
        queue.get('target_repository') != REPOSITORY or
        not isinstance(entries, list) or queue.get('next_sequence') != len(entries) + 1):
        raise BeetleBridgeError('untrusted producer queue')
    for seq, row in enumerate(entries, 1):
        if (not isinstance(row, dict) or row.get('sequence') != seq or
            not re.fullmatch(r'[0-9a-f]{20}', str(row.get('batch_id', ''))) or
            not re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256', '')))):
            raise BeetleBridgeError(f'broken queue sequence {seq}')
    ack_seq = ack.get('last_sequence')
    if type(ack_seq) is not int or ack_seq < 0 or ack_seq > len(entries):
        raise BeetleBridgeError('receiver ACK not covered by producer queue')
    if ack_seq and (ack['batch_id'] != entries[ack_seq - 1]['batch_id'] or
                    ack['sha256'] != entries[ack_seq - 1]['sha256']):
        raise BeetleBridgeError('receiver ACK SHA-256 does not match source')

    root = home / 'memory' / 'beetle'
    cursor_path = root / 'CURSOR.json'
    projection_path = root / 'CONTEXT.json'
    cursor = _load(cursor_path, {})
    projection = _load(projection_path, {})
    if cursor:
        current = cursor.get('last_sequence')
        if (cursor.get('schema') != CURSOR_SCHEMA or
            cursor.get('target_repository') != REPOSITORY or
            type(current) is not int or current < 1 or current > ack_seq or
            cursor.get('batch_id') != entries[current - 1]['batch_id'] or
            cursor.get('sha256') != entries[current - 1]['sha256'] or
            not re.fullmatch(r'[0-9a-f]{64}', str(cursor.get('rolling_sha256', ''))) or
            cursor.get('unverified_research_only') is not True or
            cursor.get('scientific_authority_delta') != 0):
            raise BeetleBridgeError('durable cursor conflicts with producer/receiver')
        if (not projection or projection.get('schema') != PROJECTION_SCHEMA or
            projection.get('last_sequence') != current or
            projection.get('target_repository') != REPOSITORY or
            projection.get('untrusted_research_only') is not True or
            projection.get('model_text_is_command') is not False or
            projection.get('scientific_authority_delta') != 0 or
            projection.get('external_effect_authority_delta') != 0 or
            cursor.get('context_sha256') != _hash(projection_path.read_bytes())):
            raise BeetleBridgeError('durable context projection integrity failed')
    else:
        current = 0
        if projection:
            raise BeetleBridgeError('unpaired context projection')

    recent = list(projection.get('recent_items', [])) if projection else []
    if projection and (not isinstance(projection.get('recent_items'), list) or
                       len(projection['recent_items']) > MAX_RECENT_ITEMS or
                       any(not isinstance(item, dict) or not item.get('untrusted_source_text') or
                           item.get('command_authority') is not False or
                       item.get('proof_authority') is not False or
                       item.get('external_effect_authority') is not False or
                       item.get('epistemic_status') != EPISTEMIC_STATUS or
                       not isinstance(item.get('context_id'), str) or
                       not item['context_id'].strip()
                           for item in recent)):
        raise BeetleBridgeError('invalid existing context projection')
    # Do not fast-path UP_TO_DATE before verifying individual context flags:
    # a hash-rewritten projection must never acquire effect/proof authority
    # merely because no fresh Beetle batch arrived during this tick.
    if current == ack_seq:
        return {'status': 'UP_TO_DATE', 'loaded': 0,
                'last_sequence': current, 'scientific_authority_delta': 0}
    rolling = cursor.get('rolling_sha256', ZERO)
    selected = entries[current:min(ack_seq, current + max_batches)]
    # Validate *all* selected payloads before advancing the durable cursor.
    new_items = []
    for entry in selected:
        batch = inbox / 'batches' / f"{entry['batch_id']}.json"
        _assert_safe_parents(batch)
        if not batch.is_file() or batch.is_symlink() or batch.stat().st_size > MAX_BATCH_BYTES:
            raise BeetleBridgeError(f"missing or oversize inbox batch {entry['batch_id']}")
        raw = batch.read_bytes()
        if _hash(raw) != entry['sha256']:
            raise BeetleBridgeError(f"inbox packet hash mismatch {entry['batch_id']}")
        data = json.loads(raw)
        if (data.get('schema') != 'janus.beetle.repo_memory_batch.v1' or
            data.get('target_repository') != REPOSITORY or
            data.get('batch_id') != entry['batch_id'] or
            data.get('claim_ceiling') != CLAIM_CEILING or
            not isinstance(data.get('items'), list) or len(data['items']) > 128):
            raise BeetleBridgeError(f"invalid inbox packet {entry['batch_id']}")
        fragment_fields = ('fragment_index', 'fragment_count', 'snapshot_items_total')
        if any(field in data for field in fragment_fields):
            if (not all(field in data for field in fragment_fields) or
                type(data['fragment_index']) is not int or
                type(data['fragment_count']) is not int or
                type(data['snapshot_items_total']) is not int or
                not 1 <= data['fragment_index'] <= data['fragment_count'] <= 256 or
                not len(data['items']) <= data['snapshot_items_total'] <= 32768):
                raise BeetleBridgeError('invalid Beetle snapshot fragment envelope')
        packet_ids = set()
        for item in data['items']:
            if (not isinstance(item, dict) or item.get('target_repository') != REPOSITORY or
                item.get('epistemic_status') != EPISTEMIC_STATUS or
                item.get('mirror_lens') not in ('FORWARD', 'REVERSE', 'COUNTEREVIDENCE', 'CONTROL') or
                not isinstance(item.get('context_id'), str) or
                not item['context_id'].strip() or len(item['context_id']) > 128 or
                not isinstance(item.get('candidate_id'), str) or
                not item['candidate_id'].strip()):
                raise BeetleBridgeError('unverified or wrong-address research item')
            if item['context_id'] in packet_ids:
                raise BeetleBridgeError('duplicate context identity inside Beetle fragment')
            packet_ids.add(item['context_id'])
            if ('source_context_sha256' in item and not
                re.fullmatch(r'[0-9a-f]{64}', str(item['source_context_sha256']))):
                raise BeetleBridgeError('invalid Beetle source context fingerprint')
            new_items.append(_project(item, entry['batch_id']))
        rolling = _hash(bytes.fromhex(rolling) + entry['sequence'].to_bytes(8, 'big') + bytes.fromhex(entry['sha256']))
    # Only a bounded read-only projection is duplicated. Original full batches
    # remain durably archived in beetle-memory and referenced by SHA-256.
    by_context = {item['context_id']: item for item in recent}
    for item in new_items:
        by_context.pop(item['context_id'], None)
        by_context[item['context_id']] = item
    latest = selected[-1]
    context = {
        'schema': PROJECTION_SCHEMA,
        'target_repository': REPOSITORY,
        'last_sequence': latest['sequence'],
        'source_batch_id': latest['batch_id'],
        'recent_items': list(by_context.values())[-MAX_RECENT_ITEMS:],
        'epistemic_status': EPISTEMIC_STATUS,
        'untrusted_research_only': True,
        'model_text_is_command': False,
        'scientific_authority_delta': 0,
        'external_effect_authority_delta': 0,
    }
    context_raw = _json_bytes(context)
    new_cursor = {
        'schema': CURSOR_SCHEMA,
        'target_repository': REPOSITORY,
        'last_sequence': latest['sequence'],
        'batch_id': latest['batch_id'],
        'sha256': latest['sha256'],
        'rolling_sha256': rolling,
        'context_sha256': _hash(context_raw),
        'recorded_at': _utc_now(),
        'unverified_research_only': True,
        'scientific_authority_delta': 0,
    }
    _atomic(projection_path, context_raw)
    _atomic(cursor_path, _json_bytes(new_cursor))
    return {'status': 'STAGED_FOR_DURABLE_STATE_COMMIT', 'loaded': len(selected),
            'last_sequence': latest['sequence'], 'remaining_acknowledged': ack_seq - latest['sequence'],
            'context_sha256': new_cursor['context_sha256'], 'scientific_authority_delta': 0}


def fetch_producer_queue() -> dict:
    """Read GitHub's contents API (not the short-lived raw-CDN cache)."""
    url = ('https://api.github.com/repos/Hawkar-usls/janus-lapis/contents/'
           'data/beetle-state/mirrors/Hawkar-usls__Janus_Genesis/delivery.json?ref=beetle-state')
    headers = {'User-Agent': 'JANUS-Genesis-Beetle-Memory-Bridge/1',
               'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
                response_bytes = response.read(MAX_MANIFEST_BYTES * 2 + 1)
            if len(response_bytes) > MAX_MANIFEST_BYTES * 2:
                raise BeetleBridgeError('producer response too large')
            payload = json.loads(response_bytes)
            if payload.get('encoding') != 'base64':
                raise BeetleBridgeError('unexpected GitHub producer content encoding')
            data = base64.b64decode(payload['content'], validate=False)
            if len(data) > MAX_MANIFEST_BYTES:
                raise BeetleBridgeError('producer queue too large')
            return json.loads(data)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < 3:
                time.sleep(1 + attempt)
    raise BeetleBridgeError(f'cannot read immutable producer queue: {last}')


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--inbox-dir', required=True)
    p.add_argument('--memory-root', required=True)
    p.add_argument('--max-batches', type=int, default=96)
    args = p.parse_args()
    outcome = sync(Path(args.inbox_dir), Path(args.memory_root), fetch_producer_queue(), max_batches=args.max_batches)
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
