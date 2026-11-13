"""ESSENCE v1.1 finite counterexample search tests: real interpreter execution."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / ".janus" / "essence"
sys.path.insert(0, str(BASE))
import counterexample_gate as gate
import kernel
import turing_machine as tm


def delayed_machine():
    m = tm.unary_increment()
    m["start"] = "warm"
    m["transitions"].extend([
        {"state": "warm", "read": "1", "write": "1", "move": "S", "next": "scan"},
        {"state": "warm", "read": "_", "write": "_", "move": "S", "next": "scan"},
    ])
    return m


def defective_machine():
    m = tm.unary_increment()
    m["transitions"][1]["write"] = "0"
    return m


def loop_machine():
    m = tm.unary_increment()
    m["transitions"][1]["move"] = "S"
    m["transitions"][1]["next"] = "scan"
    return m


class CounterexampleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = kernel.load_json(BASE / "manifest.json")
        cls.fixture = kernel.load_json(BASE / "fixture.json")

    def trial(self, parent=None, child=None, **kw):
        return gate.evaluate(
            self.manifest, self.fixture,
            parent if parent is not None else delayed_machine(),
            child if child is not None else tm.unary_increment(),
            expected_repo=kw.pop("expected_repo", "Hawkar-usls/Janus_Genesis"),
            explicit_readonly=True, **kw)

    def test_measurable_bounded_gain(self):
        r = self.trial()
        self.assertEqual(r["gate"], "RESEARCH_PASS_FINITE_DOMAIN_ONLY")
        self.assertEqual(r["cases_exhausted"], 7)
        self.assertEqual(r["faster_child_cases"], 7)
        self.assertEqual(r["slower_child_cases"], 0)
        self.assertEqual(r["semantic_mismatches"], 0)
        self.assertEqual(r["parent_total_steps"] - r["child_total_steps"], 7)
        self.assertTrue(gate.verify_replay(r,self.manifest,self.fixture,delayed_machine(),tm.unary_increment()))
        self.assertFalse(r["production_authority"])

    def test_bad_child_counterexample_at_empty_tape(self):
        r = self.trial(child=defective_machine())
        self.assertEqual(r["gate"], "HOLD_SEMANTIC_COUNTEREXAMPLE")
        self.assertEqual(r["witnesses"][0]["input"], "")
        self.assertEqual(r["witnesses"][0]["parent"]["output"], "1")
        self.assertEqual(r["witnesses"][0]["child"]["output"], "0")

    def test_regressive_child_slower(self):
        r = self.trial(parent=tm.unary_increment(), child=delayed_machine())
        self.assertEqual(r["gate"], "HOLD_PERFORMANCE_REGRESSION")
        self.assertEqual(r["slower_child_cases"], 7)

    def test_identical_candidates_no_fake_gain(self):
        m = tm.unary_increment()
        r = self.trial(parent=m, child=copy.deepcopy(m))
        self.assertEqual(r["gate"], "HOLD_NO_MEASURABLE_GAIN")
        self.assertEqual(r["faster_child_cases"], 0)

    def test_nonhalting_child_holds(self):
        r = self.trial(child=loop_machine(), max_steps=9)
        self.assertEqual(r["gate"], "HOLD_UNRESOLVED_OR_RESOURCE_BOUND")
        self.assertGreater(r["unresolved_cases"], 0)

    def test_too_short_budget_holds(self):
        r = self.trial(max_steps=2)
        self.assertEqual(r["gate"], "HOLD_UNRESOLVED_OR_RESOURCE_BOUND")

    def test_bad_alphabet_yields_unresolved_not_pass(self):
        r = self.trial(alphabet=("1", "0"), max_length=4)
        self.assertEqual(r["gate"], "HOLD_UNRESOLVED_OR_RESOURCE_BOUND")
        self.assertEqual(r["cases_exhausted"], 31)

    def test_deterministic_receipt(self):
        self.assertEqual(self.trial(), self.trial())

    def test_off_by_default(self):
        with self.assertRaises(PermissionError):
            gate.evaluate(self.manifest, self.fixture, delayed_machine(), tm.unary_increment())

    def test_repository_mismatch(self):
        with self.assertRaisesRegex(ValueError,"repository identity mismatch"):
            self.trial(expected_repo="Hawkar-usls/OTHER")

    def test_untrusted_manifest(self):
        bad = copy.deepcopy(self.manifest)
        bad["capabilities"]["network"] = True
        with self.assertRaises(ValueError):
            gate.evaluate(bad,self.fixture,delayed_machine(),tm.unary_increment(),explicit_readonly=True)

    def test_duplicate_transition_rejected(self):
        bad = tm.unary_increment()
        bad["transitions"].append(bad["transitions"][0].copy())
        with self.assertRaisesRegex(ValueError,"NONDETERMINISTIC"):
            self.trial(child=bad)

    def test_nonfinite_fixture(self):
        bad=copy.deepcopy(self.fixture)
        key=next(iter(bad["metrics"]))
        bad["metrics"][key]=float("nan")
        with self.assertRaises(ValueError):
            gate.evaluate(self.manifest,bad,delayed_machine(),tm.unary_increment(),explicit_readonly=True)

    def test_case_budget_enforced(self):
        with self.assertRaisesRegex(ValueError,"TOTAL_WORK_LIMIT"):
            self.trial(alphabet=("0","1","2"),max_length=8)

    def test_invalid_bounds_rejected(self):
        for opts in ({"max_length":True},{"max_length":9},{"max_steps":1025},
                     {"max_steps":True},{"max_cells":7},{"max_cells":True}):
            with self.subTest(opts=opts),self.assertRaises(ValueError):
                self.trial(**opts)

    def test_blanks_forbidden(self):
        with self.assertRaisesRegex(ValueError,"BLANK_MISMATCH"):
            self.trial(alphabet=("_",))

    def test_seal_rejects_tampering(self):
        r=self.trial()
        r["gate"]="RESEARCH_BYPASS"
        with self.assertRaisesRegex(ValueError,"TAMPERED"):
            gate.verify(r)

    def test_replay_rejects_forged_complete_receipt(self):
        r=self.trial()
        r["faster_child_cases"]=10
        r["receipt_sha256"]=kernel.digest({k:v for k,v in r.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"REPLAY_MISMATCH"):
            gate.verify_replay(r,self.manifest,self.fixture,delayed_machine(),tm.unary_increment())

    def test_claim_elevation_rejected_even_when_resealed(self):
        r=self.trial()
        r["production_authority"]=True
        r["receipt_sha256"]=kernel.digest({k:v for k,v in r.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED"):
            gate.verify(r)

    def test_all_short_unary_inputs(self):
        for n in range(8):
            with self.subTest(n=n):
                p=tm.run(delayed_machine(),"1"*n,max_steps=32)
                c=tm.run(tm.unary_increment(),"1"*n,max_steps=32)
                self.assertEqual(p["final_tape"],"1"*(n+1))
                self.assertEqual(c["final_tape"],"1"*(n+1))
                self.assertEqual(p["steps"],c["steps"]+1)


    def test_sparse_wide_tape_is_not_accepted_as_empty_output(self):
        transitions = [{"state":"q0","read":"_","write":"_","move":"L","next":"left1"}]
        for n in range(1,7):
            transitions.append({"state":f"left{n}","read":"_","write":"_",
                                "move":"L","next":f"left{n+1}"})
        transitions.append({"state":"left7","read":"_","write":"L",
                            "move":"R","next":"right1"})
        for n in range(1,14):
            transitions.append({"state":f"right{n}","read":"_","write":"_",
                                "move":"R","next":f"right{n+1}"})
        transitions.append({"state":"right14","read":"_","write":"R",
                            "move":"S","next":"accept"})
        spec={"blank":"_","start":"q0","accept":["accept"],"reject":[],
              "transitions":transitions}
        run=tm.run(spec,"",max_cells=8,max_steps=40)
        self.assertEqual(run["status"],"TAPE_LIMIT")
        self.assertEqual(run["final_tape"],"")
        self.assertNotEqual(run["status"],"ACCEPT")


if __name__=="__main__":
    unittest.main()
