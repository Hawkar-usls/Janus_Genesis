"""Regression and negative tests for read-only ESSENCE engineering organs."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORGANS = ROOT / ".janus" / "essence"
sys.path.insert(0, str(ORGANS))

import engineering_math as em
import engineering_matrix as matrix
import kernel
import turing_machine as tm


class CalculatorTests(unittest.TestCase):
    def test_exact_decimal(self):
        self.assertEqual(em.calculate("0.1+0.2")["value"], "0.3")

    def test_mechanical_work(self):
        r = em.calculate("5*kN*2*m", "kJ")
        self.assertEqual((r["value"], r["si_value"]), ("10", "10000"))
        self.assertTrue(r["exact_constants_and_arithmetic"])

    def test_pressure(self):
        self.assertEqual(em.calculate("15*kN/(0.01*m**2)", "MPa")["value"], "1.5")

    def test_electricity(self):
        self.assertEqual(em.calculate("12*V/(2*A)", "Ohm")["value"], "6")

    def test_sqrt_dimension(self):
        self.assertEqual(em.calculate("sqrt(9*m**2)", "m")["value"], "3")

    def test_trigonometry_discloses_approximation(self):
        r = em.calculate("sin(30*deg)")
        self.assertAlmostEqual(float(r["value"]), 0.5, places=14)
        self.assertEqual(r["precision"], "approx_binary64_functions")

    def test_dimensional_mismatch(self):
        with self.assertRaisesRegex(ValueError, "DIMENSION_MISMATCH"):
            em.calculate("2*m+3*s")

    def test_requested_output_unit_mismatch(self):
        with self.assertRaisesRegex(ValueError, "OUTPUT_DIMENSION_MISMATCH"):
            em.calculate("10*N", "J")

    def test_div_zero(self):
        with self.assertRaisesRegex(ValueError, "DIVISION_BY_ZERO"):
            em.calculate("1/(2-2)")

    def test_negative_sqrt_and_fractional_dimension(self):
        for expression in ("sqrt(-1)", "sqrt(3*m)"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                em.calculate(expression)

    def test_code_injection_rejected(self):
        for expression in ("__import__('os').system('whoami')", "1;import os", "(x for x in [1])"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                em.calculate(expression)

    def test_unbounded_power(self):
        with self.assertRaisesRegex(ValueError, "POWER_LIMIT"):
            em.calculate("2**300000")

    def test_function_dimensions(self):
        with self.assertRaisesRegex(ValueError, "DIMENSION_MISMATCH"):
            em.calculate("sin(1*m)")

    def test_corpus_against_integer_arithmetic(self):
        for a in range(-12, 13):
            for b in range(1, 9):
                out = em.calculate(f"({a}*{b})+(({a})**2)-{b}")
                self.assertEqual(int(out["value"]), a*b+a*a-b)


class TuringTests(unittest.TestCase):
    def test_unary_machine(self):
        r = tm.run(tm.unary_increment(), "111")
        self.assertEqual((r["status"], r["steps"], r["final_tape"]), ("ACCEPT", 4, "1111"))

    def test_empty_input(self):
        self.assertEqual(tm.run(tm.unary_increment(), "")["final_tape"], "1")

    def test_deterministic_trace(self):
        self.assertEqual(tm.run(tm.unary_increment(), "11"), tm.run(tm.unary_increment(), "11"))

    def test_step_budget(self):
        out = tm.run(tm.unary_increment(), "111", max_steps=2)
        self.assertEqual(out["status"], "LIMIT")
        self.assertEqual(out["steps"], 2)

    def test_duplicate_transitions_rejected(self):
        m = tm.unary_increment()
        m["transitions"].append(m["transitions"][0].copy())
        with self.assertRaisesRegex(ValueError, "NONDETERMINISTIC"):
            tm.run(m, "")

    def test_stuck(self):
        m = tm.unary_increment()
        self.assertEqual(tm.run(m, "0")["status"], "STUCK")

    def test_reject_branch(self):
        m = {
            "blank": "_", "start": "even", "accept": ["accept"],
            "reject": ["reject"], "transitions": [
                {"state": state, "read": "1", "write": "1", "move": "R", "next": other}
                for state, other in (("even", "odd"), ("odd", "even"))
            ] + [
                {"state": state, "read": "_", "write": "_", "move": "S", "next": dest}
                for state, dest in (("even", "accept"), ("odd", "reject"))
            ],
        }
        for n in range(15):
            self.assertEqual(tm.run(m, "1"*n)["status"], "ACCEPT" if n % 2 == 0 else "REJECT")

    def test_loop_always_terminates_at_budget(self):
        m = {
            "blank": "_", "start": "repeat", "accept": ["accept"], "reject": [],
            "transitions": [{"state": "repeat", "read": "_", "write": "_", "move": "S", "next": "repeat"}],
        }
        self.assertEqual(tm.run(m, "", max_steps=17)["steps"], 17)
        self.assertEqual(tm.run(m, "", max_steps=17)["status"], "LIMIT")

    def test_no_halt_to_running(self):
        m = tm.unary_increment()
        m["transitions"].append({"state": "accept", "read": "_", "write": "_", "move": "S", "next": "scan"})
        with self.assertRaisesRegex(ValueError, "HALT_HAS_OUTGOING"):
            tm.run(m, "")


class IntegratedMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = kernel.load_json(ORGANS / "manifest.json")
        cls.fixture = kernel.load_json(ORGANS / "fixture.json")

    def test_integration_preserves_six_cells(self):
        r = matrix.evaluate(self.manifest, self.fixture, expression="2*kN*3*m",
                            output_unit="kJ", tape="111", explicit_readonly=True,
                            expected_repo="Hawkar-usls/Janus_Genesis")
        self.assertEqual(r["legacy_microkernels"], 6)
        self.assertEqual(r["calculator"]["value"], "6")
        self.assertEqual(r["turing"]["final_tape"], "1111")
        self.assertEqual(r["gene_admission"], "PROPOSAL_ONLY")
        self.assertTrue(matrix.verify(r))

    def test_off_by_default(self):
        with self.assertRaises(PermissionError):
            matrix.evaluate(self.manifest, self.fixture, expression="1+1")

    def test_tamper_evidence_rejected(self):
        r = matrix.evaluate(self.manifest, self.fixture, expression="1+1", explicit_readonly=True)
        r["calculator"]["value"] = "999"
        with self.assertRaisesRegex(ValueError, "TAMPERED"):
            matrix.verify(r)

    def test_parent_restriction_survives(self):
        r = matrix.evaluate(self.manifest, self.fixture, expression="1+1", explicit_readonly=True)
        self.assertFalse(r["network_access"])
        self.assertFalse(r["model_weights_modified"])
        self.assertFalse(r["self_modification"])
        self.assertFalse(r["production_promotion"])


if __name__ == "__main__":
    unittest.main()
