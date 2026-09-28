#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

PATH = Path('protocol/JANUS_HABITAT_NEXUS_CLOUD_CURRENT_HEAD_INTEGRATION_VIEW_2026-09-28.json')
EXPECTED_GENESIS = '43588fc41870e78493221ccb2b69959709c245dc'
EXPECTED_SWARM = '51e3d031fd729ff215b934f954b06625272376d0'
EXPECTED_CLOUD_STATE = 'c23f1d83ba55009ea11e7f2312f9d8ddd195a902'
EXPECTED_CLOUD_RECEIPT = '956aa961eccec9d7b01c055b33fb08a75f4201357df16770007b74c85d4fc335'
EXPECTED_PRIVATE_AUTH_PATH = 'state/habitat_cloud_home/private_auth/PRIVATE_CLOUD_AUTH_OPAQUE_RECEIPT-2026-09-28.json'
REQUIRED = {
    'REAL_44_OWNER_SOURCE_EXACT_REPLAY_PRIVACY_SAFE',
    'PRIVATE_CLOUD_AUTH_AND_EXACT_PINNING',
    'PRESERVATION_LINEAGE_EXPECTED_HEAD_FAILED_VARIANT_CONFLICT_RETENTION',
    'EXCLUSIVE_LEASE_SESSION_DROP_EXACTLY_ONCE_HANDOFF',
    'RESIDENT_REAL_MODEL_CALL',
    'RESIDENT_IDENTITY_CONTINUITY',
    'CLOUD_HOME_DURABLE_RECONSTRUCTION',
    'TYPED_FEDERATION_44_OF_44_FINAL_VIEW_COMPATIBILITY',
    'ISSUE_162_CLOSED_LOOP_GAUNTLET',
}

def main() -> None:
    doc = json.loads(PATH.read_text(encoding='utf-8'))
    frozen = doc['frozen_view']
    assert frozen['genesis_main_sha'] == EXPECTED_GENESIS
    assert frozen['swarm_main_sha'] == EXPECTED_SWARM
    assert frozen['cloud_home_state_commit'] == EXPECTED_CLOUD_STATE
    assert frozen['cloud_home_receipt_sha256'] == EXPECTED_CLOUD_RECEIPT
    assert frozen['private_cloud_auth_receipt'] == EXPECTED_PRIVATE_AUTH_PATH
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
    no_pc = doc['no_pc_launch_law']
    for key in ['PC_REQUIRED','REMOTE_DESKTOP_REQUIRED','NAS_REQUIRED','LAN_REQUIRED','PROCESS_UPTIME_REQUIRED']:
        assert no_pc[key] is False
    assert no_pc['CLOUD_EXECUTION_REQUIRED'] is True
    assert no_pc['DURABLE_STATE_REQUIRED'] is True
    assert no_pc['PC_NAS_LANE'] == 'OPTIONAL_ADAPTER_NON_AUTHORITY'
    assert no_pc['private_cloud_credential_class'] == 'MANAGED_GITHUB_APP_INSTALLATION_CONNECTION'
    assert no_pc['private_cloud_auth_observed'] is True
    assert no_pc['fallback_to_personal_computer'] is False
    assert gates['REAL_44_OWNER_SOURCE_EXACT_REPLAY_PRIVACY_SAFE'] == 'HOLD_FULL_44_MATERIALIZATION_REQUIRED'
    assert gates['PRIVATE_CLOUD_AUTH_AND_EXACT_PINNING'] == 'REPLAY_REQUIRED_THIS_VIEW'
    assert gates['ISSUE_162_CLOSED_LOOP_GAUNTLET'].startswith('HOLD_')
    assert doc['current_launch_verdict'].startswith('HOLD_')
    print('CLOUD_CURRENT_HEAD_VIEW_CONTRACT=PASS')
    print('PC_REQUIRED=FALSE')
    print('REMOTE_DESKTOP_REQUIRED=FALSE')
    print('NAS_REQUIRED=FALSE')
    print('PRIVATE_CLOUD_AUTH_OBSERVED=TRUE')
    print('CLOUD_EXECUTION_REQUIRED=TRUE')
    print('SOURCE_WRITEBACK_DEFAULT=DENY')
    print('AUTHORITY_DELTA=0')
    print('ISSUE_162_RUNNABLE=FALSE')

if __name__ == '__main__':
    main()
