"""Genesis v5.4 cross-repo model consumer: bounded negative controls."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools import essence_v54_neural_witness as m


def first():
    return m.seal({
        "schema":m.LEDGER,
        "current_generation":2,
        "current_adapter_sha256":m.G2_SHA,
        "current_lineage_sha256":m.G2_LINEAGE,
        "current_parent_path":"models/gen0002",
        "attempts":[],"admitted":[],
        "production_promotion":False,
        "sentinel_dispatch":False,
        "external_validation":False})


class PeerWitnessTests(unittest.TestCase):
    def test_g2_ledger_and_no_production_privileges(self):
        ledger=first()
        self.assertEqual(m.validate_ledger(ledger),ledger)
        self.assertEqual(ledger["current_generation"],2)
        self.assertFalse(ledger["production_promotion"])
        self.assertFalse(ledger["sentinel_dispatch"])

    def test_untrusted_ledger_refused(self):
        variants=[
            {"current_parent_path":"../../secrets"},
            {"current_adapter_sha256":"deadbeef"},
            {"current_generation":3},
            {"production_promotion":True},
            {"sentinel_dispatch":True},
            {"external_validation":True},
            {"admitted":[{"generation":3,"adapter_sha256":"1"*64,
                          "parent_adapter_sha256":"fake",
                          "lineage_sha256":"2"*64,"external_validation":False}]}
        ]
        for change in variants:
            bad=dict(first(),**change)
            bad=m.seal({k:v for k,v in bad.items() if k!="sha256"})
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    m.validate_ledger(bad)
        tampered=first()
        tampered["current_generation"]=7
        with self.assertRaisesRegex(ValueError,"BROKEN_SEAL"):
            m.validate_ledger(tampered)

    def test_accepted_parent_chain_can_be_validated(self):
        obj=first()
        child="c"*64
        lineage="d"*64
        obj.update({
            "current_generation":3,
            "current_parent_path":"models/v54gen0003",
            "current_adapter_sha256":child,
            "current_lineage_sha256":lineage,
            "admitted":[{"generation":3,"parent_adapter_sha256":m.G2_SHA,
                         "adapter_sha256":child,"lineage_sha256":lineage,
                         "external_validation":False}],
            "attempts":[{"status":"PASS_INTERNAL_SHADOW","shadow_accepted":True,
                         "production_promotion":False}]})
        obj=m.seal({k:v for k,v in obj.items() if k!="sha256"})
        self.assertEqual(m.validate_ledger(obj)["current_generation"],3)
        bad=copy.deepcopy(obj)
        bad["attempts"][0]["shadow_accepted"]=False
        bad=m.seal({k:v for k,v in bad.items() if k!="sha256"})
        with self.assertRaisesRegex(ValueError,"CURRENT_PARENT_NOT_ACCEPTED"):
            m.validate_ledger(bad)

    def test_no_fake_first_receipt_before_producer_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"producer").mkdir()
            (root/"receiver").mkdir()
            result=m.plan(root/"producer",root/"receiver")
            self.assertEqual(result["action"],"WAIT_FOR_FIRST_V54_LINEAGE")
            self.assertFalse(result["production_promotion"])

    def test_receipt_write_is_immutable_and_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/"test"/"receipt.json"
            val=m.seal({"schema":m.SCHEMA,"generation":2})
            m.write_once(dest,val)
            self.assertEqual(m.check(m.read(dest)),val)
            with self.assertRaisesRegex(ValueError,"REPLAY_RECEIPT"):
                m.write_once(dest,val)

    def test_reject_nonfinite_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"bad.json"
            f.write_text('{"v":NaN}')
            with self.assertRaisesRegex(ValueError,"NONFINITE_JSON"):
                m.read(f)
            f.write_text('{"v":1,"v":2}')
            with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
                m.read(f)


if __name__=="__main__":
    unittest.main()
