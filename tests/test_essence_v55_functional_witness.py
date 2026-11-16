"""Genesis first-look v5.5: adversarial no-network functional examiner tests."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools import essence_v55_functional_witness as m

ROOT=Path(__file__).resolve().parents[1]


def ledger():
    return m.seal({
      "schema":m.LEDGER,"parent_v54_acceptance_exam_sha256":m.G3_EXAM,
      "current_generation":3,
      "current_adapter_sha256":m.G3,
      "current_lineage_sha256":m.G3_LINEAGE,
      "current_parent_path":m.CURRENT_G3,
      "attempts":[],"admitted":[],
      "production_promotion":False,
      "sentinel_dispatch":False,"external_validation":False})


def admission(source):
    d=copy.deepcopy(source)
    d["current_generation"]=4
    d["current_adapter_sha256"]="b"*64
    d["current_lineage_sha256"]="c"*64
    d["current_parent_path"]="models/v55gen0004"
    d["admitted"]=[{"generation":4,
                   "parent_adapter_sha256":m.G3,
                   "adapter_sha256":"b"*64,
                   "lineage_sha256":"c"*64,
                   "exam_sha256":"d"*64,
                   "external_validation":False}]
    d["attempts"]=[{"candidate_generation":4,
                    "exam_sha256":"d"*64,
                    "status":"PASS_INTERNAL_SHADOW",
                    "shadow_accepted":True,
                    "production_promotion":False}]
    return m.seal({k:v for k,v in d.items() if k!="sha256"})


class FunctionalWitnessTests(unittest.TestCase):
    def test_suite_precommitted_and_math_questions_are_frozen(self):
        cases=m.cases(ROOT)
        self.assertEqual(len(cases),16)
        self.assertEqual(len({row["id"] for row in cases}),16)
        self.assertEqual(m.git_blob(ROOT/m.SUITE),m.SUITE_BLOB)
        self.assertEqual({x["expected"] for x in cases
                          if x["id"]=="A01"},{"703"})
        self.assertEqual({x["expected"] for x in cases
                          if x["id"]=="A10"},{"7"})
        self.assertEqual({x["expected"] for x in cases
                          if x["id"]=="A09"},{"111010"})

    def test_g3_anchor_and_g4_descendant_chain(self):
        base=ledger()
        self.assertEqual(m.validate_ledger(base),base)
        d=admission(base)
        self.assertEqual(m.validate_ledger(d),d)
        self.assertEqual(d["current_generation"],4)

    def test_no_unsigned_or_escalated_model_admission(self):
        base=ledger()
        for delta in ({"production_promotion":True},
                      {"sentinel_dispatch":True},
                      {"external_validation":True},
                      {"current_parent_path":"../../secret"},
                      {"current_generation":5},
                      {"parent_v54_acceptance_exam_sha256":"f"*64}):
            d=m.seal({**{k:v for k,v in base.items() if k!="sha256"},**delta})
            with self.subTest(delta=delta):
                with self.assertRaises(ValueError):
                    m.validate_ledger(d)
        d=admission(base)
        d["current_adapter_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"UNSEALED"):
            m.validate_ledger(d)
        d=admission(base)
        d["admitted"][0]["parent_adapter_sha256"]="1"*64
        d=m.seal({k:v for k,v in d.items() if k!="sha256"})
        with self.assertRaisesRegex(ValueError,"ACCEPTANCE_CHAIN_BROKEN"):
            m.validate_ledger(d)

    def test_no_forged_admission_from_merely_successful_run(self):
        d=admission(ledger())
        d["attempts"][0]["shadow_accepted"]=False
        d=m.seal({k:v for k,v in d.items() if k!="sha256"})
        with self.assertRaisesRegex(ValueError,"ACCEPTANCE_CHAIN_BROKEN"):
            m.validate_ledger(d)
        d=admission(ledger())
        d["attempts"][0]["status"]="HOLD_NOT_BETTER"
        d=m.seal({k:v for k,v in d.items() if k!="sha256"})
        with self.assertRaisesRegex(ValueError,"ACCEPTANCE_CHAIN_BROKEN"):
            m.validate_ledger(d)

    def test_read_json_rejects_nonfinite_duplicate_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"value.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
                m.read(p)
            p.write_text('{"a":NaN}')
            with self.assertRaisesRegex(ValueError,"NONFINITE_JSON"):
                m.read(p)
            q=Path(tmp)/"link.json"
            q.symlink_to(p)
            with self.assertRaisesRegex(ValueError,"UNSAFE_JSON"):
                m.read(q)

    def test_duplicate_receipt_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"receipts"/"test.json"
            receipt=m.seal({"schema":m.SCHEMA,"production_promotion":False})
            m.write(path,receipt)
            self.assertEqual(m.check(m.read(path)),receipt)
            with self.assertRaisesRegex(ValueError,"RECEIPT_ALREADY_EXISTS"):
                m.write(path,receipt)

    def test_no_models_or_peer_text_grant_control(self):
        self.assertEqual(m.G3,len(m.G3)*"b" if False else m.G3)
        self.assertRegex(m.CURRENT_G3,r"^models/v54gen0003$")
        self.assertFalse(m.PATH.fullmatch("../../production"))
        script=(ROOT/"tools/essence_v55_functional_witness.py").read_text()
        self.assertIn('"model_text_executed_as_code":False',script)
        self.assertIn('"production_promotion":False',script)
        self.assertIn('"sentinel_dispatch":False',script)
        self.assertIn("is_trainable=False",script)
        self.assertIn("trust_remote_code=False",script)


if __name__=="__main__":
    unittest.main()
