"""ESSENCE v1.5 — adaptive quantization of research-only numeric microkernel state.

Never quantizes executable Python, root manifests or active model checkpoints.
INT4/INT8 are blockwise symmetric; FP16 fallback; FP32 stays unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

SCHEMA='janus.essence.adaptive_quantization/1.5'
POLICY={'sensing':.015,'memory':.03,'planning':.012,'verification':.002,
        'recovery':.003,'coding':.012,'essence_self':.004}
ROLES=tuple(k for k in POLICY if k!='essence_self')
HEAD=struct.Struct('<4sBHB')
PACK_MODES=(4,8,16,32)


def canonical(x):
    return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


def sha(x):return hashlib.sha256(x).hexdigest()
def seal(x):return sha(canonical(x))


def load(path):
    f=Path(path)
    if f.is_symlink() or not f.is_file() or not 2<=f.stat().st_size<=200000:
        raise ValueError('UNSAFE_OR_OVERSIZE_JSON')
    return json.loads(f.read_text(encoding='utf-8'),
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def normalized(values):
    if (not isinstance(values,list) or not 1<=len(values)<=4096 or any(
        type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e6 for x in values)):
        raise ValueError('BAD_NUMERIC_VECTOR')
    raw=struct.pack('<'+'f'*len(values),*values)
    return list(struct.unpack('<'+'f'*len(values),raw)),raw


def encode(values,bits):
    vec,raw=normalized(values)
    if type(bits) is not int or bits not in PACK_MODES:raise ValueError('BAD_BITS')
    n=len(vec)
    h=HEAD.pack(b'ESQ1',bits,n,32)
    if bits==32:return h+raw
    if bits==16:
        try:return h+b''.join(struct.pack('<e',x) for x in vec)
        except (OverflowError,struct.error) as e:raise ValueError('FP16_OVERFLOW') from e
    qmax=7 if bits==4 else 127
    scales=[];qs=[]
    for j in range(0,n,32):
        block=vec[j:j+32]
        scale=max(abs(x) for x in block)/qmax or 1.0
        scales.append(scale)
        qs.extend(max(-qmax,min(qmax,(1 if x>=0 else -1)*int(abs(x/scale)+.5))) for x in block)
    body=b''.join(struct.pack('<d',s) for s in scales)
    if bits==8:return h+body+bytes(x&255 for x in qs)
    return h+body+bytes((qs[i]&15)|((qs[i+1]&15)<<4 if i+1<n else 0)
                        for i in range(0,n,2))


def decode(packet):
    if type(packet) is not bytes or len(packet)<HEAD.size:raise ValueError('BAD_PACKET')
    magic,bits,n,block=HEAD.unpack_from(packet)
    if magic!=b'ESQ1' or bits not in PACK_MODES or not 1<=n<=4096 or block!=32:
        raise ValueError('BAD_HEADER')
    raw=packet[HEAD.size:]
    if bits in (16,32):
        size=n*(bits//8)
        if len(raw)!=size:raise ValueError('BAD_LENGTH')
        vals=list(struct.unpack('<'+('e' if bits==16 else 'f')*n,raw))
        if not all(math.isfinite(v) for v in vals):raise ValueError('NONFINITE_DECODE')
        return vals
    sn=(n+31)//32
    expected=sn*8+(n if bits==8 else (n+1)//2)
    if len(raw)!=expected:raise ValueError('BAD_LENGTH')
    scales=struct.unpack('<'+'d'*sn,raw[:sn*8])
    if any(not math.isfinite(s) or s<=0 for s in scales):raise ValueError('BAD_SCALE')
    body=raw[sn*8:]
    if bits==8:
        qs=[x-256 if x>=128 else x for x in body]
        if -128 in qs:raise ValueError('INVALID_INT8')
    else:
        qs=[]
        for x in body:qs.extend([x&15,x>>4])
        if n%2 and qs[-1]!=0:raise ValueError('INVALID_PADDING')
        qs=[x-16 if x>=8 else x for x in qs[:n]]
        if -8 in qs:raise ValueError('INVALID_INT4')
    return [x*scales[i//32] for i,x in enumerate(qs)]


def choose(values,role):
    if role not in POLICY:raise ValueError('UNKNOWN_ROLE')
    base,backup=normalized(values)
    opts=[];choice=None
    for bits in PACK_MODES:
        try:
            data=encode(base,bits);after=decode(data)
            err=max(abs(a-b) for a,b in zip(base,after))
            drift=after
            for _ in range(3):drift=decode(encode(drift,bits))
            cumulative=max(abs(a-b) for a,b in zip(base,drift))
            saving=1-len(data)/len(backup)
            allowed=bits!=32 and err<=POLICY[role] and cumulative<=POLICY[role]*1.5 and saving>=.10
            opts.append({'bits':bits,'bytes':len(data),'max_abs_error':round(err,9),
                         'four_round_drift':round(cumulative,9),
                         'saving_fraction':round(saving,6),'within_policy':allowed})
            if choice is None and allowed:choice=(bits,data)
        except ValueError:opts.append({'bits':bits,'status':'HOLD_UNREPRESENTABLE'})
    if choice is None:choice=(32,encode(base,32))
    bits,data=choice
    return {'mode':'INT'+str(bits) if bits in (4,8) else 'FP'+str(bits),
            'bits':bits,'packet':data,'snapshot':backup,'attempts':opts,
            'max_abs_error':max(abs(a-b) for a,b in zip(base,decode(data))),
            'status':'RESEARCH_QUANTIZED_ONLY' if bits!=32 else 'HOLD_NO_SAFE_SAVING'}


def validate(root,fixture):
    roles=root.get('microkernels') if isinstance(root,dict) else None
    if (not isinstance(root,dict) or root.get('schema')!='janus.essence.microkernel/0.1'
        or root.get('enabled') is not False
        or root.get('birth_policy')!='PROPOSAL_ONLY'
        or root.get('activation')!='EXPLICIT_READONLY_TEST_ONLY'
        or not isinstance(root.get('repository'),str)
        or not isinstance(root.get('capabilities'),dict)
        or set(root['capabilities'])!={'network','shell','repo_write','workflow_dispatch','secrets','hardware'}
        or any(root['capabilities'].values())
        or not isinstance(roles,list) or len(roles)!=6
        or any(not isinstance(c,dict) or type(c.get('generation')) is not int
               or c['generation']!=0 for c in roles)
        or set(c['role'] for c in roles)!=set(ROLES)):
        raise ValueError('INERT_SIX_ROLE_ROOT_REQUIRED')
    if (not isinstance(fixture,dict) or fixture.get('kind')!='SYNTHETIC_FIXTURE'
        or not isinstance(fixture.get('metrics'),dict)
        or not 1<=len(fixture['metrics'])<=16 or any(type(x) not in (float,int)
               or not math.isfinite(x) or not 0<=x<=1 for x in fixture['metrics'].values())):
        raise ValueError('SYNTHETIC_FIXTURE_REQUIRED')
    return True


def vectors(root,fixture,source=None):
    validate(root,fixture)
    if source is not None:
        if (not isinstance(source,dict) or set(source)!=
            {'schema','repository','source_class','vectors'} or
            source['schema']!='janus.essence.numeric_state/1.5' or
            source['repository']!=root['repository'] or
            source['source_class'] not in ('DECLARED_NUMERIC_STATE_UNVERIFIED',
                                         'SYNTHETIC_NUMERIC_STATE') or
            not isinstance(source['vectors'],dict) or
            set(source['vectors'])!=set(POLICY)):
            raise ValueError('UNTRUSTED_NUMERIC_STATE')
        for row in source['vectors'].values():normalized(row)
        return source['vectors']
    m=list(fixture['metrics'].values())
    result={}
    for i,role in enumerate((*ROLES,'essence_self')):
        result[role]=[math.sin((j+1)*(.17+i*.025))*(.35+.09*i)
                      +math.cos(j*.047)*.04+m[j%len(m)]*.13 for j in range(256)]
    return result


def run(root,fixture,*,allow_readonly=False,source=None):
    if allow_readonly is not True:raise PermissionError('QUANTIZER_INERT_BY_DEFAULT')
    v=vectors(root,fixture,source)
    blob=b'';backup=b'';rows=[]
    for role in (*ROLES,'essence_self'):
        x=choose(v[role],role)
        packet=x['packet'];snapshot=x['snapshot']
        rows.append({'role':role,'bits':x['bits'],'mode':x['mode'],
                     'status':x['status'],'threshold':POLICY[role],
                     'offset':len(blob),'size':len(packet),'packed_sha256':sha(packet),
                     'backup_offset':len(backup),'backup_size':len(snapshot),
                     'backup_sha256':sha(snapshot),'max_abs_error':round(x['max_abs_error'],9),
                     'alternatives':x['attempts'],'production_modified':False})
        blob+=packet;backup+=snapshot
    report={'schema':SCHEMA,'repository':root['repository'],
            'source_class':source['source_class'] if source else 'SYNTHETIC_FIXTURE',
            'source_state_sha256':seal(source) if source else None,
            'manifest_sha256':seal(root),'fixture_sha256':seal(fixture),
            'lanes':rows,'baseline_float32_bytes':len(backup),
            'quantized_binary_bytes':len(blob),
            'storage_saving_fraction':round(1-len(blob)/len(backup),6),
            'packed_bundle_sha256':sha(blob),'snapshot_bundle_sha256':sha(backup),
            'numerical_lanes_tested':7,
            'real_model_weights_modified':False,'actual_training':False,
            'production_rollback_tested':False,'production_authority':False,
            'external_blind_evaluator':False,'automatic_model_promotion':False,
            'gate':'RESEARCH_QUANTIZED_STATE_ONLY_NO_ACTIVE_MODEL_CHANGE'}
    report['receipt_sha256']=seal(report)
    verify(report,blob,backup)
    return report,blob,backup


def verify(report,blob,backup):
    if (not isinstance(report,dict) or report.get('schema')!=SCHEMA
        or report.get('receipt_sha256')!=seal({k:v for k,v in report.items() if k!='receipt_sha256'})
        or report.get('production_authority') is not False
        or report.get('automatic_model_promotion') is not False
        or report.get('real_model_weights_modified') is not False
        or report.get('gate')!='RESEARCH_QUANTIZED_STATE_ONLY_NO_ACTIVE_MODEL_CHANGE'
        or type(blob) is not bytes or type(backup) is not bytes
        or report.get('packed_bundle_sha256')!=sha(blob)
        or report.get('snapshot_bundle_sha256')!=sha(backup)
        or report.get('quantized_binary_bytes')!=len(blob)
        or report.get('baseline_float32_bytes')!=len(backup)
        or not isinstance(report.get('lanes'),list) or len(report['lanes'])!=7):
        raise ValueError('UNTRUSTED_QUANT_REPORT_OR_BUNDLES')
    offset=0;boffset=0
    if [r.get('role') for r in report['lanes']]!=list((*ROLES,'essence_self')):
        raise ValueError('UNTRUSTED_ROLE_ORDER')
    for r in report['lanes']:
        if r.get('offset')!=offset or r.get('backup_offset')!=boffset:
            raise ValueError('INVALID_OFFSETS')
        p=blob[offset:offset+r['size']];snap=backup[boffset:boffset+r['backup_size']]
        if sha(p)!=r['packed_sha256'] or sha(snap)!=r['backup_sha256'] or len(snap)%4:
            raise ValueError('INVALID_SOURCE_HASHES')
        baseline=list(struct.unpack('<'+'f'*(len(snap)//4),snap))
        decoded=decode(p)
        if len(decoded)!=len(baseline) or r['threshold']!=POLICY[r['role']]:
            raise ValueError('QUANTIZED_SCHEMA_REGRESSION')
        err=max(abs(a-b) for a,b in zip(decoded,baseline))
        if (abs(err-r['max_abs_error'])>1e-8
            or r['status']=='RESEARCH_QUANTIZED_ONLY' and
            (err>POLICY[r['role']] or len(p)>=len(snap))
            or r['status']=='HOLD_NO_SAFE_SAVING' and r['bits']!=32
            or r.get('production_modified') is not False):
            raise ValueError('QUANTIZED_ACCURACY_OR_AUTHORITY_HOLD')
        offset+=len(p);boffset+=len(snap)
    if offset!=len(blob) or boffset!=len(backup):raise ValueError('EXTRA_DATA')
    return True


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('root','fixture','state','report','binary','snapshot','verify-report','verify-binary','verify-snapshot'):
        ap.add_argument('--'+name)
    ap.add_argument('--allow-readonly',action='store_true')
    a=ap.parse_args()
    if a.verify_report:
        if not a.verify_binary or not a.verify_snapshot:raise ValueError('COMPLETE_VERIFICATION_REQUIRED')
        report=load(a.verify_report)
        verify(report,Path(a.verify_binary).read_bytes(),Path(a.verify_snapshot).read_bytes())
        print(json.dumps({'verified':True,'receipt_sha256':report['receipt_sha256']}));return
    if not a.root or not a.fixture:raise ValueError('ROOT_AND_FIXTURE_REQUIRED')
    report,blob,backup=run(load(a.root),load(a.fixture),allow_readonly=a.allow_readonly,
                           source=load(a.state) if a.state else None)
    for dest,data in ((a.report,json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n'),
                      (a.binary,blob),(a.snapshot,backup)):
        if dest:
            p=Path(dest)
            if p.exists():raise FileExistsError('NO_EVIDENCE_OVERWRITE')
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(data.encode() if isinstance(data,str) else data)
    print(json.dumps({'roles':7,'staged':sum(r['bits']!=32 for r in report['lanes']),
                      'baseline_bytes':len(backup),'packed_bytes':len(blob),
                      'saving_fraction':report['storage_saving_fraction'],
                      'gate':report['gate'],'receipt_sha256':report['receipt_sha256']},sort_keys=True))

if __name__=='__main__':main()
