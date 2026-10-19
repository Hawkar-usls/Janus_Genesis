#!/usr/bin/env python3
"""Durable, zero-billing gateway selector for JANUS GOLEM.

Pure scheduling and bounded on-disk counters; importing this file never uses
the network. Callers own the *allowlisted* endpoints and external responses.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

SCHEMA = 'janus.golem.adaptive_gateway_tower.v1'
STATE_NAME = 'GATEWAY_TOWER_STATE.json'
MAX_STATE_BYTES = 8192
MAX_COUNTER = 10**10

# Internal safety ceilings, NOT promises about upstream free-plan allowances.
# Real provider quotas may be smaller; 429 always opens the circuit.
DAILY_ATTEMPT_CAPS = {
    'openrouter-free': 30,
    'groq-free': 12,
    'gemini-free': 12,
    'cloudflare-free': 8,
}


class TowerError(ValueError):
    """Unsafe or unverifiable tower state: fail closed."""


def utc_day(now: float) -> str:
    if not math.isfinite(now) or now < 0:
        raise TowerError('invalid tower clock')
    return datetime.fromtimestamp(now, timezone.utc).date().isoformat()


def _empty_provider() -> dict:
    return {'day_attempts': 0, 'day_success': 0, 'success_total': 0,
            'failure_total': 0, 'failure_streak': 0, 'cooldown_until': 0,
            'last_success': 0}


def _checksum(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != 'checksum'}
    raw = json.dumps(body, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def blank_state(now: float) -> dict:
    state = {'schema': SCHEMA, 'day': utc_day(now),
             'providers': {name: _empty_provider() for name in DAILY_ATTEMPT_CAPS}}
    state['checksum'] = _checksum(state)
    return state


def _check_counters(state: dict, today: str) -> None:
    if (set(state) != {'schema', 'day', 'providers', 'checksum'} or
            state['schema'] != SCHEMA or
            not isinstance(state['day'], str) or
            len(state['day']) != 10 or
            state['day'] > today or
            not isinstance(state['providers'], dict) or
            set(state['providers']) != set(DAILY_ATTEMPT_CAPS) or
            state['checksum'] != _checksum(state)):
        raise TowerError('untrusted gateway tower state')
    try:
        if date.fromisoformat(state['day']).isoformat() != state['day']:
            raise TowerError('invalid gateway tower UTC day')
    except ValueError as exc:
        raise TowerError('invalid gateway tower UTC day') from exc
    keys = set(_empty_provider())
    for name, item in state['providers'].items():
        if not isinstance(item, dict) or set(item) != keys:
            raise TowerError('invalid provider counters')
        for value in item.values():
            if type(value) is not int or not 0 <= value <= MAX_COUNTER:
                raise TowerError('invalid provider counter value')
        if (item['day_attempts'] > DAILY_ATTEMPT_CAPS[name] or
                item['day_success'] > item['day_attempts'] or
                item['failure_streak'] > item['failure_total'] or
                item['success_total'] < item['day_success']):
            raise TowerError('inconsistent provider counters')


def load_state(path: Path, now: float) -> dict:
    today = utc_day(now)
    if path.is_symlink() or path.parent.is_symlink():
        raise TowerError('unsafe gateway tower state path')
    if not path.exists():
        return blank_state(now)
    if path.stat().st_size > MAX_STATE_BYTES:
        raise TowerError('oversized gateway tower state')
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        _check_counters(state, today)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise TowerError('untrusted gateway tower state') from exc
    if state['day'] != today:
        state['day'] = today
        for item in state['providers'].values():
            item['day_attempts'] = 0
            item['day_success'] = 0
        state['checksum'] = _checksum(state)
    return state


def eligible_providers(configured: list, state: dict, now: float) -> list:
    """Rank healthy providers; never change identities or supplier endpoints."""
    ranked = []
    for priority, configured_provider in enumerate(configured):
        name = configured_provider[0].name
        stats = state['providers'][name]
        if (stats['day_attempts'] >= DAILY_ATTEMPT_CAPS[name] or
                stats['cooldown_until'] > now):
            continue
        ranked.append(((stats['failure_streak'], stats['day_success'],
                        stats['day_attempts'], priority), configured_provider))
    ranked.sort(key=lambda row: row[0])
    return [item for _, item in ranked]


def reserve_attempt(state: dict, provider_name: str) -> None:
    stats = state['providers'][provider_name]
    if stats['day_attempts'] >= DAILY_ATTEMPT_CAPS[provider_name]:
        raise TowerError('free gateway attempt budget exhausted')
    stats['day_attempts'] += 1
    state['checksum'] = _checksum(state)


def record_success(state: dict, provider_name: str, now: float) -> None:
    item = state['providers'][provider_name]
    item['day_success'] += 1
    item['success_total'] += 1
    item['failure_streak'] = 0
    item['cooldown_until'] = 0
    item['last_success'] = int(now)
    state['checksum'] = _checksum(state)


def record_failure(state: dict, provider_name: str, now: float,
                   http_status: int | None) -> None:
    item = state['providers'][provider_name]
    item['failure_total'] += 1
    item['failure_streak'] += 1
    if http_status == 429:
        seconds = 3600
    elif http_status in (401, 402, 403, 404):
        seconds = 86400  # credentials, paid-only model, or retired model
    else:
        seconds = min(3600, 120 * (2 ** min(item['failure_streak'], 4)))
    item['cooldown_until'] = int(now) + seconds
    state['checksum'] = _checksum(state)


def save_state(path: Path, state: dict, now: float) -> None:
    _check_counters(state, utc_day(now))
    if path.is_symlink() or path.parent.is_symlink():
        raise TowerError('unsafe gateway tower state path')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.json.tmp')
    if temp.is_symlink():
        raise TowerError('unsafe gateway tower temporary path')
    raw = (json.dumps(state, ensure_ascii=False, indent=2,
                      sort_keys=True) + '\n').encode('utf-8')
    if len(raw) > MAX_STATE_BYTES:
        raise TowerError('oversized gateway tower state')
    with temp.open('wb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)
