"""No-network controls for separate Genesis Qwen G3→G4 functional witness."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest
from tools import essence_v57_crossrepo_functional as m

ROOT=Path(__file__).resolve().parents[1]


def valid_ledger():
    return m.sealed({
        "schema":m.LEDGER,"status":"PASS_PROSPECTIVE_INTERNAL_FUNCTIONAL_GAIN",
        "shadow_accepted":True,"candidate_generation":4,"parent_generation":3,
        "parent_adapter_sha256":m.PARENT_SHA,
        "candidate_adapter_sha256":m.CHILD_SHA,
        "candidate_lineage_sha256":m.CHILD_LINEAGE,
        "exam_sha256":m.EXAM_SHA,"child_path":m.CHILD_PATH,
        "newly_correct":14,"previously_correct_lost":0,
        "production_promotion":False,
        "sentinel_dispatch":False,"external_validation":False})


class GenesisV57Tests(unittest.TestCase):
    def test_static_frozen_suite_precedes_model_inference(self):
        rows=m.cases(ROOT)
        self.assertEqual(len(rows),24)
        self.assertEqual(len({x["id"] for x in rows}),24)
        self.assertEqual({x["category"] for x in rows},
                         {"addition","subtraction","multiplication",
                          "modulus","gcd","shortest_path"})
        self.assertEqual(m.file_sha1(ROOT/m.SUITE),m.SUITE_SHA1)
        self.assertEqual(rows[0]["expected"],"363")
        self.assertEqual(rows[15]["expected"],"26")
        self.assertEqual(rows[23]["expected"],"71")

    def test_accepted_source_research_chain_is_not_production(self):
        x=valid_ledger()
        self.assertEqual(m.checked(x),x)
        self.assertFalse(x["production_promotion"])
        self.assertFalse(x["sentinel_dispatch"])
        self.assertEqual(x["parent_generation"],3)
        self.assertEqual(x["candidate_generation"],4)

    def test_never_escalate_model_from_untrusted_metrics(self):
        source=valid_ledger()
        for field,value in [
          ("status","HOLD_FUNCTIONAL_NOT_BETTER"),
          ("shadow_accepted",False),
          ("candidate_generation",8),
          ("child_path","../../service"),
          ("previously_correct_lost",2),
          ("newly_correct",0),
          ("production_promotion",True),
          ("sentinel_dispatch",True),
          ("external_validation",True),
          ("candidate_adapter_sha256","0"*64),
          ("exam_sha256","f"*64)]:
            altered=m.sealed({**{k:v for k,v in source.items() if k!="sha256"},
                              field:value})
            # In synthetic mode, ledger() needs a source path, so assert static
            # disallowance while storage bytes remain untrusted.
            self.assertNotEqual(altered["sha256"],source["sha256"])
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/m.SOURCE
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(__import__("json").dumps(altered))
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError,"MODEL_NOT_ACCEPTED"):
                        m.ledger(tmp)

    def test_no_unsafe_checkpoint_path_or_dynamic_model_choice(self):
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_ADAPTER_PATH"):
            m.adapter(".", "../../etc",m.CHILD_SHA,m.CHILD_LINEAGE,4)
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_ADAPTER_PATH"):
            m.adapter(".", "models/production",m.CHILD_SHA,m.CHILD_LINEAGE,4)
        self.assertNotEqual(m.CHILD_SHA,m.PARENT_SHA)

    def test_receipt_seal_and_immutable_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"ack.json"
            data=m.sealed({"schema":m.SCHEMA,"production_promotion":False})
            m.write_once(p,data)
            self.assertEqual(m.checked(m.read(p)),data)
            with self.assertRaisesRegex(ValueError,"RECEIPT_REPLAY"):
                m.write_once(p,data)
            data["production_promotion"]=True
            with self.assertRaisesRegex(ValueError,"INVALID_SEAL"):
                m.checked(data)

    def test_duplicate_and_nan_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bad.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
                m.read(p)
            p.write_text('{"a":Infinity}')
            with self.assertRaisesRegex(ValueError,"NONFINITE_JSON"):
                m.read(p)

    def test_no_local_tool_execution_or_privileged_model_training(self):
        txt=(ROOT/"tools/essence_v57_crossrepo_functional.py").read_text()
        self.assertIn("is_trainable=False",txt)
        self.assertIn("trust_remote_code=False",txt)
        self.assertIn('"model_code_execution":False',txt)
        self.assertIn('"receiver_training":False',txt)
        self.assertIn('"production_promotion":False',txt)
        self.assertNotIn("exec(answer)",txt)


if __name__=="__main__":
    unittest.main()
