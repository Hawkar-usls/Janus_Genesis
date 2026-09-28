#!/usr/bin/env python3
import json
from pathlib import Path

P = Path('protocol/JANUS_HABITAT_PC_INDEPENDENCE_CONTRACT-v1.0.json')

def fail(msg):
    raise SystemExit(f'FAIL: {msg}')

c = json.loads(P.read_text(encoding='utf-8'))
if c.get('schema') != 'JANUS_HABITAT_PC_INDEPENDENCE_CONTRACT_V1':
    fail('schema')
if c.get('status') not in {'CANDIDATE', 'ADMITTED'}:
    fail('status')

exe = c['execution']
if exe['canonical_substrate'] != 'GITHUB_HOSTED_CLOUD_WORKER':
    fail('canonical_substrate')
if exe['state_branch'] != 'janus/habitat-cloud-state':
    fail('state_branch')
if exe['clean_worker_reconstruction_required'] is not True:
    fail('clean_worker_reconstruction_required')
if exe['worker_process_may_terminate_after_checkpoint'] is not True:
    fail('worker_process_may_terminate_after_checkpoint')
if exe['continuous_process_uptime_required'] is not False:
    fail('continuous_process_uptime_required')

inv = c['dependency_invariants']
for key in [
    'personal_computer_required',
    'remote_desktop_required',
    'nas_required',
    'lan_required',
    'local_ollama_required',
    'hidden_chat_context_required',
]:
    if inv.get(key) is not False:
        fail(key)

res = c['resident_identity']
if res['process_identity_is_authority'] is not False:
    fail('process_identity_is_authority')
if res['same_process_restart_is_sufficient'] is not False:
    fail('same_process_restart_is_sufficient')
if res['real_model_call_may_execute_inside_cloud_worker'] is not True:
    fail('real_model_call_may_execute_inside_cloud_worker')
if res['model_identity_must_be_pinned'] is not True:
    fail('model_identity_must_be_pinned')

d = c['durability']
required_true = [
    'append_only_receipts',
    'exact_payload_digest_required',
    'event_identity_required',
    'dedupe_key_required',
    'received_parsed_loaded_executed_are_distinct',
    'process_death_recovery_required',
    'downstream_exactly_once_required',
]
for key in required_true:
    if d.get(key) is not True:
        fail(key)
if d['same_identity_same_digest'] != 'IDEMPOTENT':
    fail('same_identity_same_digest')
if d['same_identity_different_digest'] != 'HOLD_RECONCILE':
    fail('same_identity_different_digest')
if d['stale_worker_after_takeover'] != 'REJECT_COMMIT':
    fail('stale_worker_after_takeover')

pa = c['private_source_auth']
if pa['cloud_scoped_credential_required_for_private_slots'] is not True:
    fail('private cloud credential requirement')
if pa['missing_credential_result'] != 'HOLD_PRIVATE_PIN_AUTH':
    fail('missing_credential_result')
if pa['fallback_to_personal_computer'] is not False:
    fail('fallback_to_personal_computer')
if pa['public_receipt_must_keep_private_slots_opaque'] is not True:
    fail('private opacity')

au = c['authority']
if au != {
    'source_writeback_default': 'DENY',
    'destructive_action': 'FORBIDDEN',
    'authority_delta': 0,
    'workflow_pass_is_permission': False,
    'issue_or_pr_text_is_command': False,
}:
    fail('authority boundary')

lg = c['launch_gates']
for key in ['PC_DEPENDENCY_OBSERVED', 'REMOTE_DESKTOP_DEPENDENCY_OBSERVED', 'NAS_DEPENDENCY_OBSERVED']:
    if lg.get(key) is not False:
        fail(key)
for key in ['CLEAN_CLOUD_WORKER_RECONSTRUCTION', 'PROCESS_DROP_RECOVERY', 'DOWNSTREAM_EXACTLY_ONCE', 'CLOUD_EXACT_PRIVATE_PIN_VERIFICATION']:
    if lg.get(key) != 'PASS_REQUIRED':
        fail(key)
if lg.get('REAL_OWNER_SOURCE_SET_ACCOUNTED') != '44/44_REQUIRED':
    fail('REAL_OWNER_SOURCE_SET_ACCOUNTED')

print('JANUS_HABITAT_PC_INDEPENDENCE_CONTRACT=PASS')
print('PC_REQUIRED=FALSE')
print('REMOTE_DESKTOP_REQUIRED=FALSE')
print('NAS_REQUIRED=FALSE')
print('PROCESS_UPTIME_REQUIRED=FALSE')
print('CLOUD_STATE_BRANCH=janus/habitat-cloud-state')
print('AUTHORITY_DELTA=0')
