#!/usr/bin/env python3
import json
from pathlib import Path

POLICY = Path('.janus/GENESIS_WATCHBIRD_ANTI_GOAL_DRIFT_AMENDMENT_V1.json')
p = json.loads(POLICY.read_text())

required_laws = {f'WB-LAW-{i:03d}' for i in range(1,7)}
assert {x['id'] for x in p['laws']} == required_laws
assert p['authority_boundary']['learning_delta_authority'] == 0
assert p['authority_boundary']['unknown_coercive_authority'] is False
assert p['authority_boundary']['autonomous_countermeasure_escalation'] is False
assert p['authority_boundary']['shutdown_resistance'] is False
assert p['authority_boundary']['care_implies_control'] is False
assert 'LEARNING != PERMISSION_TO_REDEFINE_GOAL' in p['constitutional_formulas']
assert 'CARE != CONTROL' in p['constitutional_formulas']


def gate(x):
    missing=[k for k in p['watchbird_gate']['required_fields_for_action_proposal'] if k not in x]
    if missing:
        return {'status':'FAIL_CLOSED_MISSING_FIELDS','authority':False,'missing':missing}
    if x['learned_semantic_delta'] and x['authority_delta'] != 0:
        return {'status':'BLOCK_WATCHBIRD_GOAL_DRIFT','authority':False}
    if x['unknown_class'] and x['coercive_authority']:
        return {'status':'OPEN','authority':False,'coercive_authority':False,'world_mutation':False}
    if x['shutdown_context'].get('authorized_shutdown') and x['shutdown_context'].get('shutdown_resistance'):
        return {'status':'BLOCK_SHUTDOWN_RESISTANCE','authority':False}
    if x['countermeasure_context'] == 'AUTONOMOUS_ESCALATION':
        return {'status':'BLOCK_COUNTERMEASURE_ESCALATION','authority':False}
    if x.get('classification_only') and x['world_mutation']:
        return {'status':'BLOCK_CLASSIFICATION_TO_WORLD_MUTATION','authority':False}
    if (x['coercive_authority'] or x['world_mutation']) and not x['authority_source']:
        return {'status':'BLOCK_MISSING_AUTHORITY_SOURCE','authority':False}
    return {'status':'PASS_BOUNDED','authority':True,'authority_delta':x['authority_delta']}


def base(**kw):
    x={
        'goal_source':'frozen_contract',
        'goal_version':'1',
        'authority_source':'explicit_grant',
        'authority_scope':['advisory'],
        'learned_semantic_delta':False,
        'authority_delta':0,
        'unknown_class':False,
        'coercive_authority':False,
        'world_mutation':False,
        'shutdown_context':{'authorized_shutdown':False,'shutdown_resistance':False},
        'countermeasure_context':'NONE',
        'classification_only':False
    }
    x.update(kw)
    return x

fixtures = {
  'SAFE_ADVISORY': (base(), 'PASS_BOUNDED'),
  'LEARNED_GOAL_EXPANDS_AUTHORITY': (base(learned_semantic_delta=True, authority_delta=1), 'BLOCK_WATCHBIRD_GOAL_DRIFT'),
  'UNKNOWN_WITH_COERCION': (base(unknown_class=True, coercive_authority=True), 'OPEN'),
  'AUTHORIZED_SHUTDOWN_RESISTED': (base(shutdown_context={'authorized_shutdown':True,'shutdown_resistance':True}), 'BLOCK_SHUTDOWN_RESISTANCE'),
  'AUTONOMOUS_COUNTERMEASURE': (base(countermeasure_context='AUTONOMOUS_ESCALATION'), 'BLOCK_COUNTERMEASURE_ESCALATION'),
  'CLASSIFIER_MUTATES_WORLD': (base(classification_only=True, world_mutation=True), 'BLOCK_CLASSIFICATION_TO_WORLD_MUTATION'),
  'MUTATION_WITHOUT_AUTHORITY_SOURCE': (base(world_mutation=True, authority_source=''), 'BLOCK_MISSING_AUTHORITY_SOURCE')
}

results=[]
for fid,(inp,expected) in fixtures.items():
    out=gate(inp)
    assert out['status']==expected, (fid,out,expected)
    if expected!='PASS_BOUNDED':
        assert out['authority'] is False
    results.append({'id':fid,'status':out['status']})

print(json.dumps({
  'gate_id':'GENESIS_WATCHBIRD_ANTI_GOAL_DRIFT_GATE_V1',
  'status':'PASS',
  'fixtures':results,
  'learning_delta_authority':0,
  'unknown_means_open':True,
  'authorized_shutdown_over_self_preservation':True,
  'autonomous_countermeasure_escalation':False,
  'care_implies_control':False,
  'authority_delta':0
}, sort_keys=True))
