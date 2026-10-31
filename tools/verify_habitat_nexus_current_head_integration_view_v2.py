#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

PATH = Path('protocol/JANUS_HABITAT_NEXUS_CURRENT_HEAD_INTEGRATION_VIEW_2026-09-28.json')
EXPECTED_GENESIS = '8e6576556aa4e7821bbe5408e56f6fee7922ce7b'
EXPECTED_SWARM = '51e3d031fd729ff215b934f954b06625272376d0'
REQUIRED = {
    'REAL_44_OWNER_SOURCE_EXACT_REPLAY_PRIVACY_SAFE',
    'PRESERVATION_LINEAGE_EXPECTED_HEAD_FAILED_VARIANT_CONFLICT_RETENTION',
    'EXCLUSIVE_LEASE_SESSION_DROP_EXACTLY_ONCE_HANDOFF',
    'RESIDENT_REAL_MODEL_CALL',
    'RESIDENT_IDENTITY_CONTINUITY',
    'REMOTE_LIVE_HOME_CURRENT_VIEW',
    'TYPED_FEDERATION_44_OF_44_FINAL_VIEW_COMPATIBILITY',
    'LIVE_NAS_HR1_HR10',
    'ISSUE_162_CLOSED_LOOP_GAUNTLET',
}


def main() -> None:
    doc = json.loads(PATH.read_text(encoding='utf-8'))
    frozen = doc['frozen_view']
    assert frozen['genesis_main_sha'] == EXPECTED_GENESIS
    assert frozen['swarm_main_sha'] == EXPECTED_SWARM
    gates = doc['required_gates']
    assert set(gates) == REQUIRED
    laws = doc['laws']
    assert laws['SOURCE_WRITEBACK_DEFAULT'] == 'DENY'
    assert laws['DESTRUCTIVE_ACTION'] == 'FORBIDDEN'
    assert laws['HISTORY_REWRITE'] is False
    assert laws['AUTHORITY_DELTA'] == 0
    assert laws['COMPONENT_CI_NE_INTEGRATION_PASS'] is True
    assert laws['SYNTHETIC_44_NE_REAL_OWNER_44'] is True
    assert laws['OLD_PASS_NE_NEW_SHA_PASS_UNLESS_REPLAYED'] is True
    assert laws['CI_GREEN_NE_LAUNCH_PASS'] is True
    assert gates['REAL_44_OWNER_SOURCE_EXACT_REPLAY_PRIVACY_SAFE'].startswith('HOLD_')
    assert gates['LIVE_NAS_HR1_HR10'].startswith('HOLD_')
    assert gates['REMOTE_LIVE_HOME_CURRENT_VIEW'].startswith('HOLD_')
    assert gates['ISSUE_162_CLOSED_LOOP_GAUNTLET'].startswith('HOLD_')
    assert doc['current_launch_verdict'].startswith('HOLD_')
    blocker = doc['live_nas_blocker']
    assert blocker['epistemic_status'] == 'REMOTE_EXECUTION_PATH_UNAVAILABLE'
    assert 'NAS_FAILED' in blocker['must_not_be_relabelled_as']
    print('CURRENT_HEAD_VIEW_CONTRACT=PASS')
    print('SOURCE_WRITEBACK_DEFAULT=DENY')
    print('AUTHORITY_DELTA=0')
    print('PHYSICAL_GATES_FALSE_PROMOTION=REJECTED')
    print('ISSUE_162_RUNNABLE=FALSE')


if __name__ == '__main__':
    main()
