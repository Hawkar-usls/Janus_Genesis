"""ESSENCE v1.5 adaptive quantization adversarial research-only test matrix."""
import copy
import hashlib
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/".janus"/"essence"))
import adaptive_quantization_v15 as q

FIXTURE=ROOT/".janus"/"essence"/"fixture.json"
MANIFEST=ROOT/".janus"/"essence"/"manifest.json"

class AdaptiveQuantizationV15(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=q.load(MANIFEST)
        cls.fixture=q.load(FIXTURE)

    def test_seven_roles_generated(self):
        doc,blob,snapshot=q.run(self.root,self.fixture,allow_readonly=True)
        self.assertTrue(q.verify(doc,blob,snapshot))
        self.assertEqual(doc["numerical_lanes_tested"],7)
        self.assertEqual(doc["storage_saving_fraction"],.626116)
        self.assertEqual(len(blob),2680)
        self.assertEqual(len(snapshot),7168)

    def test_exact_baseline_unchanged(self):
        before=copy.deepcopy(self.root)
        q.run(self.root,self.fixture,allow_readonly=True)
        self.assertEqual(before,self.root)

    def test_deterministic_receipts(self):
        self.assertEqual(q.run(self.root,self.fixture,allow_readonly=True),
                         q.run(self.root,self.fixture,allow_readonly=True))

    def test_bitpacked_formats_roundtrip(self):
        sample=[math.sin(i*.13) for i in range(257)]
        for bits in (4,8,16,32):
            with self.subTest(bits=bits):
                result=q.decode(q.encode(sample,bits))
                self.assertEqual(len(result),257)
                self.assertTrue(all(math.isfinite(x) for x in result))

    def test_odd_int4_zero_padding(self):
        packed=q.encode([.10,-.24,.31],4)
        self.assertEqual(packed[-1]>>4,0)
        self.assertEqual(len(q.decode(packed)),3)

    def test_tight_verification_chooses_fp16(self):
        a=q.choose([math.sin(i*.13) for i in range(256)],'verification')
        self.assertEqual(a['mode'],'FP16')

    def test_memory_prefers_int8(self):
        a=q.choose([math.sin(i*.13) for i in range(256)],'memory')
        self.assertEqual(a['mode'],'INT8')

    def test_low_magnitude_uses_int4(self):
        a=q.choose([.04*math.sin(i*.15) for i in range(256)],'memory')
        self.assertEqual(a['mode'],'INT4')

    def test_large_magnitude_falls_back_fp32(self):
        a=q.choose([90000*math.sin(i*.14) for i in range(256)],'verification')
        self.assertEqual(a['bits'],32)
        self.assertEqual(a['status'],'HOLD_NO_SAFE_SAVING')

    def test_tiny_packet_header_not_economical(self):
        a=q.choose([.3],'memory')
        self.assertEqual(a['bits'],32)

    def test_exact_snapshot_rollback(self):
        doc,blob,snap=q.run(self.root,self.fixture,allow_readonly=True)
        first=doc['lanes'][0]
        original=snap[first['backup_offset']:first['backup_offset']+first['backup_size']]
        self.assertEqual(hashlib.sha256(original).hexdigest(),first['backup_sha256'])
        self.assertEqual(len(original),256*4)

    def test_corrupt_binary_detected(self):
        doc,blob,snap=q.run(self.root,self.fixture,allow_readonly=True)
        broken=bytearray(blob);broken[-1]^=1
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_QUANT_REPORT_OR_BUNDLES'):
            q.verify(doc,bytes(broken),snap)

    def test_corrupt_snapshot_detected(self):
        doc,blob,snap=q.run(self.root,self.fixture,allow_readonly=True)
        broken=bytearray(snap);broken[-1]^=1
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_QUANT_REPORT_OR_BUNDLES'):
            q.verify(doc,blob,bytes(broken))

    def test_resigned_fake_production_claim_denied(self):
        doc,blob,snap=q.run(self.root,self.fixture,allow_readonly=True)
        doc['production_authority']=True
        doc['receipt_sha256']=q.seal({k:v for k,v in doc.items() if k!='receipt_sha256'})
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_QUANT_REPORT_OR_BUNDLES'):
            q.verify(doc,blob,snap)

    def test_resigned_wrong_role_threshold_denied(self):
        doc,blob,snap=q.run(self.root,self.fixture,allow_readonly=True)
        doc['lanes'][0]['threshold']=1000
        doc['receipt_sha256']=q.seal({k:v for k,v in doc.items() if k!='receipt_sha256'})
        with self.assertRaisesRegex(ValueError,'QUANTIZED_SCHEMA_REGRESSION'):
            q.verify(doc,blob,snap)

    def test_resigned_offset_forgery_denied(self):
        doc,blob,snap=q.run(self.root,self.fixture,allow_readonly=True)
        doc['lanes'][1]['offset']+=1
        doc['receipt_sha256']=q.seal({k:v for k,v in doc.items() if k!='receipt_sha256'})
        with self.assertRaisesRegex(ValueError,'INVALID_OFFSETS'):
            q.verify(doc,blob,snap)

    def test_default_inert(self):
        with self.assertRaises(PermissionError):
            q.run(self.root,self.fixture)

    def test_untrusted_repo_write_denied(self):
        root=copy.deepcopy(self.root);root['capabilities']['repo_write']=True
        with self.assertRaisesRegex(ValueError,'INERT_SIX_ROLE_ROOT_REQUIRED'):
            q.run(root,self.fixture,allow_readonly=True)

    def test_untrusted_enabled_root_denied(self):
        root=copy.deepcopy(self.root);root['enabled']=True
        with self.assertRaisesRegex(ValueError,'INERT_SIX_ROLE_ROOT_REQUIRED'):
            q.run(root,self.fixture,allow_readonly=True)

    def test_untrusted_generation_denied(self):
        root=copy.deepcopy(self.root);root['microkernels'][0]['generation']=1
        with self.assertRaisesRegex(ValueError,'INERT_SIX_ROLE_ROOT_REQUIRED'):
            q.run(root,self.fixture,allow_readonly=True)

    def test_fake_live_metrics_denied(self):
        fixture=copy.deepcopy(self.fixture);fixture['kind']='PRODUCTION'
        with self.assertRaisesRegex(ValueError,'SYNTHETIC_FIXTURE_REQUIRED'):
            q.run(self.root,fixture,allow_readonly=True)

    def test_invalid_numeric_values_denied(self):
        for x in (True, float('nan'),float('inf'),1e10):
            with self.subTest(x=x):
                with self.assertRaisesRegex(ValueError,'BAD_NUMERIC_VECTOR'):
                    q.encode([x],4)

    def test_invalid_encoding_denied(self):
        with self.assertRaisesRegex(ValueError,'BAD_BITS'):
            q.encode([.5],3)

    def test_invalid_int4_sign_code_denied(self):
        b=bytearray(q.encode([.1]*64,4))
        b[-1]=8
        with self.assertRaisesRegex(ValueError,'INVALID_INT4'):
            q.decode(bytes(b))

    def test_invalid_int8_sign_code_denied(self):
        b=bytearray(q.encode([.1]*64,8))
        b[-1]=128
        with self.assertRaisesRegex(ValueError,'INVALID_INT8'):
            q.decode(bytes(b))

    def test_nan_scale_denied(self):
        b=bytearray(q.encode([.1]*64,8))
        b[q.HEAD.size:q.HEAD.size+8]=struct.pack('<d',float('nan'))
        with self.assertRaisesRegex(ValueError,'BAD_SCALE'):
            q.decode(bytes(b))

    def test_invalid_int4_padding_denied(self):
        b=bytearray(q.encode([.1,.2,.3],4));b[-1]|=0x10
        with self.assertRaisesRegex(ValueError,'INVALID_PADDING'):
            q.decode(bytes(b))

    def test_trailing_data_denied(self):
        with self.assertRaisesRegex(ValueError,'BAD_LENGTH'):
            q.decode(q.encode([.5]*64,16)+b'X')

    def test_external_numeric_state_adapter_research_only(self):
        state={'schema':'janus.essence.numeric_state/1.5',
               'repository':self.root['repository'],
               'source_class':'DECLARED_NUMERIC_STATE_UNVERIFIED',
               'vectors':{r:[.04*math.sin(i*.1) for i in range(256)] for r in q.POLICY}}
        report,blob,snapshot=q.run(self.root,self.fixture,allow_readonly=True,source=state)
        self.assertTrue(q.verify(report,blob,snapshot))
        self.assertEqual(report['source_class'],'DECLARED_NUMERIC_STATE_UNVERIFIED')
        self.assertFalse(report['real_model_weights_modified'])

    def test_external_numeric_state_cannot_spoof_other_repo(self):
        state={'schema':'janus.essence.numeric_state/1.5',
               'repository':'Fake/Injected',
               'source_class':'DECLARED_NUMERIC_STATE_UNVERIFIED',
               'vectors':{r:[.1]*64 for r in q.POLICY}}
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_NUMERIC_STATE'):
            q.run(self.root,self.fixture,allow_readonly=True,source=state)

if __name__=='__main__':
    unittest.main()
